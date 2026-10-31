"""Combat and Vấn Đạo (spec 8.1), all decided by the server.

Every monster wears a Mặc Thuẫn. While it is up, hits do 1 damage and can never kill it.
Engaging a monster (hitting it, or an aggressive one coming at you) brings a question;
while answering you have Hộ Thể (no damage, no moving, no attacking). Right: the shield
breaks and a "Ngộ Đạo" strike lands (x2, more when fast). Wrong or too late: Mặc Kích, a
hit of 10/15/20% of your max HP (less with Kháng Mực), and the next question in 3 s.

The tick (sync, no database) moves monsters, lands telegraphed attacks, checks question
deadlines and regenerates. Everything needing the database (creating questions, grading
timeouts, rewards, death penalty) runs as background tasks and comes back into memory.
"""
from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

from .. import balance
from .. import db as dbm

if TYPE_CHECKING:
    from .ai import Monster
    from .world import World
    from .zone import ChannelZone, Player

log = logging.getLogger("khu_vuon.combat")
FACING_NAMES = ("down", "up", "left", "right")


def cfg() -> dict:
    return balance.load("combat")


def _world() -> "World":
    from .world import world
    return world


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


# ------------------------------------------------------------------ damage
def weapon_profile(p: "Player") -> dict:
    c = cfg()
    w = p.weapon
    return c["weapon_kinds"].get(w, c["unarmed"]) if w else c["unarmed"]


def base_damage(p: "Player", m: "Monster") -> float:
    """A normal hit: attack x weapon multiplier, minus half the monster's defence."""
    atk = p.stats.get("atk", 10) * weapon_profile(p).get("mult", 1.0)
    return max(1.0, atk - m.info.get("def", 0) * cfg()["defense_factor"])


def roll_crit(p: "Player", rng: random.Random) -> bool:
    chance = p.stats.get("crit", 0) + weapon_profile(p).get("crit_bonus", 0)
    return rng.random() * 100 < chance


def hurt_monster(ch: "ChannelZone", m: "Monster", p: "Player | None", dmg: float, crit: bool, now: float,
                 bee: str | None = None) -> float:
    if not m.alive:
        return 0.0
    regrow = False
    if m.shield:  # spec 8.1: a shielded monster cannot be killed, a hit only scratches it
        dmg = float(cfg()["shielded_damage"])
        m.hp = max(1.0, m.hp - dmg)
    elif m.regen and m.hp - dmg <= m.max_hp * m.regen[0] / 100:
        # elites: the Mặc Thuẫn comes back at its threshold, even a huge hit stops there
        m.hp = min(m.hp, m.max_hp * m.regen[0] / 100)
        regrow = True
    else:
        m.hp -= dmg
    ev = {"k": "hit", "id": m.eid, "v": int(round(dmg)), "c": int(crit), "by": p.eid if p else None,
          "x": m.x, "y": m.y, "sh": int(m.shield)}
    if bee:
        ev["b"] = bee   # stung by a guard bee of this species
    ch.event(**ev)
    if p is not None:
        p.last_combat = now
    if m.hp <= 0:
        kill(ch, m, now)
        return dmg
    if regrow:
        m.regen.pop(0)
        m.shield = True
        m.group_hits = set()
        ch.event(k="shield", id=m.eid, on=1, x=m.x, y=m.y)
        for uid in m.engaged:
            pl = ch.players.get(uid)
            if pl is not None and pl.question is None and not pl.dead:
                pl.next_q = (m.eid, now + 0.3)
    return dmg


def hurt_player(ch: "ChannelZone", p: "Player", dmg: float, now: float, kind: str = "hit", by: str | None = None,
                ignore_protect: bool = False) -> float:
    if p.dead or (p.protected(now) and not ignore_protect):
        return 0.0
    if now < p.guard_until:
        dmg *= 1 - p.guard_reduce
    dmg = max(1.0, dmg)
    p.hp -= dmg
    p.last_combat = now
    ch.event(k=kind, id=p.eid, v=int(round(dmg)), by=by, x=p.x, y=p.y)
    if p.hp <= 0:
        die(ch, p, now)
    return dmg


def mac_kich(p: "Player", m: "Monster") -> float:
    c = cfg()
    pct = c["mac_kich_pct"].get(m.info.get("rank", "normal"), 10)
    from ..systems import buffs
    res = min(p.stats.get("ink_res", 0) + buffs.ink_res(_world().buffs_left(p)), c["ink_res_cap"])
    dmg = p.max_hp * pct / 100 * (1 - res / 100)
    pet = getattr(p, "pet", None)
    if pet:   # Rắn (stage 8): Mặc Kích is lighter
        from ..systems import catalog
        sk = catalog.pets()["species"].get(pet, {}).get("skill", {})
        if sk.get("type") == "mac_kich":
            dmg *= 1 - float(sk["value"])
    return dmg


# ------------------------------------------------------------------ engagement
def engage(ch: "ChannelZone", m: "Monster", p: "Player", now: float) -> None:
    if not m.alive or p.dead:
        return
    if p.user_id not in m.engaged:
        m.engaged.add(p.user_id)
        if m.mode == "wander":
            m.mode = "chase"
            m.target = None
            m.idle = 0
    p.last_combat = now
    if m.shield and p.question is None and not p.q_pending and p.next_q is None:
        request_question(ch, p, m, now)


def disengage(ch: "ChannelZone", m: "Monster", uid: int, now: float) -> None:
    m.engaged.discard(uid)
    p = ch.players.get(uid)
    if p is None:
        return
    if p.question and p.question["mid"] == m.eid:
        end_question(p, "gone")
    if p.next_q and p.next_q[0] == m.eid:
        p.next_q = None


def end_question(p: "Player", reason: str) -> None:
    q = p.question
    p.question = None
    p.protect_until = 0.0
    if q and p.session is not None:
        p.session.send({"t": "q_end", "sid": q["sid"], "reason": reason})


def request_question(ch: "ChannelZone", p: "Player", m: "Monster", now: float) -> None:
    if p.question is not None or p.q_pending or now < p.no_words_until:
        return
    if p.user_id in m.group_hits:   # a bí cảnh boss: this player already did their part of the shield
        return
    p.q_pending = True
    p.next_q = None
    _world().spawn(_create_question(ch, p, m.eid, m.kind))


async def _create_question(ch: "ChannelZone", p: "Player", mid: str, kind: str) -> None:
    from ..learning import question_bank as qb
    from ..learning import quiz, selection
    from ..learning.wordbank import bank
    from ..models import User
    from ..systems import codex, cultivation
    from .world import zone_defs
    w = _world()
    rng = random.Random()
    try:
        async with dbm.SessionLocal() as db:
            user = await db.get(User, p.user_id)
            tier = cultivation.tier_of(p.realm)
            zone_tier = getattr(ch, "question_tier", None) or zone_defs().get(ch.zone_id, {}).get("tier", tier)
            try:
                word_id = await selection.pick_word(db, p.user_id, zone_tier, rng)
            except selection.NoWordAvailable:
                p.q_pending = False
                p.no_words_until = w.mono() + 10
                if p.session:
                    p.session.send({"t": "error", "code": "nothing_learned",
                                    "message_vi": "Con chưa học chữ nào nên chưa phá được Mặc Thuẫn. "
                                                  "Về vườn học ít nhất một chữ đã!"})
                return
            word = bank().get(word_id)
            types = balance.quiz()["types"]
            allowed = [q for q in ch.monster(mid).info.get("qtypes", []) if types[q]["min_tier"] <= tier] \
                if ch.monster(mid) else []
            question = qb.generate_any(allowed or ["Q1", "Q2"], word,
                                       quiz.gen_context(rng, max_tier=max(tier, word.tier)))
            out = await quiz.create_session(db, user, "combat", question, ref=f"{ch.key}|{mid}")
            first = await codex.meet_monster(db, p.user_id, kind)
            await db.commit()
    except Exception:
        log.exception("could not create a combat question")
        p.q_pending = False
        return
    p.q_pending = False
    now = w.mono()
    m = ch.monster(mid)
    if (m is None or not m.alive or not m.shield or p.dead or p.channel is not ch or p.session is None
            or p.user_id not in m.engaged or p.question is not None):
        return  # the fight moved on while the question was being written; it simply expires
    limit = float(question.time_limit)
    deadline = now + limit + balance.quiz()["network_grace"]
    p.question = {"sid": out["session_id"], "mid": mid, "deadline": deadline, "asked": now, "limit": limit,
                  "timeout_sent": False}
    p.protect_until = deadline
    p.inputs.clear()
    p.queued_ms = 0
    p.session.send({"t": "q", "mid": mid, "q": out, "first_meet": first})


def on_answer(p: "Player", sid: str, correct: bool, answer_ms: int | None) -> dict:
    """Called (in memory) by the 'combat' quiz handler after the answer was graded."""
    w = _world()
    q = p.question
    if q is None or q["sid"] != sid or p.channel is None:
        return {"stale": True}
    ch = p.channel
    now = w.mono()
    p.question = None
    p.protect_until = 0.0
    m = ch.monster(q["mid"])
    if m is None or not m.alive:
        return {"gone": True}
    c = cfg()
    if correct:
        if m.shield and m.info.get("group_shield"):
            # spec 14.2: the boss's big shield needs N right answers from N different players
            m.group_hits.add(p.user_id)
            need = ch.group_need(m) if hasattr(ch, "group_need") else 1
            ch.event(k="gshield", id=m.eid, n=len(m.group_hits), need=need, by=p.eid, x=m.x, y=m.y)
            p.qi = min(p.max_qi, p.qi + c["correct_qi_gain"])
            if len(m.group_hits) < need:
                return {"correct": True, "shield_broken": False, "shield_progress": [len(m.group_hits), need],
                        "damage": 0, "crit": False, "monster_hp": max(0, m.hp_pct()), "killed": False}
        broke = m.shield
        if m.shield:
            break_shield(ch, m, p, now)
        fast = answer_ms is not None and answer_ms <= c["fast_answer_fraction"] * q["limit"] * 1000
        dmg = base_damage(p, m) * c["ngo_dao_mult"] * (c["fast_answer_crit_mult"] if fast else 1.0)
        p.qi = min(p.max_qi, p.qi + c["correct_qi_gain"])
        dealt = hurt_monster(ch, m, p, dmg, fast, now)
        return {"correct": True, "shield_broken": broke, "damage": int(round(dealt)), "crit": fast,
                "monster_hp": max(0, m.hp_pct()), "killed": not m.alive}
    dmg = hurt_player(ch, p, mac_kich(p, m), now, kind="mk", by=m.eid, ignore_protect=True)
    if m.alive and m.shield and not p.dead:
        p.next_q = (m.eid, now + c["next_question_delay"])
    return {"correct": False, "mac_kich": int(round(dmg)), "hp": max(0, int(round(p.hp))), "dead": p.dead}


def break_shield(ch: "ChannelZone", m: "Monster", p: "Player | None", now: float) -> None:
    m.shield = False
    m.group_hits = set()
    ch.event(k="shield", id=m.eid, on=0, x=m.x, y=m.y, by=p.eid if p else None)
    for uid in list(m.engaged):  # whoever is right first breaks it for everyone (spec 8.1)
        other = ch.players.get(uid)
        if other is not None and other is not p and other.question and other.question["mid"] == m.eid:
            end_question(other, "broken")


async def combat_handler(db, user, s, correct: bool, now) -> dict:
    from ..learning import quiz
    out = await quiz.practice_handler(db, user, s, correct, now)
    w = _world()
    p = w.players.get(user.id)
    if p is not None:
        out["combat"] = on_answer(p, s.id, correct, s.answer_ms)
        if "mastery" in out:
            w.word_mastery_changed(user.id, s.word_id, out["mastery"])
    return out


async def _grade_timeout(uid: int, sid: str) -> None:
    from ..learning import quiz
    from ..models import User
    try:
        async with dbm.SessionLocal() as db:
            user = await db.get(User, uid)
            await quiz.answer(db, user, sid, None)   # past expires_at: graded as timed out
            await db.commit()
    except quiz.QuizError:
        pass  # answered just in time
    except Exception:
        log.exception("timeout grading failed")


# ------------------------------------------------------------------ actions
def attack(p: "Player", eid: str, now: float, rng: random.Random) -> str | None:
    """Normal attack (left click). Returns an error code or None."""
    ch = p.channel
    if ch is None or p.dead:
        return "cannot"
    if p.protected(now):
        return "answering"
    if now < p.next_attack_at:
        return "cooldown"
    m = ch.monster(eid)
    if m is None or not m.alive:
        return "no_target"
    prof = weapon_profile(p)
    if dist(p.x, p.y - 6, m.x, m.y - 6) > prof["range"] + 10:
        return "too_far"
    p.next_attack_at = now + prof["cooldown"]
    dx, dy = m.x - p.x, m.y - p.y
    p.facing = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")
    crit = roll_crit(p, rng)
    ch.event(k="atk", by=p.eid, id=m.eid, x=p.x, y=p.y, wp=p.weapon or "")
    engage(ch, m, p, now)
    hurt_monster(ch, m, p, base_damage(p, m) * (cfg_mult("crit_mult") if crit else 1.0), crit, now)
    return None


def cfg_mult(key: str) -> float:
    return float(cfg()[key])


def cast(p: "Player", sid: str, eid: str | None, now: float, rng: random.Random) -> str | None:
    from ..systems import catalog
    ch = p.channel
    if ch is None or p.dead:
        return "cannot"
    if p.protected(now):
        return "answering"
    known = p.skills.get(sid)
    if not known or known.get("level", 0) < 1:
        return "not_learned"
    sk = catalog.skills()
    s = sk["skills"][sid]
    if now < p.skill_ready.get(sid, 0):
        return "cooldown"
    if p.qi < s["qi"]:
        return "no_qi"
    mult = sk["level_mult"][min(4, known["level"]) - 1]
    if s["effect"] == "damage":
        m = ch.monster(eid) if eid else None
        if m is None or not m.alive:
            return "no_target"
        if dist(p.x, p.y, m.x, m.y) > s["range"]:
            return "too_far"
        ch.event(k="skill", by=p.eid, s=sid, x=p.x, y=p.y - 12, tx=m.x, ty=m.y - 8)
        engage(ch, m, p, now)
        hurt_monster(ch, m, p, base_damage(p, m) * s["power"] * mult, False, now)
    elif s["effect"] == "slow":
        ch.event(k="skill", by=p.eid, s=sid, x=p.x, y=p.y, r=s["radius"])
        for m in ch.monsters:
            if m.alive and dist(p.x, p.y, m.x, m.y) <= s["radius"]:
                m.slow_until, m.slow_mult = now + s["duration"], s["slow"]
                engage(ch, m, p, now)
                hurt_monster(ch, m, p, base_damage(p, m) * s["power"] * mult, False, now)
    elif s["effect"] == "heal":
        amount = p.max_hp * s["heal_pct"] / 100 * mult
        p.hp = min(p.max_hp, p.hp + amount)
        ch.event(k="skill", by=p.eid, s=sid, x=p.x, y=p.y - 12)
        ch.event(k="heal", id=p.eid, v=int(round(amount)), x=p.x, y=p.y)
    elif s["effect"] == "guard":
        p.guard_until, p.guard_reduce = now + s["duration"] * mult, s["reduce"]
        ch.event(k="skill", by=p.eid, s=sid, x=p.x, y=p.y - 12, d=s["duration"] * mult)
    p.qi -= s["qi"]
    p.skill_ready[sid] = now + s["cooldown"]
    return None


# ------------------------------------------------------------------ death & rewards
def kill(ch: "ChannelZone", m: "Monster", now: float) -> None:
    m.mode = "dead"
    m.hp = 0
    m.moving = False
    m.tele = None
    m.respawn_at = now + m.info.get("respawn_seconds", 30)
    ch.event(k="die", id=m.eid, x=m.x, y=m.y)
    for uid in list(m.engaged):
        p = ch.players.get(uid)
        if p is not None:
            if p.question and p.question["mid"] == m.eid:
                end_question(p, "killed")
            if p.next_q and p.next_q[0] == m.eid:
                p.next_q = None
            if not p.dead:
                _world().spawn(_reward(p.user_id, m.kind, _loot_bonus(p, m)))
    _party_share(ch, m)
    for uid, ids in m.bee_assist.items():  # guard bees that helped grow a little
        if ids:
            _world().spawn(_bee_xp(uid, sorted(ids)))
    m.engaged = set()
    m.bee_assist = {}
    m.burn = None


def _party_share(ch: "ChannelZone", m: "Monster") -> None:
    """Spec 15.3: party members fighting nearby get part of the Tu Vi even if they did not
    touch this monster."""
    from ..systems import catalog
    rc = balance.load("realm")
    xp = int(catalog.monsters()[m.kind].get("xp", 0) * rc["party_xp_share"])
    if xp <= 0:
        return
    parties = _world().parties
    paid = set(m.engaged)
    for uid in list(m.engaged):
        for mate in parties.mates(uid):
            q = ch.players.get(mate)
            if mate in paid or q is None or q.dead or dist(q.x, q.y, m.x, m.y) > rc["party_share_radius"]:
                continue
            paid.add(mate)
            _world().spawn(_share_xp(mate, xp))


async def _share_xp(uid: int, xp: int) -> None:
    from ..systems import cultivation
    try:
        async with dbm.SessionLocal() as db:
            info = await cultivation.add_xp(db, uid, xp, "party")
            await db.commit()
    except Exception:
        log.exception("party xp failed")
        return
    _world().notify(uid, {"t": "party_xp", "xp": info})


def _loot_bonus(p: "Player", m: "Monster") -> dict:
    """Ong Ngọc Bích & co (skill 'loot'): more stones and drops from monsters they stung;
    the worn pet may add to it."""
    stung = m.bee_assist.get(p.user_id, set())
    best = {"stones_pct": 0.0, "drop_mult": 1.0}
    for b in p.bees:
        sk = b.skill or {}
        if b.id in stung and sk.get("type") == "loot":
            best["stones_pct"] = max(best["stones_pct"], float(sk.get("stones_pct", 0)))
            best["drop_mult"] = max(best["drop_mult"], float(sk.get("drop_mult", 1.0)))
    pet = getattr(p, "pet", None)
    if pet:   # Chó: more drops, Ngựa: more stones (stage 8)
        from ..systems import catalog
        sk = catalog.pets()["species"].get(pet, {}).get("skill", {})
        if sk.get("type") == "drop":
            best["drop_mult"] *= 1 + float(sk["value"])
        elif sk.get("type") == "kill_stones":
            best["stones_pct"] += float(sk["value"]) * 100
    return best


async def _bee_xp(uid: int, bee_ids: list[int]) -> None:
    from ..systems import bees
    try:
        await bees.combat_xp(uid, bee_ids)
    except Exception:
        log.exception("bee xp failed")


async def _reward(uid: int, kind: str, loot: dict | None = None) -> None:
    from ..systems import catalog, codex, cultivation, inventory, items, quests
    info = catalog.monsters()[kind]
    rng = random.Random()
    loot = loot or {"stones_pct": 0.0, "drop_mult": 1.0}
    out = {"t": "loot", "monster": info["name_vi"], "items": [], "equipment": []}
    try:
        async with dbm.SessionLocal() as db:
            lo, hi = info.get("stones", [0, 0])
            stones = int(round(rng.randint(lo, hi) * (1 + loot["stones_pct"] / 100)))
            if stones:
                out["spirit_stones"] = await inventory.change_currency(db, uid, "spirit_stones", stones, "kill", kind)
                out["stones"] = stones
            for d in info.get("drops", []):
                if rng.random() >= min(1.0, d["chance"] * loot["drop_mult"]):
                    continue
                if "item" in d:
                    qty = rng.randint(*d.get("qty", [1, 1]))
                    out["items"] += await items.grant_items(db, uid, [{"item": d["item"], "qty": qty}], "drop", kind)
                else:
                    item_id = rng.choice(d["equipment"])
                    rar = items.roll_rarity(rng, d.get("min_rarity"))
                    out["equipment"].append(await items.grant_equipment(db, uid, item_id, rar, "drop", kind))
            out["kills"] = await codex.monster_killed(db, uid, kind)
            out["quests"] = await quests.on_event(db, uid, "kill", kind)
            out["xp"] = await cultivation.add_xp(db, uid, info.get("xp", 0), "kill")
            await db.commit()
    except Exception:
        log.exception("reward failed")
        return
    _world().notify(uid, out)


def die(ch: "ChannelZone", p: "Player", now: float) -> None:
    if ch.instance:   # a bí cảnh: no Tu Vi lost, the player becomes a ghost (spec 14.2)
        ch.on_down(p, now)
        return
    p.dead = True
    p.hp = 0
    p.respawn_at = now + cfg()["death_overlay_seconds"]
    p.inputs.clear()
    p.queued_ms = 0
    ch.event(k="die", id=p.eid, x=p.x, y=p.y)
    for m in ch.monsters:
        if p.user_id in m.engaged:
            m.engaged.discard(p.user_id)
    if p.question:
        end_question(p, "dead")
    p.next_q = None
    if p.session is not None:
        p.session.send({"t": "dead", "respawn_in": cfg()["death_overlay_seconds"]})
    _world().spawn(_death_penalty(p.user_id))


async def _death_penalty(uid: int) -> None:
    from ..systems import cultivation
    try:
        async with dbm.SessionLocal() as db:
            lost = await cultivation.lose_xp_pct(db, uid, cultivation.cfg()["death_xp_loss_pct"])
            await db.commit()
        _world().notify(uid, {"t": "xp_lost", "lost": lost})
    except Exception:
        log.exception("death penalty failed")


# ------------------------------------------------------------------ the tick
def _move_monster(m: "Monster", tx: float, ty: float, speed: float, dt: float, col) -> None:
    dx, dy = tx - m.x, ty - m.y
    d = math.hypot(dx, dy)
    if d < 0.5:
        m.moving = False
        return
    stepd = min(d, speed * dt)
    nx, ny = m.x + dx / d * stepd, m.y + dy / d * stepd
    if not col.blocked(nx, ny):
        m.x, m.y = nx, ny
    elif not col.blocked(nx, m.y):
        m.x = nx
    elif not col.blocked(m.x, ny):
        m.y = ny
    m.moving = True
    m.facing = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")


def _respawn_monster(ch: "ChannelZone", m: "Monster") -> None:
    a = m.area
    for _ in range(20):
        x, y = ch.rng.uniform(a.x + 8, a.x + a.w - 8), ch.rng.uniform(a.y + 8, a.y + a.h - 8)
        if not ch.map.collider.blocked(x, y):
            m.x, m.y = x, y
            break
    m.reset()
    m.idle = 1.0


def _monster_tick(ch: "ChannelZone", m: "Monster", dt: float, now: float) -> None:
    c = cfg()
    info = m.info
    col = ch.map.collider
    if m.mode == "dead":
        if now >= m.respawn_at:
            _respawn_monster(ch, m)
        return
    if now < m.stun_until:  # stunned by a guard bee: no moving, no attacking
        m.moving = False
        m.tele = None
        return
    slow = m.slow_mult if now < m.slow_until else 1.0
    if m.mode == "return":
        hx, hy = m.home
        _move_monster(m, hx, hy, info["speed"] * c["return_speed_mult"], dt, col)
        if dist(m.x, m.y, hx, hy) < 6 or not m.moving:
            hp_keep = m.max_hp
            m.reset()
            m.hp = hp_keep
        return
    # who is it fighting?
    for uid in list(m.engaged):
        p = ch.players.get(uid)
        if p is None or p.dead:
            m.engaged.discard(uid)
    if not m.engaged and info.get("aggressive"):
        r = info.get("aggro_radius", 0)
        near = [p for p in ch.players.values() if not p.dead and dist(p.x, p.y, m.x, m.y) <= r]
        if near:
            engage(ch, m, min(near, key=lambda p: dist(p.x, p.y, m.x, m.y)), now)
    if not m.engaged:
        if m.mode == "chase":
            m.mode = "return"
        else:
            m.update(dt, col, ch.rng)
        return
    hx, hy = m.home
    if dist(m.x, m.y, hx, hy) > c["leash_radius"]:  # dragged too far from home: give up and heal
        for uid in list(m.engaged):
            disengage(ch, m, uid, now)
        m.mode, m.tele = "return", None
        return
    m.mode = "chase"
    targets = [ch.players[u] for u in m.engaged if u in ch.players]
    tgt = min(targets, key=lambda p: dist(p.x, p.y, m.x, m.y))
    if m.tele is not None:
        tx, ty, r, land = m.tele
        if now >= land:
            m.tele = None
            m.atk_ready = now + c["monster_attack_cooldown"]
            dmg = max(1.0, info.get("atk", 5) - tgt.stats.get("def", 0) * c["defense_factor"])
            for p in list(ch.players.values()):
                if not p.dead and dist(p.x, p.y, tx, ty) <= r + 5:
                    hurt_player(ch, p, dmg, now, by=m.eid)
            from . import guard
            guard.hit_bees(ch, m, now)
        m.moving = False
        return
    d = dist(tgt.x, tgt.y, m.x, m.y)
    reach = info.get("attack_radius", 20)
    if d <= reach + 6:
        m.moving = False
        if now >= m.atk_ready and not tgt.protected(now):
            land = now + c["telegraph_seconds"]
            m.tele = (tgt.x, tgt.y, reach, land)
            ch.event(k="tele", id=m.eid, x=round(tgt.x, 1), y=round(tgt.y, 1), r=reach, d=c["telegraph_seconds"])
        return
    _move_monster(m, tgt.x, tgt.y, info["speed"] * c["chase_speed_mult"] * slow, dt, col)


def tick(ch: "ChannelZone", dt: float, now: float) -> None:
    c = cfg()
    w = _world()
    for m in ch.monsters:
        _monster_tick(ch, m, dt, now)
    for p in list(ch.players.values()):
        if p.dead:
            if now >= p.respawn_at:
                w.respawn(p)
            continue
        q = p.question
        if q is not None and now >= q["deadline"] + 0.25 and not q["timeout_sent"]:
            q["timeout_sent"] = True  # nobody answered in time: grade it as a timeout (= wrong)
            w.spawn(_grade_timeout(p.user_id, q["sid"]))
        if p.next_q is not None and now >= p.next_q[1] and p.question is None and not p.q_pending:
            mid = p.next_q[0]
            p.next_q = None
            m = ch.monster(mid)
            if m is not None and m.alive and m.shield and p.user_id in m.engaged:
                request_question(ch, p, m, now)
        if now - p.last_combat > c["out_of_combat_seconds"]:
            mult = c["safe_zone_regen_mult"] if ch.safe else 1.0
            p.hp = min(p.max_hp, p.hp + p.max_hp * c["hp_regen_pct_per_second"] / 100 * dt * mult)
            p.qi = min(p.max_qi, p.qi + c["qi_regen_per_second"] * dt * mult)


def _register() -> None:
    from ..learning import quiz
    quiz.register_handler("combat", combat_handler)


_register()
