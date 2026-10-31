"""Ghép Câu (spec 6.4): put fruit characters in the right order to form a sentence.

The player sees the Vietnamese meaning and the number of slots, and picks fruits from
their basket. Correct order -> fruits are used up, reward = 2 x the fruits' sell value.
Wrong order -> nothing is used, and Trúc Lão points at the first wrong slot.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..config import settings
from ..learning.wordbank import Sentence, bank
from ..models import CraftedSentence, Fruit, User
from ..systems import inventory
from ..systems.gacha_service import player_tier
from .garden import GardenError


def _needed(s: Sentence) -> Counter:
    return Counter(s.word_ids)


def _value(s: Sentence) -> int:
    prices = balance.garden()["fruit_sell_price"]
    b = bank()
    return sum(prices[b.get(w).rarity] for w in s.word_ids)


async def _fruits(db: AsyncSession, user_id: int) -> Counter:
    rows = (await db.execute(select(Fruit).where(Fruit.user_id == user_id, Fruit.count > 0))).scalars().all()
    return Counter({r.word_id: r.count for r in rows})


async def list_sentences(db: AsyncSession, user: User) -> dict:
    tier = await player_tier(db, user.id)
    have = await _fruits(db, user.id)
    crafted = Counter((await db.execute(select(CraftedSentence.sentence_id).where(
        CraftedSentence.user_id == user.id))).scalars().all())
    out = []
    for s in bank().sentences.values():
        if s.tier > tier or not (s.reviewed or settings.allow_unreviewed):
            continue
        need = _needed(s)
        ready = all(have[w] >= n for w, n in need.items())
        if not ready and not crafted[s.id]:
            continue  # only show sentences the player can actually build (or has built)
        out.append({"sentence_id": s.id, "vi": s.vi, "slots": len(s.word_ids),
                    "end_punct": "" if s.tokens[-1]["word_id"] else s.tokens[-1]["t"],
                    "ready": ready, "times_crafted": crafted[s.id],
                    "reward": _value(s) * balance.garden()["craft_reward_mult"]})
    out.sort(key=lambda d: (not d["ready"], d["sentence_id"]))
    return {"sentences": out}


async def craft(db: AsyncSession, user: User, sentence_id: str, word_ids: list[str]) -> dict:
    s = bank().sentences.get(sentence_id)
    if s is None or not (s.reviewed or settings.allow_unreviewed):
        raise GardenError(404, "no_sentence", "Không có câu này.")
    if s.tier > await player_tier(db, user.id):
        raise GardenError(400, "too_hard", "Câu này dành cho cảnh giới cao hơn.")
    if not isinstance(word_ids, list) or len(word_ids) != len(s.word_ids):
        raise GardenError(400, "wrong_length", f"Câu này cần đúng {len(s.word_ids)} quả chữ.")
    have = await _fruits(db, user.id)
    if any(have[w] < n for w, n in Counter(word_ids).items()):
        raise GardenError(400, "not_enough_fruit", "Bạn không có đủ những quả chữ này.")
    if word_ids != s.word_ids:
        first_wrong = next(i for i, (a, b) in enumerate(zip(word_ids, s.word_ids)) if a != b)
        right_set = Counter(word_ids) == Counter(s.word_ids)
        return {"correct": False, "first_wrong_slot": first_wrong,
                "right_words_wrong_order": right_set}
    for w, n in _needed(s).items():
        await inventory.change_fruit(db, user.id, w, -n, "craft_sentence", s.id)
    reward = _value(s) * balance.garden()["craft_reward_mult"]
    stones = await inventory.change_currency(db, user.id, "spirit_stones", reward, "craft_sentence", s.id)
    db.add(CraftedSentence(user_id=user.id, sentence_id=s.id, crafted_at=clock.now()))
    await db.flush()
    return {"correct": True, "reward": reward, "spirit_stones": stones, "text": s.text,
            "pinyin": " ".join(t["pinyin"] for t in s.tokens), "vi": s.vi}
