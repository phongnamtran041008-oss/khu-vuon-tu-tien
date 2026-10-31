from sqlalchemy import select

from app import db as dbm
from app import models


async def register(client, name="tester", password="secret123"):
    r = await client.post("/auth/register", json={"username": name, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['token']}"}, data


async def answer_key(session_id: str) -> dict:
    async with dbm.SessionLocal() as s:
        q = (await s.execute(select(models.QuizSession).where(models.QuizSession.id == session_id))).scalar_one()
        return q.answer_key


def correct_answer(qtype: str, key: dict) -> dict:
    if qtype == "Q5":
        return {"text": key["pinyin_numeric"].replace(" ", "")}
    if qtype == "Q9":
        by_text = {}
        for tid, txt in key["token_text"].items():
            by_text.setdefault(txt, []).append(tid)
        return {"order": [by_text[t].pop() for t in key["order_text"]]}
    return {"option": key["option"]}


def wrong_answer(qtype: str, key: dict) -> dict:
    if qtype == "Q5":
        return {"text": "xx9"}
    if qtype == "Q9":
        ids = list(key["token_text"])
        return {"order": list(reversed(correct_answer(qtype, key)["order"]))} if len(ids) > 1 else {"order": []}
    opts = "abcd" if qtype != "Q11" else "1234"
    return {"option": next(o for o in opts if o != key["option"])}
