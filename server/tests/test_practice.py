"""Practice quiz: the shared learning service outside the garden (mastery ±2, never
changes the garden stage, never asks about a word the player has not been shown)."""
import random

from sqlalchemy import select

from app.learning import selection
from app.models import Collection, Plot, QuizSession
from tests.helpers import answer_key, correct_answer, register, wrong_answer


async def _learned(client, h):
    garden = (await client.get("/garden", headers=h)).json()
    seed = (await client.get("/seeds", headers=h)).json()["seeds"][0]
    pid = [p for p in garden["plots"] if p["unlocked"]][0]["id"]
    await client.post("/garden/plant", json={"plot_id": pid, "seed_id": seed["seed_id"]}, headers=h)
    return pid


async def test_practice_requires_introduced_word(client):
    h, _ = await register(client)
    pid = await _learned(client, h)
    r = await client.post("/quiz/practice", json={}, headers=h)
    assert r.json()["error"]["code"] == "nothing_learned"
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    r = await client.post("/quiz/practice", json={}, headers=h)
    assert r.status_code == 200


async def test_practice_mastery_and_stage_unchanged(client, db):
    h, _ = await register(client)
    pid = await _learned(client, h)
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    q = (await client.post("/quiz/practice", json={"qtype": "Q2"}, headers=h)).json()
    key = await answer_key(q["session_id"])
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": correct_answer("Q2", key)},
                          headers=h)
    assert r.json()["correct"] and r.json()["mastery"] == 2
    q = (await client.post("/quiz/practice", json={"qtype": "Q11"}, headers=h)).json()
    key = await answer_key(q["session_id"])
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": wrong_answer("Q11", key)},
                          headers=h)
    assert r.json()["mastery"] == 0
    col = (await db.execute(select(Collection))).scalar_one()
    assert col.needs_review and col.times_correct == 1 and col.times_wrong == 1
    plot = await db.get(Plot, pid)
    assert plot.stage == 1  # practice never moves the garden stage


async def test_every_type_available_through_api(client, db):
    h, _ = await register(client)
    pid = await _learned(client, h)
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    word_id = (await db.execute(select(Collection.word_id))).scalar_one()
    ok = 0
    for qt in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10", "Q11"]:
        r = await client.post("/quiz/practice", json={"qtype": qt, "word_id": word_id}, headers=h)
        if r.status_code == 200:
            ok += 1
            pub = r.json()
            assert "answer_key" not in pub and "option" not in str(pub.get("prompt"))
            key = await answer_key(pub["session_id"])
            res = await client.post("/quiz/answer", json={"session_id": pub["session_id"],
                                                          "answer": correct_answer(qt, key)}, headers=h)
            assert res.json()["correct"], qt
    assert ok >= 8  # 水 supports most types (not Q6/Q8: no classifier, pictograph)


async def test_selection_no_repeat_and_known_only(client, db):
    h, _ = await register(client)
    user_id = (await client.get("/me", headers=h)).json()["id"]
    from app.learning.wordbank import bank
    words = [w for w in bank().words.values() if w.tier == 1 and not w.hidden and w.hanzi != "水"][:12]
    from app import clock
    for w in words[:8]:
        db.add(Collection(user_id=user_id, word_id=w.id, introduced=True, first_seen_at=clock.now()))
    for w in words[8:]:  # owned but never introduced: must never be asked
        db.add(Collection(user_id=user_id, word_id=w.id, introduced=False, first_seen_at=clock.now()))
    await db.commit()
    rng = random.Random(3)
    asked = []
    for _ in range(40):
        wid = await selection.pick_word(db, user_id, 1, rng)
        assert wid in {w.id for w in words[:8]}
        assert wid not in asked[-5:]
        asked.append(wid)
        db.add(QuizSession(id=f"s{len(asked)}", user_id=user_id, context="practice", qtype="Q1", word_id=wid,
                           payload={}, answer_key={}, created_at=clock.now(), expires_at=clock.now()))
        await db.commit()
        clock._clock.advance(seconds=1)
