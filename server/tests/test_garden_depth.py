"""Stage 2 garden depth: adjacency reactions, fire, tone mishaps, sentence crafting,
plot expansion, character creation, name filter."""
import datetime as dt

import pytest
from sqlalchemy import select

from app import clock
from app.learning.wordbank import bank
from app.models import Collection, Fruit, Plot, QuizSession, Seed, User
from app.moderation import contains_banned
from tests.helpers import answer_key, register

B = bank()


async def put(db, user_id, x, y, hanzi, stage=1):
    """Place a word directly on plot (x, y) at a stage (test setup shortcut)."""
    w = B.by_hanzi[hanzi]
    p = (await db.execute(select(Plot).where(Plot.user_id == user_id, Plot.x == x, Plot.y == y))).scalar_one()
    p.word_id, p.stage, p.wither = w.id, stage, 0.0
    p.next_review_at = clock.now() + dt.timedelta(days=30) if stage else None
    p.wither_checked_at = clock.now()
    p.fire_checked_date = clock.local_date(clock.now())
    if not (await db.execute(select(Collection).where(Collection.user_id == user_id,
                                                     Collection.word_id == w.id))).scalar_one_or_none():
        db.add(Collection(user_id=user_id, word_id=w.id, introduced=True, first_seen_at=clock.now()))
    await db.commit()
    return p


async def setup_user(client, db, name="vuon"):
    h, _ = await register(client, name)
    await client.get("/garden", headers=h)  # creates plots
    uid = (await db.execute(select(User.id).where(User.username == name))).scalar_one()
    return h, uid


async def test_hao_discovery_once_with_reward(client, db):
    h, uid = await setup_user(client, db)
    await put(db, uid, 0, 0, "女")
    await put(db, uid, 1, 0, "子", stage=0)
    g = (await client.get("/garden", headers=h)).json()
    assert g["discoveries"] == []  # stage 0 plants do not react yet
    await put(db, uid, 1, 0, "子", stage=1)
    g = (await client.get("/garden", headers=h)).json()
    assert [d["result"] for d in g["discoveries"]] == ["好"]
    d = g["discoveries"][0]
    assert d["reward"]["spirit_stones"] == 50 and d["seed_id"] and d["etymology_verified"]
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == 350
    g = (await client.get("/garden", headers=h)).json()
    assert g["discoveries"] == []  # never twice
    seeds = (await client.get("/seeds", headers=h)).json()["seeds"]
    assert any(s["hanzi"] == "好" and s["source"] == "combo" for s in seeds)
    book = (await client.get("/discoveries", headers=h)).json()
    assert book["total"] == 6 and [f["result"] for f in book["found"]] == ["好"]


async def test_diagonal_does_not_count(client, db):
    h, uid = await setup_user(client, db)
    await put(db, uid, 0, 0, "日")
    await put(db, uid, 1, 1, "月")
    assert (await client.get("/garden", headers=h)).json()["discoveries"] == []
    await put(db, uid, 1, 0, "月")  # 月 moves next to 日 (and leaves the diagonal)
    p = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.x == 1, Plot.y == 1))).scalar_one()
    p.word_id = None
    await db.commit()
    assert [d["result"] for d in (await client.get("/garden", headers=h)).json()["discoveries"]] == ["明"]


async def test_three_wood_l_shape_and_pairs(client, db):
    h, uid = await setup_user(client, db)
    # a player gets extra 木 plants from duplicate seeds
    for (x, y) in [(0, 0), (0, 1), (1, 1)]:
        w = B.by_hanzi["木"]
        p = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.x == x, Plot.y == y))).scalar_one()
        p.word_id, p.stage, p.next_review_at = w.id, 2, clock.now() + dt.timedelta(days=9)
    await db.commit()
    found = {d["result"] for d in (await client.get("/garden", headers=h)).json()["discoveries"]}
    assert found == {"林", "森"}
    g = (await client.get("/garden", headers=h)).json()
    assert "small_forest" in g["decorations"]


async def test_water_aura_shortens_wait(client, db, frozen):
    h, uid = await setup_user(client, db)
    await put(db, uid, 0, 0, "水", stage=2)
    seed = Seed(user_id=uid, word_id=B.by_hanzi["火"].id, duplicate=False, source="test", obtained_at=clock.now())
    db.add(seed)
    await db.commit()
    p = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.x == 1, Plot.y == 0))).scalar_one()
    await client.post("/garden/plant", json={"plot_id": p.id, "seed_id": seed.id}, headers=h)
    r = (await client.post("/garden/learn", json={"plot_id": p.id}, headers=h)).json()
    assert r["seconds_until_due"] == 8 * 60  # 10 minutes x 0.8
    g = (await client.get("/garden", headers=h)).json()
    assert next(x for x in g["plots"] if x["id"] == p.id)["auras"] == ["water"]
    water = next(x for x in g["plots"] if x["x"] == 0 and x["y"] == 0)
    assert water["auras"] == ["fire"]


async def test_fire_scorches_wood_deterministically(client, db, frozen):
    h, uid = await setup_user(client, db)
    await put(db, uid, 0, 0, "火", stage=2)
    wood = await put(db, uid, 1, 0, "木", stage=2)
    events = []
    for _ in range(25):  # tokens last 30 days
        frozen.advance(days=1)
        g = (await client.get("/garden", headers=h)).json()
        again = (await client.get("/garden", headers=h)).json()
        assert again["fire_events"] == []  # reloading the same day never re-rolls
        events += g["fire_events"]
        p = await db.get(Plot, wood.id)
        await db.refresh(p)
        p.wither, p.next_review_at = 0.0, clock.now() + dt.timedelta(days=30)  # keep it alive
        await db.commit()
    assert 1 <= len(events) <= 12  # 20% a day over 25 days (seeded, so stable)


async def test_tone_mishap_loses_a_few_stones(client, db, frozen):
    h, uid = await setup_user(client, db)
    await put(db, uid, 0, 0, "买", stage=2)
    p = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.x == 0, Plot.y == 0))).scalar_one()
    p.next_review_at = clock.now()
    await db.commit()
    for _ in range(30):  # find a question where 卖's tone (mài) is offered
        q = (await client.post("/garden/review", json={"plot_id": p.id}, headers=h)).json()
        key = await answer_key(q["session_id"])
        mai4 = [oid for oid, num in key["option_numeric"].items() if num == "mai4"]
        if mai4:
            break
        s = await db.get(QuizSession, q["session_id"])
        await db.refresh(s)
        s.expires_at = clock.now() - dt.timedelta(seconds=1)
        await db.commit()
    assert mai4, "the funny wrong reading should be preferred as a distractor"
    r = (await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": {"option": mai4[0]}},
                           headers=h)).json()
    assert r["correct"] is False
    assert r["mishap"]["id"] == "sell_hoe" and r["mishap"]["stones_lost"] == 10
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == 290


async def test_mishap_never_negative(client, db):
    h, uid = await setup_user(client, db)
    user = await db.get(User, uid)
    user.spirit_stones = 3
    await db.commit()
    s = QuizSession(id="m1", user_id=uid, context="practice", qtype="Q3", word_id=B.by_hanzi["买"].id,
                    payload={}, answer_key={"option": "a", "option_numeric": {"a": "mai3", "b": "mai4"}},
                    created_at=clock.now(), expires_at=clock.now() + dt.timedelta(seconds=30))
    db.add(s)
    await db.commit()
    r = (await client.post("/quiz/answer", json={"session_id": "m1", "answer": {"option": "b"}}, headers=h)).json()
    assert r["mishap"]["stones_lost"] == 3
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == 0


async def test_sentence_crafting(client, db):
    h, uid = await setup_user(client, db)
    s = B.sentences["s001"]  # 我 喜欢 吃 苹果 。
    for wid in s.word_ids:
        db.add(Fruit(user_id=uid, word_id=wid, count=1))
    await db.commit()
    lst = (await client.get("/sentences", headers=h)).json()["sentences"]
    entry = next(x for x in lst if x["sentence_id"] == "s001")
    assert entry["ready"] and entry["slots"] == 4 and entry["end_punct"] == "。"
    assert "tokens" not in entry and "text" not in entry  # the puzzle is not spoiled
    wrong = [s.word_ids[1], s.word_ids[0]] + s.word_ids[2:]
    r = (await client.post("/sentences/craft", json={"sentence_id": "s001", "word_ids": wrong}, headers=h)).json()
    assert r["correct"] is False and r["first_wrong_slot"] == 0 and r["right_words_wrong_order"]
    fruits = (await client.get("/fruits", headers=h)).json()["fruits"]
    assert sum(f["count"] for f in fruits) == 4  # nothing used on a wrong try
    r = (await client.post("/sentences/craft", json={"sentence_id": "s001", "word_ids": s.word_ids},
                           headers=h)).json()
    assert r["correct"] and r["text"] == "我喜欢吃苹果。"
    assert r["reward"] == entry["reward"] and r["spirit_stones"] == 300 + entry["reward"]
    assert (await client.get("/fruits", headers=h)).json()["fruits"] == []
    r = await client.post("/sentences/craft", json={"sentence_id": "s001", "word_ids": s.word_ids}, headers=h)
    assert r.json()["error"]["code"] == "not_enough_fruit"


async def test_expand_garden(client, db):
    h, uid = await setup_user(client, db)
    g = (await client.get("/garden", headers=h)).json()
    far = next(p for p in g["plots"] if (p["x"], p["y"]) == (4, 4))
    near = next(p for p in g["plots"] if (p["x"], p["y"]) == (3, 0))
    assert not far["can_unlock"] and near["can_unlock"] and near["unlock_cost"] == 150
    r = await client.post("/garden/expand", json={"plot_id": far["id"]}, headers=h)
    assert r.json()["error"]["code"] == "not_adjacent"
    r = (await client.post("/garden/expand", json={"plot_id": near["id"]}, headers=h)).json()
    assert r["cost"] == 150 and r["spirit_stones"] == 150
    nxt = next(p for p in (await client.get("/garden", headers=h)).json()["plots"] if (p["x"], p["y"]) == (3, 1))
    assert nxt["unlock_cost"] == 200
    r = await client.post("/garden/expand", json={"plot_id": nxt["id"]}, headers=h)
    assert r.json()["error"]["code"] == "insufficient_funds"


async def test_character_create(client, db):
    h, _ = await register(client, "taonv")
    assert (await client.get("/me", headers=h)).json()["has_character"] is False
    opts = (await client.get("/character/options")).json()
    good = {"hair_color": opts["hair_colors"][1], "hair_style": "dai", "body": "nu"}
    for name, code in [("a", "bad_name"), ("Tên  có__gạch", "bad_name"), ("địt mẹ", "banned_name")]:
        r = await client.post("/character/create", json={"display_name": name, "appearance": good}, headers=h)
        assert r.json()["error"]["code"] == code, name
    r = await client.post("/character/create", json={"display_name": "Tiểu Phong", "appearance": {"hair_color": "#FFFFFF"}},
                          headers=h)
    assert r.json()["error"]["code"] == "bad_appearance"
    r = (await client.post("/character/create", json={"display_name": "Tiểu Phong", "appearance": good}, headers=h)).json()
    assert r["realm"] == "pham_nhan" and r["outfit"] == "ao_vai_pham_nhan" and r["zone_id"] == "abode"
    assert (await client.post("/character/create", json={"display_name": "Khác", "appearance": good},
                              headers=h)).status_code == 409
    h2, _ = await register(client, "taonv2")
    r = await client.post("/character/create", json={"display_name": "tiểu phong", "appearance": good}, headers=h2)
    assert r.json()["error"]["code"] == "name_taken"
    r = await client.post("/character/position", json={"x": 100, "y": 120, "facing": "left"}, headers=h)
    assert r.status_code == 200
    ch = (await client.get("/character", headers=h)).json()
    assert (ch["x"], ch["y"], ch["facing"]) == (100, 120, "left")
    me = (await client.get("/me", headers=h)).json()
    assert me["has_character"]


async def test_tutorial_step_only_moves_forward(client):
    h, _ = await register(client, "hocviec")
    assert (await client.post("/tutorial", json={"step": 3}, headers=h)).json()["tutorial_step"] == 3
    assert (await client.post("/tutorial", json={"step": 1}, headers=h)).json()["tutorial_step"] == 3
    assert (await client.get("/me", headers=h)).json()["tutorial_step"] == 3


@pytest.mark.parametrize("name,bad", [("Trúc Lão", False), ("Lớn Lên", False), ("lồn", True), ("dmmm", True),
                                       ("Vcl", True), ("Đệ tử", False), ("dit me", True), ("Phong 2008", False)])
def test_name_filter(name, bad):
    assert contains_banned(name) is bad


async def test_cutting_lets_a_word_grow_twice(client, db):
    h, uid = await setup_user(client, db)
    mu = B.by_hanzi["木"].id
    r = await client.post("/garden/cutting", json={"word_id": mu}, headers=h)
    assert r.json()["error"]["code"] == "not_learned"
    await put(db, uid, 0, 0, "木", stage=1)
    r = (await client.post("/garden/cutting", json={"word_id": mu}, headers=h)).json()
    assert r["cost"] == 60 and r["spirit_stones"] == 240
    p = (await db.execute(select(Plot).where(Plot.user_id == uid, Plot.x == 1, Plot.y == 0))).scalar_one()
    r = await client.post("/garden/plant", json={"plot_id": p.id, "seed_id": r["seed_id"]}, headers=h)
    assert r.status_code == 200
    r = (await client.post("/garden/learn", json={"plot_id": p.id}, headers=h)).json()
    assert [d["result"] for d in r["discoveries"]] == ["林"]  # popup comes with the action
    g = (await client.get("/discoveries", headers=h)).json()
    assert [f["result"] for f in g["found"]] == ["林"]
