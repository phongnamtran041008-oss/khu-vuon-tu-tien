"""Which word to ask about outside the garden (spec 8.2): 70% from the player's own
collection, preferring words that are due or marked 'cần ôn' (so fighting is also
reviewing), 30% from words of the zone's level that the player has already been
introduced to. Never a word the player has not seen, never one of the last N asked."""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance
from ..models import Collection, Plot, QuizSession
from .wordbank import bank


class NoWordAvailable(Exception):
    pass


async def recent_word_ids(db: AsyncSession, user_id: int, n: int) -> set[str]:
    rows = (await db.execute(select(QuizSession.word_id).where(QuizSession.user_id == user_id)
                             .order_by(QuizSession.created_at.desc()).limit(n))).scalars().all()
    return set(rows)


async def pick_word(db: AsyncSession, user_id: int, zone_tier: int, rng: random.Random) -> str:
    cfg = balance.quiz()
    b = bank()
    introduced = (await db.execute(select(Collection).where(
        Collection.user_id == user_id, Collection.introduced.is_(True)))).scalars().all()
    known = [c for c in introduced if c.word_id in b.words]
    if not known:
        raise NoWordAvailable()
    recent = await recent_word_ids(db, user_id, cfg["no_repeat_window"])
    fresh = [c for c in known if c.word_id not in recent] or known  # tiny collections may repeat

    due_at = dict((await db.execute(select(Plot.word_id, Plot.next_review_at).where(
        Plot.user_id == user_id, Plot.word_id.is_not(None)))).all())

    if rng.random() < cfg["selection_collection_share"]:
        def urgency(c: Collection) -> tuple:
            nra = due_at.get(c.word_id)
            return (not c.needs_review, nra is None, nra or 0, c.mastery, rng.random())
        pool = sorted(fresh, key=urgency)
        top = pool[:max(1, len(pool) // 3)]  # some variety among the most urgent third
        return rng.choice(top).word_id
    zone = [c for c in fresh if b.words[c.word_id].tier == zone_tier] or fresh
    return rng.choice(zone).word_id
