"""Stage 8: luyện đan (spec 12.3). Đan phương, ingredients, the fee, the canh lửa minigame replayed
on the server, pinyin of learned characters, quality, the furnace, and the pills it makes
(Tụ Linh, Kháng Mực, Ngộ Tính, Phong Vương)."""
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app import balance, clock
from app.models import AlchemySession, Bee
from app.systems import alchemy_fire, catalog
from tests.econ_helpers import common_word, fruits, give, give_fruit, player, qty, set_stones, stones
from tests.helpers import answer_key, correct_answer

ROOT = Path(__file__).resolve().parents[2]
C = balance.load("alchemy")


def perfect_timings(fire: dict) -> list[int]:
    """Stop the needle on the centre of each văn hỏa zone."""
    out = []
    for z, period in zip(fire["zones"], fire["periods"]):
        half = period // 2
        out.append(max(C["min_press_ms"], round(z["center"] / fire["bar"] * half)))
    return out


def miss_timings(fire: dict) -> list[int]:
    out = []
    for z, period in zip(fire["zones"], fire["periods"]):
        half = period // 2
        out.append(half if z["center"] < 60 else C["min_press_ms"])   # at the far end, or right at the start
    return out


async def brewer(client, name="dan_su", **kw):
    h, uid = await player(client, name, stones=500, **kw)
    await give(uid, "dp_hoi_huyet", 1)
    await give(uid, "truc_diep_thao", 3)
    await give_fruit(uid, common_word(), 6)
    return h, uid


async def finish(client, h, fire, timings, answers=None, frozen=None):
    if frozen is not None:
        frozen.advance(milliseconds=sum(timings) + 50)
    return await client.post("/alchemy/finish", json={"session_id": fire["session_id"], "timings": timings,
                                                      "pinyin_answers": answers or [None] * len(timings)}, headers=h)


# ------------------------------------------------------------------ data
def test_shared_fire_file_is_identical():
    a = (ROOT / "server" / "app" / "systems" / "alchemy_fire.py").read_bytes()
    b = (ROOT / "client" / "engine" / "alchemy_fire.py").read_bytes()
    assert a == b


def test_needle_and_judging():
    assert alchemy_fire.needle(0, 2000) == 0
    assert alchemy_fire.needle(1000, 2000) == 100
    assert alchemy_fire.needle(1500, 2000) == 50
    assert alchemy_fire.needle(2000, 2000) == 0        # back at the start
    assert alchemy_fire.judge(50, 50, 20, 6) == "perfect"
    assert alchemy_fire.judge(58, 50, 20, 6) == "good"
    assert alchemy_fire.judge(70, 50, 20, 6) == "miss"
    q = C["quality"]
    assert alchemy_fire.quality(*alchemy_fire.total(["perfect"] * 3, [None] * 3, C["points"]), q) == "thuong"
    assert alchemy_fire.quality(*alchemy_fire.total(["miss"] * 3, [None] * 3, C["points"]), q) == "phe"
    # wrong readings pull a perfect fire down
    assert alchemy_fire.quality(*alchemy_fire.total(["perfect"] * 3, [False] * 3, C["points"]), q) != "thuong"


def test_every_recipe_is_complete():
    pills, mats = catalog.pills(), catalog.materials()
    for rid, r in catalog.recipes().items():
        assert rid in pills, rid
        assert mats[r["item"]]["kind"] == "recipe" and mats[r["item"]]["recipe"] == rid
        assert len(r["chars"]) == C["presses"] and "".join(c["c"] for c in r["chars"]) == pills[rid]["hanzi"]
        for ing in r["ingredients"]:
            if ing["kind"] == "item":
                assert catalog.stack_item(ing["item"]) is not None, ing
        assert set(r["yield"]) == {"ha", "trung", "thuong"}
    # spec 12.3 names every one of these pills
    for pid in ("hoi_huyet_dan", "hoi_khi_dan", "tu_linh_dan", "khang_muc_dan", "ngo_tinh_dan", "truc_co_dan",
                "kim_dan_dan", "phong_vuong_dan"):
        assert pid in catalog.recipes()


def test_recipe_readings_match_cc_cedict():
    path = ROOT / "tools" / "raw" / "cedict.txt"
    if not path.exists():
        pytest.skip("CC-CEDICT not downloaded (tools/raw/cedict.txt)")
    readings: dict[str, set[str]] = {}
    for line in path.read_text("utf-8").splitlines():
        m = re.match(r"^(\S+) (\S+) \[([^\]]+)\]", line)
        if m and len(m.group(2)) == 1:
            readings.setdefault(m.group(2), set()).add(m.group(3).lower())
    from app.learning import pinyin as py
    for r in catalog.recipes().values():
        for c in r["chars"]:
            assert c["numeric"] in readings.get(c["c"], set()), (c, readings.get(c["c"]))
            assert py.numeric_to_marked(c["numeric"]) == c["pinyin"], c


# ------------------------------------------------------------------ brewing
async def test_brew_takes_ingredients_and_fee_and_perfect_fire_gives_thuong_pham(client, frozen):
    h, uid = await brewer(client)
    ov = (await client.get("/alchemy", headers=h)).json()
    hh = next(r for r in ov["recipes"] if r["id"] == "hoi_huyet_dan")
    assert hh["known"] and hh["ready"] and ov["where"] == "home"
    unknown = next(r for r in ov["recipes"] if r["id"] == "truc_co_dan")
    assert not unknown["known"] and "ingredients" not in unknown and unknown["sources_vi"]
    r = await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)
    assert r.status_code == 200, r.text
    fire = r.json()["fire"]
    assert await stones(uid) == 500 - 10
    assert await qty(uid, "truc_diep_thao") == 2 and await fruits(uid) == 4
    assert await qty(uid, "dp_hoi_huyet") == 1          # the recipe is kept
    # nothing learned yet: every character comes with its reading, nothing to type
    assert all(not c["ask"] and c["pinyin"] for c in fire["chars"])
    assert [c["c"] for c in fire["chars"]] == ["回", "血", "丹"]
    res = (await finish(client, h, fire, perfect_timings(fire), frozen=frozen)).json()
    assert res["quality"] == "thuong" and res["hits"] == ["perfect"] * 3
    assert res["made"] == 3 and await qty(uid, "hoi_huyet_dan") == 3
    # the same session cannot pay out twice
    r = await finish(client, h, fire, perfect_timings(fire))
    assert r.status_code == 409


async def test_a_missed_fire_is_phe_dan_and_the_ingredients_are_gone(client, frozen):
    h, uid = await brewer(client)
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()["fire"]
    res = (await finish(client, h, fire, miss_timings(fire), frozen=frozen)).json()
    assert res["quality"] == "phe" and res["made"] == 0
    assert await qty(uid, "hoi_huyet_dan") == 0 and await fruits(uid) == 4


async def test_without_recipe_ingredients_or_money_nothing_is_taken(client):
    h, uid = await player(client, stones=500)
    r = await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)
    assert r.json()["error"]["code"] == "no_recipe"
    await give(uid, "dp_hoi_huyet", 1)
    await give(uid, "truc_diep_thao", 1)
    await give_fruit(uid, common_word(), 1)               # needs 2
    r = await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)
    assert r.json()["error"]["code"] == "no_ingredient"
    assert await qty(uid, "truc_diep_thao") == 1 and await fruits(uid) == 1 and await stones(uid) == 500
    await give_fruit(uid, common_word(), 1)
    await set_stones(uid, 5)                              # the fee is 10
    r = await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)
    assert r.json()["error"]["code"] == "insufficient_funds"
    assert await qty(uid, "truc_diep_thao") == 1 and await fruits(uid) == 2 and await stones(uid) == 5


async def test_realm_gate(client):
    h, uid = await player(client, stones=5000)
    await give(uid, "dp_kim_dan", 1)
    r = await client.post("/alchemy/start", json={"recipe_id": "kim_dan_dan"}, headers=h)
    assert r.json()["error"]["code"] == "realm_low"


async def test_finishing_faster_than_the_needle_can_run_is_refused(client, frozen):
    h, uid = await brewer(client)
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()["fire"]
    r = await client.post("/alchemy/finish", json={"session_id": fire["session_id"], "timings": [9000, 9000, 9000],
                                                   "pinyin_answers": [None] * 3}, headers=h)
    assert r.json()["error"]["code"] == "too_fast"
    r = await client.post("/alchemy/finish", json={"session_id": fire["session_id"], "timings": [1, 2],
                                                   "pinyin_answers": [None] * 2}, headers=h)
    assert r.json()["error"]["code"] == "bad_timings"
    # still open: an honest finish works
    res = (await finish(client, h, fire, perfect_timings(fire), frozen=frozen)).json()
    assert res["quality"] == "thuong"


async def test_starting_again_resumes_the_same_fire(client):
    h, uid = await brewer(client)
    a = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()
    b = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()
    assert b["resumed"] and b["fire"]["session_id"] == a["fire"]["session_id"]
    assert await qty(uid, "truc_diep_thao") == 2            # taken once


async def test_a_fire_left_too_long_goes_out(client, frozen):
    h, uid = await brewer(client)
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()["fire"]
    frozen.advance(seconds=C["session_seconds"] + 1)
    res = (await finish(client, h, fire, perfect_timings(fire))).json()
    assert res["expired"] and res["made"] == 0


async def test_learned_characters_are_asked_and_graded_on_the_server(client, frozen, db):
    """回气丹: 气 is in 天气, so a player who learned 天气 has to type qì."""
    h, uid = await player(client, learn=["天气"], stones=500)
    await give(uid, "dp_hoi_khi", 1)
    await give(uid, "linh_mat", 2)
    await give(uid, "truc_diep_thao", 2)
    await give_fruit(uid, common_word(), 2)
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_khi_dan"}, headers=h)).json()["fire"]
    by = {c["c"]: c for c in fire["chars"]}
    assert by["气"]["ask"] and "pinyin" not in by["气"] and "key" not in by["气"]
    assert not by["回"]["ask"] and by["回"]["pinyin"] == "huí"
    row = await db.get(AlchemySession, fire["session_id"])
    assert row.params["chars"][1]["key"] == "qi4"
    answers = [None, "qi2", None]          # wrong tone
    res = (await finish(client, h, fire, perfect_timings(fire), answers, frozen=frozen)).json()
    assert res["chars"][1] == {"c": "气", "pinyin": "qì", "hv": "khí", "right": False}
    assert res["points"] == 6 - 1 and res["best"] == 7 and res["quality"] == "trung"
    # right this time: Thượng phẩm and a little Tu Vi
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_khi_dan"}, headers=h)).json()["fire"]
    res = (await finish(client, h, fire, perfect_timings(fire), [None, "qi4", None], frozen=frozen)).json()
    assert res["quality"] == "thuong" and res["chars"][1]["right"] and res["xp"]["gained"] == C["xp_per_right_pinyin"]


async def test_far_from_any_furnace(client, monkeypatch):
    h, uid = await brewer(client)
    from app.realtime.world import world
    monkeypatch.setattr(world, "in_world", lambda u: True)
    monkeypatch.setattr(world, "near_npc", lambda u, npc, radius=56: False)
    r = await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)
    assert r.json()["error"]["code"] == "too_far"
    monkeypatch.setattr(world, "near_npc", lambda u, npc, radius=56: npc == "alchemist")
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()["fire"]
    assert fire["furnace_level"] == C["public_furnace_level"]
    r = await client.post("/alchemy/furnace/upgrade", headers=h)
    assert r.json()["error"]["code"] == "not_home"


async def test_upgrading_the_furnace_widens_the_zones(client):
    h, uid = await brewer(client)
    lv2 = C["furnace"][1]
    r = await client.post("/alchemy/furnace/upgrade", headers=h)
    assert r.json()["error"]["code"] == "no_material"
    for m in lv2["materials"]:
        await give(uid, m["item"], m["qty"])
    await set_stones(uid, lv2["cost"]["spirit_stones"] + 10)
    r = await client.post("/alchemy/furnace/upgrade", headers=h)
    assert r.status_code == 200 and r.json()["furnace"]["level"] == 2
    assert await stones(uid) == 10 and await qty(uid, "muc_tinh") == 0
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()["fire"]
    assert fire["zones"][0]["width"] == C["zone_width"]["1"] + lv2["zone_bonus"] and fire["furnace_level"] == 2


async def test_brewing_counts_for_quests(client, frozen):
    h, uid = await brewer(client)
    from app.models import Quest
    from app import db as dbm
    async with dbm.SessionLocal() as s:
        s.add(Quest(user_id=uid, quest_id="dd2_me_dan_dau", state="active", progress={"n": 0}))
        await s.commit()
    fire = (await client.post("/alchemy/start", json={"recipe_id": "hoi_huyet_dan"}, headers=h)).json()["fire"]
    await finish(client, h, fire, perfect_timings(fire), frozen=frozen)
    qs = (await client.get("/quests", headers=h)).json()
    q = next(x for x in qs["quests"] if x["id"] == "dd2_me_dan_dau")
    assert q["state"] == "done"


# ------------------------------------------------------------------ the pills
async def test_tu_linh_dan_gives_more_tu_vi_for_right_answers(client, db):
    h, uid = await player(client, learn=["水"], stones=0)
    await give(uid, "tu_linh_dan", 1)
    q = (await client.post("/quiz/practice", json={}, headers=h)).json()
    base = (await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                    "answer": correct_answer(q["qtype"], await answer_key(q["session_id"]))},
                              headers=h)).json()["xp"]["gained"]
    r = await client.post("/inventory/use", json={"item_id": "tu_linh_dan"}, headers=h)
    assert r.status_code == 200 and r.json()["buff"] == "tu_linh" and r.json()["seconds"] == C["buff_seconds"]
    q = (await client.post("/quiz/practice", json={}, headers=h)).json()
    more = (await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                    "answer": correct_answer(q["qtype"], await answer_key(q["session_id"]))},
                              headers=h)).json()["xp"]["gained"]
    assert more == round(base * C["buffs"]["tu_linh"]["xp_mult"])
    cult = (await client.get("/cultivation", headers=h)).json()
    assert cult["buffs"][0]["id"] == "tu_linh"


async def test_ngo_tinh_dan_adds_seconds_to_every_question(client, frozen):
    h, uid = await player(client, learn=["水"])
    await give(uid, "ngo_tinh_dan", 1)
    q1 = (await client.post("/quiz/practice", json={"qtype": "Q1"}, headers=h)).json()
    await client.post("/inventory/use", json={"item_id": "ngo_tinh_dan"}, headers=h)
    q2 = (await client.post("/quiz/practice", json={"qtype": "Q1"}, headers=h)).json()
    assert q2["time_limit"] == q1["time_limit"] + C["buffs"]["ngo_tinh"]["extra_seconds"]
    frozen.advance(seconds=C["buff_seconds"] + 1)            # it wears off
    q3 = (await client.post("/quiz/practice", json={"qtype": "Q1"}, headers=h)).json()
    assert q3["time_limit"] == q1["time_limit"]


async def test_taking_the_same_buff_twice_stacks_up_to_two_doses(client):
    h, uid = await player(client)
    await give(uid, "khang_muc_dan", 3)
    secs = [(await client.post("/inventory/use", json={"item_id": "khang_muc_dan"}, headers=h)).json()["seconds"]
            for _ in range(3)]
    assert secs == [C["buff_seconds"], 2 * C["buff_seconds"], 2 * C["buff_seconds"]]


async def test_khang_muc_dan_softens_mac_kich():
    from app.realtime import combat
    from app.realtime.world import world
    from app.realtime.zone import Player
    p = Player(1, "a", {}, "luyen_khi", 0, 0)
    p.max_hp = 200
    m = type("M", (), {"info": {"rank": "normal"}})()
    plain = combat.mac_kich(p, m)
    p.buffs = {"khang_muc": world.mono() + 100}
    assert combat.mac_kich(p, m) == pytest.approx(plain * (1 - C["buffs"]["khang_muc"]["ink_res"] / 100))


async def test_phong_vuong_dan_feeds_a_bee(client, db):
    h, uid = await player(client)
    await client.get("/garden", headers=h)
    await client.get("/hive", headers=h)
    db.add(Bee(user_id=uid, bee_type="muc", level=1, xp=0, hive_slot=0, role="hive", bond=0, obtained_at=clock.now()))
    await db.commit()
    bee = (await db.execute(select(Bee).where(Bee.user_id == uid))).scalar_one()
    await give(uid, "phong_vuong_dan", 1)
    r = await client.post("/inventory/use", json={"item_id": "phong_vuong_dan"}, headers=h)
    assert r.json()["error"]["code"] == "bee_food"
    r = await client.post("/bees/feed", json={"bee_id": bee.id, "food": "phong_vuong_dan"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["xp_gained"] >= C["bee_food"]["phong_vuong_dan"]["xp"] and r.json()["levels_gained"] >= 1
    assert r.json()["bond"] >= C["bee_food"]["phong_vuong_dan"]["bond"]
