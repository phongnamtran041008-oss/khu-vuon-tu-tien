"""Stage 5 REST: the Linh Phong hive, bees and the Ong Phổ (spec 10). Guard bees fight
through the WebSocket world (docs/PROTOCOL.md)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import User
from ..systems import bees

router = APIRouter(tags=["bees"])


class EggIn(BaseModel):
    item_id: str = Field(max_length=40)


class MoveIn(BaseModel):
    bee_id: int
    slot: int = Field(ge=0, le=63)


class RoleIn(BaseModel):
    bee_id: int
    role: Literal["hive", "pollinate", "guard"]


class FeedIn(BaseModel):
    bee_id: int
    food: str = Field(max_length=60)


class BeeIn(BaseModel):
    bee_id: int


class DecorIn(BaseModel):
    decoration: str = Field(max_length=24)
    on: bool = True


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except bees.BeeError as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


@router.get("/bees/species")
async def bee_species():
    """Static: names and colours of every species (the client draws other players' bees)."""
    return bees.species_catalog()


@router.get("/hive")
async def hive(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.hive_view(db, user))


@router.post("/hive/collect")
async def hive_collect(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.collect(db, user))


@router.post("/hive/hatch")
async def hive_hatch(body: EggIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.hatch(db, user, body.item_id))


@router.post("/hive/unlock_cell")
async def hive_unlock(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.unlock_cell(db, user))


@router.post("/hive/upgrade")
async def hive_upgrade(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.upgrade(db, user))


@router.post("/hive/decoration")
async def hive_decoration(body: DecorIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.set_decoration(db, user, body.decoration, body.on))


@router.post("/bees/move")
async def bee_move(body: MoveIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.move(db, user, body.bee_id, body.slot))


@router.post("/bees/role")
async def bee_role(body: RoleIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.set_role(db, user, body.bee_id, body.role))


@router.post("/bees/feed")
async def bee_feed(body: FeedIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.feed(db, user, body.bee_id, body.food))


@router.post("/bees/release")
async def bee_release(body: BeeIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, bees.release(db, user, body.bee_id))


@router.get("/codex/bee")
async def codex_bee(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await bees.bee_book(db, user)
