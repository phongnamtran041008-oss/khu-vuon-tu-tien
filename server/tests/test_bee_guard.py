"""Stage 5: guard bees in the shared world (spec 10.2.3). The world runs with a fake clock
and its tick is called by hand, like test_combat.py."""
from sqlalchemy import select

from app import clock
from app import db as dbm
from app.models import Bee, Character, Hive
from app.realtime import combat, guard
from app.systems import bees as beesys
from tests.test_combat import FOREST, answer, at_monster, fighter, gw, hit, last, run, settle  # noqa: F401


async def with_guards(client, w, username, display, kinds=("muc", "hoang_kim"), realm="luyen_khi", level=1):
    h, uid, s = await fighter(client, w, username, display)
    async with dbm.SessionLocal() as db:
        ch = await db.get(Character, uid)
        ch.realm, ch.realm_stage = realm, 1
        db.add(Hive(user_id=uid, layout={}, level=1, decorations=[], honey=0.0, wax=0.0, cells=10,
                    honey_checked_at=clock.now(), pollen_checked_at=clock.now()))
        for i, k in enumerate(kinds):
            db.add(Bee(user_id=uid, bee_type=k, level=level, xp=0, hive_slot=beesys.cell_order()[i], role="guard",
                       bond=0, obtained_at=clock.now()))
        await db.commit()
        s.realm = realm
        await w._load_combat(s, ch)
    return h, uid, s


def bee_hits(s) -> list[dict]:
    return [ev for m in s.sent if m.get("t") == "snap" for ev in m.get("fx", []) if ev.get("k") == "hit" and ev.get("b")]


async def test_guards_follow_and_show_in_snapshots(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_1", "Ong Một")
    p, m = at_monster(gw, s)
    assert [b.sp for b in p.bees] == ["muc", "hoang_kim"]
    run(gw, 0.5)
    snap = last(s, "snap")
    mine = snap["me"][7]
    assert [x[1] for x in mine] == ["muc", "hoang_kim"] and mine[0][2] == mine[0][3] > 0
    assert p.state()[6] == [["muc", 100, "", 0], ["hoang_kim", 100, "", 0]]
    assert p.full()["bees"][1][0] == "hoang_kim"


async def test_bees_never_touch_a_shielded_monster(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_2", "Ong Hai", kinds=("hoang_kim", "kim_o"), level=20)
    p, m = at_monster(gw, s)
    full = m.hp
    run(gw, 20)                      # bees hover for 20 s next to a shielded monster
    assert m.hp == full and m.shield and m.burn is None
    assert all(b.target is None for b in p.bees) and not bee_hits(s)
    # the player answers right: the shield breaks and now the bees join in
    p.x, p.y = m.x, m.y              # (it wandered a little meanwhile)
    await hit(gw, p, m)
    await answer(client, h, s, True)
    assert not m.shield
    m.hp = m.max_hp                  # (keep it alive for a moment)
    before = m.hp
    run(gw, 2.0)
    hits = bee_hits(s)
    assert hits and {ev["b"] for ev in hits} <= {"hoang_kim", "kim_o"} and m.hp < before
    assert all(b.target == m.eid or not m.alive for b in p.bees)


async def test_shield_coming_back_stops_the_bees(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_3", "Ong Ba", kinds=("hoang_kim", "muc"), level=20)
    p, m = at_monster(gw, s, "ink_fox")
    p.max_hp = p.hp = 5000
    await hit(gw, p, m)
    await answer(client, h, s, True)
    assert not m.shield
    m.hp = m.max_hp * 0.52
    for _ in range(200):             # bees sting until the elite's shield returns at 50 %
        run(gw, 0.1)
        if m.shield:
            break
    assert m.shield and m.hp >= m.max_hp * 0.5 - 1e-6
    hp = m.hp
    run(gw, 5)
    assert m.hp == hp                # nothing gets through the new Mặc Thuẫn


async def test_kill_gives_bee_xp_and_owner_loot(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_4", "Ong Bốn", kinds=("hoang_kim", "ngoc_bich"), level=20)
    p, m = at_monster(gw, s)
    await hit(gw, p, m)
    await answer(client, h, s, True)
    for _ in range(100):
        if not m.alive:
            break
        run(gw, 0.2)
    assert not m.alive
    await settle(gw)
    assert last(s, "loot") is not None                  # the kill is the owner's
    async with dbm.SessionLocal() as db:
        rows = (await db.execute(select(Bee).where(Bee.user_id == uid))).scalars().all()
        assert all(b.xp == 0 and b.level == 20 for b in rows)   # max level: XP stays 0
    # a level-1 bee does gain XP
    async with dbm.SessionLocal() as db:
        for b in (await db.execute(select(Bee).where(Bee.user_id == uid))).scalars().all():
            b.level = 1
        await db.commit()
    await beesys.combat_xp(uid, [b.id for b in p.bees])
    async with dbm.SessionLocal() as db:
        rows = (await db.execute(select(Bee).where(Bee.user_id == uid))).scalars().all()
        assert all(b.xp == beesys.cfg()["xp_kill_assist"] for b in rows)


async def test_loot_bee_raises_drops():
    class P:
        user_id = 1
        bees = [guard.GuardBee(5, "ngoc_bich", 30, 4, 1.5, {"type": "loot", "stones_pct": 25, "drop_mult": 1.25})]

    class M:
        bee_assist = {1: {5}}
    assert combat._loot_bonus(P(), M()) == {"stones_pct": 25.0, "drop_mult": 1.25}
    M.bee_assist = {1: set()}
    assert combat._loot_bonus(P(), M()) == {"stones_pct": 0.0, "drop_mult": 1.0}


async def test_monster_hits_bees_and_they_rest_60s(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_5", "Ong Năm", kinds=("muc",))
    p, m = at_monster(gw, s)
    await hit(gw, p, m)
    await answer(client, h, s, True)
    m.hp = m.max_hp
    run(gw, 1.0)
    b = p.bees[0]
    assert b.target == m.eid
    b.hp = 1
    guard.hit_bees(p.channel, m, gw.mono())
    assert b.is_down(gw.mono()) and b.target is None
    fx = [ev for ev in p.channel.events if ev.get("k") == "bee_down"]
    assert fx and fx[0]["s"] == "muc"
    left = b.down_until - gw.mono()
    assert abs(left - beesys.cfg()["guard"]["down_seconds"]) < 0.01
    run(gw, 30)
    assert b.is_down(gw.mono()) and last(s, "snap")["me"][7][0][4] > 0
    run(gw, 31)
    assert not b.is_down(gw.mono()) and b.hp == b.max_hp


async def test_skills_burn_slow_stun_heal(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_6", "Ong Sáu", kinds=("kim_o", "bang_tam"), level=1)
    p, m = at_monster(gw, s, "ink_fox")
    p.max_hp = p.hp = 5000
    await hit(gw, p, m)
    await answer(client, h, s, True)
    m.hp = m.max_hp
    run(gw, 2.5)
    assert m.burn is not None and m.slow_until > gw.mono() and m.slow_mult == 0.5
    # stun and heal, called directly with a fixed dice roll
    import random
    ch = p.channel
    stunner = guard.GuardBee(99, "loi_van", 30, 4, 1.4, {"type": "stun", "chance": 1.0, "duration": 1.0})
    guard._sting(ch, p, stunner, m, gw.mono(), random.Random(1))
    assert m.stun_until > gw.mono() and m.tele is None
    p.hp = p.max_hp / 2
    healer = guard.GuardBee(98, "duoc_su", 30, 2, 1.6, {"type": "heal", "pct": 2.0})
    guard._sting(ch, p, healer, m, gw.mono(), random.Random(1))
    assert p.hp == p.max_hp / 2 + p.max_hp * 0.02


async def test_role_change_reaches_the_world(client, gw):
    h, uid, s = await with_guards(client, gw, "ong_7", "Ong Bảy", kinds=("muc", "hoa"))
    p, m = at_monster(gw, s)
    bid = p.bees[1].id
    r = await client.post("/bees/role", json={"bee_id": bid, "role": "hive"}, headers=h)
    assert r.status_code == 200, r.text
    assert [b.sp for b in p.bees] == ["muc"] and [d["sp"] for d in s.bees] == ["muc"]
    r = await client.post("/bees/role", json={"bee_id": bid, "role": "guard"}, headers=h)
    assert [b.sp for b in p.bees] == ["muc", "hoa"]


def test_build_keeps_hp_and_rest():
    old = guard.build([{"id": 1, "sp": "muc", "hp": 30, "atk": 3, "cd": 1.5}])
    old[0].hp, old[0].down_until = 10, 500.0
    new = guard.build([{"id": 1, "sp": "muc", "hp": 40, "atk": 4, "cd": 1.5, "level": 2}], old)
    assert new[0].hp == 20 and new[0].down_until == 500.0 and new[0].atk == 4
