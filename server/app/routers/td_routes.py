"""Stage 7 REST: Ải Thủ Vườn (spec 9, 16) and Tàng Thư Các (spec 9.3). Questions in a run are
answered through /quiz/answer like every other question (docs/API.md)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import User
from ..systems import library, td

router = APIRouter(tags=["td"])


class LoadoutIn(BaseModel):
    slots: list[str] = Field(default_factory=list, max_length=20)


class StartIn(BaseModel):
    level_id: str = Field(max_length=32)
    loadout: list[str] | None = Field(default=None, max_length=20)


class QuestionIn(BaseModel):
    run_id: str = Field(max_length=40)
    kind: Literal["break", "tu_khi", "upgrade"]
    word_id: str | None = Field(default=None, max_length=40)


class EventIn(BaseModel):
    run_id: str = Field(max_length=40)
    start: int = Field(ge=0, le=6000)
    events: list[dict] = Field(default_factory=list, max_length=6000)


class FinishIn(BaseModel):
    run_id: str = Field(max_length=40)
    events: list[dict] = Field(default_factory=list, max_length=6000)
    claim: dict = Field(default_factory=dict)


class WearIn(BaseModel):
    title: str | None = Field(default=None, max_length=40)
    frame: str | None = Field(default=None, max_length=40)


class BuyIn(BaseModel):
    item_id: str = Field(max_length=40)


class ClaimIn(BaseModel):
    book: str = Field(max_length=16)
    pct: int = Field(ge=0, le=100)


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except (td.TdError, library.LibraryError) as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


@router.get("/td/levels")
async def td_levels(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.levels_view(db, user))


@router.post("/td/loadout")
async def td_loadout(body: LoadoutIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.save_loadout(db, user, body.slots))


@router.post("/td/start")
async def td_start(body: StartIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.start(db, user, body.level_id, body.loadout))


@router.post("/td/question")
async def td_question(body: QuestionIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.ask(db, user, body.run_id, body.kind, body.word_id))


@router.post("/td/event")
async def td_event(body: EventIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.save_events(db, user, body.run_id, body.start, body.events))


@router.post("/td/resume")
async def td_resume(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.resume(db, user))


@router.post("/td/finish")
async def td_finish(body: FinishIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.finish(db, user, body.run_id, body.events, body.claim))


@router.post("/td/cancel")
async def td_cancel(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, td.cancel(db, user))


@router.get("/td/endless/board")
async def td_board(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await td.board(db, user)


# ------------------------------------------------------------------ Tàng Thư Các
@router.get("/library")
async def library_view(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.overview(db, user))


@router.get("/codex/plant")
async def codex_plant(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.herb_book(db, user))


@router.get("/codex/treasure")
async def codex_treasure(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.treasure_book(db, user))


@router.get("/library/search")
async def library_search(q: str = "", user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.search(db, user, q[:40]))


@router.get("/library/mistakes")
async def library_mistakes(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await library.mistakes(db, user)


@router.post("/library/wear")
async def library_wear(body: WearIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.wear(db, user, body.title, body.frame))


@router.post("/library/buy")
async def library_buy(body: BuyIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.buy(db, user, body.item_id))


@router.post("/library/claim")
async def library_claim(body: ClaimIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, library.claim(db, user, body.book, body.pct))
