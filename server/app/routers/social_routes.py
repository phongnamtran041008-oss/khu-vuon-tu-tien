from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import User
from ..systems import social

router = APIRouter(tags=["social"])


class NameIn(BaseModel):
    display_name: str = Field(max_length=40)


class UserIn(BaseModel):
    user_id: int


class HelpIn(BaseModel):
    friend_id: int
    plot_id: int


class ReportIn(BaseModel):
    user_id: int
    message: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=300)


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
    except social.SocialError as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out


@router.get("/friends")
async def friends(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await social.list_friends(db, user)


@router.post("/friends/request")
async def friend_request(body: NameIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.request(db, user, body.display_name))


@router.post("/friends/accept")
async def friend_accept(body: UserIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.accept(db, user, body.user_id))


@router.post("/friends/decline")
async def friend_decline(body: UserIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.decline(db, user, body.user_id))


@router.post("/friends/remove")
async def friend_remove(body: UserIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.remove(db, user, body.user_id))


@router.get("/friends/{friend_id}/garden")
async def friend_garden(friend_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await social.visit(db, user, friend_id)
    except social.SocialError as e:
        raise api_error(e.status, e.code, e.message_vi)


@router.post("/friends/help")
async def friend_help(body: HelpIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.start_help(db, user, body.friend_id, body.plot_id))


@router.get("/blocks")
async def blocks(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await social.list_blocks(db, user)


@router.post("/blocks")
async def block(body: UserIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.block(db, user, body.user_id))


@router.post("/blocks/remove")
async def unblock(body: UserIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.unblock(db, user, body.user_id))


@router.post("/reports")
async def report(body: ReportIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    return await _run(db, social.report(db, user, body.user_id, body.message, body.reason))
