"""Khắc Văn (spec 12.2): carve a learned word onto a piece of equipment for a stat that fits
the word. It takes a mastery of at least 70 and three right answers in a row about that
word (quiz context "forge"); one wrong answer ends the try and the fee is gone. A piece
has 1-3 slots by rarity; a carved character can be scraped off for a small fee.

The carved list lives in equipment_instances.inscriptions as
[{word_id, hanzi, stat, value}], and cultivation.instance_stats adds it to the piece."""
from __future__ import annotations

import datetime as dt
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning import question_bank as qb
from ..learning import quiz
from ..learning.wordbank import bank
from ..models import Collection, EquipmentInstance, QuizSession, User
from . import catalog, inventory, items

STATS_VI = {"atk": "Công", "def": "Thủ", "max_hp": "Sinh Lực", "max_qi": "Linh Lực", "crit": "Bạo kích",
            "ink_res": "Kháng Mực"}


class InscribeError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("inscription")


def slots(rarity: str) -> int:
    return int(cfg()["slots"].get(rarity, 1))


def stat_for(word_id: str, rarity: str) -> dict:
    from . import td
    c = cfg()
    w = bank().get(word_id)
    base = c["by_hanzi"].get(w.hanzi) or c["by_role"][td.role_of(word_id)]
    value = max(1, int(round(base["value"] * c["rarity_mult"].get(rarity, 1.0))))
    return {"stat": base["stat"], "stat_vi": STATS_VI.get(base["stat"], base["stat"]), "value": value}


async def _piece(db: AsyncSession, user: User, instance_id: int) -> EquipmentInstance:
    e = await db.get(EquipmentInstance, instance_id)
    if e is None or e.user_id != user.id:
        raise InscribeError(404, "no_item", "Không tìm thấy trang bị này.")
    return e


def _fee_vi() -> str:
    c = cfg()
    parts = [f"{c['fee']['spirit_stones']} Linh Thạch"]
    parts += [f"{f['qty']} {catalog.item_name(f['item'])}" for f in c["fee_items"]]
    return ", ".join(parts)


async def options(db: AsyncSession, user: User, instance_id: int) -> dict:
    """The piece, its slots, and every learned word that could be carved on it."""
    e = await _piece(db, user, instance_id)
    c = cfg()
    on = {i["word_id"] for i in e.inscriptions or []}
    cols = (await db.execute(select(Collection).where(Collection.user_id == user.id,
                                                      Collection.introduced.is_(True)))).scalars().all()
    b = bank()
    words = []
    for col in sorted(cols, key=lambda x: -x.mastery):
        if col.word_id not in b.words:
            continue
        w = b.get(col.word_id)
        words.append({"word_id": w.id, "hanzi": w.hanzi, "pinyin": w.pinyin, "meaning_vi": w.meaning_vi,
                      "mastery": col.mastery, "ok": col.mastery >= c["mastery_min"] and w.id not in on,
                      "carved": w.id in on, **stat_for(w.id, e.rarity)})
    return {"item": items.equipment_view(e), "slots": slots(e.rarity), "used": len(e.inscriptions or []),
            "inscriptions": e.inscriptions or [], "mastery_min": c["mastery_min"], "questions": c["questions"],
            "fee_vi": _fee_vi(), "erase_fee": c["erase_fee"], "words": words,
            "running": (user.flags or {}).get("inscribe")}


def _question(word_id: str, number: int, rng: random.Random) -> qb.Question:
    w = bank().get(word_id)
    types = [q for q in cfg()["qtypes"] if balance.quiz()["types"][q]["min_tier"] <= max(1, w.tier)]
    order = types[number % len(types):] + types[:number % len(types)]   # a different kind each time
    ctx = quiz.gen_context(rng, max_tier=max(w.tier, 1))
    try:
        return qb.generate_first(order, w, ctx)
    except qb.QuestionError:
        return qb.generate_any(["Q1", "Q2"], w, ctx)


async def _ask(db: AsyncSession, user: User, run: dict, rng: random.Random) -> dict:
    q = _question(run["word"], run["right"], rng)
    out = await quiz.create_session(db, user, "forge", q, ref=f"{run['instance']}:{run['word']}")
    out.update({"number": run["right"] + 1, "total": cfg()["questions"]})
    return out


async def start(db: AsyncSession, user: User, instance_id: int, word_id: str,
                rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    c = cfg()
    e = await _piece(db, user, instance_id)
    if word_id not in bank().words:
        raise InscribeError(404, "no_word", "Không có chữ này.")
    col = await quiz.get_collection(db, user.id, word_id)
    if col is None or not col.introduced:
        raise InscribeError(400, "not_learned", "Chỉ khắc được chữ con đã học.")
    if col.mastery < c["mastery_min"]:
        raise InscribeError(400, "mastery_low", f"Phải thuộc chữ {bank().get(word_id).hanzi} từ {c['mastery_min']}% "
                                                f"mới khắc được (hiện {col.mastery}%).")
    if any(i["word_id"] == word_id for i in e.inscriptions or []):
        raise InscribeError(400, "already_carved", "Chữ này đã khắc trên món đồ này rồi.")
    if len(e.inscriptions or []) >= slots(e.rarity):
        raise InscribeError(400, "no_slot", "Món đồ này đã hết ô khắc. Mài bớt một chữ cũ đã.")
    ref = f"{e.id}:{word_id}"
    try:
        for f in c["fee_items"]:
            await inventory.consume_item(db, user.id, f["item"], f["qty"], "inscribe", ref)
        await inventory.charge(db, user.id, c["fee"], "inscribe", ref)
    except inventory.InsufficientFunds as err:
        raise InscribeError(400, "insufficient_funds", f"Khắc văn cần {_fee_vi()} "
                                                       f"(thiếu {catalog.item_name(err.what)}).")
    run = {"instance": e.id, "word": word_id, "right": 0, "at": clock.now().isoformat()}
    flags = dict(user.flags or {})
    flags["inscribe"] = run
    user.flags = flags
    return {"question": await _ask(db, user, run, rng), "item": items.equipment_view(e)}


async def forge_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool, now: dt.datetime) -> dict:
    out = await quiz.practice_handler(db, user, s, correct, now)   # mastery ±2 like any non-garden answer
    flags = dict(user.flags or {})
    run = flags.get("inscribe")
    if not run or f"{run['instance']}:{run['word']}" != s.ref:
        return out
    total = cfg()["questions"]
    if not correct:
        flags.pop("inscribe", None)
        user.flags = flags
        out["inscribe"] = {"done": True, "success": False, "right": run["right"], "total": total}
        return out
    run = {**run, "right": run["right"] + 1}
    if run["right"] < total:
        flags["inscribe"] = run
        user.flags = flags
        out["next"] = await _ask(db, user, run, random.Random())
        out["inscribe"] = {"done": False, "right": run["right"], "total": total}
        return out
    flags.pop("inscribe", None)
    user.flags = flags
    e = await db.get(EquipmentInstance, run["instance"])
    if e is None or e.user_id != user.id or len(e.inscriptions or []) >= slots(e.rarity):
        out["inscribe"] = {"done": True, "success": False, "right": run["right"], "total": total}
        return out
    w = bank().get(run["word"])
    st = stat_for(w.id, e.rarity)
    e.inscriptions = list(e.inscriptions or []) + [{"word_id": w.id, "hanzi": w.hanzi, "stat": st["stat"],
                                                    "value": st["value"]}]
    await db.flush()
    stats = await items._after_gear_change(db, user.id) if e.equipped_slot else None
    from . import quests
    await quests.on_event(db, user.id, "inscribe", "*")
    out["inscribe"] = {"done": True, "success": True, "right": run["right"], "total": total,
                       "item": items.equipment_view(e), "carved": {"hanzi": w.hanzi, **st}, "stats": stats}
    return out


quiz.register_handler("forge", forge_handler)


async def erase(db: AsyncSession, user: User, instance_id: int, index: int) -> dict:
    e = await _piece(db, user, instance_id)
    ins = list(e.inscriptions or [])
    if not 0 <= index < len(ins):
        raise InscribeError(400, "no_inscription", "Không có chữ khắc này.")
    try:
        await inventory.change_currency(db, user.id, "spirit_stones", -cfg()["erase_fee"], "inscribe_erase", str(e.id))
    except inventory.InsufficientFunds as err:
        raise InscribeError(400, "insufficient_funds", err.message_vi)
    gone = ins.pop(index)
    e.inscriptions = ins
    await db.flush()
    stats = await items._after_gear_change(db, user.id) if e.equipped_slot else None
    return {"erased": gone, "item": items.equipment_view(e), "stats": stats}


async def abandon_if_stale(db: AsyncSession, user: User) -> None:
    """A try whose question was never answered (closed game) is simply over."""
    run = (user.flags or {}).get("inscribe")
    if not run:
        return
    open_q = (await db.execute(select(QuizSession).where(
        QuizSession.user_id == user.id, QuizSession.context == "forge",
        QuizSession.answered_at.is_(None), QuizSession.expires_at > clock.now()))).scalars().first()
    if open_q is None:
        flags = dict(user.flags or {})
        flags.pop("inscribe", None)
        user.flags = flags
