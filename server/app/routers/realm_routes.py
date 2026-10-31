"""Stage 9 REST: what the Cổng Bí Cảnh shows (realms, opening hours, entries left today, the
party and the queue) and the forge for Mảnh Bảo Vật. Entering, the party and the run itself
go through the WebSocket (docs/PROTOCOL.md)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import api_error, current_user, write_user
from ..db import get_db
from ..models import User
from ..systems import secret_realm

router = APIRouter(tags=["realm"])


class ForgeIn(BaseModel):
    piece: str = Field(max_length=40)


@router.get("/realms")
async def realms_view(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await secret_realm.view(db, user)


@router.post("/realm/forge")
async def realm_forge(body: ForgeIn, user: User = Depends(write_user), db: AsyncSession = Depends(get_db)):
    try:
        out = await secret_realm.forge(db, user, body.piece)
    except secret_realm.RealmError as e:
        await db.rollback()
        raise api_error(e.status, e.code, e.message_vi)
    await db.commit()
    return out
