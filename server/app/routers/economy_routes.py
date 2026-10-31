"""Stage 8 REST: luyện đan, khắc văn, Linh Thú, the Sạp Tạp Hóa and presents between friends
(docs/API.md). The economy itself is described in docs/BALANCE.md."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import User
from ..systems import alchemy, inscription, pets, shop, social

router = APIRouter(tags=["economy"])

ERRORS = (alchemy.AlchemyError, inscription.InscribeError, pets.PetError, shop.ShopError, social.SocialError)


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except ERRORS as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


class RecipeIn(BaseModel):
    recipe_id: str = Field(max_length=32)


class AlchemyFinishIn(BaseModel):
    session_id: str = Field(max_length=36)
    timings: list[int] = Field(max_length=10)
    pinyin_answers: list[str | None] = Field(max_length=10)


class InscribeIn(BaseModel):
    instance_id: int
    word_id: str = Field(max_length=40)


class EraseIn(BaseModel):
    instance_id: int
    index: int


class PetIn(BaseModel):
    pet_id: int | None = None


class BuyIn(BaseModel):
    item_id: str = Field(max_length=40)
    qty: int = 1
    rarity: str | None = Field(default=None, max_length=12)


class InstanceIn(BaseModel):
    instance_id: int


class GiftIn(BaseModel):
    friend_id: int
    item_id: str = Field(max_length=40)
    qty: int = 1


# ---------------------------------------------------------------- luyện đan
@router.get("/alchemy")
async def alchemy_view(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, alchemy.overview(db, user))


@router.post("/alchemy/start")
async def alchemy_start(body: RecipeIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, alchemy.start(db, user, body.recipe_id))


@router.post("/alchemy/finish")
async def alchemy_finish(body: AlchemyFinishIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, alchemy.finish(db, user, body.session_id, body.timings, body.pinyin_answers))


@router.post("/alchemy/furnace/upgrade")
async def furnace_upgrade(user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, alchemy.upgrade_furnace(db, user))


# ---------------------------------------------------------------- khắc văn
@router.get("/forge/inscribe/{instance_id}")
async def inscribe_options(instance_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await inscription.abandon_if_stale(db, user)
    return await _run(db, inscription.options(db, user, instance_id))


@router.post("/forge/inscribe/start")
async def inscribe_start(body: InscribeIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, inscription.start(db, user, body.instance_id, body.word_id))


@router.post("/forge/inscribe/erase")
async def inscribe_erase(body: EraseIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, inscription.erase(db, user, body.instance_id, body.index))


# ---------------------------------------------------------------- Linh Thú
@router.get("/pets")
async def pet_list(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await pets.overview(db, user)


@router.post("/pets/equip")
async def pet_equip(body: PetIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, pets.equip(db, user, body.pet_id))


# ---------------------------------------------------------------- Sạp Tạp Hóa
@router.get("/shop")
async def shop_view(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await shop.view(db, user)


@router.post("/shop/buy")
async def shop_buy(body: BuyIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, shop.buy(db, user, body.item_id, body.qty, body.rarity))


@router.post("/shop/sell_equipment")
async def shop_sell_equipment(body: InstanceIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, shop.sell_equipment(db, user, body.instance_id))


# ---------------------------------------------------------------- presents
@router.post("/friends/gift")
async def friend_gift(body: GiftIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.gift(db, user, body.friend_id, body.item_id, body.qty))
