"""Tu Vi, realms, stats, đả tọa and Thiên Kiếp (spec 7.3).

Tu Vi comes mostly from right answers (any context), plus kills, harvests, quests and
meditation. Inside a realm the next stage comes by itself when Tu Vi is full; entering a
new realm (Luyện Khí 9 -> Trúc Cơ...) needs full Tu Vi, the realm's pill and a 20-question
Thiên Kiếp. There is no way to gain Tu Vi without answering (meditation asks a question).
"""
from __future__ import annotations

import datetime as dt
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..config import settings
from ..learning import question_bank as qb
from ..learning import quiz, selection
from ..learning.wordbank import bank
from ..models import Character, EquipmentInstance, InventoryItem, QuizSession, TribulationRun, User
from . import catalog, inventory

STAGE_LABELS = ["sơ kỳ", "trung kỳ", "hậu kỳ"]
REALM_TIER = {"pham_nhan": 1, "luyen_khi": 1, "truc_co": 2, "kim_dan": 3, "nguyen_anh": 4}


class CultivationError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("cultivation")


# ------------------------------------------------------------------ realm ladder
def order() -> list[str]:
    return [r["id"] for r in catalog.realms()]


def realm_name(realm: str) -> str:
    return next((r["name_vi"] for r in catalog.realms() if r["id"] == realm), realm)


def first_stage(realm: str) -> int:
    return 0 if realm == "pham_nhan" else 1


def last_stage(realm: str) -> int:
    return 0 if realm == "pham_nhan" else len(cfg()["xp_to_next"][realm])


def stage_label(realm: str, stage: int) -> str:
    if realm == "pham_nhan":
        return realm_name(realm)
    if realm == "luyen_khi":
        return f"{realm_name(realm)} tầng {stage}"
    return f"{realm_name(realm)} {STAGE_LABELS[min(stage, 3) - 1]}"


def xp_needed(realm: str, stage: int) -> int | None:
    xs = cfg()["xp_to_next"].get(realm)
    if not xs:
        return None
    i = 0 if realm == "pham_nhan" else stage - 1
    return xs[i] if 0 <= i < len(xs) else None


def next_step(realm: str, stage: int) -> tuple[str, int, str | None] | None:
    """(realm, stage, pill needed or None) of the step after this one."""
    if stage < last_stage(realm):
        return realm, stage + 1, None
    o = order()
    i = o.index(realm)
    if i + 1 >= len(o):
        return None
    nxt = o[i + 1]
    return nxt, first_stage(nxt), cfg()["tribulation_to"].get(nxt)


def level_index(realm: str, stage: int) -> int:
    n = 0
    for r in order():
        if r == realm:
            return n + stage
        n += last_stage(r)
    return n


def tier_of(realm: str) -> int:
    return REALM_TIER.get(realm, 1)


# ------------------------------------------------------------------ stats
def instance_stats(e: EquipmentInstance) -> dict:
    eq = catalog.equipment()
    item = eq["items"].get(e.item_id, {})
    mult = eq["rarities"][e.rarity]["mult"] * (1 + eq["enhance"]["stat_bonus_per_level"] * e.enhance_level)
    out = {k: int(round(v * mult)) for k, v in item.get("stats", {}).items()}
    for ins in e.inscriptions or []:      # Khắc Văn (stage 8): each carved character adds its stat
        out[ins["stat"]] = out.get(ins["stat"], 0) + int(ins["value"])
    return out


def stats_for(realm: str, stage: int, equipped: list[EquipmentInstance], extra: dict | None = None) -> dict:
    """extra: the worn Linh Thú's bonus (stage 8)."""
    s = cfg()["stats"]
    lvl = level_index(realm, stage)
    out = {k: v + s["per_stage"].get(k, 0) * lvl for k, v in s["base"].items()}
    for k, v in s["realm_bonus"].get(realm, {}).items():
        out[k] = out.get(k, 0) + v
    for k, v in (extra or {}).items():
        out[k] = out.get(k, 0) + v
    weapon = None
    eq = catalog.equipment()
    worn_sets: dict[str, int] = {}
    for e in equipped:
        for k, v in instance_stats(e).items():
            out[k] = out.get(k, 0) + v
        if e.equipped_slot == "weapon":
            weapon = eq["items"].get(e.item_id, {}).get("kind")
        set_id = eq["items"].get(e.item_id, {}).get("set")
        if set_id:
            worn_sets[set_id] = worn_sets.get(set_id, 0) + 1
    for set_id, n in worn_sets.items():   # đồ bộ from secret realms (stage 9)
        for need, bonus in eq.get("sets", {}).get(set_id, {}).get("bonus", {}).items():
            if n >= int(need):
                for k, v in bonus.items():
                    out[k] = out.get(k, 0) + v
    out["weapon"] = weapon
    out["ink_res"] = min(out.get("ink_res", 0), balance.load("combat")["ink_res_cap"])
    return out


async def equipped(db: AsyncSession, user_id: int) -> list[EquipmentInstance]:
    return list((await db.execute(select(EquipmentInstance).where(
        EquipmentInstance.user_id == user_id, EquipmentInstance.equipped_slot.is_not(None)))).scalars().all())


async def current_stats(db: AsyncSession, ch: Character) -> dict:
    from . import pets
    return stats_for(ch.realm, ch.realm_stage, await equipped(db, ch.user_id), await pets.worn_stats(db, ch.user_id))


async def push_to_world(db: AsyncSession, ch: Character) -> None:
    """Tell the live world about new stats/realm (if the character is standing in it)."""
    from ..realtime.world import world
    world.update_character(ch.user_id, ch.realm, ch.realm_stage, await current_stats(db, ch))


# ------------------------------------------------------------------ Tu Vi
async def add_xp(db: AsyncSession, user_id: int, amount: int, reason: str = "") -> dict | None:
    ch = await db.get(Character, user_id)
    if ch is None or amount <= 0:
        return None
    before = (ch.realm, ch.realm_stage)
    ch.cultivation_xp += int(amount)
    bottleneck = False
    for _ in range(50):
        need = xp_needed(ch.realm, ch.realm_stage)
        nxt = next_step(ch.realm, ch.realm_stage)
        if need is None or nxt is None or ch.cultivation_xp < need:
            break
        if nxt[2]:  # a new realm: wait at full Tu Vi for the pill and Thiên Kiếp
            ch.cultivation_xp = need
            bottleneck = True
            break
        ch.cultivation_xp -= need
        ch.realm, ch.realm_stage = nxt[0], nxt[1]
    changed = (ch.realm, ch.realm_stage) != before
    if changed:
        st = await current_stats(db, ch)
        ch.max_hp = st["max_hp"]
        ch.hp = st["max_hp"]  # reaching a new stage restores the body
        ch.qi = st["max_qi"]
        await push_to_world(db, ch)
        if ch.realm != before[0]:
            from . import quests
            await quests.on_event(db, user_id, "realm", ch.realm)
    return {"gained": int(amount), "xp": ch.cultivation_xp, "need": xp_needed(ch.realm, ch.realm_stage),
            "realm": ch.realm, "stage": ch.realm_stage, "label": stage_label(ch.realm, ch.realm_stage),
            "stage_up": changed, "bottleneck": bottleneck, "reason": reason}


async def lose_xp_pct(db: AsyncSession, user_id: int, pct: float) -> int:
    """Lose pct% of the current stage's requirement; never drops a stage (spec 7.1)."""
    ch = await db.get(Character, user_id)
    if ch is None:
        return 0
    need = xp_needed(ch.realm, ch.realm_stage) or 0
    loss = min(ch.cultivation_xp, int(round(need * pct / 100)))
    ch.cultivation_xp -= loss
    return loss


def view(ch: Character, stats: dict, skills: list[dict], pills: dict[str, int], now: dt.datetime) -> dict:
    need = xp_needed(ch.realm, ch.realm_stage)
    nxt = next_step(ch.realm, ch.realm_stage)
    pill = nxt[2] if nxt else None
    full = need is not None and ch.cultivation_xp >= need
    retry = ch.tribulation_retry_at if ch.tribulation_retry_at and ch.tribulation_retry_at > now else None
    return {"realm": ch.realm, "realm_name": realm_name(ch.realm), "stage": ch.realm_stage,
            "label": stage_label(ch.realm, ch.realm_stage), "xp": ch.cultivation_xp, "need": need,
            "next_realm": nxt[0] if nxt and pill else None, "pill": pill,
            "pill_name": catalog.item_name(pill) if pill else None, "has_pill": pills.get(pill, 0) > 0 if pill else False,
            "can_tribulation": bool(pill and full and pills.get(pill, 0) > 0 and retry is None),
            "tribulation_ready_in": int((retry - now).total_seconds()) + 1 if retry else 0,
            "stats": stats, "skills": skills}


# ------------------------------------------------------------------ đả tọa
def _scaled(seconds: float) -> dt.timedelta:
    return dt.timedelta(seconds=seconds / settings.time_scale)


async def meditate(db: AsyncSession, user: User, rng: random.Random | None = None) -> dict:
    """One review question at the meditation mat, at most every 2 minutes (spec 7.3)."""
    from ..realtime.world import world
    rng = rng or random.Random()
    ch = await db.get(Character, user.id)
    if ch is None:
        raise CultivationError(404, "no_character", "Bạn chưa tạo nhân vật.")
    if world.in_world(user.id) or ch.zone_id != "abode":
        raise CultivationError(400, "not_home", "Chỉ đả tọa được ở bàn đả tọa trong động phủ.")
    now = clock.now()
    flags = dict(user.flags or {})
    last = flags.get("meditate_at")
    if last:
        ready = dt.datetime.fromisoformat(last) + _scaled(cfg()["meditate_interval_seconds"])
        if now < ready:
            wait = int((ready - now).total_seconds()) + 1
            raise CultivationError(400, "meditate_wait", f"Tâm còn xao động, {wait} giây nữa mới có câu tiếp.")
    tier = tier_of(ch.realm)
    try:
        word_id = await selection.pick_word(db, user.id, tier, rng)
    except selection.NoWordAvailable:
        raise CultivationError(400, "nothing_learned", "Hãy học ít nhất một chữ trong vườn trước đã.")
    w = bank().get(word_id)
    allowed = [q for q in cfg()["meditate_qtypes"] if balance.quiz()["types"][q]["min_tier"] <= tier]
    question = qb.generate_any(allowed, w, quiz.gen_context(rng, max_tier=max(tier, w.tier)))
    flags["meditate_at"] = now.isoformat()
    user.flags = flags
    return await quiz.create_session(db, user, "meditate", question)


async def meditate_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool, now: dt.datetime) -> dict:
    out = await quiz.practice_handler(db, user, s, correct, now)
    if correct:
        from . import quests
        await quests.on_event(db, user.id, "meditate", "")
    nxt = dt.datetime.fromisoformat((user.flags or {}).get("meditate_at", now.isoformat())) + \
        _scaled(cfg()["meditate_interval_seconds"])
    out["next_in"] = max(0, int((nxt - now).total_seconds()) + 1)
    return out


quiz.register_handler("meditate", meditate_handler)


# ------------------------------------------------------------------ Thiên Kiếp
async def _pill_count(db: AsyncSession, user_id: int, item_id: str) -> int:
    rows = (await db.execute(select(InventoryItem.quantity).where(
        InventoryItem.user_id == user_id, InventoryItem.item_id == item_id))).scalars().all()
    return sum(rows)


def _tribulation_question(run: TribulationRun, rng: random.Random) -> qb.Question:
    t = cfg()["tribulation"]
    w = bank().get(run.words[run.index])
    tier = tier_of(run.from_realm)
    allowed = [q for q, c in balance.quiz()["types"].items() if c["min_tier"] <= tier]
    q = qb.generate_any(allowed, w, quiz.gen_context(rng, max_tier=tier))
    q.time_limit = float(t["time_limit"])
    return q


async def _ask(db: AsyncSession, user: User, run: TribulationRun, rng: random.Random) -> dict:
    q = _tribulation_question(run, rng)
    out = await quiz.create_session(db, user, "tribulation", q, ref=str(run.id))
    out.update({"run_id": run.id, "number": run.index + 1, "total": len(run.words), "correct_so_far": run.correct})
    return out


async def tribulation_start(db: AsyncSession, user: User, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    ch = await db.get(Character, user.id)
    if ch is None:
        raise CultivationError(404, "no_character", "Bạn chưa tạo nhân vật.")
    now = clock.now()
    run = (await db.execute(select(TribulationRun).where(
        TribulationRun.user_id == user.id, TribulationRun.finished_at.is_(None)))).scalars().first()
    if run is not None:  # resume: the open question, or count an expired one as wrong and go on
        s = (await db.execute(select(QuizSession).where(
            QuizSession.user_id == user.id, QuizSession.context == "tribulation", QuizSession.ref == str(run.id),
            QuizSession.answered_at.is_(None)).order_by(QuizSession.created_at.desc()))).scalars().first()
        if s is not None and s.expires_at > now:
            out = quiz.public_session(s)
            out.update({"run_id": run.id, "number": run.index + 1, "total": len(run.words),
                        "correct_so_far": run.correct})
            return {"question": out, "resumed": True}
        if s is not None:
            res = await quiz.answer(db, user, s.id, None)
            if res.get("next"):
                return {"question": res["next"], "resumed": True}
            return {"result": res.get("tribulation"), "resumed": True}
        return {"question": await _ask(db, user, run, rng), "resumed": True}
    need = xp_needed(ch.realm, ch.realm_stage)
    nxt = next_step(ch.realm, ch.realm_stage)
    if nxt is None or not nxt[2]:
        raise CultivationError(400, "no_tribulation", "Chưa đến lúc đột phá cảnh giới mới.")
    if need is None or ch.cultivation_xp < need:
        raise CultivationError(400, "xp_not_full", "Tu Vi chưa đầy.")
    if ch.tribulation_retry_at and ch.tribulation_retry_at > now:
        wait = int((ch.tribulation_retry_at - now).total_seconds()) + 1
        raise CultivationError(400, "tribulation_wait", f"Kinh mạch còn tổn thương, {wait} giây nữa mới thi lại được.")
    if await _pill_count(db, user.id, nxt[2]) <= 0:
        raise CultivationError(400, "no_pill", f"Cần {catalog.item_name(nxt[2])} để đột phá.")
    t = cfg()["tribulation"]
    tier = tier_of(ch.realm)
    pool = [w.id for w in bank().words.values() if w.tier == tier and not w.hidden]
    words = rng.sample(pool, min(t["questions"], len(pool)))
    run = TribulationRun(user_id=user.id, from_realm=ch.realm, to_realm=nxt[0], words=words, index=0, correct=0,
                         started_at=now)
    db.add(run)
    await db.flush()
    return {"question": await _ask(db, user, run, rng), "resumed": False}


async def tribulation_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool, now: dt.datetime) -> dict:
    out = await quiz.practice_handler(db, user, s, correct, now)
    run = await db.get(TribulationRun, int(s.ref)) if s.ref else None
    if run is None or run.finished_at is not None or run.user_id != user.id:
        return out
    run.index += 1
    run.correct += int(correct)
    out["number"], out["total"], out["correct_so_far"] = run.index, len(run.words), run.correct
    if run.index < len(run.words):
        out["next"] = await _ask(db, user, run, random.Random())
        return out
    t = cfg()["tribulation"]
    ch = await db.get(Character, user.id)
    passed = run.correct * 100 >= t["pass_pct"] * len(run.words)
    run.finished_at, run.result = now, "passed" if passed else "failed"
    result = {"passed": passed, "correct": run.correct, "total": len(run.words), "pass_pct": t["pass_pct"]}
    if passed:
        pill = cfg()["tribulation_to"][run.to_realm]
        await inventory.consume_item(db, user.id, pill, 1, "tribulation", str(run.id))
        ch.realm, ch.realm_stage, ch.cultivation_xp = run.to_realm, first_stage(run.to_realm), 0
        ch.tribulation_retry_at = None
        st = await current_stats(db, ch)
        ch.max_hp, ch.hp, ch.qi = st["max_hp"], st["max_hp"], st["max_qi"]
        jade = t["reward_jade"]
        await inventory.change_currency(db, user.id, "immortal_jade", jade, "tribulation", str(run.id))
        result.update({"realm": ch.realm, "label": stage_label(ch.realm, ch.realm_stage), "jade": jade})
        await push_to_world(db, ch)
        from . import quests
        await quests.on_event(db, user.id, "realm", ch.realm)
    else:
        lost = await lose_xp_pct(db, user.id, t["fail_xp_loss_pct"])
        ch.tribulation_retry_at = now + _scaled(t["retry_wait_seconds"])
        result.update({"xp_lost": lost, "retry_in": int(_scaled(t["retry_wait_seconds"]).total_seconds())})
    out["tribulation"] = result
    return out


quiz.register_handler("tribulation", tribulation_handler)
