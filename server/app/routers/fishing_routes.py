"""Stage 6 REST: câu cá (spec 11) — rods and baits at Ngư Ông, the cast -> hook -> reel flow,
the Ngư Phổ and the size records. Fishing questions are answered through /quiz/answer like
every other question (docs/API.md)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import User
from ..systems import fishing

router = APIRouter(tags=["fishing"])


class EquipIn(BaseModel):
    rod: str | None = Field(default=None, max_length=40)
    bait: str | None = Field(default=None, max_length=40)
    no_bait: bool = False


class BuyIn(BaseModel):
    item_id: str = Field(max_length=40)
    qty: int = Field(default=1, ge=1, le=99)


class CraftIn(BaseModel):
    bait_id: str = Field(max_length=40)
    times: int = Field(default=1, ge=1, le=50)


class RodIn(BaseModel):
    rod_id: str = Field(max_length=40)


class CastIn(BaseModel):
    spot: Literal["abode", "world"]


class HookIn(BaseModel):
    cast_id: str = Field(max_length=40)


class ReelIn(BaseModel):
    cast_id: str = Field(max_length=40)
    toggles: list[int] = Field(default_factory=list, max_length=3000)


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except fishing.FishingError as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


@router.get("/fishing")
async def fishing_view(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.view(db, user))


@router.post("/fishing/equip")
async def fishing_equip(body: EquipIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.equip(db, user, body.rod, body.bait, body.no_bait))


@router.post("/fishing/buy")
async def fishing_buy(body: BuyIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.buy(db, user, body.item_id, body.qty))


@router.post("/fishing/craft")
async def fishing_craft(body: CraftIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.craft_bait(db, user, body.bait_id, body.times))


@router.post("/fishing/upgrade")
async def fishing_upgrade(body: RodIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.upgrade_rod(db, user, body.rod_id))


@router.post("/fishing/cast")
async def fishing_cast(body: CastIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.cast(db, user, body.spot))


@router.post("/fishing/hook")
async def fishing_hook(body: HookIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.hook(db, user, body.cast_id))


@router.post("/fishing/reel")
async def fishing_reel(body: ReelIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, fishing.reel(db, user, body.cast_id, body.toggles))


@router.post("/fishing/cancel")
async def fishing_cancel(user: User = Depends(write_user)):
    return fishing.cancel(user)


@router.get("/fishing/records")
async def fishing_records(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await fishing.records(db, user)


@router.get("/codex/fish")
async def codex_fish(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await fishing.book(db, user)


@router.get("/world/weather")
async def weather(zone: str = "abode", user: User = Depends(current_user)):
    """Night and rain for a zone (spec 7.1, 11.3): the client draws the rain from this."""
    return {"zone": zone, **fishing.conditions(zone[:32], clock.now())}
