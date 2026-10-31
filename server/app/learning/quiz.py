"""Question sessions (spec 8, 17): the shared learning service.

Any system asks for a question with `create_session(context=...)` and later calls
`answer()`. Grading is identical everywhere; what happens next is decided by the
handler registered for the context (garden -> SRS stage, practice/combat -> mastery ±2,
...). Answer keys stay in the database and are revealed only after answering.
"""
from __future__ import annotations

import datetime as dt
import random
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..config import DATA_DIR, settings
from ..models import Collection, QuizSession, User
from . import question_bank as qb
from .wordbank import bank

AUDIO_DIR = DATA_DIR / "audio"


class QuizError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def has_audio(word_id: str) -> bool:
    p = AUDIO_DIR / f"{word_id}.mp3"
    return p.exists() and p.stat().st_size > 0


def gen_context(rng: random.Random | None = None, max_tier: int = 1) -> qb.GenContext:
    return qb.GenContext(bank=bank(), rng=rng or random.Random(), max_tier=max_tier,
                         allow_unreviewed=settings.allow_unreviewed, has_audio=has_audio)


Handler = Callable[[AsyncSession, User, QuizSession, bool, dt.datetime], Awaitable[dict]]
_handlers: dict[str, Handler] = {}


def register_handler(context: str, fn: Handler) -> None:
    _handlers[context] = fn


async def create_session(db: AsyncSession, user: User, context: str, question: qb.Question,
                         ref: str | None = None, expires_in: float | None = None) -> dict:
    now = clock.now()
    from ..systems import buffs
    extra = buffs.extra_seconds(user, now)        # Ngộ Tính Đan (stage 8): more time to think
    if extra and question.time_limit:
        question.time_limit = float(question.time_limit) + extra
    grace = balance.quiz()["network_grace"]
    life = expires_in if expires_in is not None else question.time_limit + grace
    s = QuizSession(id=str(uuid.uuid4()), user_id=user.id, context=context, ref=ref,
                    qtype=question.qtype, word_id=question.word_id, payload=question.public(),
                    answer_key=question.answer_key, created_at=now,
                    expires_at=now + dt.timedelta(seconds=life))
    db.add(s)
    await db.flush()
    return public_session(s)


def public_session(s: QuizSession) -> dict:
    return {"session_id": s.id, "context": s.context, **s.payload,
            "server_time": clock.now().isoformat() + "Z", "expires_at": s.expires_at.isoformat() + "Z"}


async def get_collection(db: AsyncSession, user_id: int, word_id: str) -> Collection | None:
    return (await db.execute(select(Collection).where(
        Collection.user_id == user_id, Collection.word_id == word_id))).scalar_one_or_none()


def bump_mastery(col: Collection, delta: int) -> None:
    col.mastery = max(0, min(balance.garden()["mastery_max"], col.mastery + delta))


async def answer(db: AsyncSession, user: User, session_id: str, given: dict | None) -> dict:
    s = (await db.execute(select(QuizSession).where(QuizSession.id == session_id)
                          .with_for_update())).scalar_one_or_none()
    if s is None or s.user_id != user.id:
        raise QuizError(404, "no_session", "Không tìm thấy câu hỏi này.")
    if s.answered_at is not None:
        raise QuizError(409, "already_answered", "Câu này đã được trả lời rồi.")
    now = clock.now()
    timed_out = now > s.expires_at
    correct = (not timed_out) and qb.grade(s.qtype, s.answer_key, given)
    s.answered_at, s.correct = now, correct
    s.answer = given if isinstance(given, dict) and len(str(given)) < 500 else None
    s.answer_ms = int((now - s.created_at).total_seconds() * 1000)
    _watch_for_bots(user, correct, s.answer_ms)

    col = await get_collection(db, user.id, s.word_id)
    if col is not None:
        col.times_correct += int(correct)
        col.times_wrong += int(not correct)
        col.last_answered_at = now

    handler = _handlers.get(s.context)
    extra = await handler(db, user, s, correct, now) if handler else {}
    if correct:  # Tu Vi: right answers anywhere are the main source (spec 7.3)
        from ..systems import buffs, cultivation, pets, quests
        amount = cultivation.cfg()["xp_per_correct"].get(s.context, 0)
        if amount:   # Tụ Linh Đan, and the Gà for garden reviews (stage 8)
            mult = buffs.xp_mult(user, now)
            if s.context == "garden":
                mult *= 1 + await pets.skill_value(db, user.id, "xp_garden")
            amount = int(round(amount * mult))
        info = await cultivation.add_xp(db, user.id, amount, s.context) if amount else None
        if info:
            extra["xp"] = info
        await quests.on_event(db, user.id, "answer", "*")
    mishap = await _tone_mishap(db, user, s, given, correct)
    if mishap:
        extra["mishap"] = mishap
    result = {"correct": correct, "timed_out": timed_out,
              "correct_option": s.answer_key.get("option"),
              "reveal": s.answer_key.get("reveal"), **extra}
    if s.qtype == "Q9":
        result["correct_order"] = s.answer_key["order_text"]
    return result


def _watch_for_bots(user: User, correct: bool, answer_ms: int) -> None:
    """Spec 17: a long run of right answers that are all inhumanly fast flags the account
    for an admin (`/admin flagged`). Nothing is banned automatically. The user row is only
    written when the streak actually changes."""
    w = balance.quiz()["bot_watch"]
    flags = user.flags or {}
    streak = int(flags.get("fast_streak", 0))
    new = streak + 1 if correct and answer_ms < w["fast_ms"] else 0
    if new == streak:
        return
    user.flags = {**flags, "fast_streak": new}
    if new >= w["streak"] and not user.suspicious_flag:
        user.suspicious_flag = (f"{new} câu đúng liền, mỗi câu dưới {w['fast_ms']} ms "
                                f"({clock.now():%d/%m/%Y %H:%M} UTC)")


async def _tone_mishap(db: AsyncSession, user: User, s: QuizSession, given, correct: bool) -> dict | None:
    """Spec 6.6: picking a wrong tone that spells a real, funny word triggers a gag.
    Purely cosmetic except a tiny stone loss that can never go below zero."""
    if correct or s.qtype != "Q3" or not isinstance(given, dict):
        return None
    chosen = s.answer_key.get("option_numeric", {}).get(str(given.get("option")))
    if not chosen:
        return None
    from . import pinyin as py
    from ..systems import inventory
    for m in bank().mishaps:
        if m["target_id"] == s.word_id and py.canonical(m["wrong_pinyin"]) == py.canonical(chosen):
            out = {k: m[k] for k in ("id", "effect", "line_vi", "wrong_hanzi", "wrong_vi")}
            out["wrong_pinyin"] = m["wrong_pinyin_marked"]
            if m["effect"] == "lose_stones":
                have = (await db.execute(select(User.spirit_stones).where(User.id == user.id))).scalar_one()
                loss = min(balance.garden()["mishap_stone_loss"], have)
                if loss:
                    await inventory.change_currency(db, user.id, "spirit_stones", -loss, "tone_mishap", s.id)
                out["stones_lost"] = loss
            return out
    return None


async def practice_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool,
                           now: dt.datetime) -> dict:
    """Non-garden contexts (spec 8.3): mastery ±2, wrong answers mark the word 'cần ôn';
    the garden stage never changes here."""
    q = balance.quiz()
    col = await get_collection(db, user.id, s.word_id)
    if col is None:
        return {}
    bump_mastery(col, q["non_garden_mastery_correct"] if correct else q["non_garden_mastery_wrong"])
    if not correct:
        col.needs_review = True
    return {"mastery": col.mastery}


register_handler("practice", practice_handler)
