"""Stage 6: câu cá (spec 11). The checks asked for by the stage plan:
  * the odds of each fish follow the rod and the bait (100 000 rolls against the formula);
  * the client cannot cheat the result: it never chooses the fish, its reel input is
    played again on the server, and a catch faster than real time is refused.
Plus the flow cast -> hook -> question -> reel, baits, rods, Ngư Phổ, records and weather."""
import random
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import select

from app import clock
from app.learning.wordbank import bank
from app.models import Character, Collection, FishCatch, InventoryItem, User
from app.systems import catalog, fishing
from app.systems import fishing_sim as fs
from tests.helpers import answer_key, correct_answer, register, wrong_answer

LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}
DAY = {"night": False, "rain": False}
NIGHT_RAIN = {"night": True, "rain": True}


# ------------------------------------------------------------------ helpers
async def player(client, name="ngu_phu", learn: list[str] | None = None):
    h, data = await register(client, name)
    r = await client.post("/character/create", json={"display_name": name.replace("_", " ").title(), "appearance": LOOK},
                          headers=h)
    assert r.status_code == 200, r.text
    uid = data["user_id"]
    if learn:
        from app import db as dbm
        async with dbm.SessionLocal() as db:
            for hz in learn:
                wid = bank().by_hanzi[hz].id
                col = await db.get(Collection, (uid, wid))
                if col is None:
                    db.add(Collection(user_id=uid, word_id=wid, introduced=True, mastery=40, first_seen_at=clock.now()))
                else:
                    col.introduced, col.mastery = True, 40
            await db.commit()
    return h, uid


async def qty(uid: int, item_id: str) -> int:
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        rows = (await db.execute(select(InventoryItem).where(InventoryItem.user_id == uid,
                                                             InventoryItem.item_id == item_id))).scalars().all()
        return sum(r.quantity for r in rows)


async def give(uid: int, item_id: str, n: int) -> None:
    from app import db as dbm
    from app.systems import inventory
    async with dbm.SessionLocal() as db:
        await inventory.change_item(db, uid, item_id, n, "test")
        await db.commit()


def honest_toggles(params: dict) -> tuple[list[int], int, str]:
    """What a good player does: hold while the hook is under the fish."""
    r = fs.Reel(params)
    hold, flips = False, []
    while r.result is None:
        want = r.hook + r.vel * 0.25 < r.fish
        if want != hold:
            flips.append(r.steps)
            hold = want
        r.step(hold)
    return flips, r.steps, r.result


@pytest.fixture
def force_fish(monkeypatch):
    """Pick the species the next bite will be (the server still decides the size)."""
    chosen = {}

    def roll(pool, cond, bait_id, luck, rng):
        return chosen.get("fish", "ca_diec")
    monkeypatch.setattr(fishing, "roll_fish", roll)
    return chosen


@pytest.fixture(autouse=True)
def no_casts():
    fishing._casts.clear()
    yield
    fishing._casts.clear()


class InWorld:
    """Puts a character in a world zone at a position, like the WebSocket world would."""

    def __init__(self, uid: int, zone: str, x: float, y: float):
        from app.realtime import maps
        from app.realtime.zone import Player

        class Ch:
            map = maps.load(zone)
        self.uid = uid
        self.p = Player(uid, "Ngư Phủ", {}, "pham_nhan", x, y)
        self.p.channel = Ch()

    def __enter__(self):
        from app.realtime.world import world
        world.players[self.uid] = self.p
        return self.p

    def __exit__(self, *a):
        from app.realtime.world import world
        world.players.pop(self.uid, None)


def dock_tip():
    from app.realtime import maps
    m = maps.load("ho_nghien_muc")
    return m, (27.9 * 16, 19.6 * 16)


async def cast_and_hook(client, h, frozen, spot="abode"):
    r = await client.post("/fishing/cast", json={"spot": spot}, headers=h)
    assert r.status_code == 200, r.text
    c = r.json()
    frozen.advance(seconds=c["bite_in"])
    hk = await client.post("/fishing/hook", json={"cast_id": c["cast_id"]}, headers=h)
    assert hk.status_code == 200, hk.text
    return c, hk.json()


async def reel_honestly(client, h, frozen, cast_id, params):
    flips, steps, result = honest_toggles(params)
    frozen.advance(seconds=steps * fs.STEP_MS / 1000)
    r = await client.post("/fishing/reel", json={"cast_id": cast_id, "toggles": flips}, headers=h)
    assert r.status_code == 200, r.text
    return r.json(), result


# ------------------------------------------------------------------ data
def test_thirty_species_five_rarities_and_names():
    sp = catalog.fish()
    assert len(sp) >= 30
    assert {f["rarity"] for f in sp.values()} == set(fishing.RARITIES)
    words = bank().by_hanzi
    for fid, f in sp.items():
        assert f["pinyin"] and f["hanzi"] and f["name_vi"]
        if f["fictional"]:
            assert f["meaning_en"] is None
            assert f["hanzi"] not in words, f"{fid}: an invented name must never be a vocabulary word"
        else:
            assert f["meaning_en"], f"{fid}: real fish names come from CC-CEDICT"
    assert sp["chep_hoa_long"]["fictional"] and sp["chep_hoa_long"]["bait"] == ["linh_qua_vun"]
    assert sp["ca_chep"]["hanzi"] == "鲤鱼" and sp["ca_vang"]["hanzi"] == "金鱼" and sp["ca_tram_co"]["hanzi"] == "草鱼"


def test_fish_names_are_never_asked():
    """Fish are not words of the game: no question can be generated about a fish name."""
    ids = set(bank().words)
    assert not any(fid in ids or fishing.fish_item(fid) in ids for fid in catalog.fish())


# ------------------------------------------------------------------ odds (stage plan: distribution by rod/bait)
@pytest.mark.parametrize("pool,cond,bait,rod", [
    ("ho", DAY, "giun_dat", "can_truc_tho"),
    ("ho", DAY, "giun_dat", "can_long_cot"),
    ("ho", NIGHT_RAIN, "linh_qua_vun", "can_ngoc_bich"),
    ("ao", DAY, "banh_mat", "can_tre_gia"),
    ("ho", {"night": True, "rain": False}, "moi_muc", "can_tre_gia"),
])
def test_rarity_and_species_rates_match_the_formula(pool, cond, bait, rod):
    luck = fishing.rod_stats(rod, 0)["luck"] + catalog.baits()[bait]["luck"]
    rar = fishing.rarity_odds(pool, cond, bait, luck)
    spo = fishing.species_odds(pool, cond, bait, luck)
    assert abs(sum(rar.values()) - 1) < 1e-9 and abs(sum(spo.values()) - 1) < 1e-9
    rng = random.Random(f"{pool}{bait}{rod}")
    n = 100_000
    got = Counter(fishing.roll_fish(pool, cond, bait, luck, rng) for _ in range(n))
    by_r = Counter()
    for fid, k in got.items():
        by_r[catalog.fish()[fid]["rarity"]] += k
    for r, p in rar.items():
        assert abs(by_r[r] / n - p) < 0.01, (r, by_r[r] / n, p)
    for fid, p in spo.items():
        assert abs(got[fid] / n - p) < 0.006, (fid, got[fid] / n, p)
    assert set(got) <= set(spo)


def test_better_rod_and_bait_mean_rarer_fish():
    def rare(rod, bait):   # chance of Huyền or rarer
        luck = fishing.rod_stats(rod, 0)["luck"] + (catalog.baits()[bait]["luck"] if bait else 0)
        odds = fishing.rarity_odds("ho", DAY, bait, luck)
        return 1 - odds["pham"] - odds["linh"]
    chain = [rare(r, "giun_dat") for r in ("can_truc_tho", "can_tre_gia", "can_ngoc_bich", "can_long_cot", "can_thien_to")]
    assert chain == sorted(chain) and chain[-1] > chain[0] * 1.7
    assert rare("can_truc_tho", "linh_qua_vun") > rare("can_truc_tho", "giun_dat")
    # an upgraded rod is luckier than the same rod at level 0
    l0, l5 = fishing.rod_stats("can_tre_gia", 0)["luck"], fishing.rod_stats("can_tre_gia", 5)["luck"]
    assert l5 > l0


def test_bait_rules():
    # a bait doubles the species it attracts
    luck = 0.0
    base = fishing.species_odds("ho", DAY, "linh_qua_vun", luck)
    worm = fishing.species_odds("ho", DAY, "giun_dat", luck)
    pham_share = lambda o, f: o[f] / sum(p for k, p in o.items() if catalog.fish()[k]["rarity"] == "pham")  # noqa: E731
    assert abs(pham_share(worm, "ca_diec") / pham_share(base, "ca_diec") - 2) < 0.35
    # Mồi Mực attracts only ink fish, and nothing at all by day
    ink = fishing.eligible("ho", {"night": True, "rain": False}, "moi_muc")
    assert ink and all("ink" in catalog.fish()[f]["tags"] for f in ink)
    # no bait: only Phàm and Linh bite
    assert {catalog.fish()[f]["rarity"] for f in fishing.eligible("ho", DAY, None)} <= {"pham", "linh"}
    # Cá Chép Hóa Long: Hồ Nghiên Mực, night, rain, Linh Quả Vụn only
    assert "chep_hoa_long" in fishing.eligible("ho", NIGHT_RAIN, "linh_qua_vun")
    for pool, cond, bait in (("ao", NIGHT_RAIN, "linh_qua_vun"), ("ho", {"night": True, "rain": False}, "linh_qua_vun"),
                             ("ho", NIGHT_RAIN, "giun_dat"), ("ho", {"night": False, "rain": True}, "linh_qua_vun")):
        assert "chep_hoa_long" not in fishing.eligible(pool, cond, bait)


def test_weather_is_shared_and_rains_at_the_configured_rate():
    import datetime as dt
    t0 = dt.datetime(2026, 3, 1)
    assert fishing.is_raining("ho_nghien_muc", t0) == fishing.is_raining("ho_nghien_muc", t0 + dt.timedelta(seconds=5))
    period = fishing.cfg()["weather_period_seconds"]
    rains = sum(fishing.is_raining("ho_nghien_muc", t0 + dt.timedelta(seconds=period * i)) for i in range(4000))
    assert abs(rains / 4000 - fishing.cfg()["rain_chance"]["ho_nghien_muc"]) < 0.03
    # night follows the world's day/night (one game day = two real hours)
    from app.realtime.world import World
    for minutes in range(0, 240, 7):
        t = dt.datetime(2026, 3, 1, 10, 0) + dt.timedelta(minutes=minutes)
        clock.set_clock(clock.FrozenClock(t))
        try:
            h = World.day_phase() * 24
            assert fishing.is_night(t) == (h >= 18 or h < 6)
        finally:
            clock.set_clock(clock.Clock())


# ------------------------------------------------------------------ the shared minigame
def test_minigame_is_shared_with_the_client_and_replays_exactly():
    root = Path(__file__).resolve().parents[2]
    a = (root / "server" / "app" / "systems" / "fishing_sim.py").read_bytes()
    b = (root / "client" / "engine" / "fishing_sim.py").read_bytes()
    assert a == b
    rod = fishing.rod_stats("can_truc_tho", 0)
    rng = random.Random(7)
    for i in range(200):
        p = fishing.reel_params(rng.choice(fishing.RARITIES), rng.random(), rod, rng.choice((0.65, 1.0, 1.3)),
                                rng.randrange(1, 2 ** 31))
        flips, steps, result = honest_toggles(p)
        r = fs.replay(p, flips)
        assert (r.result, r.steps) == (result, steps)
    p = fishing.reel_params("pham", 0.2, rod, 1.0, 99)
    assert fs.replay(p, [0]).result == fs.SNAPPED        # holding all the time snaps the line
    assert fs.replay(p, []).result == fs.ESCAPED         # never pulling lets it go


def test_quiz_widens_or_narrows_the_zone():
    rod = fishing.rod_stats("can_truc_tho", 0)
    z = lambda m: fishing.reel_params("linh", 0.5, rod, m, 1)["zone"]  # noqa: E731
    assert z(1.3) > z(1.0) > z(0.65)


# ------------------------------------------------------------------ the flow through the API
async def test_cast_hook_reel_lands_a_fish_in_the_abode_pond(client, frozen, force_fish):
    h, uid = await player(client)
    v = (await client.get("/fishing", headers=h)).json()
    assert v["rod"] == "can_truc_tho" and v["rods"][0]["owned"] and v["bait"] is None
    force_fish["fish"] = "ca_chep"
    c, hk = await cast_and_hook(client, h, frozen)
    assert c["pool"] == "ao" and hk["stage"] == "reel" and hk["rarity"] == "pham"
    out, expected = await reel_honestly(client, h, frozen, c["cast_id"], hk["params"])
    assert out["result"] == expected == "caught"
    assert out["fish"]["id"] == "ca_chep" and out["new_species"] and out["personal_record"]
    lo, hi = catalog.fish()["ca_chep"]["size_cm"]
    assert lo <= out["size_cm"] <= hi
    item = "ca_nho" if out["small"] else "fish_ca_chep"
    assert await qty(uid, item) == 1
    book = (await client.get("/codex/fish", headers=h)).json()
    assert book["found"] == 1 and book["total"] >= 30
    entry = next(e for e in book["species"] if e["id"] == "ca_chep")
    assert entry["caught"] and entry["count"] == 1 and entry["best_size_cm"] == out["size_cm"]
    hidden = next(e for e in book["species"] if e["id"] == "con")
    assert not hidden["caught"] and "hanzi" not in hidden and hidden["hint_vi"]
    # sold to the village like any material
    if not out["small"]:
        r = await client.post("/inventory/sell", json={"item_id": "fish_ca_chep", "qty": 1}, headers=h)
        assert r.status_code == 200 and r.json()["earned"] == catalog.fish()["ca_chep"]["sell_price"]


async def test_hook_too_early_or_too_late(client, frozen, force_fish):
    h, _ = await player(client)
    c = (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).json()
    frozen.advance(seconds=max(0.0, c["bite_in"] - 1.0))
    assert (await client.post("/fishing/hook", json={"cast_id": c["cast_id"]}, headers=h)).json()["stage"] == "early"
    # the cast is over: hooking again does nothing
    assert (await client.post("/fishing/hook", json={"cast_id": c["cast_id"]}, headers=h)).status_code == 409
    c = (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).json()
    frozen.advance(seconds=c["bite_in"] + c["window"] + 3)
    assert (await client.post("/fishing/hook", json={"cast_id": c["cast_id"]}, headers=h)).json()["stage"] == "late"


async def test_client_cannot_choose_the_fish_or_claim_a_catch(client, frozen, force_fish):
    h, uid = await player(client)
    force_fish["fish"] = "ca_diec"
    c = (await client.post("/fishing/cast", json={"spot": "abode", "fish": "chep_hoa_long"}, headers=h)).json()
    frozen.advance(seconds=c["bite_in"])
    hk = (await client.post("/fishing/hook", json={"cast_id": c["cast_id"], "fish": "chep_hoa_long", "size_cm": 999},
                            headers=h)).json()
    assert hk["rarity"] == "pham"   # extra fields are ignored: the server picked the fish
    # reeling before the hook was set is refused
    c2 = (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).json()
    assert (await client.post("/fishing/reel", json={"cast_id": c2["cast_id"], "toggles": []}, headers=h)).status_code == 409
    fishing._casts.clear()
    c, hk = await cast_and_hook(client, h, frozen)
    flips, steps, result = honest_toggles(hk["params"])
    assert result == "caught"
    # a perfect input sent at once (no real time passed) is refused
    r = await client.post("/fishing/reel", json={"cast_id": c["cast_id"], "toggles": flips}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_fast"
    # malformed input is refused
    frozen.advance(seconds=steps * fs.STEP_MS / 1000)
    for bad in ([5, 5, 9], [9, 3], [-1, 4]):
        r = await client.post("/fishing/reel", json={"cast_id": c["cast_id"], "toggles": bad}, headers=h)
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_input"
    # an input that does not catch the fish loses it, whatever the client believes (never
    # pressing keeps the hook on the bottom, below the fish; holding all the time is not a sure
    # loss: when the fish swims near the top the hook stays inside its zone)
    r = (await client.post("/fishing/reel", json={"cast_id": c["cast_id"], "toggles": []}, headers=h)).json()
    assert r["result"] == "escaped" and "fish" not in r
    assert await qty(uid, "fish_ca_diec") == 0 and await qty(uid, "ca_nho") == 0
    # and the cast cannot be reeled a second time
    r = await client.post("/fishing/reel", json={"cast_id": c["cast_id"], "toggles": flips}, headers=h)
    assert r.status_code == 404 or r.status_code == 409


async def test_rare_fish_ask_a_question_and_never_hurt(client, frozen, force_fish):
    h, uid = await player(client, learn=["水", "火", "木", "人", "大"])
    hp_before = None
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        hp_before = (await db.get(Character, uid)).hp
    base = fishing.reel_params("linh", 0.0, fishing.rod_stats("can_truc_tho", 0), 1.0, 1)["zone"]
    for right in (True, False):
        force_fish["fish"] = "ca_vang"
        c, hk = await cast_and_hook(client, h, frozen)
        assert hk["stage"] == "quiz" and hk["need"] == 1 and hk["question"]["context"] == "fishing"
        q = hk["question"]
        key = await answer_key(q["session_id"])
        ans = correct_answer(q["qtype"], key) if right else wrong_answer(q["qtype"], key)
        res = (await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": ans}, headers=h)).json()
        assert res["correct"] is right
        f = res["fishing"]
        assert f["stage"] == "reel"
        assert f["params"]["zone"] == pytest.approx(base * (1.3 if right else 0.65), abs=1e-3)
        if right:
            assert res["xp"]["gained"] > 0
        out, _ = await reel_honestly(client, h, frozen, c["cast_id"], f["params"])
        assert out["result"] in ("caught", "escaped", "snapped")
    async with dbm.SessionLocal() as db:
        assert (await db.get(Character, uid)).hp == hp_before   # spec 11.1: no health lost


async def test_thien_fish_needs_two_right_answers_in_a_row(client, frozen, force_fish):
    h, uid = await player(client, learn=["水", "火", "木", "人", "大", "小"])
    force_fish["fish"] = "con"
    c, hk = await cast_and_hook(client, h, frozen)
    assert hk["stage"] == "quiz" and hk["need"] == 2
    q = hk["question"]
    key = await answer_key(q["session_id"])
    res = (await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": correct_answer(q["qtype"], key)},
                             headers=h)).json()
    assert res["fishing"]["stage"] == "quiz" and res["fishing"]["right"] == 1
    q2 = res["fishing"]["next_question"]
    key = await answer_key(q2["session_id"])
    res = (await client.post("/quiz/answer", json={"session_id": q2["session_id"], "answer": wrong_answer(q2["qtype"], key)},
                             headers=h)).json()
    assert res["fishing"]["stage"] == "reel" and res["fishing"]["quiz_mult"] == 0.65
    # the first question cannot be answered twice to get a second chance
    assert (await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": {"option": "a"}},
                              headers=h)).status_code == 409


async def test_no_words_learned_means_no_question(client, frozen, force_fish):
    h, _ = await player(client)
    force_fish["fish"] = "ca_koi"
    _, hk = await cast_and_hook(client, h, frozen)
    assert hk["stage"] == "reel" and hk["quiz_mult"] == 1.0


# ------------------------------------------------------------------ where you can fish
async def test_world_fishing_needs_the_water(client, frozen, force_fish):
    h, uid = await player(client)
    m, (x, y) = dock_tip()
    r = await client.post("/fishing/cast", json={"spot": "world"}, headers=h)
    assert r.json()["error"]["code"] == "not_here"
    sx, sy = m.spawns["spawn"]
    with InWorld(uid, "ho_nghien_muc", sx, sy):
        assert (await client.post("/fishing/cast", json={"spot": "world"}, headers=h)).json()["error"]["code"] == "not_here"
    with InWorld(uid, "ho_nghien_muc", x, y):
        # standing in the world, the abode pond is out of reach
        assert (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).json()["error"]["code"] == "not_here"
        c, hk = await cast_and_hook(client, h, frozen, spot="world")
        assert c["zone"] == "ho_nghien_muc" and c["pool"] == "ho" and hk["stage"] == "reel"
    # the village pond is a small pond too
    v = __import__("app.realtime.maps", fromlist=["load"]).load("truc_lam_thon")
    pond = v.fishing[0]
    with InWorld(uid, "truc_lam_thon", pond.x + pond.w / 2, pond.y + pond.h + 10):
        c = (await client.post("/fishing/cast", json={"spot": "world"}, headers=h)).json()
        assert c["pool"] == "ao"


async def test_baits_are_used_up_and_moi_muc_waits_for_night(client, frozen, force_fish, monkeypatch):
    h, uid = await player(client)
    await give(uid, "giun_dat", 2)
    await client.post("/fishing/equip", json={"bait": "giun_dat"}, headers=h)
    for left in (1, 0):
        c = (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).json()
        assert c["bait"] == "giun_dat" and c["bait_left"] == left
        assert await qty(uid, "giun_dat") == left
    r = await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)
    assert r.json()["error"]["code"] == "no_bait"
    await client.post("/fishing/equip", json={"no_bait": True}, headers=h)
    assert (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).status_code == 200
    await give(uid, "moi_muc", 1)
    await client.post("/fishing/equip", json={"bait": "moi_muc"}, headers=h)
    monkeypatch.setattr(fishing, "is_night", lambda now: False)
    r = await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)
    assert r.json()["error"]["code"] == "bait_needs_night" and await qty(uid, "moi_muc") == 1
    monkeypatch.setattr(fishing, "is_night", lambda now: True)
    assert (await client.post("/fishing/cast", json={"spot": "abode"}, headers=h)).status_code == 200


# ------------------------------------------------------------------ Ngư Ông, Lò Rèn
async def test_shop_bait_crafting_and_rods(client, frozen):
    h, uid = await player(client)
    from app.realtime import maps
    lake = maps.load("ho_nghien_muc")
    fx, fy = lake.npcs["fisher"]
    r = await client.post("/fishing/buy", json={"item_id": "giun_dat", "qty": 5}, headers=h)
    assert r.json()["error"]["code"] == "too_far"
    with InWorld(uid, "ho_nghien_muc", fx, fy + 12):
        r = (await client.post("/fishing/buy", json={"item_id": "giun_dat", "qty": 5}, headers=h)).json()
        assert r["bought"] == "giun_dat" and await qty(uid, "giun_dat") == 5
        await give(uid, "linh_mat", 2)
        r = (await client.post("/fishing/craft", json={"bait_id": "banh_mat", "times": 2}, headers=h)).json()
        assert r["made"] == 6 and await qty(uid, "banh_mat") == 6 and await qty(uid, "linh_mat") == 0
        # stage 9: Cần Thiên Tơ is made from secret-realm silk, and needs Trúc Cơ like Long Cốt
        assert (await client.post("/fishing/buy", json={"item_id": "can_thien_to"}, headers=h)).json()["error"]["code"]             == "realm_too_low"
        assert (await client.post("/fishing/buy", json={"item_id": "can_ngoc_bich"}, headers=h)).json()["error"]["code"] \
            == "realm_too_low"
        r = (await client.post("/fishing/buy", json={"item_id": "can_tre_gia"}, headers=h)).json()
        assert r["error"]["code"] == "not_enough"   # 300 - 20 for the worms < 400
        from app import db as dbm
        async with dbm.SessionLocal() as db:
            (await db.get(User, uid)).spirit_stones = 2000
            await db.commit()
        r = (await client.post("/fishing/buy", json={"item_id": "can_tre_gia"}, headers=h)).json()
        assert r["bought"] == "can_tre_gia"
        assert (await client.post("/fishing/buy", json={"item_id": "can_tre_gia"}, headers=h)).json()["error"]["code"] == "owned"
    v = (await client.post("/fishing/equip", json={"rod": "can_tre_gia"}, headers=h)).json()
    assert v["rod"] == "can_tre_gia"
    assert (await client.post("/fishing/equip", json={"rod": "can_long_cot"}, headers=h)).json()["error"]["code"] == "no_rod"
    # upgrades happen at the Lò Rèn
    assert (await client.post("/fishing/upgrade", json={"rod_id": "can_tre_gia"}, headers=h)).json()["error"]["code"] == "too_far"
    village = maps.load("truc_lam_thon")
    sx, sy = village.npcs["smith"]
    with InWorld(uid, "truc_lam_thon", sx, sy + 12):
        assert (await client.post("/fishing/upgrade", json={"rod_id": "can_tre_gia"}, headers=h)).json()["error"]["code"] \
            == "not_enough"
        await give(uid, "vay_linh_ngu", 2)
        r = (await client.post("/fishing/upgrade", json={"rod_id": "can_tre_gia"}, headers=h)).json()
        assert r["level"] == 1 and await qty(uid, "vay_linh_ngu") == 0
    rod = next(x for x in r["rods"] if x["id"] == "can_tre_gia")
    assert rod["stats"]["pull"] > catalog.rods()["can_tre_gia"]["pull"]


# ------------------------------------------------------------------ rewards, records, quests
async def test_scales_small_fish_records_and_milestones(client, frozen, force_fish, monkeypatch):
    h, uid = await player(client, "ngu_a")
    h2, uid2 = await player(client, "ngu_b")
    # a Linh fish brings a Vảy Linh Ngư
    force_fish["fish"] = "ca_koi"
    c, hk = await cast_and_hook(client, h, frozen)
    out, _ = await reel_honestly(client, h, frozen, c["cast_id"], hk["params"])
    if out["result"] == "caught":
        assert await qty(uid, "vay_linh_ngu") == 1 and await qty(uid, "fish_ca_koi") == 1
    # a tiny Phàm fish becomes a Cá Nhỏ (bee food)
    monkeypatch.setattr(fishing, "roll_size", lambda fid, rng: (11.0, 0.05))
    force_fish["fish"] = "ca_diec"
    c, hk = await cast_and_hook(client, h, frozen)
    out, _ = await reel_honestly(client, h, frozen, c["cast_id"], hk["params"])
    assert out["result"] == "caught" and out["small"] and await qty(uid, "ca_nho") == 1
    # records: the biggest of each species on the server
    for hh, size in ((h, 20.0), (h2, 25.5)):
        monkeypatch.setattr(fishing, "roll_size", lambda fid, rng, s=size: (s, 0.6))
        c, hk = await cast_and_hook(client, hh, frozen)
        out, _ = await reel_honestly(client, hh, frozen, c["cast_id"], hk["params"])
        assert out["result"] == "caught"
    assert out["server_record"]
    rec = (await client.get("/fishing/records", headers=h)).json()["records"]
    diec = next(r for r in rec if r["id"] == "ca_diec")
    assert [t["size_cm"] for t in diec["top"]] == [25.5, 20.0] and diec["top"][1]["me"]
    # Ngư Phổ milestone at 5 species
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        stones = (await db.get(User, uid)).spirit_stones
    monkeypatch.setattr(fishing, "roll_size", lambda fid, rng: (30.0, 0.5))
    got = []
    for fid in ("ca_chep", "ca_ro_phi", "ca_the_be", "ca_tram_co"):
        force_fish["fish"] = fid
        c, hk = await cast_and_hook(client, h, frozen)
        out, _ = await reel_honestly(client, h, frozen, c["cast_id"], hk["params"])
        assert out["result"] == "caught"
        got += out["milestones"]
    found = (await client.get("/codex/fish", headers=h)).json()
    assert found["found"] >= 5 and got == [{"species": 5, "spirit_stones": 200}]
    async with dbm.SessionLocal() as db:
        assert (await db.get(User, uid)).spirit_stones == stones + 200


async def test_quest_chain_counts_fish(client, frozen, force_fish):
    h, uid = await player(client)
    qs = (await client.get("/quests", headers=h)).json()["quests"]
    assert any(q["id"] == "no1_ben_ho" for q in qs)
    force_fish["fish"] = "ca_diec"
    from app import db as dbm
    from app.models import Quest
    async with dbm.SessionLocal() as db:   # pretend the first step is done and claimed
        (await db.get(Quest, (uid, "no1_ben_ho"))).state = "claimed"
        db.add(Quest(user_id=uid, quest_id="no2_ba_con_ca", state="active", progress={"n": 0}))
        await db.commit()
    for _ in range(3):
        c, hk = await cast_and_hook(client, h, frozen)
        out, _ = await reel_honestly(client, h, frozen, c["cast_id"], hk["params"])
        assert out["result"] == "caught"
    async with dbm.SessionLocal() as db:
        assert (await db.get(Quest, (uid, "no2_ba_con_ca"))).state == "done"
    async with dbm.SessionLocal() as db:
        assert (await db.execute(select(FishCatch).where(FishCatch.user_id == uid))).scalar_one().count == 3
