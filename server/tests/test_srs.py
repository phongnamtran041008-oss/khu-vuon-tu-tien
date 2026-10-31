"""Garden SRS rules (spec 6.2, 6.3) on plain objects, then end-to-end over the API."""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import balance
from app.config import settings
from app.learning import srs
from app.models import AuditLog, Collection, User
from tests.helpers import answer_key, correct_answer, register, wrong_answer

T0 = dt.datetime(2026, 1, 1, 8, 0, 0)
DAY = dt.timedelta(days=1)


def plot(stage=1, nra=T0, wither=0.0):
    return SimpleNamespace(stage=stage, next_review_at=nra, wither=wither, wither_checked_at=None)


def test_stage_table():
    g = balance.garden()
    assert srs.question_types(1) == ["Q1"] and srs.question_types(2) == ["Q3"]
    assert srs.question_types(3) == ["Q4"] and set(srs.question_types(4)) == {"Q5", "Q7"}
    assert g["review_wait_after_reaching_stage"] == {"1": 600, "2": 86400, "3": 259200, "4": 604800}


def test_correct_advances_with_waits_and_reward():
    p = plot(stage=0, nra=None)
    srs.learn(p, T0)
    assert p.stage == 1 and p.next_review_at == T0 + dt.timedelta(minutes=10)
    expected = {2: DAY, 3: 3 * DAY, 4: 7 * DAY}
    for stage in (2, 3, 4):
        out = srs.apply_correct(p, T0)
        assert out.new_stage == stage and out.reward == 10 * stage and out.mastery_delta == 10
        assert p.next_review_at == T0 + expected[stage]
    out = srs.apply_correct(p, T0)
    assert out.new_stage == 5 and out.reward == 50 and p.next_review_at is None


def test_wrong_keeps_stage_retry_in_5_minutes():
    p = plot(stage=2)
    out = srs.apply_wrong(p, T0)
    assert p.stage == 2 and p.next_review_at == T0 + dt.timedelta(minutes=5)
    assert p.wither == 20 and out.mastery_delta == -5


def test_due_only_after_next_review():
    p = plot(stage=2, nra=T0 + DAY)
    assert not srs.is_due(p, T0)
    assert srs.is_due(p, T0 + DAY)
    assert not srs.is_due(plot(stage=5, nra=None), T0)


def test_wither_grace_then_10_per_day():
    p = plot(stage=3, nra=T0)
    srs.refresh_wither(p, T0 + DAY)
    assert p.wither == 0
    srs.refresh_wither(p, T0 + 2 * DAY)
    assert p.wither == pytest.approx(10)
    srs.refresh_wither(p, T0 + 4 * DAY)
    assert p.wither == pytest.approx(30)


def test_wither_lazy_equals_live():
    live, lazy = plot(stage=4), plot(stage=4)
    for h in range(0, 24 * 40, 6):
        srs.refresh_wither(live, T0 + dt.timedelta(hours=h))
    srs.refresh_wither(lazy, T0 + dt.timedelta(hours=24 * 40 - 6))
    assert (live.stage, round(live.wither, 6)) == (lazy.stage, round(lazy.wither, 6))


def test_wither_100_regresses_one_stage_never_dies():
    p = plot(stage=3)
    regressed = srs.refresh_wither(p, T0 + 11 * DAY)  # 1 day grace + 10 days * 10
    assert regressed and p.stage == 2 and p.wither == 60
    p = plot(stage=1)
    srs.refresh_wither(p, T0 + 200 * DAY)
    assert p.stage == 1  # cannot fall below "Nảy mầm"; the word is never lost


def test_correct_clears_ink():
    p = plot(stage=2, wither=70)
    srs.apply_correct(p, T0)
    assert p.wither == 20


def test_time_scale(monkeypatch):
    monkeypatch.setattr(settings, "time_scale", 1440.0)
    p = plot(stage=1)
    srs.apply_correct(p, T0)
    assert p.next_review_at == T0 + dt.timedelta(minutes=1)  # 1 day -> 1 minute


# ------------------------------------------------------------------ API flow
async def _grow(client, h, plot_id, frozen, stage_wait):
    r = await client.post("/garden/review", json={"plot_id": plot_id}, headers=h)
    assert r.status_code == 200, r.text
    q = r.json()
    key = await answer_key(q["session_id"])
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                               "answer": correct_answer(q["qtype"], key)}, headers=h)
    assert r.status_code == 200 and r.json()["correct"], r.text
    frozen.advance(seconds=stage_wait)
    return q, r.json()


async def test_full_garden_flow(client, db, frozen):
    h, reg = await register(client)
    assert len(reg["recovery_code"]) == 14
    garden = (await client.get("/garden", headers=h)).json()
    assert len(garden["plots"]) == 25 and sum(p["unlocked"] for p in garden["plots"]) == 9
    seeds = (await client.get("/seeds", headers=h)).json()["seeds"]
    assert len(seeds) == 1 and seeds[0]["hanzi"] == "水"
    pid = [p for p in garden["plots"] if p["unlocked"]][0]["id"]
    r = await client.post("/garden/plant", json={"plot_id": pid, "seed_id": seeds[0]["seed_id"]}, headers=h)
    assert r.json()["stage"] == 0

    r = await client.post("/garden/review", json={"plot_id": pid}, headers=h)
    assert r.json()["error"]["code"] == "needs_intro"
    card = (await client.get(f"/garden/intro/{pid}", headers=h)).json()
    assert card["hanzi"] == "水" and card["pinyin"] == "shuǐ" and card["meaning_vi"]
    r = await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    assert r.json()["stage"] == 1

    r = await client.post("/garden/review", json={"plot_id": pid}, headers=h)
    assert r.json()["error"]["code"] == "not_due"  # cannot answer before next_review_at
    frozen.advance(minutes=10)

    seen_types = []
    for wait in (86400, 3 * 86400, 7 * 86400, 0):
        q, res = await _grow(client, h, pid, frozen, wait)
        seen_types.append(q["qtype"])
    assert seen_types[:3] == ["Q1", "Q3", "Q4"] and seen_types[3] in ("Q5", "Q7")
    assert res["plot"]["ripe"]
    me = (await client.get("/me", headers=h)).json()
    assert me["spirit_stones"] == 300 + 20 + 30 + 40 + 50

    r = await client.post("/garden/harvest", json={"plot_id": pid}, headers=h)
    assert r.json()["fruits_gained"] == 3
    r = await client.post("/fruits/sell", json={"word_id": card["id"], "count": 3}, headers=h)
    earned = r.json()["earned"]
    assert earned == 3 * balance.garden()["fruit_sell_price"][card["rarity"]]
    r = await client.post("/fruits/sell", json={"word_id": card["id"], "count": 1}, headers=h)
    assert r.json()["error"]["code"] == "not_enough_fruit"
    col = (await db.execute(select(Collection))).scalar_one()
    assert col.introduced and col.mastery == 40 and col.times_correct == 4

    # progress survives: a fresh login sees the same state
    r = await client.post("/auth/login", json={"username": "tester", "password": "secret123"})
    h2 = {"Authorization": f"Bearer {r.json()['token']}"}
    assert (await client.get("/me", headers=h2)).json()["spirit_stones"] == me["spirit_stones"] + earned
    logs = (await db.execute(select(AuditLog).where(AuditLog.reason == "garden_review"))).scalars().all()
    assert len(logs) == 4


async def test_wrong_answer_and_answer_once(client, db, frozen):
    h, _ = await register(client)
    garden = (await client.get("/garden", headers=h)).json()
    seed = (await client.get("/seeds", headers=h)).json()["seeds"][0]
    pid = [p for p in garden["plots"] if p["unlocked"]][4]["id"]
    await client.post("/garden/plant", json={"plot_id": pid, "seed_id": seed["seed_id"]}, headers=h)
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    frozen.advance(minutes=10)
    q = (await client.post("/garden/review", json={"plot_id": pid}, headers=h)).json()
    # asking again returns the same open question, not a new one
    q_again = (await client.post("/garden/review", json={"plot_id": pid}, headers=h)).json()
    assert q_again["session_id"] == q["session_id"]
    key = await answer_key(q["session_id"])
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                               "answer": wrong_answer(q["qtype"], key)}, headers=h)
    body = r.json()
    assert body["correct"] is False and body["correct_option"] == key["option"]
    assert body["plot"]["stage"] == 1 and body["plot"]["wither"] == 20
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                               "answer": correct_answer(q["qtype"], key)}, headers=h)
    assert r.status_code == 409
    r = await client.post("/garden/review", json={"plot_id": pid}, headers=h)
    assert r.json()["error"]["code"] == "not_due"
    frozen.advance(minutes=5)
    assert (await client.post("/garden/review", json={"plot_id": pid}, headers=h)).status_code == 200
    user = (await db.execute(select(User))).scalar_one()
    assert user.spirit_stones == 300  # no reward for a wrong answer


async def test_expired_answer_counts_as_wrong(client, frozen):
    h, _ = await register(client)
    garden = (await client.get("/garden", headers=h)).json()
    seed = (await client.get("/seeds", headers=h)).json()["seeds"][0]
    pid = [p for p in garden["plots"] if p["unlocked"]][0]["id"]
    await client.post("/garden/plant", json={"plot_id": pid, "seed_id": seed["seed_id"]}, headers=h)
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    frozen.advance(minutes=10)
    q = (await client.post("/garden/review", json={"plot_id": pid}, headers=h)).json()
    key = await answer_key(q["session_id"])
    frozen.advance(minutes=11)
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                               "answer": correct_answer(q["qtype"], key)}, headers=h)
    assert r.json()["correct"] is False and r.json()["timed_out"] is True


async def test_other_player_cannot_touch_my_garden(client, frozen):
    h1, _ = await register(client, "alice")
    h2, _ = await register(client, "bob")
    g1 = (await client.get("/garden", headers=h1)).json()
    seed1 = (await client.get("/seeds", headers=h1)).json()["seeds"][0]
    r = await client.post("/garden/plant", json={"plot_id": [p for p in g1["plots"] if p["unlocked"]][0]["id"], "seed_id": seed1["seed_id"]},
                          headers=h2)
    assert r.status_code == 404
    await client.post("/garden/plant", json={"plot_id": [p for p in g1["plots"] if p["unlocked"]][0]["id"], "seed_id": seed1["seed_id"]}, headers=h1)
    await client.post("/garden/learn", json={"plot_id": [p for p in g1["plots"] if p["unlocked"]][0]["id"]}, headers=h1)
    frozen.advance(minutes=10)
    q = (await client.post("/garden/review", json={"plot_id": [p for p in g1["plots"] if p["unlocked"]][0]["id"]}, headers=h1)).json()
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": {"option": "a"}}, headers=h2)
    assert r.status_code == 404


async def test_neglected_plant_withers_on_load(client, db, frozen):
    h, _ = await register(client)
    garden = (await client.get("/garden", headers=h)).json()
    seed = (await client.get("/seeds", headers=h)).json()["seeds"][0]
    pid = [p for p in garden["plots"] if p["unlocked"]][0]["id"]
    await client.post("/garden/plant", json={"plot_id": pid, "seed_id": seed["seed_id"]}, headers=h)
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    frozen.advance(minutes=10)
    q, _ = await _grow(client, h, pid, frozen, 0)          # now stage 2, due in 1 day
    frozen.advance(days=1 + 1 + 5)                          # due + grace + 5 days
    g = (await client.get("/garden", headers=h)).json()
    p = next(x for x in g["plots"] if x["id"] == pid)
    assert p["stage"] == 2 and p["wither"] == pytest.approx(50, abs=0.5) and p["due"]
