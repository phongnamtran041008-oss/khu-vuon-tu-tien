"""Stage 5: Linh Phong (spec 10). Hive, eggs, honey, feeding, Ong Phổ, pollination and the
guard-slot rule. The checks asked for by the stage plan:
  * pollination never moves a plant to the next stage without an answer;
  * the review wait is never cut by more than 25 %;
  * the number of guard bees follows the realm.
Guard bees in combat are tested in test_bee_guard.py."""
import datetime as dt
import random

import pytest
from sqlalchemy import select

from app import clock
from app.learning import srs
from app.learning.wordbank import bank
from app.models import Bee, Character, CodexEntry, Collection, Fruit, Hive, InventoryItem, Plot, Quest, User
from app.systems import bees as beesys
from app.systems import catalog
from tests.helpers import answer_key, correct_answer, register, wrong_answer

B = bank()
LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}


async def player(client, db, name="ongchu", character=True):
    h, data = await register(client, name)
    if character:
        r = await client.post("/character/create", json={"display_name": name.replace("_", " ").title(), "appearance": LOOK},
                              headers=h)
        assert r.status_code == 200, r.text
    await client.get("/garden", headers=h)   # creates the plots
    return h, data["user_id"]


async def item_qty(db, uid, item_id) -> int:
    db.expire_all()
    rows = (await db.execute(select(InventoryItem).where(InventoryItem.user_id == uid,
                                                         InventoryItem.item_id == item_id))).scalars().all()
    return sum(r.quantity for r in rows)


async def give_bee(db, uid, kind="muc", role="hive", slot=None, level=1):
    hive = await db.get(Hive, uid)
    if slot is None:
        used = set((await db.execute(select(Bee.hive_slot).where(Bee.user_id == uid))).scalars().all())
        slot = next(i for i in beesys.open_cells(hive) if i not in used)
    b = Bee(user_id=uid, bee_type=kind, level=level, xp=0, hive_slot=slot, role=role, bond=0,
            obtained_at=clock.now())
    db.add(b)
    await db.commit()
    return Ref(b.id)


class Ref:
    """Just the id: ORM objects expire on every commit of the test session."""

    def __init__(self, id_: int):
        self.id = id_


async def put(db, uid, x, y, hanzi, stage=3, wait_days=None):
    w = B.by_hanzi[hanzi]
    p = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.x == x, Plot.y == y))).scalar_one()
    now = clock.now()
    p.word_id, p.stage, p.wither, p.pollen, p.pollinated, p.pollen_boost = w.id, stage, 0.0, 0.0, False, False
    wait = srs.wait_after_reaching(stage) if wait_days is None else dt.timedelta(days=wait_days)
    p.next_review_at = now + wait if (stage and wait is not None) else None
    p.wither_checked_at = now
    p.fire_checked_date = clock.local_date(now)
    if not (await db.execute(select(Collection).where(Collection.user_id == uid,
                                                     Collection.word_id == w.id))).scalar_one_or_none():
        db.add(Collection(user_id=uid, word_id=w.id, introduced=True, first_seen_at=now))
    pid, nra = p.id, p.next_review_at
    await db.commit()
    r = Ref(pid)
    r.next_review_at = nra
    return r


async def plot_of(client, h, pid):
    g = (await client.get("/garden", headers=h)).json()
    return next(p for p in g["plots"] if p["id"] == pid), g


async def answer_garden(client, h, pid, right=True):
    q = (await client.post("/garden/review", json={"plot_id": pid}, headers=h)).json()
    key = await answer_key(q["session_id"])
    a = correct_answer(q["qtype"], key) if right else wrong_answer(q["qtype"], key)
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": a}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ species data (spec 10.1, 5)
def test_species_data_is_verified():
    sp = catalog.bees()
    assert len(sp) >= 15
    assert {s["rarity"] for s in sp.values()} == {"pham", "linh", "huyen", "dia", "thien"}
    for kind, s in sp.items():
        w = B.get(s["word_id"])
        assert s["hanzi"] == w.hanzi + "蜂" and s["pinyin"] == w.pinyin + "fēng", kind
        assert not w.hidden, kind
        assert s["element"] in beesys.cfg()["element_names_vi"]
        fav = s["favorite"]
        assert fav in ("linh_mat", "linh_qua") or fav[6:] in B.by_hanzi
    assert sp["hoang_kim"]["real_word"] and "wasp" in sp["hoang_kim"]["real_meaning_en"]
    assert not sp["hoa_diem"]["real_word"]


def test_hex_grid():
    order = beesys.cell_order()
    assert sorted(order) == list(range(30))
    first = order[0]
    assert len(beesys.neighbours(first)) == 6           # the comb opens from its middle
    for i in range(30):
        for n in beesys.neighbours(i):
            assert i in beesys.neighbours(n)            # symmetric


# ------------------------------------------------------------------ hive, eggs, Ong Phổ
async def test_starter_egg_hatch_and_book(client, db):
    h, uid = await player(client, db)
    hv = (await client.get("/hive", headers=h)).json()
    assert hv["cells"] == 5 and len(hv["open_cells"]) == 5 and hv["bees"] == []
    assert [e["item_id"] for e in hv["eggs"]] == ["trung_ong_pham"]
    hv2 = (await client.get("/hive", headers=h)).json()
    assert hv2["eggs"][0]["qty"] == 1                   # given once only
    r = (await client.post("/hive/hatch", json={"item_id": "trung_ong_pham"}, headers=h)).json()
    bee = r["bee"]
    assert r["new_species"] and bee["rarity"] == "pham" and bee["slot"] in hv["open_cells"]
    assert bee["role"] == "hive" and bee["level"] == 1 and bee["favorite"] is None
    assert await item_qty(db, uid, "trung_ong_pham") == 0
    book = (await client.get("/codex/bee", headers=h)).json()
    assert book["found"] == 1 and book["total"] >= 15
    found = next(e for e in book["entries"] if e["found"])
    assert found["id"] == bee["species"] and found["hanzi"].endswith("蜂") and found["favorite"] is None
    hidden = next(e for e in book["entries"] if not e["found"])
    assert "name_vi" not in hidden and hidden["look"] is None
    q = await db.get(Quest, (uid, "lp1_trung_ong"))
    assert q.state == "done"
    r = await client.post("/hive/hatch", json={"item_id": "trung_ong_pham"}, headers=h)
    assert r.json()["error"]["code"] == "no_egg"


async def test_hive_full_and_cells(client, db):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    for _ in range(5):
        await give_bee(db, uid)
    r = await client.post("/hive/hatch", json={"item_id": "trung_ong_pham"}, headers=h)
    assert r.json()["error"]["code"] == "hive_full"
    r = (await client.post("/hive/unlock_cell", headers=h)).json()
    assert r["cells"] == 6
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == 300 - 150
    r = await client.post("/hive/hatch", json={"item_id": "trung_ong_pham"}, headers=h)
    assert r.status_code == 200
    hive = await db.get(Hive, uid)
    await db.refresh(hive)
    hive.cells = 10
    await db.commit()
    u = await db.get(User, uid)
    await db.refresh(u)
    u.spirit_stones = 5000
    await db.commit()
    r = (await client.post("/hive/unlock_cell", headers=h)).json()   # 11th cell needs 3 species
    assert r["error"]["code"] == "need_species"


async def test_move_and_swap(client, db):
    h, uid = await player(client, db)
    hv = (await client.get("/hive", headers=h)).json()
    cells = hv["open_cells"]
    a = await give_bee(db, uid, "muc", slot=cells[0])
    b = await give_bee(db, uid, "hoa", slot=cells[1])
    r = (await client.post("/bees/move", json={"bee_id": a.id, "slot": cells[1]}, headers=h)).json()
    slots = {x["id"]: x["slot"] for x in r["bees"]}
    assert slots[a.id] == cells[1] and slots[b.id] == cells[0]
    locked = next(i for i in range(30) if i not in cells)
    r = await client.post("/bees/move", json={"bee_id": a.id, "slot": locked}, headers=h)
    assert r.json()["error"]["code"] == "cell_locked"


async def test_resonance_same_element_neighbours(client, db):
    h, uid = await player(client, db)
    hv = (await client.get("/hive", headers=h)).json()
    cells = hv["open_cells"]
    centre = cells[0]
    nbs = [c for c in beesys.neighbours(centre) if c in cells]
    assert len(nbs) >= 2
    a = await give_bee(db, uid, "thao", slot=centre)        # Mộc
    await give_bee(db, uid, "hoa", slot=nbs[0])             # Mộc
    await give_bee(db, uid, "vu", slot=nbs[1])              # Thủy: no resonance
    hv = (await client.get("/hive", headers=h)).json()
    bee = next(x for x in hv["bees"] if x["id"] == a.id)
    assert bee["resonance_pct"] == 5


# ------------------------------------------------------------------ honey
async def test_honey_is_made_lazily_and_capped(client, db, frozen):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    b = await give_bee(db, uid, "tra", role="hive")
    hv = (await client.get("/hive", headers=h)).json()
    rate = next(x for x in hv["bees"] if x["id"] == b.id)["honey_per_hour"]
    assert rate == pytest.approx(1.6, abs=0.01) and hv["honey_per_hour"] == pytest.approx(rate)
    frozen.advance(hours=5)
    hv = (await client.get("/hive", headers=h)).json()
    assert hv["honey"] == pytest.approx(rate * 5, abs=0.02)
    assert hv["wax"] == pytest.approx(rate * 5 * 0.1, abs=0.01)
    r = (await client.post("/hive/collect", headers=h)).json()
    assert r["honey"] == 8 and await item_qty(db, uid, "linh_mat") == 8
    frozen.advance(days=10)
    hv = (await client.get("/hive", headers=h)).json()
    assert hv["honey"] == pytest.approx(hv["capacity"], abs=0.5)   # the comb is full, nothing more
    # pollinating bees make no honey
    await client.post("/hive/collect", headers=h)
    await client.post("/bees/role", json={"bee_id": b.id, "role": "pollinate"}, headers=h)
    frozen.advance(hours=5)
    hv = (await client.get("/hive", headers=h)).json()
    assert hv["honey"] < 1


async def test_sell_honey(client, db):
    h, uid = await player(client, db)
    from app.systems import inventory
    await inventory.change_item(db, uid, "linh_mat", 10, "test")
    await db.commit()
    r = (await client.post("/inventory/sell", json={"item_id": "linh_mat", "qty": 4}, headers=h)).json()
    assert r["earned"] == 8 and r["left"] == 6 and r["spirit_stones"] == 308
    r = await client.post("/inventory/sell", json={"item_id": "trung_ong_pham", "qty": 1}, headers=h)
    assert r.json()["error"]["code"] == "not_sellable"


# ------------------------------------------------------------------ feeding
async def test_feeding_levels_and_favourite(client, db):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    b = await give_bee(db, uid, "hoa_diem")     # likes fruit 火
    db.add(CodexEntry(user_id=uid, codex="bee", entry_id="hoa_diem", discovered_at=clock.now(),
                      progress={"hatched": 1, "favorite_known": False, "best_level": 1}))
    from app.systems import inventory
    await inventory.change_item(db, uid, "linh_mat", 5, "test")
    await inventory.change_fruit(db, uid, B.by_hanzi["火"].id, 3, "test")
    await inventory.change_fruit(db, uid, B.by_hanzi["水"].id, 1, "test")
    await db.commit()
    r = (await client.post("/bees/feed", json={"bee_id": b.id, "food": "linh_mat"}, headers=h)).json()
    assert r["xp_gained"] == 25 and not r["favorite"] and r["bond"] == 2
    r = (await client.post("/bees/feed", json={"bee_id": b.id, "food": f"fruit:{B.by_hanzi['水'].id}"},
                           headers=h)).json()
    assert r["xp_gained"] == 12 and not r["favorite"]
    r = (await client.post("/bees/feed", json={"bee_id": b.id, "food": f"fruit:{B.by_hanzi['火'].id}"},
                           headers=h)).json()
    assert r["favorite"] and r["favorite_discovered"] and r["xp_gained"] == 24 and r["bond"] == 12
    assert r["favorite_vi"] == "Quả chữ 火"
    assert r["level"] == 2   # 25 + 12 + 24 = 61 >= 50 (level 1 -> 2)
    book = (await client.get("/codex/bee", headers=h)).json()
    e = next(x for x in book["entries"] if x["id"] == "hoa_diem")
    assert e["favorite_known"] and e["favorite"] == "Quả chữ 火" and e["best_level"] == 2
    r = await client.post("/bees/feed", json={"bee_id": b.id, "food": f"fruit:{B.by_hanzi['水'].id}"}, headers=h)
    assert r.json()["error"]["code"] == "no_food"
    r = await client.post("/bees/feed", json={"bee_id": b.id, "food": "muc_tinh"}, headers=h)
    assert r.json()["error"]["code"] == "bad_food"


async def test_level_and_bond_make_bees_stronger(client, db):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    weak = await give_bee(db, uid, "muc", level=1)
    strong = await give_bee(db, uid, "muc", level=10)
    (await db.get(Bee, strong.id)).bond = 100
    await db.commit()
    hv = (await client.get("/hive", headers=h)).json()
    w = next(x for x in hv["bees"] if x["id"] == weak.id)
    s = next(x for x in hv["bees"] if x["id"] == strong.id)
    assert s["guard"]["atk"] > w["guard"]["atk"] and s["honey_per_hour"] > w["honey_per_hour"]


async def test_release_gives_wax(client, db):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    b = await give_bee(db, uid, "bang_tam")
    r = (await client.post("/bees/release", json={"bee_id": b.id}, headers=h)).json()
    assert r["wax"] == 4 and await item_qty(db, uid, "sap_ong") == 4
    assert await db.get(Bee, b.id) is None


async def test_upgrade_hive_needs_materials(client, db):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    r = await client.post("/hive/upgrade", headers=h)
    assert r.json()["error"]["code"] == "no_material"
    from app.systems import inventory
    await inventory.change_item(db, uid, "sap_ong", 5, "test")
    await inventory.change_item(db, uid, "go_linh_moc", 3, "test")
    await db.commit()
    r = (await client.post("/hive/upgrade", headers=h)).json()
    assert r["level"] == 2 and r["capacity"] == 80 and r["decorations"][0]["id"] == "den_long"
    assert await item_qty(db, uid, "sap_ong") == 0
    r = (await client.post("/hive/decoration", json={"decoration": "den_long", "on": False}, headers=h)).json()
    assert not r["decorations"][0]["on"]
    r = await client.post("/hive/decoration", json={"decoration": "hoa_sen", "on": True}, headers=h)
    assert r.json()["error"]["code"] == "decoration_locked"


# ------------------------------------------------------------------ gacha (spec 13)
async def test_bee_gacha_gives_eggs(client, db):
    h, uid = await player(client, db)
    r = (await client.post("/gacha/roll", json={"banner": "bees", "count": 1}, headers=h)).json()
    assert r["spirit_stones"] == 0 and r["results"][0]["item"].startswith("trung_ong_")
    assert await item_qty(db, uid, r["results"][0]["item"]) >= 1
    r = await client.post("/gacha/roll", json={"banner": "bees", "count": 1}, headers=h)
    assert r.json()["error"]["code"] == "insufficient_funds"
    u = await db.get(User, uid)
    await db.refresh(u)
    u.immortal_jade = 50
    await db.commit()
    r = (await client.post("/gacha/roll", json={"banner": "bees", "count": 10, "currency": "immortal_jade"},
                           headers=h)).json()
    assert r["immortal_jade"] == 5 and len(r["results"]) == 10
    assert any(x["rarity"] != "pham" for x in r["results"])     # ten-pull: at least one Linh
    r = await client.post("/gacha/roll", json={"banner": "bees", "free": True}, headers=h)
    assert r.json()["error"]["code"] == "no_free_roll"
    info = (await client.get("/gacha/banners", headers=h)).json()["banners"]
    bees = next(b for b in info if b["id"] == "bees")
    assert bees["enabled"] and bees["alt_price"] == {"immortal_jade": 5}


def test_bee_banner_rates_and_pity():
    from app.systems.gacha import Banner
    b = Banner.load("bees")
    rng = random.Random(7)
    counts = {r: 0 for r in b.rarities}
    state = {}
    for _ in range(20000):
        out, state = b.roll(1, state, rng, use_pity=False)
        counts[out[0]] += 1
    assert abs(counts["pham"] / 20000 - 0.60) < 0.015
    out, _ = b.roll(1, {"thien": 89, "huyen": 0}, rng)
    assert out == ["thien"]
    out, _ = b.roll(1, {"thien": 0, "huyen": 29}, rng)
    assert out[0] in ("huyen", "dia", "thien")


# ------------------------------------------------------------------ pollination (spec 10.2.2)
async def test_pollination_never_grows_a_plant_without_an_answer(client, db, frozen):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    for kind in ("hai_trieu", "hoa", "thuy_linh"):
        await give_bee(db, uid, kind, role="pollinate")
    p3 = await put(db, uid, 0, 0, "花", stage=3)
    p4 = await put(db, uid, 1, 0, "水", stage=4)
    p1 = await put(db, uid, 2, 0, "火", stage=2)
    for _ in range(12):
        frozen.advance(hours=6)
        await client.get("/garden", headers=h)
    a, _ = await plot_of(client, h, p3.id)
    b, _ = await plot_of(client, h, p4.id)
    c, _ = await plot_of(client, h, p1.id)
    assert a["pollinated"] and b["pollinated"]
    assert a["stage"] == 3 and b["stage"] == 4          # still the same stage after days of bees
    assert not c["pollinated"] and c["pollen"] == 0 and c["stage"] == 2   # below Ra hoa: bees ignore it
    r = await client.post("/garden/harvest", json={"plot_id": p4.id}, headers=h)
    assert r.json()["error"]["code"] == "not_ripe"
    # only a right answer moves it on
    res = await answer_garden(client, h, p3.id, right=False)
    assert res["plot"]["stage"] == 3
    frozen.advance(minutes=6)
    res = await answer_garden(client, h, p3.id, right=True)
    assert res["plot"]["stage"] == 4


async def test_pollination_cut_is_at_most_25_percent(client, db, frozen, monkeypatch):
    """The running wait shrinks by at most 25 % of the scheduled wait, whatever the bees, even
    if balance/bees.json asked for more."""
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    cfg = dict(beesys.cfg())
    cfg["pollination"] = {**cfg["pollination"], "review_wait_cut": 0.9}
    monkeypatch.setattr(beesys, "cfg", lambda: cfg)
    assert beesys.review_cut() == 0.25
    rng = random.Random(3)
    kinds = list(catalog.bees())
    for trial in range(6):
        for b in (await db.execute(select(Bee).where(Bee.user_id == uid))).scalars().all():
            await db.delete(b)
        await db.commit()
        for _ in range(rng.randint(1, 6)):
            await give_bee(db, uid, rng.choice(kinds), role="pollinate", level=rng.randint(1, 20))
        hanzi = rng.choice(["花", "水", "火", "山", "茶"])
        stage = rng.choice([3, 4])
        p = await put(db, uid, 0, 0, hanzi, stage=stage)
        hive = await db.get(Hive, uid)
        await db.refresh(hive)
        hive.pollen_checked_at = clock.now()
        await db.commit()
        start = clock.now()
        scheduled = p.next_review_at - start
        for _ in range(48):
            frozen.advance(hours=1)
            v, _g = await plot_of(client, h, p.id)
            if v["pollinated"]:
                break
        assert v["pollinated"], trial
        db.expire_all()
        q = await db.get(Plot, p.id)
        new_wait = q.next_review_at - start
        assert new_wait >= scheduled * 0.75 - dt.timedelta(seconds=1), (trial, new_wait, scheduled)
        assert new_wait <= scheduled
        assert q.stage == stage


async def test_pollinated_while_due_cuts_the_next_wait(client, db, frozen):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    await give_bee(db, uid, "hai_trieu", role="pollinate", level=20)
    p = await put(db, uid, 0, 0, "花", stage=3, wait_days=0)   # due right now
    for _ in range(10):
        frozen.advance(hours=1)
        v, _ = await plot_of(client, h, p.id)
        if v["pollinated"]:
            break
    assert v["pollinated"]
    db.expire_all()
    assert (await db.get(Plot, p.id)).pollen_boost
    res = await answer_garden(client, h, p.id, right=True)
    assert res["plot"]["stage"] == 4
    normal = srs.wait_after_reaching(4).total_seconds()
    left = res["plot"]["seconds_until_due"]
    assert normal * 0.75 - 2 <= left <= normal * 0.75 + 2
    db.expire_all()
    assert not (await db.get(Plot, p.id)).pollen_boost       # used once


async def test_water_bee_is_faster_next_to_water(client, db, frozen):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    await give_bee(db, uid, "thuy_linh", role="pollinate")
    wet = await put(db, uid, 0, 0, "花", stage=3)
    await put(db, uid, 1, 0, "水", stage=1)                  # a 水 neighbour (stage 1: not pollinated itself)
    dry = await put(db, uid, 0, 2, "茶", stage=3)            # Mộc, no water nearby
    frozen.advance(hours=2)
    a, _ = await plot_of(client, h, wet.id)
    b, _ = await plot_of(client, h, dry.id)
    assert a["pollen"] == pytest.approx(b["pollen"] * 1.5, rel=0.02) and a["pollen"] > 0


async def test_pollinated_harvest_gives_more(client, db, frozen):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    p = await put(db, uid, 0, 0, "花", stage=5)
    q = await db.get(Plot, p.id)
    q.pollinated, q.pollen = True, 100.0
    await db.commit()
    r = (await client.post("/garden/harvest", json={"plot_id": p.id}, headers=h)).json()
    assert r["fruits_gained"] == 5 and r["pollinated"]
    p2 = await put(db, uid, 1, 0, "水", stage=5)
    r = (await client.post("/garden/harvest", json={"plot_id": p2.id}, headers=h)).json()
    assert r["fruits_gained"] == 3 and not r["pollinated"] and r["spirit_fruit"] == 0


async def test_pollinate_quest_and_bee_xp(client, db, frozen):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    await client.get("/quests", headers=h)
    q = await db.get(Quest, (uid, "lp1_trung_ong"))
    q.state = "claimed"
    db.add(Quest(user_id=uid, quest_id="lp3_thu_phan", state="active", progress={"n": 0}))
    b = await give_bee(db, uid, "hai_trieu", role="pollinate")
    await db.commit()
    await put(db, uid, 0, 0, "花", stage=3)
    frozen.advance(hours=10)
    await client.get("/garden", headers=h)
    db.expire_all()
    assert (await db.get(Quest, (uid, "lp3_thu_phan"))).state == "done"
    assert (await db.get(Bee, b.id)).xp == beesys.cfg()["xp_pollinated_plant"]


# ------------------------------------------------------------------ guard slots (spec 7.3, 10.2.3)
@pytest.mark.parametrize("realm,slots", [("pham_nhan", 0), ("luyen_khi", 2), ("truc_co", 3), ("kim_dan", 4),
                                         ("nguyen_anh", 5)])
async def test_guard_slots_follow_realm(client, db, realm, slots):
    h, uid = await player(client, db, f"ho_ve_{realm[:4]}")
    await client.get("/hive", headers=h)
    hive = await db.get(Hive, uid)
    await db.refresh(hive)
    hive.cells = 10
    ch = await db.get(Character, uid)
    ch.realm, ch.realm_stage = realm, 0 if realm == "pham_nhan" else 1
    await db.commit()
    ids = [(await give_bee(db, uid, "muc")).id for _ in range(6)]
    ok = 0
    for bid in ids:
        r = await client.post("/bees/role", json={"bee_id": bid, "role": "guard"}, headers=h)
        if r.status_code == 200:
            ok += 1
        else:
            assert r.json()["error"]["code"] == ("no_guard_slot" if slots == 0 else "guard_full")
    assert ok == slots
    hv = (await client.get("/hive", headers=h)).json()
    assert hv["guard_slots"] == slots and hv["guard_used"] == slots
    assert len(await beesys.guard_loadout(db, uid)) == slots


def test_guard_slot_table_matches_spec():
    assert beesys.cfg()["guard"]["slots_by_realm"] == {"pham_nhan": 0, "luyen_khi": 2, "truc_co": 3,
                                                        "kim_dan": 4, "nguyen_anh": 5}


async def test_pollinator_cap(client, db):
    h, uid = await player(client, db)
    await client.get("/hive", headers=h)
    hive = await db.get(Hive, uid)
    await db.refresh(hive)
    hive.cells = 10
    await db.commit()
    ids = [(await give_bee(db, uid, "hoa")).id for _ in range(7)]
    codes = [(await client.post("/bees/role", json={"bee_id": i, "role": "pollinate"}, headers=h)).status_code
             for i in ids]
    assert codes.count(200) == 6 and codes[-1] == 400
