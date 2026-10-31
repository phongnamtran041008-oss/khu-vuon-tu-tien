"""Stage 9: tổ đội, matchmaking, bí cảnh instances, the five co-op puzzles, the boss with
many phases, loot per player (never twice) and coming back after a lost connection.

Like test_combat, the world runs on a fake clock and its tick is called by hand; players
talk to it with the real protocol messages and answer through the real REST API."""
import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import balance, clock
from app import db as dbm
from app.learning.wordbank import bank
from app.models import Character, EquipmentInstance, InventoryItem, RealmClaim, RealmMember
from app.realtime import maps, realm
from app.realtime import world as wmod
from app.realtime.world import World
from app.systems import cultivation, secret_realm
from tests.helpers import answer_key, correct_answer
from tests.realm_bot import Bot, Team
from tests.test_combat import FakeMono, fighter, last, learn, run, settle

TIER1 = [w.hanzi for w in bank().words.values() if w.tier == 1]
ALL_ROOMS = ["compose", "sentence", "tone", "mirror", "maze", "boss"]


@pytest_asyncio.fixture
async def gw(app, monkeypatch):
    w = World(mono=FakeMono())
    monkeypatch.setattr(wmod, "world", w)
    monkeypatch.setitem(balance.load("realm"), "always_open", True)
    yield w
    await settle(w)


def gate() -> tuple[float, float]:
    return maps.load("truc_lam_thon").interacts["realm"]


async def hero(client, w, username, display, realm_id="truc_co", words=None):
    h, uid, s = await fighter(client, w, username, display, learned=False)
    await learn(uid, words or TIER1)
    async with dbm.SessionLocal() as db:
        ch = await db.get(Character, uid)
        ch.realm, ch.realm_stage = realm_id, cultivation.first_stage(realm_id)
        await db.commit()
    s.realm = realm_id
    assert w.join(s, "truc_lam_thon", "abode")
    gx, gy = gate()
    w._place(s, "truc_lam_thon", gx, gy + 14, "up")
    return h, uid, s


def msgs(s, t, event=None):
    return [m for m in s.sent if m.get("t") == t and (event is None or m.get("event") == event)]


async def make_party(w, leader, *others):
    for o in others:
        await w.handle(leader, {"t": "party", "op": "invite", "name": o.name})
        assert last(o, "party")["event"] == "invite"
        await w.handle(o, {"t": "party", "op": "accept", "uid": leader.user_id})
    return w.parties.party_of(leader.user_id)


async def tick(w, seconds: float = 0.05) -> None:
    run(w, seconds)
    await settle(w)


def answerer(client):
    async def answer(bot, q):
        key = await answer_key(q["session_id"])
        r = await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                    "answer": correct_answer(q["qtype"], key)}, headers=bot.h)
        assert r.status_code == 200, r.text
        return r.json()
    return answer


async def play(w, bots, seconds: float, until) -> bool:
    for _ in range(int(seconds / 0.05)):
        for b in bots:
            await b.think()
        await tick(w)
        if until():
            return True
    return False


# ------------------------------------------------------------------ tổ đội
async def test_party_invite_accept_chat_leave(client, gw):
    _, a, sa = await hero(client, gw, "doi_a", "Đội A")
    _, b, sb = await hero(client, gw, "doi_b", "Đội B")
    _, c, sc = await hero(client, gw, "doi_c", "Đội C")
    await gw.handle(sb, {"t": "party", "op": "accept", "uid": a})
    assert last(sb, "error")["code"] == "no_invite"               # nobody asked
    party = await make_party(gw, sa, sb)
    assert party.leader == a and party.members == [a, b]
    st = last(sa, "party")
    assert st["event"] == "state" and [m["name"] for m in st["party"]["members"]] == ["Đội A", "Đội B"]
    assert st["party"]["members"][1]["hp"] == 100                 # party members see each other's health
    await gw.handle(sb, {"t": "party", "op": "invite", "name": "Đội C"})
    assert last(sb, "error")["code"] == "not_leader"
    # the Tổ Đội chat channel reaches the party only
    sc.sent.clear()
    await gw.handle(sa, {"t": "chat", "ch": "party", "text": "vào bí cảnh không?"})
    assert last(sb, "chat")["ch"] == "party" and not msgs(sc, "chat")
    await gw.handle(sc, {"t": "chat", "ch": "party", "text": "?"})
    assert last(sc, "error")["code"] == "no_party"
    # health changes reach the others within a second
    gw.players[b].hp -= 30
    await tick(gw, 1.1)
    assert last(sa, "party")["party"]["members"][1]["hp"] < 100
    # the leader leaves: a party of one is disbanded
    await gw.handle(sa, {"t": "party", "op": "leave"})
    assert last(sa, "party")["event"] == "left" and last(sb, "party")["reason"] == "disbanded"
    assert gw.parties.party_of(b) is None and not gw.parties.parties


async def test_party_full_and_kick(client, gw, monkeypatch):
    monkeypatch.setitem(balance.load("realm"), "party_max", 2)
    _, a, sa = await hero(client, gw, "kick_a", "Kick A")
    _, b, sb = await hero(client, gw, "kick_b", "Kick B")
    _, c, sc = await hero(client, gw, "kick_c", "Kick C")
    await make_party(gw, sa, sb)
    await gw.handle(sa, {"t": "party", "op": "invite", "name": "Kick C"})
    assert last(sa, "error")["code"] == "party_full"
    await gw.handle(sa, {"t": "party", "op": "kick", "uid": b})
    assert last(sb, "party")["reason"] == "kicked" and gw.parties.party_of(a) is None


async def test_party_members_share_xp(client, gw):
    from app.realtime import combat
    _, a, sa = await hero(client, gw, "chia_a", "Chia A")
    _, b, sb = await hero(client, gw, "chia_b", "Chia B")
    await make_party(gw, sa, sb)
    ch = gw._pick_channel("rung_muc_loang")
    m = next(m for m in ch.monsters if m.kind == "ink_slime")
    gw._place(sa, "rung_muc_loang", m.x, m.y, "down")
    gw._place(sb, "rung_muc_loang", m.x + 30, m.y, "down")
    m.engaged = {a}
    combat.kill(ch, m, gw.mono())
    await settle(gw)
    got = last(sb, "party_xp")
    assert got and got["xp"]["gained"] == int(m.info["xp"] * balance.load("realm")["party_xp_share"])


# ------------------------------------------------------------------ the whole run with three bots
async def test_three_bots_clear_a_realm_together(client, gw):
    """Spec 20, stage 9: three players clear one bí cảnh; each gets their own loot, once."""
    heroes = [await hero(client, gw, f"bot_{i}", f"Đạo Hữu {i}") for i in range(3)]
    (h0, u0, s0), (h1, u1, s1), (h2, u2, s2) = heroes
    for _, uid, _s in heroes:   # sturdy bots, so the test is about the rules, not the luck
        p = gw.players[uid]
        p.max_hp = p.hp = 600
        p.stats["atk"] = 45
    party = await make_party(gw, s0, s1, s2)
    assert len(party.members) == 3
    gw.realms.room_order = ALL_ROOMS              # all five puzzles, then the boss
    await gw.handle(s1, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    assert last(s1, "error")["code"] == "not_leader"
    await gw.handle(s0, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    await settle(gw)
    inst = gw.realms.instance_of(gw.players[u0])
    assert inst is not None and inst.rooms == ALL_ROOMS
    assert all(gw.realms.instance_of(gw.players[u]) is inst for u in (u1, u2))
    assert last(s0, "zone")["zone"] == "bi_canh"
    team = Team()
    bots = [Bot(gw, client, h, uid, s, team, answerer(client)) for h, uid, s in heroes]
    # every player sees only their own piece of a puzzle
    room = last(s0, "realm") if last(s0, "realm")["event"] == "room" else msgs(s0, "realm", "room")[-1]
    assert room["kind"] == "compose" and "piece" in room["mine"]
    done = await play(gw, bots, 900, lambda: inst.phase == "ended")
    assert done, f"stuck in room {inst.room_i} ({inst.kind}): {inst.puzzle.public(gw.mono()) if inst.puzzle else None}"
    assert inst.result == "won", inst.result
    end = msgs(s0, "realm", "end")[-1]
    assert end["puzzles"] == 5 and end["fragments"] == inst._fragments()
    # the boss's big shield took three different players each phase (spec 14.2)
    gs = [e for m in msgs(s0, "snap") for e in m.get("fx", []) if e.get("k") == "gshield"]
    # after each move to a new room the others are sent again in full (the client forgets them on `zone`)
    zones = [i for i, m in enumerate(s0.sent) if m.get("t") == "zone" and m.get("zone") == "bi_canh"]
    assert len(zones) == 6
    for i in zones[1:]:
        snap = next(m for m in s0.sent[i:] if m.get("t") == "snap")
        assert {f"p{u1}", f"p{u2}"} <= {e["id"] for e in snap.get("add", [])}
    phases = [gs[i:i + 3] for i in range(0, len(gs), 3)]
    assert len(phases) == 4 and all([e["n"] for e in ph] == [1, 2, 3] and len({e["by"] for e in ph}) == 3
                                    and all(e["need"] == 3 for e in ph) for ph in phases)
    for b in bots:
        b.read()
        assert b.ended and b.ended["result"] == "won"
    await tick(gw, 0.2)
    # loot: every player has their own claims, one per room and one chest
    async with dbm.SessionLocal() as db:
        for uid in (u0, u1, u2):
            rows = (await db.execute(select(RealmClaim).where(RealmClaim.run_id == inst.run_id,
                                                              RealmClaim.user_id == uid))).scalars().all()
            assert sorted(r.stage for r in rows) == sorted([f"room{i}" for i in range(6)] + ["chest"])
            chest = next(r for r in rows if r.stage == "chest")
            frag = next(i for i in chest.loot["items"] if i["item"] == "manh_bao_vat")
            assert frag["qty"] == inst._fragments() >= 4    # Mảnh Bảo Vật: the same for the whole team
            m = await db.get(RealmMember, (inst.run_id, uid))
            assert m.result == "won" and m.left_at is not None
    # asking again pays nothing (spec 14.3: no loot twice)
    for uid in (u0, u1, u2):
        assert await secret_realm.claim_chest(inst.run_id, uid, inst.realm_id, 4, False) is None
        assert await secret_realm.claim_room(inst.run_id, uid, 0, "compose") is None
    # each bot was told about its own loot only
    for b in bots:
        b.read()
        assert {lt["stage"] for lt in b.loot} == {f"room{i}" for i in range(6)} | {"chest"}
    # after the result screen everyone is back at the gate in Trúc Lâm Thôn
    await tick(gw, balance.load("realm")["exit_seconds"] + 0.5)
    assert all(gw.players[u].channel.zone_id == "truc_lam_thon" for u in (u0, u1, u2))
    assert not gw.realms.instances


# ------------------------------------------------------------------ entering
async def enter(gw, leader, *others, realm_id="mac_anh_dong", rooms=None):
    await make_party(gw, leader, *others)
    gw.realms.room_order = rooms
    await gw.handle(leader, {"t": "realm", "op": "enter", "realm": realm_id})
    await settle(gw)
    return gw.realms.instance_of(gw.players[leader.user_id])


async def test_entry_rules_realm_party_and_daily_limit(client, gw, monkeypatch):
    _, a, sa = await hero(client, gw, "luat_a", "Luật A")
    _, b, sb = await hero(client, gw, "luat_b", "Luật B", realm_id="luyen_khi")
    await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    assert last(sa, "error")["code"] == "need_party"                 # 2-5 players
    await make_party(gw, sa, sb)
    await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    assert last(sa, "error")["code"] == "cannot_enter" and "Luật B" in last(sa, "error")["message_vi"]
    await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "khe_nut_muc"})
    assert last(sa, "error")["code"] == "no_realm"                   # rifts are entered at a rift
    # the scheduled realm keeps its hours (spec 14.1)
    monkeypatch.setitem(balance.load("realm"), "always_open", False)
    await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    assert last(sa, "error")["code"] == "realm_closed"
    monkeypatch.setitem(balance.load("realm"), "always_open", True)
    # two entries a day, the third is refused for everyone in the party
    _, c, sc = await hero(client, gw, "luat_c", "Luật C")
    gw.parties.leave(b)
    await make_party(gw, sa, sc)
    for _ in range(2):
        gw.realms.room_order = ["boss"]
        await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
        await settle(gw)
        assert gw.realms.instance_of(gw.players[a]) is not None, last(sa, "error")
        await gw.handle(sa, {"t": "realm", "op": "leave"})
        await gw.handle(sc, {"t": "realm", "op": "leave"})
        await tick(gw)
        assert gw.realms.instance_of(gw.players[a]) is None and gw.players[a].channel.zone_id == "truc_lam_thon"
        gw._place(sa, "truc_lam_thon", *gate(), "up")
        gw._place(sc, "truc_lam_thon", *gate(), "up")
    await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    await settle(gw)
    assert last(sc, "error")["code"] == "daily_limit" and gw.realms.instance_of(gw.players[a]) is None
    async with dbm.SessionLocal() as db:
        assert (await secret_realm.entries_used(db, a))["mac_anh_dong"] == 2
    clock._clock.advance(days=1)                                     # a new day (UTC+7): entries again
    async with dbm.SessionLocal() as db:
        assert (await secret_realm.entries_used(db, a)).get("mac_anh_dong", 0) == 0


async def test_must_stand_at_the_gate(client, gw):
    _, a, sa = await hero(client, gw, "xa_a", "Xa A")
    _, b, sb = await hero(client, gw, "xa_b", "Xa B")
    gw._place(sa, "truc_lam_thon", 100, 300, "up")
    await make_party(gw, sa, sb)
    await gw.handle(sa, {"t": "realm", "op": "enter", "realm": "mac_anh_dong"})
    assert last(sa, "error")["code"] == "too_far"


async def test_matchmaking_queue_forms_a_party(client, gw):
    """Spec 14.1: solo players queue at the gate; a party is made by realm when enough wait."""
    fill = balance.load("realm")["queue"]["fill_seconds"]
    _, a, sa = await hero(client, gw, "cho_a", "Chờ A")
    _, b, sb = await hero(client, gw, "cho_b", "Chờ B")
    _, c, sc = await hero(client, gw, "cho_c", "Chờ C", realm_id="luyen_khi")
    await gw.handle(sc, {"t": "realm", "op": "queue", "realm": "mac_anh_dong"})
    assert last(sc, "error")["code"] == "cannot_enter"               # not yet Trúc Cơ
    gw.realms.room_order = ["boss"]
    await gw.handle(sa, {"t": "realm", "op": "queue", "realm": "mac_anh_dong"})
    assert last(sa, "realm")["event"] == "queued" and last(sa, "realm")["waiting"] == 1
    await tick(gw, 2.0)
    assert gw.realms.queued.get(a) == "mac_anh_dong"                 # alone: still waiting
    await gw.handle(sb, {"t": "realm", "op": "queue", "realm": "mac_anh_dong"})
    assert last(sa, "realm")["waiting"] == 2
    await tick(gw, fill - 3.0)
    assert gw.realms.instance_of(gw.players[a]) is None              # waiting a little for more people
    await tick(gw, 1.5)
    await settle(gw)
    inst = gw.realms.instance_of(gw.players[a])
    assert inst is not None and gw.realms.instance_of(gw.players[b]) is inst
    assert set(gw.parties.party_of(a).members) == {a, b} and not gw.realms.queued


async def test_rift_appears_near_players_and_closes(client, gw):
    _, a, sa = await hero(client, gw, "nut_a", "Nứt A", realm_id="luyen_khi")
    _, b, sb = await hero(client, gw, "nut_b", "Nứt B", realm_id="luyen_khi")
    ch = gw._pick_channel("rung_muc_loang")
    gw._place(sa, "rung_muc_loang", 300, 330, "down")
    gw._place(sb, "rung_muc_loang", 300, 340, "down")
    r = gw.realms.spawn_rift(ch, gw.mono(), 330, 330)
    assert last(sa, "notice")
    await tick(gw, 0.2)
    snap = [m for m in msgs(sa, "snap") if any(e.get("k") == "r" for e in m.get("add", []))]
    assert snap and next(e for e in snap[-1]["add"] if e["k"] == "r")["realm"] == "khe_nut_muc"
    await make_party(gw, sa, sb)
    gw.players[a].x = 600                                            # far away: cannot step in
    await gw.handle(sa, {"t": "realm", "op": "enter", "rift": r.id})
    assert last(sa, "error")["code"] == "too_far"
    gw.players[a].x = 320
    gw.realms.room_order = ["boss"]
    await gw.handle(sa, {"t": "realm", "op": "enter", "rift": r.id})
    await settle(gw)
    inst = gw.realms.instance_of(gw.players[a])
    assert inst is not None and inst.realm_id == "khe_nut_muc"
    await tick(gw, balance.load("realm")["rift"]["life_seconds"] + 1)   # five minutes later it is gone
    assert r.id not in gw.realms.rifts and r not in ch.extras


async def test_rift_queue_pairs_strangers(client, gw):
    _, a, sa = await hero(client, gw, "la_a", "Lạ A", realm_id="luyen_khi")
    _, b, sb = await hero(client, gw, "la_b", "Lạ B", realm_id="luyen_khi")
    ch = gw._pick_channel("ho_nghien_muc")
    gw._place(sa, "ho_nghien_muc", 820, 300, "down")
    gw._place(sb, "ho_nghien_muc", 830, 300, "down")
    r = gw.realms.spawn_rift(ch, gw.mono(), 825, 310)
    gw.realms.room_order = ["boss"]
    await gw.handle(sa, {"t": "realm", "op": "queue", "rift": r.id})
    await gw.handle(sb, {"t": "realm", "op": "queue", "rift": r.id})
    await tick(gw, balance.load("realm")["queue"]["fill_seconds"] + 1.5)
    await settle(gw)
    inst = gw.realms.instance_of(gw.players[a])
    assert inst is not None and inst.realm_id == "khe_nut_muc" and gw.realms.instance_of(gw.players[b]) is inst


# ------------------------------------------------------------------ puzzles: what a mistake costs
async def three(client, gw, prefix, rooms, **kw):
    hs = [await hero(client, gw, f"{prefix}_{i}", f"{prefix.title()} {i}", **kw) for i in range(3)]
    inst = await enter(gw, hs[0][2], hs[1][2], hs[2][2], rooms=rooms)
    assert inst is not None
    inst.monsters[:] = [m for m in inst.monsters if m is inst.boss]   # about the puzzle alone (the boss stays)
    return hs, inst


def stand(p, a, dx=0.0, dy=0.0):
    p.x, p.y = a.x + a.w / 2 + dx, a.y + a.h / 2 + dy


def away(inst, ps):
    cx, cy = inst.room_center()
    for i, p in enumerate(ps):
        p.x, p.y = cx - 40 + 40 * i, cy + 80


async def test_compose_wrong_stone_hurts_and_deals_again(client, gw):
    hs, inst = await three(client, gw, "ghep", ["compose", "boss"])
    pz = inst.puzzle
    ps = [gw.players[u] for _, u, _ in hs]
    ped = {o.props["slot"]: o for o in inst.objs("pedestal")}
    away(inst, ps)
    first, second = pz.required
    owner = next(p for p in ps if pz.pieces[p.user_id] == pz.need[first])
    decoy = next(p for p in ps if pz.pieces[p.user_id] not in pz.need.values())
    hp, hp_owner = decoy.hp, owner.hp
    stand(owner, ped[first])
    stand(decoy, ped[second])
    await tick(gw, 0.1)
    assert decoy.hp < hp and owner.hp == hp_owner                    # only the wrong holder pays
    assert pz.mistakes == 1 and not pz.solved
    assert "piece" in msgs(hs[0][2], "realm", "mine")[-1]["mine"]    # the pieces were dealt again
    away(inst, ps)
    await tick(gw, 3.0)
    for slot in pz.required:
        p = next(p for p in ps if pz.pieces[p.user_id] == pz.need[slot]
                 and not any(inst.on(p, o) for o in ped.values()))
        stand(p, ped[slot])
    await tick(gw, 0.1)
    assert pz.solved and pz.public(gw.mono())["answer"] == pz.word.hanzi


async def test_compose_window_runs_out(client, gw):
    hs, inst = await three(client, gw, "cham", ["compose", "boss"])
    pz = inst.puzzle
    ps = [gw.players[u] for _, u, _ in hs]
    away(inst, ps)
    stand(ps[0], next(o for o in inst.objs("pedestal") if o.props["slot"] == pz.required[0]))
    await tick(gw, 0.1)
    assert pz.public(gw.mono())["window"] is not None
    await tick(gw, balance.load("realm")["compose"]["window_seconds"] + 0.2)
    assert pz.mistakes == 1


async def test_sentence_wrong_step_hurts_right_steps_reveal(client, gw):
    hs, inst = await three(client, gw, "cau", ["sentence", "boss"])
    pz = inst.puzzle
    ps = {u: gw.players[u] for _, u, _ in hs}
    tiles = {int(o.props["n"]): o for o in inst.objs("tile")}
    away(inst, list(ps.values()))
    wrong = next(p for u, p in ps.items() if pz.owner[0] != u)
    hp = wrong.hp
    stand(wrong, tiles[1])
    await tick(gw, 0.1)
    assert wrong.hp < hp and pz.k == 0 and pz.mistakes == 1
    wrong.y += 60
    await tick(gw, 0.1)
    for i in range(pz.n):
        p = ps[pz.owner[i]]
        stand(p, tiles[i + 1])
        await tick(gw, 0.1)
        assert pz.k == i + 1
        p.y += 60
        await tick(gw, 0.1)
    assert pz.solved
    assert [t["t"] for t in pz.public(gw.mono())["done"]] == [t["t"] for t in pz.tokens]


async def test_sentence_each_player_sees_only_their_words(client, gw):
    hs, inst = await three(client, gw, "rieng", ["sentence", "boss"])
    pz = inst.puzzle
    seen = []
    for _, u, s in hs:
        mine = msgs(s, "realm", "room")[-1]["mine"]["tokens"]
        assert sorted(t["t"] for t in mine) == sorted(t["t"] for i, t in enumerate(pz.tokens) if pz.owner[i] == u)
        seen += [t["t"] for t in mine]
    assert sorted(seen) == sorted(t["t"] for t in pz.tokens)


async def test_tone_pillars_streak_and_timeout(client, gw):
    hs, inst = await three(client, gw, "dieu", ["tone", "boss"])
    pz = inst.puzzle
    ps = [gw.players[u] for _, u, _ in hs]
    pil = {int(o.props["tone"]): o for o in inst.objs("pillar")}
    for i, p in enumerate(ps):
        x, y = realm.anchor(pil[i + 1])
        p.x, p.y = x, y + 8
    await tick(gw, 3.2)
    assert pz.round is not None and "hanzi" in pz.public(gw.mono())["round"]
    assert "tone" not in pz.public(gw.mono())["round"]               # never the answer
    t = pz.round["tone"]
    striker = ps[0]
    striker.x, striker.y = realm.anchor(pil[t])[0], realm.anchor(pil[t])[1] + 8
    await gw.handle(hs[0][2], {"t": "ract", "obj": pil[t].name})
    assert pz.streak == 1
    await tick(gw, 2.0)                                              # nobody strikes this time
    assert pz.round is not None
    resp = gw.players[pz.round["resp"]]
    hp = resp.hp
    await tick(gw, balance.load("realm")["tone"]["answer_seconds"] + 1.5)
    assert pz.streak == 0 and pz.mistakes == 1 and resp.hp < hp     # the one nearest the right pillar pays
    await tick(gw, 2.0)
    t = pz.round["tone"]
    bad = 1 if t != 1 else 2                                         # the wrong pillar
    striker.x, striker.y = realm.anchor(pil[bad])[0], realm.anchor(pil[bad])[1] + 8
    hp = striker.hp
    await gw.handle(hs[0][2], {"t": "ract", "obj": pil[bad].name})
    assert pz.mistakes == 2 and striker.hp < hp


async def test_mirror_wrong_person_hurts_everyone(client, gw):
    hs, inst = await three(client, gw, "guong", ["mirror", "boss"])
    pz = inst.puzzle
    ps = {u: gw.players[u] for _, u, _ in hs}
    mir = inst.objs("mirror")[0]
    away(inst, list(ps.values()))
    await tick(gw, 2.2)
    assert pz.target is not None
    for _, u, s in hs:   # each sees their own word only
        assert msgs(s, "realm", "mine")[-1]["mine"]["hanzi"] == pz.assigned[u].hanzi
    wrong = next(p for u, p in ps.items() if pz.assigned[u].id != pz.target.id)
    before = {u: p.hp for u, p in ps.items()}
    stand(wrong, mir)
    await tick(gw, 0.1)
    assert pz.mistakes == 1 and all(ps[u].hp < before[u] for u in ps)
    away(inst, list(ps.values()))
    await tick(gw, 2.2)
    for _ in range(pz.need):
        who = next(p for u, p in ps.items() if pz.assigned[u].id == pz.target.id)
        stand(who, mir)
        await tick(gw, 0.1)
        away(inst, list(ps.values()))
        await tick(gw, 2.0)
    assert pz.solved and pz.correct == pz.need


async def test_maze_light_and_lantern(client, gw):
    hs, inst = await three(client, gw, "toi", ["maze", "boss"], words=[h for h in TIER1 if h not in ("明", "光")])
    pz = inst.puzzle
    assert pz.lantern and len(pz.carriers) == 1 and pz.radius == balance.load("realm")["maze"]["lantern_radius"]
    ps = [gw.players[u] for _, u, _ in hs]
    carrier = gw.players[pz.carriers[0]]
    lost = next(p for p in ps if p is not carrier)
    door = inst.objs("maze_exit")[0]
    hp = lost.hp
    stand(lost, door)                                                # alone in the dark, far from the light
    await tick(gw, 2.1)
    assert lost.hp < hp
    for p in ps:
        stand(p, door)
    await tick(gw, 0.1)
    assert pz.solved


async def test_maze_carriers_are_who_learned_ming(client, gw):
    hs = [await hero(client, gw, "sang_0", "Sáng 0"),
          await hero(client, gw, "sang_1", "Sáng 1", words=[h for h in TIER1 if h != "明"])]
    inst = await enter(gw, hs[0][2], hs[1][2], rooms=["maze", "boss"])
    assert inst.puzzle.carriers == [hs[0][1]] and not inst.puzzle.lantern


# ------------------------------------------------------------------ ghosts, the boss, coming back
async def test_down_in_a_realm_is_a_ghost_until_the_next_room(client, gw):
    from app.realtime import combat
    hs, inst = await three(client, gw, "hon", ["maze", "boss"])
    p = gw.players[hs[1][1]]
    async with dbm.SessionLocal() as db:
        xp_before = (await db.get(Character, p.user_id)).cultivation_xp
    combat.hurt_player(inst, p, p.max_hp * 2, gw.mono())
    await settle(gw)
    assert p.dead and p.ghost and last(hs[1][2], "dead")["ghost"] == 1
    x0 = p.x
    await gw.handle(hs[1][2], {"t": "in", "s": 900, "k": [[0, -1, 50]]})
    await tick(gw, 0.1)
    assert p.y != x0 or p.x != x0                                    # a ghost still follows the party
    await tick(gw, 5)
    assert p.ghost and p.channel is inst                             # no respawn in the village
    async with dbm.SessionLocal() as db:
        assert (await db.get(Character, p.user_id)).cultivation_xp == xp_before   # no Tu Vi lost
    door = inst.objs("maze_exit")[0]
    for _, u, _ in hs:
        stand(gw.players[u], door)
    await tick(gw, 0.1)
    assert inst.phase == "advancing"                                 # the living were enough
    await tick(gw, balance.load("realm")["advance_seconds"] + 0.1)
    assert inst.kind == "boss" and not p.ghost and not p.dead and p.hp > 0
    assert any(m.get("event") == "revived" for m in msgs(hs[1][2], "realm"))


async def test_everyone_down_fails_the_run(client, gw):
    from app.realtime import combat
    hs, inst = await three(client, gw, "bai", ["maze", "boss"])
    for _, u, _ in hs:
        p = gw.players[u]
        combat.hurt_player(inst, p, p.max_hp * 2, gw.mono())
    await tick(gw, 0.1)
    assert inst.phase == "ended" and inst.result == "failed"
    await tick(gw, balance.load("realm")["exit_seconds"] + 0.5)
    assert all(gw.players[u].channel.zone_id == "truc_lam_thon" and not gw.players[u].dead for _, u, _ in hs)


async def test_boss_needs_one_right_answer_per_living_member(client, gw):
    from app.realtime import combat
    hs, inst = await three(client, gw, "ma", ["boss"])
    await tick(gw, 3.5)
    b = inst.boss
    assert b is not None and b.shield and b.info["rank"] == "boss"
    extra = balance.load("realm")["boss"]["hp_per_extra_member"] * 2
    assert round(b.max_hp) == round(b.info["hp"] * (1 + extra))      # grows with the party
    ps = [gw.players[u] for _, u, _ in hs]
    assert all(p.question is not None for p in ps)                   # everyone gets their own question
    for h, u, s in hs[:2]:
        q = last(s, "q")["q"]
        key = await answer_key(q["session_id"])
        r = await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                    "answer": correct_answer(q["qtype"], key)}, headers=h)
        res = r.json()["combat"]
        assert res["correct"] and not res["shield_broken"]
    assert b.shield and len(b.group_hits) == 2                       # two of three: still up
    combat.hurt_player(inst, ps[2], 10_000, gw.mono(), ignore_protect=True)   # the third falls
    await tick(gw, 0.1)
    assert not b.shield                                              # the two living ones were enough


async def test_reconnect_within_a_minute_keeps_the_place(client, gw):
    hs, inst = await three(client, gw, "rot", ["mirror", "maze", "boss"])
    h, u, s = hs[2]
    p = gw.players[u]
    gw.disconnect(s)
    assert p.session is None
    assert p.linger_until - gw.mono() == pytest.approx(balance.load("realm")["reconnect_seconds"])
    await tick(gw, 40)
    assert p.channel is inst and inst.members[u].state == "in"
    s2 = type(s)(u, s.username, s.name, s.realm, s.appearance)
    s2.sent = []
    gw.sessions[u] = s2
    assert gw.join(s2, "bi_canh", "resume")
    kinds = [(m["t"], m.get("event")) for m in s2.sent]
    assert ("zone", None) in kinds and ("realm", "start") in kinds and ("realm", "room") in kinds
    room = msgs(s2, "realm", "room")[-1]
    assert room["kind"] == inst.kind and "mine" in room and p.session is s2


async def test_gone_too_long_leaves_but_keeps_the_loot(client, gw):
    hs, inst = await three(client, gw, "mat", ["maze", "mirror", "boss"])
    door = inst.objs("maze_exit")[0]
    for _, u, _ in hs:
        stand(gw.players[u], door)
    await tick(gw, 0.1)
    await settle(gw)
    h, u, s = hs[2]
    gw.disconnect(s)
    for _ in range(2 * (balance.load("realm")["reconnect_seconds"] + 1)):
        await tick(gw, 0.5)
        inst.monsters[:] = []      # the two left idle must not die meanwhile (that would end the run)
    assert inst.kind == "mirror" and inst.phase != "ended"
    await settle(gw)
    await gw.flush_saves()
    assert u not in gw.players and inst.members[u].state == "left"
    async with dbm.SessionLocal() as db:
        assert (await db.get(Character, u)).zone_id == "truc_lam_thon"   # a bí cảnh is never saved as a place
        claims = (await db.execute(select(RealmClaim).where(RealmClaim.user_id == u))).scalars().all()
        assert [c.stage for c in claims] == ["room0"]                # the maze's loot stays theirs
        assert (await db.get(RealmMember, (inst.run_id, u))).result == "disconnected"
    assert any(m.get("event") == "member_left" for m in msgs(hs[0][2], "realm"))



async def test_run_ending_while_someone_is_away_gives_them_the_run_result(client, gw):
    """Someone drops, 40 s later the run fails (finish_run writes "failed" for them too), and their
    60 s reconnect window runs out before the 30 s exit: the first result written stays (left_at IS NULL)."""
    hs, inst = await three(client, gw, "vang", ["maze", "boss"])
    h, u, s = hs[2]
    gw.disconnect(s)
    for _ in range(80):
        await tick(gw, 0.5)
        inst.monsters[:] = []
    inst._finish("failed", gw.mono.t)          # the two still here fell to the boss
    await settle(gw)
    await tick(gw, 25)                          # past the reconnect window, before everyone is sent out
    await gw.flush_saves()
    assert inst.members[u].state == "left"
    async with dbm.SessionLocal() as db:
        assert (await db.get(RealmMember, (inst.run_id, u))).result == "failed"

# ------------------------------------------------------------------ loot
async def test_loot_is_claimed_once_even_when_asked_twice_at_once(client, gw):
    _, a, sa = await hero(client, gw, "kho_a", "Kho A")
    _, b, sb = await hero(client, gw, "kho_b", "Kho B")
    async with dbm.SessionLocal() as db:
        run_id = await secret_realm.create_run(db, "khe_nut_muc", [a, b])
        await db.commit()
    got = await asyncio.gather(*[secret_realm.claim_chest(run_id, a, "khe_nut_muc", 3, False) for _ in range(4)])
    assert sum(1 for x in got if x is not None) == 1
    assert await secret_realm.claim_chest(run_id, b, "khe_nut_muc", 3, False) is not None   # b rolls on their own
    async with dbm.SessionLocal() as db:
        for uid in (a, b):
            frag = (await db.execute(select(InventoryItem.quantity).where(
                InventoryItem.user_id == uid, InventoryItem.item_id == "manh_bao_vat"))).scalars().all()
            assert sum(frag) == 3
        assert len((await db.execute(select(RealmClaim).where(RealmClaim.run_id == run_id))).scalars().all()) == 2


async def test_fast_clear_pays_more(client, gw, monkeypatch):
    _, a, sa = await hero(client, gw, "nhanh_a", "Nhanh A")
    async with dbm.SessionLocal() as db:
        run_id = await secret_realm.create_run(db, "khe_nut_muc", [a])
        await db.commit()
    monkeypatch.setitem(balance.load("realm")["chest"]["khe_nut_muc"], "stones", [100, 100])
    fast = await secret_realm.claim_chest(run_id, a, "khe_nut_muc", 2, True)
    assert fast["stones"] == 100 * balance.load("realm")["fast_bonus"]["stones_mult"] and fast["fast"]


async def test_forge_fragments_into_a_set_piece_with_bonus(client, gw):
    h, a, sa = await hero(client, gw, "ren_a", "Rèn A")
    fc = balance.load("realm")["forge"]
    r = await client.post("/realm/forge", json={"piece": "mac_anh_bao"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_enough"
    async with dbm.SessionLocal() as db:
        from app.systems import inventory
        await inventory.change_item(db, a, "manh_bao_vat", fc["fragments"] * 2, "test")
        await inventory.change_currency(db, a, "spirit_stones", fc["stones"] * 2, "test")
        await db.commit()
    ids = []
    for piece in ("mac_anh_bao", "mac_anh_quan"):
        r = await client.post("/realm/forge", json={"piece": piece}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["equipment"]["rarity"] == "thien"
        ids.append(r.json()["equipment"]["id"])
    async with dbm.SessionLocal() as db:
        ch = await db.get(Character, a)
        before = await cultivation.current_stats(db, ch)
        own = 0
        for e in (await db.execute(select(EquipmentInstance).where(EquipmentInstance.id.in_(ids)))).scalars():
            e.equipped_slot = {"mac_anh_bao": "body", "mac_anh_quan": "hat"}[e.item_id]
            own += cultivation.instance_stats(e).get("ink_res", 0)
        await db.commit()
        after = await cultivation.current_stats(db, ch)
    set_bonus = cultivation.catalog.equipment()["sets"]["mac_anh"]["bonus"]["2"]["ink_res"]
    assert after["ink_res"] - before["ink_res"] == own + set_bonus    # Bộ Mặc Ảnh, 2 pieces


async def test_gate_view(client, gw):
    h, a, sa = await hero(client, gw, "cong_a", "Cổng A")
    v = (await client.get("/realms", headers=h)).json()
    ids = {r["id"]: r for r in v["realms"]}
    assert ids["mac_anh_dong"]["entries_left"] == 2 and ids["mac_anh_dong"]["open"] is True
    assert ids["khe_nut_muc"]["kind"] == "rift" and v["party"] is None and v["forge"]["fragments"] > 0
    assert set(v["puzzles"]) >= {"compose", "sentence", "tone", "mirror", "maze"}


def test_schedule_window(monkeypatch):
    import datetime as dt
    c = balance.load("realm")
    monkeypatch.setitem(c, "always_open", False)
    h = c["schedule"]["hours_local"][0]
    at = dt.datetime(2026, 3, 1, h, 5) - clock.VN_OFFSET            # five minutes after it opened
    st = realm.window_status(at)
    assert st["open"] and st["closes_in"] == (c["schedule"]["open_minutes"] - 5) * 60
    st = realm.window_status(at - dt.timedelta(minutes=15))
    assert not st["open"] and st["opens_in"] == 10 * 60
