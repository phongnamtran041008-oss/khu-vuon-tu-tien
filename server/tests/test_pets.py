"""Stage 8: Linh Thú (spec 13, 6.8). The banner, the 12 con giáp, duplicates, wearing one pet, its
combat bonus, and each skill where it acts. No skill answers or skips a question."""
import datetime as dt
import random
import re
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import select

from app import balance, clock
from app.learning.wordbank import bank
from app.models import CodexEntry, Pet, Plot, User
from app.systems import catalog, pets
from app.systems.gacha import Banner
from tests.econ_helpers import give_fruit, player, stones
from tests.helpers import answer_key, correct_answer

ROOT = Path(__file__).resolve().parents[2]
SP = catalog.pets()["species"]


async def give_pet(db, uid, kind, level=1, equipped=True) -> int:
    p = Pet(user_id=uid, pet_type=kind, level=level, equipped=equipped)
    db.add(p)
    await db.commit()
    return p.id


def test_twelve_zodiac_pets_with_the_banner_rarities():
    assert len(SP) == 12
    b = balance.gacha()["banners"]["pets"]
    assert b["enabled"] and b["price"] == {"spirit_stones": 500} and b["alt_price"] == {"immortal_jade": 10}
    assert {s["rarity"] for s in SP.values()} == set(b["rarities"])
    assert [s["zodiac_vi"] for s in SP.values()] == ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân",
                                                    "Dậu", "Tuất", "Hợi"]
    assert SP["rong"]["rarity"] == "legendary"
    # the four skills of bản 1 are there as written (spec 13)
    assert SP["chuot"]["skill"] == {"type": "seed_rare", "value": 0.05}
    assert SP["trau"]["skill"] == {"type": "review_stones", "value": 0.2}
    assert SP["ho"]["skill"] == {"type": "wither_slow", "value": 0.5}
    assert SP["rong"]["skill"] == {"type": "streak_double", "every": 5}
    assert len({s["skill"]["type"] for s in SP.values()}) == 12


def test_pet_names_match_cc_cedict():
    path = ROOT / "tools" / "raw" / "cedict.txt"
    if not path.exists():
        pytest.skip("CC-CEDICT not downloaded (tools/raw/cedict.txt)")
    from app.learning import pinyin as py
    readings: dict[str, set[str]] = {}
    for line in path.read_text("utf-8").splitlines():
        m = re.match(r"^(\S+) (\S+) \[([^\]]+)\]", line)
        if m and len(m.group(2)) == 1:
            readings.setdefault(m.group(2), set()).add(m.group(3).lower())
    for pid, s in SP.items():
        assert py.marked_to_numeric(s["pinyin"]) in readings.get(s["hanzi"], set()), (pid, s, readings.get(s["hanzi"]))


def test_banner_rates_hold_over_many_rolls():
    banner = Banner.load("pets")
    rng = random.Random(8)
    got, _ = banner.roll(100_000, {}, rng, use_pity=False)
    n = Counter(got)
    for r, p in banner.rates.items():
        assert abs(n[r] / 100_000 - p) < 0.01, r


async def test_rolling_gives_pets_levels_duplicates_and_codex(client, db):
    h, uid = await player(client, "thu_nuoi", stones=60_000)
    seen = Counter()
    for _ in range(12):
        r = await client.post("/gacha/roll", json={"banner": "pets", "count": 10}, headers=h)
        assert r.status_code == 200, r.text
        for res in r.json()["results"]:
            seen[res["pet_type"]] += 1
            assert res["rarity"] == SP[res["pet_type"]]["rarity"]
    rows = (await db.execute(select(Pet).where(Pet.user_id == uid))).scalars().all()
    assert len(rows) == len(seen)                         # one row per species
    for p in rows:
        assert p.level == min(catalog.pets()["max_level"], seen[p.pet_type])
    codex = (await db.execute(select(CodexEntry).where(CodexEntry.user_id == uid, CodexEntry.codex == "pet"))
             ).scalars().all()
    assert {c.entry_id for c in codex} == set(seen)
    ov = (await client.get("/pets", headers=h)).json()
    assert ov["found"] == len(seen) and ov["total"] == 12
    hidden = [b for b in ov["book"] if not b["found"]]
    assert all("name_vi" not in b and "skill_vi" not in b for b in hidden)


async def test_a_copy_past_the_top_level_becomes_stones(client, db):
    h, uid = await player(client, "thu_day", stones=0)
    await give_pet(db, uid, "chuot", level=catalog.pets()["max_level"], equipped=False)
    user = await db.get(User, uid)
    out = await pets.resolve_gacha(db, user, ["common"], type("R", (), {"choice": staticmethod(lambda xs: "chuot")})())
    await db.commit()
    assert out[0]["stones"] == catalog.pets()["dupe_stones"]["common"]
    assert await stones(uid) == catalog.pets()["dupe_stones"]["common"]


async def test_wearing_one_pet_adds_its_stats(client, db):
    h, uid = await player(client, "thu_deo")
    a = await give_pet(db, uid, "ho", level=1, equipped=False)
    b = await give_pet(db, uid, "trau", level=3, equipped=False)
    base = (await client.get("/cultivation", headers=h)).json()["stats"]
    r = await client.post("/pets/equip", json={"pet_id": a}, headers=h)
    assert r.status_code == 200 and r.json()["equipped"] == a
    st = (await client.get("/cultivation", headers=h)).json()
    assert st["stats"]["atk"] == base["atk"] + SP["ho"]["stats"]["atk"] and st["pet"]["pet_type"] == "ho"
    r = await client.post("/pets/equip", json={"pet_id": b}, headers=h)
    assert r.json()["equipped"] == b
    worn = (await db.execute(select(Pet).where(Pet.user_id == uid, Pet.equipped.is_(True)))).scalars().all()
    assert [p.id for p in worn] == [b]                    # only one at a time
    st = (await client.get("/cultivation", headers=h)).json()["stats"]
    mult = 1 + catalog.pets()["stat_per_level"] * 2
    assert st["def"] == base["def"] + round(SP["trau"]["stats"]["def"] * mult) and st["atk"] == base["atk"]
    r = await client.post("/pets/equip", json={"pet_id": None}, headers=h)
    assert r.json()["equipped"] is None
    h2, _ = await player(client, "ke_khac")
    r = await client.post("/pets/equip", json={"pet_id": a}, headers=h2)
    assert r.json()["error"]["code"] == "no_pet"


# ------------------------------------------------------------------ skills
async def _ripe_review(client, db, h, uid, hanzi="水"):
    """A plant due for review; returns the answer of a right review."""
    w = bank().by_hanzi[hanzi]
    plot = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.unlocked.is_(True)))).scalars().first()
    plot.word_id, plot.stage = w.id, 2
    plot.next_review_at = clock.now() - dt.timedelta(seconds=1)
    plot.wither, plot.wither_checked_at = 0.0, clock.now()
    await db.commit()
    q = (await client.post("/garden/review", json={"plot_id": plot.id}, headers=h)).json()
    return (await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                    "answer": correct_answer(q["qtype"], await answer_key(q["session_id"]))},
                              headers=h)).json()


async def test_trau_adds_20_percent_to_review_stones(client, db):
    h, uid = await player(client, "chu_trau", learn=["水"])
    await client.get("/garden", headers=h)
    plain = (await _ripe_review(client, db, h, uid))["reward"]["spirit_stones"]
    await give_pet(db, uid, "trau")
    res = await _ripe_review(client, db, h, uid)
    assert res["reward"]["spirit_stones"] == plain + round(plain * 0.2) and res["pet_bonus"]["pet"] == "trau"


async def test_rong_doubles_the_fifth_right_answer_in_a_row(client, db):
    h, uid = await player(client, "chu_rong", learn=["水"])
    await client.get("/garden", headers=h)
    await give_pet(db, uid, "rong")
    rewards = []
    for _ in range(5):
        res = await _ripe_review(client, db, h, uid)
        rewards.append(res["reward"]["spirit_stones"])
    assert rewards[:4] == [rewards[0]] * 4 and rewards[4] == 2 * rewards[0] and res["streak"] == 5


async def test_ho_slows_wither_by_half(client, db, frozen):
    h, uid = await player(client, "chu_ho", learn=["水"])
    await client.get("/garden", headers=h)
    w = bank().by_hanzi["水"]
    plots = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.unlocked.is_(True)))).scalars().all()
    for p in plots[:1]:
        p.word_id, p.stage, p.next_review_at = w.id, 2, clock.now()
        p.wither, p.wither_checked_at = 0.0, clock.now()
    await db.commit()
    frozen.advance(days=4)   # 1 day of grace, then 3 days overdue
    plain = next(p for p in (await client.get("/garden", headers=h)).json()["plots"] if p.get("word"))["wither"]
    p = await db.get(Plot, plots[0].id)
    await db.refresh(p)
    p.wither, p.wither_checked_at, p.next_review_at = 0.0, clock.now(), clock.now()
    await db.commit()
    await give_pet(db, uid, "ho")
    frozen.advance(days=4)
    slow = next(p for p in (await client.get("/garden", headers=h)).json()["plots"] if p.get("word"))["wither"]
    assert plain > 0 and slow == pytest.approx(plain / 2, abs=0.2)


async def test_chuot_moves_five_percent_from_common_to_rare(client, db, monkeypatch):
    h, uid = await player(client, "chu_chuot", stones=1000)
    seen = []
    real = Banner.roll

    def spy(self, n, state, rng, use_pity=True):
        seen.append(dict(self.rates))
        return real(self, n, state, rng, use_pity)
    monkeypatch.setattr(Banner, "roll", spy)
    await client.post("/gacha/roll", json={"banner": "seeds", "count": 1}, headers=h)
    await give_pet(db, uid, "chuot")
    await client.post("/gacha/roll", json={"banner": "seeds", "count": 1}, headers=h)
    base = balance.gacha()["banners"]["seeds"]["rates"]
    assert seen[0] == base
    assert seen[1]["rare"] == pytest.approx(base["rare"] + 0.05) and seen[1]["common"] == pytest.approx(base["common"] - 0.05)
    assert sum(seen[1].values()) == pytest.approx(1.0)
    assert balance.gacha()["banners"]["seeds"]["rates"] == base   # the config itself is untouched


async def test_lon_sells_fruit_for_more(client, db):
    h, uid = await player(client, "chu_lon", stones=0)
    w = next(x for x in bank().words.values() if x.rarity == "common")
    await give_fruit(uid, w.hanzi, 10)
    r = await client.post("/fruits/sell", json={"word_id": w.id, "count": 5}, headers=h)
    plain = r.json()["earned"]
    await give_pet(db, uid, "lon")
    r = await client.post("/fruits/sell", json={"word_id": w.id, "count": 5}, headers=h)
    assert r.json()["earned"] == int(plain * 1.1)


async def test_ga_adds_tu_vi_to_garden_reviews(client, db):
    h, uid = await player(client, "chu_ga", learn=["水"])
    await client.get("/garden", headers=h)
    plain = (await _ripe_review(client, db, h, uid))["xp"]["gained"]
    await give_pet(db, uid, "ga")
    assert (await _ripe_review(client, db, h, uid))["xp"]["gained"] == round(plain * 1.1)


async def test_khi_gives_more_linh_khi_in_thu_vuon(client, db):
    h, uid = await player(client, "chu_khi", learn=["水", "火", "木"])
    lo = [bank().by_hanzi[x].id for x in ("水", "火", "木")]
    a = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": lo}, headers=h)).json()
    await give_pet(db, uid, "khi")
    b = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": lo}, headers=h)).json()
    assert b["params"]["qi"]["start"] == a["params"]["qi"]["start"] + 20


async def test_combat_pets_ran_cho_ngua():
    from app.realtime import combat
    from app.realtime.zone import Player
    p = Player(1, "a", {}, "luyen_khi", 0, 0)
    p.max_hp = 200
    m = type("M", (), {"info": {"rank": "normal"}, "bee_assist": {}})()
    plain = combat.mac_kich(p, m)
    p.pet = "ran"
    assert combat.mac_kich(p, m) == pytest.approx(plain * 0.8)
    p.pet = "cho"
    assert combat._loot_bonus(p, m)["drop_mult"] == pytest.approx(1.15)
    p.pet = "ngua"
    assert combat._loot_bonus(p, m)["stones_pct"] == pytest.approx(15)


async def test_de_and_meo_skills_are_wired(client, db):
    assert await pets.skill_value(db, 999999, "honey") == 0.0
    h, uid = await player(client, "chu_de")
    await give_pet(db, uid, "de")
    assert await pets.skill_value(db, uid, "honey") == pytest.approx(0.15)
    assert await pets.skill_value(db, uid, "fish_luck") == 0.0
