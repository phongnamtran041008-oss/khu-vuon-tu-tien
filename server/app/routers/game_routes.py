from __future__ import annotations

import random

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..garden import garden as gd
from ..learning import question_bank as qb
from ..learning import quiz, selection
from ..learning.wordbank import bank
from ..models import Collection, QuizSession, Seed, User
from ..garden import combos, crafting
from ..models import Character
from ..schemas import (AnswerIn, CharacterCreateIn, CraftIn, GachaRollIn, PlantIn, PlotIn, PositionIn,
                       PracticeIn, SellFruitIn, SellSeedIn, TutorialIn, WordIn)
from ..systems import character as charsys
from ..systems import gacha_service
from ..systems.gacha import GachaError

router = APIRouter()


def _garden_err(e: gd.GardenError):
    return api_error(e.status, e.code, e.message_vi)


@router.get("/me")
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    gacha_service.reset_daily(user, clock.local_date(clock.now()))
    from ..systems import quests
    await quests.ensure(db, user.id)    # today's daily tasks exist before anything counts toward them
    await db.commit()
    cfg = balance.gacha()
    has_char = await db.get(Character, user.id) is not None
    return {"id": user.id, "username": user.username, "spirit_stones": user.spirit_stones,
            "immortal_jade": user.immortal_jade, "is_admin": user.is_admin,
            "has_character": has_char, "tutorial_step": (user.flags or {}).get("tutorial", 0),
            "daily_rolls_left": cfg["daily_roll_limit"] - user.daily_new_seeds_count,
            "free_rolls_left": cfg["daily_free_rolls"] - user.daily_free_rolls_used,
            "title": (user.flags or {}).get("title"), "frame": (user.flags or {}).get("frame")}


@router.post("/tutorial")
async def tutorial(body: TutorialIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    flags = dict(user.flags or {})
    flags["tutorial"] = max(int(flags.get("tutorial", 0)), body.step)  # never goes backwards
    user.flags = flags
    await db.commit()
    return {"tutorial_step": flags["tutorial"]}


# ---------------------------------------------------------------- character
def _char_err(e: charsys.CharacterError):
    return api_error(e.status, e.code, e.message_vi)


@router.post("/character/create")
async def character_create(body: CharacterCreateIn, user: User = Depends(write_user),
                           db: AsyncSession = Depends(get_db)):
    try:
        out = await charsys.create(db, user, body.display_name, body.appearance)
    except charsys.CharacterError as e:
        await db.rollback()
        raise _char_err(e)
    await db.commit()
    return out


@router.get("/character")
async def character_get(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    ch = await db.get(Character, user.id)
    if ch is None:
        raise api_error(404, "no_character", "Bạn chưa tạo nhân vật.")
    return charsys.view(ch)


@router.get("/character/options")
async def character_options():
    c = charsys.cfg()
    return {k: c[k] for k in ("hair_colors", "hair_styles", "bodies", "display_name_min", "display_name_max")}


@router.post("/character/position")
async def character_position(body: PositionIn, user: User = Depends(write_user),
                             db: AsyncSession = Depends(get_db)):
    try:
        out = await charsys.save_position(db, user, body.zone_id, body.x, body.y, body.facing)
    except charsys.CharacterError as e:
        raise _char_err(e)
    await db.commit()
    return out


# ---------------------------------------------------------------- gacha
@router.get("/gacha/banners")
async def gacha_banners(user: User = Depends(current_user)):
    return {"banners": gacha_service.banner_info(user)}


@router.post("/gacha/roll")
async def gacha_roll(body: GachaRollIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    try:
        out = await gacha_service.roll(db, user, body.banner, body.count, body.free, currency=body.currency)
    except GachaError as e:
        await db.rollback()
        raise api_error(400, e.code, e.message_vi)
    await db.commit()
    return out


# ---------------------------------------------------------------- garden
@router.get("/garden")
async def get_garden(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    out = await gd.load_garden(db, user)
    await db.commit()
    return out


@router.get("/seeds")
async def get_seeds(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Seed).where(Seed.user_id == user.id).order_by(Seed.id))).scalars().all()
    b = bank()
    return {"seeds": [{"seed_id": s.id, "word_id": s.word_id, "hanzi": b.get(s.word_id).hanzi,
                       "rarity": b.get(s.word_id).rarity, "duplicate": s.duplicate, "source": s.source}
                      for s in rows]}


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except gd.GardenError as e:
        await db.rollback()
        raise _garden_err(e)
    await db.commit()
    return out


@router.post("/garden/plant")
async def garden_plant(body: PlantIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.plant(db, user, body.plot_id, body.seed_id))


@router.get("/garden/intro/{plot_id}")
async def garden_intro(plot_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.intro_card(db, user, plot_id))


@router.post("/garden/learn")
async def garden_learn(body: PlotIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.learn(db, user, body.plot_id))


@router.post("/garden/review")
async def garden_review(body: PlotIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.start_review(db, user, body.plot_id))


@router.post("/garden/harvest")
async def garden_harvest(body: PlotIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.harvest(db, user, body.plot_id))


@router.post("/garden/expand")
async def garden_expand(body: PlotIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.expand(db, user, body.plot_id))


@router.post("/garden/cutting")
async def garden_cutting(body: WordIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.take_cutting(db, user, body.word_id))


@router.get("/discoveries")
async def get_discoveries(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await combos.discoveries(db, user)


@router.get("/sentences")
async def get_sentences(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await crafting.list_sentences(db, user)


@router.post("/sentences/craft")
async def craft_sentence(body: CraftIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, crafting.craft(db, user, body.sentence_id, body.word_ids))


@router.get("/fruits")
async def get_fruits(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return {"fruits": await gd.list_fruits(db, user)}


@router.post("/fruits/sell")
async def fruits_sell(body: SellFruitIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.sell_fruit(db, user, body.word_id, body.count))


@router.post("/seeds/sell")
async def seeds_sell(body: SellSeedIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, gd.sell_duplicate_seed(db, user, body.seed_id))


@router.get("/collection")
async def get_collection(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Collection).where(Collection.user_id == user.id))).scalars().all()
    b = bank()
    out = []
    for c in rows:
        w = b.get(c.word_id)
        entry = {"word_id": c.word_id, "hanzi": w.hanzi, "rarity": w.rarity, "introduced": c.introduced,
                 "mastery": c.mastery, "times_correct": c.times_correct, "times_wrong": c.times_wrong,
                 "needs_review": c.needs_review}
        if c.introduced:  # details only after the intro card (no peeking at unopened seeds)
            entry.update(w.public())
        out.append(entry)
    return {"collection": out}


# ---------------------------------------------------------------- quiz
@router.post("/quiz/answer")
async def quiz_answer(body: AnswerIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    try:
        out = await quiz.answer(db, user, body.session_id, body.answer)
    except quiz.QuizError as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


@router.get("/quiz/{session_id}/audio")
async def quiz_audio(session_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Listening questions stream audio through the session so the client never learns
    which word (= the answer) is being played."""
    s = await db.get(QuizSession, session_id)
    if s is None or s.user_id != user.id or s.qtype != "Q4":
        raise api_error(404, "no_audio", "Không có âm thanh.")
    path = quiz.AUDIO_DIR / f"{s.word_id}.mp3"
    if not path.exists():
        raise api_error(404, "no_audio", "Không có âm thanh.")
    return FileResponse(path, media_type="audio/mpeg", filename="q.mp3")


@router.post("/quiz/practice")
async def quiz_practice(body: PracticeIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    """Free practice on learned words (Tàng Thư Các 'Sổ Lỗi' uses it; also handy for testing
    every question type). Only introduced words can be asked."""
    rng = random.Random()
    tier = await gacha_service.player_tier(db, user.id)
    if body.word_id:
        col = await quiz.get_collection(db, user.id, body.word_id)
        if col is None or not col.introduced:
            raise api_error(400, "not_learned", "Bạn chưa học chữ này.")
        word_id = body.word_id
    else:
        try:
            word_id = await selection.pick_word(db, user.id, tier, rng)
        except selection.NoWordAvailable:
            raise api_error(400, "nothing_learned", "Hãy học ít nhất một chữ trong vườn trước đã.")
    w = bank().get(word_id)
    ctx = quiz.gen_context(rng, max_tier=max(tier, w.tier))
    try:
        if body.qtype:
            if body.qtype not in qb.QTYPES:
                raise api_error(400, "bad_qtype", "Dạng câu hỏi không tồn tại.")
            question = qb.generate(body.qtype, w, ctx)
        else:
            allowed = [q for q, c in balance.quiz()["types"].items() if c["min_tier"] <= tier]
            question = qb.generate_any(allowed, w, ctx)
    except qb.QuestionError:
        raise api_error(400, "no_question", "Không tạo được dạng câu hỏi này cho chữ đó.")
    out = await quiz.create_session(db, user, "practice", question)
    await db.commit()
    return out
