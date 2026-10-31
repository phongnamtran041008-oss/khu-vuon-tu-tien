"""Stage 7: Tàng Thư Các (spec 9.3, 8.3): every book counted with its % and milestones, the
Bách Thảo Phổ (silhouettes and empty frames for what is not found yet), search by hanzi,
pinyin with or without tones, or Vietnamese meaning, the Sổ Lỗi."""
from sqlalchemy import select

from app import clock
from app.learning.wordbank import bank
from app.models import CodexEntry, Collection, FishCatch, Hive, User
from app.systems import library
from tests.helpers import register

LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}


async def player(client, name="thu_thu", learn: dict[str, int] | None = None):
    h, data = await register(client, name)
    r = await client.post("/character/create", json={"display_name": name.replace("_", " ").title(), "appearance": LOOK},
                          headers=h)
    assert r.status_code == 200, r.text
    uid = data["user_id"]
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        for col in (await db.execute(select(Collection).where(Collection.user_id == uid))).scalars():
            await db.delete(col)
        await db.flush()
        for hz, m in (learn or {}).items():
            db.add(Collection(user_id=uid, word_id=bank().by_hanzi[hz].id, introduced=True, mastery=m,
                              first_seen_at=clock.now()))
        await db.commit()
    return h, uid


def book(view: dict, bid: str) -> dict:
    return next(b for b in view["books"] if b["id"] == bid)


async def test_overview_counts_every_book(client):
    h, uid = await player(client, learn={"水": 30, "火": 80, "明": 10})
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        db.add(FishCatch(user_id=uid, fish_id="ca_diec", count=2, best_size_cm=12.0, first_caught_at=clock.now()))
        db.add(CodexEntry(user_id=uid, codex="monster", entry_id="ink_slime", discovered_at=clock.now(), progress={}))
        db.add(CodexEntry(user_id=uid, codex="monster", entry_id="td_muc_con", discovered_at=clock.now(), progress={}))
        await db.commit()
    v = (await client.get("/library", headers=h)).json()
    assert [b["id"] for b in v["books"]] == ["plant", "monster", "bee", "fish", "discovery", "treasure", "pet"]
    assert book(v, "plant")["found"] == 3 and book(v, "plant")["total"] == len(bank().words)
    assert book(v, "fish")["found"] == 1 and book(v, "monster")["found"] == 2
    for b in v["books"]:
        assert [m["pct"] for m in b["milestones"]] == [25, 50, 75, 100]
        assert all(not m["ready"] for m in b["milestones"])


async def test_milestones_are_claimed_once_when_reached(client):
    h, uid = await player(client)
    from app.garden import combos
    unlocks = [c for c in combos.combos() if c["kind"] == "unlock"]
    r = await client.post("/library/claim", json={"book": "discovery", "pct": 25}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_yet"
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        for c in unlocks[:(len(unlocks) + 1) // 2]:
            db.add(CodexEntry(user_id=uid, codex="discovery", entry_id=c["id"], discovered_at=clock.now(), progress={}))
        await db.commit()
    stones = (await client.get("/me", headers=h)).json()["spirit_stones"]
    r = await client.post("/library/claim", json={"book": "discovery", "pct": 25}, headers=h)
    assert r.status_code == 200, r.text
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == stones + 80
    r = await client.post("/library/claim", json={"book": "discovery", "pct": 25}, headers=h)
    assert r.status_code == 409
    assert (await client.post("/library/claim", json={"book": "discovery", "pct": 50}, headers=h)).status_code == 200
    v = (await client.get("/library", headers=h)).json()
    ms = {m["pct"]: m for m in book(v, "discovery")["milestones"]}
    assert ms[25]["claimed"] and ms[50]["claimed"] and not ms[75]["ready"]
    assert (await client.post("/library/claim", json={"book": "nope", "pct": 25}, headers=h)).status_code == 400


async def test_titles_and_hive_cells_from_milestones(client):
    h, uid = await player(client)
    from app import db as dbm
    from app.systems import catalog
    async with dbm.SessionLocal() as db:
        for bid in list(catalog.bees())[:9]:
            db.add(CodexEntry(user_id=uid, codex="bee", entry_id=bid, discovered_at=clock.now(), progress={}))
        await db.commit()
    await client.get("/hive", headers=h)
    async with dbm.SessionLocal() as db:
        cells = (await db.get(Hive, uid)).cells
    assert (await client.post("/library/claim", json={"book": "bee", "pct": 50}, headers=h)).status_code == 200
    async with dbm.SessionLocal() as db:
        assert (await db.get(Hive, uid)).cells == cells + 1
    async with dbm.SessionLocal() as db:
        for f in list(catalog.fish())[:15]:
            db.add(FishCatch(user_id=uid, fish_id=f, count=1, best_size_cm=10.0, first_caught_at=clock.now()))
        await db.commit()
    v = (await client.post("/library/claim", json={"book": "fish", "pct": 50}, headers=h)).json()
    assert "Lão Câu Thủ" in v["titles"]


async def test_herb_book_hides_what_is_not_found(client):
    h, uid = await player(client, learn={"火": 70, "林": 20, "一石二鸟": 10})
    hb = (await client.get("/codex/plant", headers=h)).json()
    assert hb["total"] == len(bank().words) and hb["found"] == 3
    by = {p["word_id"]: p for p in hb["plants"]}
    fire = by[bank().by_hanzi["火"].id]
    assert fire["found"] and fire["hanzi"] == "火" and fire["role"] == "hoa" and fire["mastery"] == 70
    assert fire["role_stats"]["dmg"] > 0 and fire["quip_vi"] and "power" in fire
    idiom = by[bank().by_hanzi["一石二鸟"].id]
    assert idiom["role"] == "thanh_ngu" and idiom["skill"]["type"] == "strike_strongest"
    water = by[bank().by_hanzi["水"].id]
    assert not water["found"] and "hanzi" not in water and "meaning_vi" not in water   # a silhouette
    ming = by[bank().by_hanzi["明"].id]
    assert not ming["found"] and ming["hidden"] and set(ming) == {"word_id", "found", "hidden", "tier"}  # empty frame
    assert by[bank().by_hanzi["林"].id]["found"]


async def test_search_by_hanzi_pinyin_and_meaning(client):
    h, uid = await player(client, learn={"妈妈": 50, "马": 40, "火": 10, "中国": 10})

    async def titles(q):
        r = (await client.get("/library/search", params={"q": q}, headers=h)).json()
        return {x["title"] for x in r["results"]}

    assert await titles("火") == {"火"}
    assert await titles("māma") == {"妈妈"}           # pinyin with tones
    assert await titles("mama") == {"妈妈"}           # without tones
    assert await titles("ma") >= {"妈妈", "马"}
    assert await titles("ma1ma5") == {"妈妈"}         # numbered
    assert await titles("zhongguo") == {"中国"}
    w = bank().by_hanzi["马"]
    assert await titles(w.meaning_vi) == {"马"}       # Vietnamese meaning
    folded = library.fold(w.meaning_vi)
    assert "马" in await titles(folded)               # ... even typed without accents
    assert await titles("水") == set()                # not found yet: searching never reveals it
    assert await titles("") == set()


async def test_search_finds_fish_and_monsters(client):
    h, uid = await player(client, learn={"火": 10})
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        db.add(FishCatch(user_id=uid, fish_id="ca_chep", count=1, best_size_cm=30.0, first_caught_at=clock.now()))
        db.add(CodexEntry(user_id=uid, codex="monster", entry_id="td_muc_dac", discovered_at=clock.now(), progress={}))
        await db.commit()
    r = (await client.get("/library/search", params={"q": "chep"}, headers=h)).json()
    assert any(x["book"] == "fish" and x["id"] == "ca_chep" for x in r["results"])
    r = (await client.get("/library/search", params={"q": "lǐyú"}, headers=h)).json()
    assert any(x["id"] == "ca_chep" for x in r["results"])
    r = (await client.get("/library/search", params={"q": "muc dac"}, headers=h)).json()
    assert any(x["id"] == "td_muc_dac" for x in r["results"])


async def test_mistakes_book_lists_the_words_missed_most(client):
    h, uid = await player(client, learn={"火": 50, "水": 50, "山": 50})
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        for hz, right, wrong in (("火", 5, 1), ("水", 1, 6), ("山", 3, 0)):
            c = await db.get(Collection, (uid, bank().by_hanzi[hz].id))
            c.times_correct, c.times_wrong = right, wrong
        await db.commit()
    words = (await client.get("/library/mistakes", headers=h)).json()["words"]
    assert [w["hanzi"] for w in words] == ["水", "火"]
    assert words[0]["accuracy"] == round(1 / 7, 2)
    r = await client.post("/quiz/practice", json={"word_id": words[0]["word_id"]}, headers=h)
    assert r.status_code == 200 and r.json()["context"] == "practice"


async def test_treasure_book_lists_everything_ever_owned(client):
    h, uid = await player(client)
    tb = (await client.get("/codex/treasure", headers=h)).json()
    start = tb["found"]
    pill = next(e for e in tb["entries"] if e["id"] == "hoi_huyet_dan")
    assert tb["total"] == len(library.treasure_catalog()) and not pill["found"] and "name_vi" not in pill
    from app import db as dbm
    from app.systems import inventory
    async with dbm.SessionLocal() as db:
        await inventory.change_item(db, uid, "hoi_huyet_dan", 2, "test")
        await inventory.change_item(db, uid, "hoi_huyet_dan", -2, "test")     # used up: still in the book
        await db.commit()
    tb = (await client.get("/codex/treasure", headers=h)).json()
    pill = next(e for e in tb["entries"] if e["id"] == "hoi_huyet_dan")
    assert tb["found"] == start + 1 and pill["found"] and pill["name_vi"] == "Hồi Huyết Đan" and pill["first_at"]
    v = (await client.get("/library", headers=h)).json()
    assert book(v, "treasure")["found"] == start + 1
    r = (await client.get("/library/search", params={"q": "hoi huyet"}, headers=h)).json()
    assert any(x["book"] == "treasure" and x["id"] == "hoi_huyet_dan" for x in r["results"])


async def test_wear_a_title_and_a_frame(client):
    h, uid = await player(client)
    r = await client.post("/library/wear", json={"title": "Bách Thảo Tiên"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_title"     # not earned yet
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        u = await db.get(User, uid)
        u.flags = {**(u.flags or {}), "titles": ["Kẻ Săn Mực"], "frames": ["khung_muc"]}
        await db.commit()
    v = (await client.post("/library/wear", json={"title": "Kẻ Săn Mực", "frame": "khung_muc"}, headers=h)).json()
    assert v["title"] == "Kẻ Săn Mực" and v["frame"] == "khung_muc"
    me = (await client.get("/me", headers=h)).json()
    assert me["title"] == "Kẻ Săn Mực" and me["frame"] == "khung_muc"
    v = (await client.post("/library/wear", json={"title": ""}, headers=h)).json()
    assert v["title"] is None and v["frame"] == "khung_muc"


async def test_buy_manuals_from_the_librarian(client, monkeypatch):
    h, uid = await player(client, learn={"火": 60})
    v = (await client.get("/library", headers=h)).json()
    manuals = {s["item_id"] for s in v["shop"] if s["kind"] == "manual"}
    assert manuals == {"bi_kip_moc", "bi_kip_thuy", "bi_kip_hoa", "bi_kip_son"}
    assert {s["kind"] for s in v["shop"]} == {"manual", "recipe"}          # stage 8: đan phương too
    assert not v["at_desk"]
    r = await client.post("/library/buy", json={"item_id": "bi_kip_hoa"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_far"      # must stand by the Thủ Thư
    monkeypatch.setattr(library, "at_desk", lambda uid: True)
    r = await client.post("/library/buy", json={"item_id": "bi_kip_hoa"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_enough"   # 300 Linh Thạch at the start
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        (await db.get(User, uid)).spirit_stones = 1000
        await db.commit()
    r = await client.post("/library/buy", json={"item_id": "bi_kip_hoa"}, headers=h)
    assert r.status_code == 200, r.text
    hoa = next(s for s in r.json()["shop"] if s["item_id"] == "bi_kip_hoa")
    assert hoa["have"] == 1 and not hoa["learned"]
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == 1000 - hoa["price"]
    assert (await client.post("/library/buy", json={"item_id": "hoi_huyet_dan"}, headers=h)).status_code == 400
    # the manual teaches the skill as usual (the word must be known >= 50%)
    r = await client.post("/inventory/use", json={"item_id": "bi_kip_hoa"}, headers=h)
    assert r.status_code == 200, r.text
    hoa = next(s for s in (await client.get("/library", headers=h)).json()["shop"] if s["item_id"] == "bi_kip_hoa")
    assert hoa["learned"] and hoa["have"] == 0


async def test_buy_a_recipe_once(client, monkeypatch):
    """Stage 8: đan phương on the Thủ Thư's shelf; one is enough forever."""
    h, uid = await player(client)
    monkeypatch.setattr(library, "at_desk", lambda uid: True)
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        (await db.get(User, uid)).spirit_stones = 1000
        await db.commit()
    r = await client.post("/library/buy", json={"item_id": "dp_hoi_khi"}, headers=h)
    assert r.status_code == 200, r.text
    dp = next(s for s in r.json()["shop"] if s["item_id"] == "dp_hoi_khi")
    assert dp["have"] == 1 and dp["learned"]
    r = await client.post("/library/buy", json={"item_id": "dp_hoi_khi"}, headers=h)
    assert r.json()["error"]["code"] == "already_have"
