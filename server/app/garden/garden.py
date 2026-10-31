"""The word garden in each player's abode (spec 6): plots, planting, introduction card,
reviews (through the shared quiz service), adjacency reactions, harvest and selling."""
from __future__ import annotations

import datetime as dt
import math
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning import question_bank as qb
from ..learning import quiz, srs
from ..learning.wordbank import bank
from ..models import Collection, Fruit, Plot, QuizSession, Seed, User
from ..systems import inventory
from . import combos


class GardenError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def _grid() -> dict:
    return balance.garden()["grid"]


async def ensure_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    """5x5 field; the first 3x3 is open, the rest is unlocked with Linh Thạch (spec 6: mở rộng ô đất)."""
    g = _grid()
    plots = list((await db.execute(select(Plot).where(Plot.user_id == user_id))).scalars().all())
    have = {(p.x, p.y) for p in plots}
    added = False
    for y in range(g["height"]):
        for x in range(g["width"]):
            if (x, y) not in have:
                db.add(Plot(user_id=user_id, x=x, y=y, stage=0, wither=0.0,
                            unlocked=x < g["initial_width"] and y < g["initial_height"]))
                added = True
    if added:
        await db.flush()
        plots = list((await db.execute(select(Plot).where(Plot.user_id == user_id))).scalars().all())
    plots.sort(key=lambda p: (p.y, p.x))
    return plots


def unlock_cost(plots: list[Plot]) -> int | None:
    g = _grid()
    extra = sum(1 for p in plots if p.unlocked) - g["initial_width"] * g["initial_height"]
    costs = balance.garden()["plot_unlock_costs"]
    return costs[extra] if 0 <= extra < len(costs) else None


def _can_unlock(plots: list[Plot], p: Plot) -> bool:
    open_cells = {(q.x, q.y) for q in plots if q.unlocked}
    return not p.unlocked and any((p.x + dx, p.y + dy) in open_cells for dx, dy in combos.NEIGHBOURS)


def plot_view(p: Plot, now: dt.datetime, plots: list[Plot] | None = None) -> dict:
    d = {"id": p.id, "x": p.x, "y": p.y, "unlocked": p.unlocked, "word": None}
    if not p.unlocked:
        if plots is not None:
            d["can_unlock"] = _can_unlock(plots, p)
            d["unlock_cost"] = unlock_cost(plots) if d["can_unlock"] else None
        return d
    if p.word_id:
        w = bank().get(p.word_id)
        d.update({
            "word": {"id": w.id, "hanzi": w.hanzi, "pinyin": w.pinyin if p.stage >= 1 else None,
                     "rarity": w.rarity},
            "stage": p.stage,
            "stage_name_vi": balance.garden()["stage_names_vi"][p.stage],
            "wither": round(p.wither, 1),
            "next_review_at": p.next_review_at.isoformat() + "Z" if p.next_review_at else None,
            "due": srs.is_due(p, now),
            # ceil: the client must never think a plant is due before the server does
            "seconds_until_due": (max(0, math.ceil((p.next_review_at - now).total_seconds()))
                                  if p.next_review_at and p.stage < srs.RIPE else None),
            "ripe": p.stage >= srs.RIPE,
            # Linh Phong (spec 10.2): pollen bar of flowering plants, never their stage
            "pollen": round(p.pollen or 0.0, 1),
            "pollinated": bool(p.pollinated),
        })
        if plots is not None:
            d["auras"] = combos.auras_for(plots, p)
    return d


async def wither_rate(db: AsyncSession, user_id: int) -> float:
    """How fast sương mực spreads over this player's garden (the Hổ halves it, stage 8)."""
    from ..systems import pets
    return 1.0 - await pets.skill_value(db, user_id, "wither_slow")


async def load_garden(db: AsyncSession, user: User) -> dict:
    now = clock.now()
    plots = await ensure_plots(db, user.id)
    rate = await wither_rate(db, user.id)
    regressed = [p.id for p in plots if p.word_id and srs.refresh_wither(p, now, rate)]
    fire = combos.apply_fire(plots, clock.local_date(now))
    from ..systems import bees as beesys
    pollinated = await beesys.sync_garden(db, user.id, plots, now)
    found = await combos.check_discoveries(db, user, plots)
    needs_review = set((await db.execute(select(Collection.word_id).where(
        Collection.user_id == user.id, Collection.needs_review.is_(True)))).scalars().all())
    views = []
    for p in plots:
        v = plot_view(p, now, plots)
        if p.word_id:
            v["needs_review"] = p.word_id in needs_review
        views.append(v)
    g = _grid()
    bee_rows = await beesys.bees_of(db, user.id)
    hive = await beesys.get_hive(db, user.id)
    return {"width": g["width"], "height": g["height"], "plots": views, "regressed_plot_ids": regressed,
            "fire_events": fire, "discoveries": found, "pollinated": pollinated,
            "bees": [{"id": b.id, "sp": b.bee_type, "role": b.role} for b in bee_rows],
            "hive": {"level": hive.level, "decorations": list(hive.decorations or [])} if hive else None,
            "decorations": (user.flags or {}).get("decorations", []),
            "server_time": now.isoformat() + "Z"}


async def _plot(db: AsyncSession, user: User, plot_id: int, need_unlocked: bool = True) -> Plot:
    p = await db.get(Plot, plot_id)
    if p is None or p.user_id != user.id:
        raise GardenError(404, "no_plot", "Không tìm thấy ô đất này.")
    if need_unlocked and not p.unlocked:
        raise GardenError(400, "plot_locked", "Ô đất này chưa được khai hoang.")
    return p


async def _all_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    return list((await db.execute(select(Plot).where(Plot.user_id == user_id))).scalars().all())


async def expand(db: AsyncSession, user: User, plot_id: int) -> dict:
    plots = await ensure_plots(db, user.id)
    p = await _plot(db, user, plot_id, need_unlocked=False)
    if p.unlocked:
        raise GardenError(400, "already_open", "Ô đất này đã khai hoang rồi.")
    if not _can_unlock(plots, p):
        raise GardenError(400, "not_adjacent", "Chỉ khai hoang được ô nằm cạnh ô đã có.")
    cost = unlock_cost(plots)
    if cost is None:
        raise GardenError(400, "max_plots", "Vườn đã rộng hết cỡ.")
    try:
        stones = await inventory.change_currency(db, user.id, "spirit_stones", -cost, "plot_unlock", str(p.id))
    except inventory.InsufficientFunds as e:
        raise GardenError(400, "insufficient_funds", e.message_vi)
    p.unlocked = True
    await db.flush()
    return {"plot": plot_view(p, clock.now(), plots), "cost": cost, "spirit_stones": stones}


async def plant(db: AsyncSession, user: User, plot_id: int, seed_id: int) -> dict:
    p = await _plot(db, user, plot_id)
    if p.word_id:
        raise GardenError(400, "plot_busy", "Ô đất này đã có cây.")
    seed = await db.get(Seed, seed_id)
    if seed is None or seed.user_id != user.id:
        raise GardenError(404, "no_seed", "Không tìm thấy hạt giống này.")
    now = clock.now()
    p.word_id, p.stage, p.planted_at = seed.word_id, 0, now
    p.next_review_at, p.wither, p.wither_checked_at = None, 0.0, now
    p.pollen, p.pollinated, p.fire_checked_date = 0.0, False, clock.local_date(now)
    p.pollen_boost = False
    await db.delete(seed)
    await db.flush()
    return plot_view(p, now, await _all_plots(db, user.id))


async def intro_card(db: AsyncSession, user: User, plot_id: int) -> dict:
    p = await _plot(db, user, plot_id)
    if not p.word_id:
        raise GardenError(400, "empty_plot", "Ô đất này còn trống.")
    w = bank().get(p.word_id)
    card = w.public()
    card["has_audio"] = quiz.has_audio(w.id)
    return card


async def learn(db: AsyncSession, user: User, plot_id: int) -> dict:
    """'Đã nhớ' on the introduction card: stage 0 -> 1, word now counts as introduced."""
    p = await _plot(db, user, plot_id)
    if not p.word_id or p.stage != 0:
        raise GardenError(400, "not_new", "Cây này không ở giai đoạn hạt mới gieo.")
    now = clock.now()
    plots = await _all_plots(db, user.id)
    srs.learn(p, now, combos.wait_multiplier(plots, p))
    col = await quiz.get_collection(db, user.id, p.word_id)
    if col is None:
        col = Collection(user_id=user.id, word_id=p.word_id, first_seen_at=now)
        db.add(col)
    col.introduced = True
    await db.flush()
    found = await combos.check_discoveries(db, user, plots)
    return {**plot_view(p, now, plots), "discoveries": found}


async def start_review(db: AsyncSession, user: User, plot_id: int,
                       rng: random.Random | None = None) -> dict:
    p = await _plot(db, user, plot_id)
    now = clock.now()
    if not p.word_id:
        raise GardenError(400, "empty_plot", "Ô đất này còn trống.")
    srs.refresh_wither(p, now, await wither_rate(db, user.id))
    if p.stage == 0:
        raise GardenError(400, "needs_intro", "Hãy xem thẻ giới thiệu chữ trước đã.")
    if p.stage >= srs.RIPE:
        raise GardenError(400, "ripe", "Cây đã chín, thu hoạch thôi!")
    if not srs.is_due(p, now):
        wait = int((p.next_review_at - now).total_seconds())
        raise GardenError(400, "not_due", f"Chưa đến giờ ôn, còn {wait} giây nữa.")
    open_s = (await db.execute(select(QuizSession).where(
        QuizSession.user_id == user.id, QuizSession.context == "garden",
        QuizSession.ref == str(p.id), QuizSession.answered_at.is_(None),
        QuizSession.expires_at > now))).scalars().first()
    if open_s:
        return quiz.public_session(open_s)
    w = bank().get(p.word_id)
    ctx = quiz.gen_context(rng, max_tier=w.tier)
    try:
        question = qb.generate_first(srs.question_types(p.stage), w, ctx)
    except qb.QuestionError:
        question = qb.generate_first(["Q1", "Q2"], w, ctx)
    return await quiz.create_session(db, user, "garden", question, ref=str(p.id),
                                     expires_in=balance.garden()["garden_quiz_expiry_seconds"])


async def garden_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool,
                         now: dt.datetime) -> dict:
    p = await db.get(Plot, int(s.ref)) if s.ref else None
    if p is None or p.user_id != user.id or p.word_id != s.word_id:
        return {"note": "plot_changed"}
    plots = await _all_plots(db, user.id)
    srs.refresh_wither(p, now, await wither_rate(db, user.id))
    from ..systems import bees as beesys
    await beesys.sync_garden(db, user.id, plots, now)   # pollen up to the moment of the answer
    out = (srs.apply_correct(p, now, combos.wait_multiplier(plots, p)) if correct
           else srs.apply_wrong(p, now))
    if correct and p.pollen_boost and p.next_review_at is not None:
        # pollinated while it was already due: this new wait is the one that gets shorter
        p.next_review_at = now + (p.next_review_at - now) * (1 - beesys.review_cut())
        p.pollen_boost = False
    col = await quiz.get_collection(db, user.id, s.word_id)
    if col is not None:
        quiz.bump_mastery(col, out.mastery_delta)
        if correct:
            col.needs_review = False
    reward, pet_bonus = await _pet_reward(db, user, out.reward, correct)
    balance_after = None
    if reward:
        balance_after = await inventory.change_currency(db, user.id, "spirit_stones", reward,
                                                        "garden_review", s.id)
    found = await combos.check_discoveries(db, user, plots) if correct else []
    if correct:
        from ..systems import quests
        await quests.on_event(db, user.id, "review", "*")
    res = {"plot": plot_view(p, now, plots), "reward": {"spirit_stones": reward} if reward else {},
           "regressed": out.regressed, "spirit_stones": balance_after,
           "mastery": col.mastery if col else None, "discoveries": found,
           "streak": int((user.flags or {}).get("garden_streak", 0))}
    if pet_bonus:
        res["pet_bonus"] = pet_bonus
    return res


async def _pet_reward(db: AsyncSession, user: User, reward: int, correct: bool) -> tuple[int, dict | None]:
    """Stage 8 pets on a garden review: Trâu +20% stones; Rồng doubles the 5th right answer
    in a row. The streak is kept for everyone (it shows in the answer)."""
    from ..systems import pets
    flags = dict(user.flags or {})
    streak = int(flags.get("garden_streak", 0)) + 1 if correct else 0
    flags["garden_streak"] = streak
    user.flags = flags
    if not reward:
        return reward, None
    sk = await pets.skill(db, user.id)
    if not sk:
        return reward, None
    if sk["type"] == "review_stones":
        extra = int(round(reward * float(sk["value"])))
        return reward + extra, {"pet": "trau", "extra": extra}
    if sk["type"] == "streak_double" and streak % int(sk["every"]) == 0:
        return reward * 2, {"pet": "rong", "extra": reward, "streak": streak}
    return reward, None


quiz.register_handler("garden", garden_handler)


async def harvest(db: AsyncSession, user: User, plot_id: int) -> dict:
    p = await _plot(db, user, plot_id)
    if not p.word_id or p.stage < srs.RIPE:
        raise GardenError(400, "not_ripe", "Cây chưa chín.")
    now = clock.now()
    from ..systems import bees as beesys
    await beesys.sync_garden(db, user.id, await _all_plots(db, user.id), now)
    n, spirit = beesys.harvest_bonus(p, random.Random())
    pollinated = bool(p.pollinated)
    word_id = p.word_id
    total = await inventory.change_fruit(db, user.id, word_id, n, "harvest", str(p.id))
    linh_qua = None
    if spirit:
        item = beesys.cfg()["pollination"]["spirit_fruit_item"]
        linh_qua = await inventory.change_item(db, user.id, item, spirit, "harvest", str(p.id))
    p.word_id, p.stage, p.next_review_at, p.wither = None, 0, None, 0.0
    p.pollen, p.pollinated, p.planted_at, p.pollen_boost = 0.0, False, None, False
    await db.flush()
    from ..systems import cultivation
    xp = await cultivation.add_xp(db, user.id, cultivation.cfg()["xp_harvest"], "harvest")
    return {"word_id": word_id, "fruits_gained": n, "fruits_total": total, "plot": plot_view(p, now), "xp": xp,
            "pollinated": pollinated, "spirit_fruit": spirit, "spirit_fruit_total": linh_qua}


async def take_cutting(db: AsyncSession, user: User, word_id: str) -> dict:
    """Giâm cành: buy an extra seed of a word you already learned, to grow it twice
    (林 needs 木 + 木) or again after harvest. A Linh Thạch sink."""
    col = await quiz.get_collection(db, user.id, word_id)
    if col is None or not col.introduced:
        raise GardenError(400, "not_learned", "Chỉ giâm cành được chữ bạn đã học.")
    cost = balance.garden()["cutting_cost"]
    try:
        stones = await inventory.change_currency(db, user.id, "spirit_stones", -cost, "cutting", word_id)
    except inventory.InsufficientFunds as e:
        raise GardenError(400, "insufficient_funds", e.message_vi)
    seed = Seed(user_id=user.id, word_id=word_id, duplicate=True, source="cutting", obtained_at=clock.now())
    db.add(seed)
    await db.flush()
    return {"seed_id": seed.id, "cost": cost, "spirit_stones": stones}


async def sell_fruit(db: AsyncSession, user: User, word_id: str, count: int) -> dict:
    if count <= 0 or count > 999:
        raise GardenError(400, "bad_count", "Số lượng không hợp lệ.")
    w = bank().words.get(word_id)
    if w is None:
        raise GardenError(404, "no_word", "Không có quả chữ này.")
    try:
        left = await inventory.change_fruit(db, user.id, word_id, -count, "sell_fruit")
    except inventory.InsufficientFunds:
        raise GardenError(400, "not_enough_fruit", "Không đủ quả để bán.")
    price = balance.garden()["fruit_sell_price"][w.rarity] * count
    from ..systems import pets
    price = int(price * (1 + await pets.skill_value(db, user.id, "fruit_sell")))   # Lợn (stage 8)
    stones = await inventory.change_currency(db, user.id, "spirit_stones", price, "sell_fruit", word_id)
    return {"sold": count, "earned": price, "fruits_left": left, "spirit_stones": stones}


async def sell_duplicate_seed(db: AsyncSession, user: User, seed_id: int) -> dict:
    seed = await db.get(Seed, seed_id)
    if seed is None or seed.user_id != user.id:
        raise GardenError(404, "no_seed", "Không tìm thấy hạt giống này.")
    if not seed.duplicate:
        raise GardenError(400, "not_duplicate", "Chỉ bán được hạt trùng.")
    price = balance.gacha()["duplicate_seed_sell_price"]
    await db.delete(seed)
    stones = await inventory.change_currency(db, user.id, "spirit_stones", price, "sell_seed", str(seed_id))
    return {"earned": price, "spirit_stones": stones}


async def list_fruits(db: AsyncSession, user: User) -> list[dict]:
    rows = (await db.execute(select(Fruit).where(Fruit.user_id == user.id, Fruit.count > 0))).scalars().all()
    b = bank()
    return [{"word_id": r.word_id, "hanzi": b.get(r.word_id).hanzi, "pinyin": b.get(r.word_id).pinyin,
             "count": r.count, "rarity": b.get(r.word_id).rarity,
             "sell_price": balance.garden()["fruit_sell_price"][b.get(r.word_id).rarity]} for r in rows]
