"""Stage 3: friends, blocks, reports, visiting a friend's abode and "tưới giúp" (spec 15.3)."""
import datetime as dt

from sqlalchemy import select

from app import clock
from app import db as dbm

from app.models import AuditLog, ChatReport, Collection, Plot, User
from tests.helpers import answer_key, correct_answer, register, wrong_answer
from tests.test_garden_depth import put

LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}


async def learn(db, uid, hanzi):
    """Mark a word as introduced for a player (the starter 水 is in the collection but unread)."""
    from app.learning.wordbank import bank
    w = bank().by_hanzi[hanzi]
    col = (await db.execute(select(Collection).where(Collection.user_id == uid,
                                                     Collection.word_id == w.id))).scalar_one_or_none()
    if col is None:
        db.add(Collection(user_id=uid, word_id=w.id, introduced=True, first_seen_at=clock.now()))
    else:
        col.introduced = True
    await db.commit()


async def player(client, db, username, display):
    h, _ = await register(client, username)
    r = await client.post("/character/create", json={"display_name": display, "appearance": LOOK}, headers=h)
    assert r.status_code == 200, r.text
    await client.get("/garden", headers=h)
    uid = (await db.execute(select(User.id).where(User.username == username))).scalar_one()
    return h, uid


async def befriend(client, ha, hb, name_b, uid_a):
    r = await client.post("/friends/request", json={"display_name": name_b}, headers=ha)
    assert r.json()["status"] == "pending"
    r = await client.post("/friends/accept", json={"user_id": uid_a}, headers=hb)
    assert r.json()["status"] == "accepted", r.text


async def test_friend_request_flow(client, db):
    ha, a = await player(client, db, "an_01", "An")
    hb, b = await player(client, db, "binh_01", "Bình")
    r = await client.post("/friends/request", json={"display_name": "bình"}, headers=ha)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    inc = (await client.get("/friends", headers=hb)).json()
    assert [p["display_name"] for p in inc["incoming"]] == ["An"] and inc["friends"] == []
    assert (await client.get("/friends", headers=ha)).json()["outgoing"][0]["user_id"] == b
    await client.post("/friends/accept", json={"user_id": a}, headers=hb)
    fa = (await client.get("/friends", headers=ha)).json()
    fb = (await client.get("/friends", headers=hb)).json()
    assert [f["display_name"] for f in fa["friends"]] == ["Bình"]
    assert [f["display_name"] for f in fb["friends"]] == ["An"]
    assert fa["friends"][0]["online"] is False and fb["incoming"] == []
    r = await client.post("/friends/request", json={"display_name": "Bình"}, headers=ha)
    assert r.status_code == 409
    await client.post("/friends/remove", json={"user_id": b}, headers=ha)
    assert (await client.get("/friends", headers=hb)).json()["friends"] == []


async def test_mutual_requests_become_friends(client, db):
    ha, a = await player(client, db, "an_02", "An Hai")
    hb, b = await player(client, db, "binh_02", "Bình Hai")
    await client.post("/friends/request", json={"display_name": "Bình Hai"}, headers=ha)
    r = await client.post("/friends/request", json={"display_name": "An Hai"}, headers=hb)
    assert r.json()["status"] == "accepted"


async def test_request_errors(client, db):
    ha, a = await player(client, db, "an_03", "An Ba")
    assert (await client.post("/friends/request", json={"display_name": "An Ba"}, headers=ha)).status_code == 400
    assert (await client.post("/friends/request", json={"display_name": "Không Có"}, headers=ha)).status_code == 404
    assert (await client.post("/friends/accept", json={"user_id": 999}, headers=ha)).status_code == 404


async def test_block_ends_friendship_and_stops_requests(client, db):
    ha, a = await player(client, db, "an_04", "An Bốn")
    hb, b = await player(client, db, "binh_04", "Bình Bốn")
    await befriend(client, ha, hb, "Bình Bốn", a)
    assert (await client.post("/blocks", json={"user_id": b}, headers=ha)).status_code == 200
    assert (await client.get("/friends", headers=hb)).json()["friends"] == []
    assert [x["display_name"] for x in (await client.get("/blocks", headers=ha)).json()["blocked"]] == ["Bình Bốn"]
    r = await client.post("/friends/request", json={"display_name": "An Bốn"}, headers=hb)
    assert r.status_code == 403
    await client.post("/blocks/remove", json={"user_id": b}, headers=ha)
    assert (await client.get("/blocks", headers=ha)).json()["blocked"] == []


async def test_report(client, db):
    ha, a = await player(client, db, "an_05", "An Năm")
    hb, b = await player(client, db, "binh_05", "Bình Năm")
    r = await client.post("/reports", json={"user_id": b, "message": "nói bậy", "reason": "chat"}, headers=ha)
    assert r.status_code == 200
    rows = (await db.execute(select(ChatReport))).scalars().all()
    assert [(x.reporter_id, x.reported_id, x.message) for x in rows] == [(a, b, "nói bậy")]


async def test_visit_requires_friendship_and_hides_unknown_words(client, db):
    ha, a = await player(client, db, "an_06", "An Sáu")
    hb, b = await player(client, db, "binh_06", "Bình Sáu")
    assert (await client.get(f"/friends/{b}/garden", headers=ha)).status_code == 403
    await befriend(client, ha, hb, "Bình Sáu", a)
    await put(db, b, 0, 0, "火", stage=2)
    await put(db, b, 1, 0, "水", stage=3)
    await learn(db, a, "水")  # An knows 水 but not 火
    v = (await client.get(f"/friends/{b}/garden", headers=ha)).json()
    assert v["owner"]["display_name"] == "Bình Sáu" and v["helps_left"] == 5
    by = {p["word"]["hanzi"]: p for p in v["plots"] if p["word"]}
    assert by["水"]["helpable"] and by["水"]["word"]["pinyin"] == "shuǐ"
    assert not by["火"]["helpable"] and by["火"]["word"]["pinyin"] is None
    assert "meaning_vi" not in str(by["火"]["word"].get("meaning_vi") or "")


async def test_visiting_changes_nothing(client, db, frozen):
    ha, a = await player(client, db, "an_07", "An Bảy")
    hb, b = await player(client, db, "binh_07", "Bình Bảy")
    await befriend(client, ha, hb, "Bình Bảy", a)
    p = await put(db, b, 0, 0, "水", stage=2)
    p.next_review_at = clock.now() - dt.timedelta(days=3)
    await db.commit()
    before = (p.stage, p.wither, p.wither_checked_at)
    frozen.advance(days=4)  # overdue: the view shows wither but must not store it
    v = (await client.get(f"/friends/{b}/garden", headers=ha)).json()
    assert v["plots"][0]["wither"] > 0 or v["plots"][0]["stage"] < 2
    pid = p.id
    async with dbm.SessionLocal() as fresh:
        p = (await fresh.execute(select(Plot).where(Plot.id == pid))).scalar_one()
        assert (p.stage, p.wither, p.wither_checked_at) == before


async def test_help_water_rewards_both_and_is_limited(client, db):
    ha, a = await player(client, db, "an_08", "An Tám")
    hb, b = await player(client, db, "binh_08", "Bình Tám")
    await befriend(client, ha, hb, "Bình Tám", a)
    plot = await put(db, b, 0, 0, "水", stage=2)
    await learn(db, a, "水")
    stones = lambda uid: db.execute(select(User.spirit_stones).where(User.id == uid))  # noqa: E731
    a0, b0 = (await stones(a)).scalar_one(), (await stones(b)).scalar_one()
    # right answer: both get the reward; the owner's plant does not change
    q = (await client.post("/friends/help", json={"friend_id": b, "plot_id": plot.id}, headers=ha)).json()
    assert "context" in q, q
    assert q["context"] == "help" and q["helps_left"] == 4 and "answer_key" not in q
    key = await answer_key(q["session_id"])
    r = (await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                "answer": correct_answer(q["qtype"], key)}, headers=ha)).json()
    assert r["correct"] and r["reward"] == {"spirit_stones": 10}
    async with dbm.SessionLocal() as fresh:
        got = [(await fresh.execute(select(User.spirit_stones).where(User.id == u))).scalar_one() for u in (a, b)]
    assert got == [a0 + 10, b0 + 10]
    async with dbm.SessionLocal() as fresh:
        reasons = {x.reason for x in (await fresh.execute(select(AuditLog))).scalars().all()}
        assert {"help_water", "helped_by_friend"} <= reasons
        assert (await fresh.execute(select(Plot.stage).where(Plot.id == plot.id))).scalar_one() == 2
    # a wrong answer still uses up an attempt and gives nothing
    q = (await client.post("/friends/help", json={"friend_id": b, "plot_id": plot.id}, headers=ha)).json()
    key = await answer_key(q["session_id"])
    r = (await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                "answer": wrong_answer(q["qtype"], key)}, headers=ha)).json()
    assert not r["correct"] and "reward" not in r
    async with dbm.SessionLocal() as fresh:
        assert (await fresh.execute(select(Collection.needs_review).where(
            Collection.user_id == a, Collection.introduced.is_(True)))).scalars().first()
    for _ in range(3):
        assert (await client.post("/friends/help", json={"friend_id": b, "plot_id": plot.id},
                                  headers=ha)).status_code == 200
    r = await client.post("/friends/help", json={"friend_id": b, "plot_id": plot.id}, headers=ha)
    assert r.status_code == 400 and r.json()["error"]["code"] == "help_limit"


async def test_help_needs_a_learned_word_and_friendship(client, db):
    ha, a = await player(client, db, "an_09", "An Chín")
    hb, b = await player(client, db, "binh_09", "Bình Chín")
    plot = await put(db, b, 0, 0, "火", stage=2)
    r = await client.post("/friends/help", json={"friend_id": b, "plot_id": plot.id}, headers=ha)
    assert r.status_code == 403
    await befriend(client, ha, hb, "Bình Chín", a)
    r = await client.post("/friends/help", json={"friend_id": b, "plot_id": plot.id}, headers=ha)
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_learned"
    own = await put(db, a, 0, 0, "火", stage=1)
    r = await client.post("/friends/help", json={"friend_id": b, "plot_id": own.id}, headers=ha)
    assert r.status_code == 404  # not the friend's plot


async def test_abode_position_ignored_while_in_world(client, db):
    from app.realtime.world import world
    from app.realtime.zone import Player
    ha, a = await player(client, db, "an_10", "An Mười")
    world.players[a] = Player(a, "An Mười", {}, "pham_nhan", 1, 1)
    world.players[a].channel = object()  # standing in some zone
    try:
        r = (await client.post("/character/position", json={"zone_id": "abode", "x": 10, "y": 10},
                               headers=ha)).json()
        assert r == {"ok": False, "ignored": "in_world"}
    finally:
        world.players.pop(a, None)
