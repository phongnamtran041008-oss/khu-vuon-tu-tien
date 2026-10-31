"""Stage 4 REST: cultivation (Tu Vi, đả tọa, Thiên Kiếp), inventory, equipment, forge,
quests and the Yêu Quái Phổ. Fighting itself goes through the WebSocket (docs/PROTOCOL.md)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import Character, User
from ..systems import codex, cultivation, items, quests

router = APIRouter(tags=["rpg"])


class ItemIn(BaseModel):
    item_id: str = Field(max_length=40)


class SellIn(BaseModel):
    item_id: str = Field(max_length=40)
    qty: int = 1


class InstanceIn(BaseModel):
    instance_id: int


class SlotIn(BaseModel):
    slot: str = Field(max_length=16)


class QuestIn(BaseModel):
    quest_id: str = Field(max_length=40)


class NpcIn(BaseModel):
    npc: str = Field(max_length=24)


ERRORS = (cultivation.CultivationError, items.ItemError, quests.QuestError)


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except ERRORS as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


async def _char(db: AsyncSession, user: User) -> Character:
    ch = await db.get(Character, user.id)
    if ch is None:
        raise api_error(404, "no_character", "Bạn chưa tạo nhân vật.")
    return ch


@router.get("/cultivation")
async def cultivation_view(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    ch = await _char(db, user)
    stats = await cultivation.current_stats(db, ch)
    out = cultivation.view(ch, stats, await items.skill_list(db, user.id), await items.stacks(db, user.id), clock.now())
    from ..systems import buffs, pets
    out["buffs"] = buffs.view(user, clock.now())          # stage 8: pill buffs and the worn Linh Thú
    worn = await pets.worn(db, user.id)
    out["pet"] = pets.view(worn) if worn else None
    await db.commit()
    return out


@router.post("/cultivation/meditate")
async def meditate(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    return await _run(db, cultivation.meditate(db, user))


@router.post("/cultivation/breakthrough/start")
async def breakthrough(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, cultivation.tribulation_start(db, user))


@router.get("/inventory")
async def inventory(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await items.inventory_view(db, user)


@router.post("/inventory/use")
async def use_item(body: ItemIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, items.use(db, user, body.item_id))


@router.post("/inventory/sell")
async def sell_item(body: SellIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, items.sell(db, user, body.item_id, body.qty))


@router.post("/equipment/equip")
async def equip(body: InstanceIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, items.equip(db, user, body.instance_id))


@router.post("/equipment/unequip")
async def unequip(body: SlotIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, items.unequip(db, user, body.slot))


@router.post("/forge/enhance")
async def enhance(body: InstanceIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, items.enhance(db, user, body.instance_id))


@router.get("/quests")
async def quest_list(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    out = await quests.list_quests(db, user)
    await db.commit()
    return out


@router.post("/quests/claim")
async def quest_claim(body: QuestIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, quests.claim(db, user, body.quest_id))


@router.post("/quests/talk")
async def quest_talk(body: NpcIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, quests.talk(db, user, body.npc))


@router.get("/codex/monster")
async def codex_monster(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await codex.monster_book(db, user)
