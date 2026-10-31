"""WebSocket endpoint /ws (spec 15.1). The first message must be `hello` with the
protocol version and the JWT; after that the connection reads messages into the world
and a writer task sends whatever the world queued for this session."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import balance
from .. import db as dbm
from ..auth import user_from_token
from ..models import Character
from . import protocol
from .world import CLOSE, Session, world

router = APIRouter()
log = logging.getLogger("khu_vuon.ws")


def cfg() -> dict:
    return balance.load("world")


async def _reject(ws: WebSocket, code: str, message_vi: str, close_code: int = 4000) -> None:
    try:
        await ws.send_text(json.dumps(protocol.error(code, message_vi), ensure_ascii=False))
        await ws.close(close_code)
    except Exception:  # the client may already be gone
        pass


async def _authenticate(ws: WebSocket):
    c = cfg()
    try:
        raw = await asyncio.wait_for(ws.receive_text(), c["hello_timeout_seconds"])
        hello = protocol.Hello.model_validate(json.loads(raw))
    except (asyncio.TimeoutError, ValueError, TypeError):
        await _reject(ws, "no_hello", "Kết nối không hợp lệ.")
        return None
    except WebSocketDisconnect:
        return None
    if hello.v != protocol.PROTOCOL_VERSION:
        await _reject(ws, "version", "Phiên bản game đã cũ, hãy cập nhật để chơi tiếp.", 4002)
        return None
    async with dbm.SessionLocal() as db:
        try:
            user = await user_from_token(db, hello.token)
        except HTTPException as e:
            d = e.detail if isinstance(e.detail, dict) else {}
            await _reject(ws, d.get("code", "bad_token"), d.get("message_vi", "Phiên đăng nhập không hợp lệ."), 4003)
            return None
        ch = await db.get(Character, user.id)
        if ch is None:
            await _reject(ws, "no_character", "Bạn chưa tạo nhân vật.", 4004)
            return None
    return user, ch


async def _writer(ws: WebSocket, s: Session) -> None:
    try:
        while True:
            msg = await s.outbox.get()
            if msg is CLOSE:
                await ws.close(s.close_code)
                return
            await ws.send_text(json.dumps(msg, ensure_ascii=False, separators=(",", ":")))
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        pass


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    auth = await _authenticate(ws)
    if auth is None:
        return
    user, character = auth
    s = await world.connect(user, character)
    writer = asyncio.create_task(_writer(ws, s))
    c = cfg()
    try:
        while not s.closed:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), c["idle_timeout_seconds"])
            except asyncio.TimeoutError:  # no heartbeat for too long
                s.close(4005, {"t": "kicked", "reason": "timeout", "message_vi": "Mất kết nối quá lâu."})
                break
            if s.closed:
                break
            if not s.allow_message(world.mono()):
                s.close(4008, {"t": "kicked", "reason": "flood", "message_vi": "Gửi dữ liệu quá nhanh."})
                break
            if len(raw) > c["ws_message_max_bytes"]:
                s.send(protocol.error("too_big", "Gói tin quá lớn."))
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                s.send(protocol.error("bad_json", "Gói tin không hợp lệ."))
                continue
            await world.handle(s, data)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        log.exception("websocket error for user %s", s.user_id)
    finally:
        world.disconnect(s)
        if not s.closed:
            s.close(1000)
        try:
            await asyncio.wait_for(writer, 2.0)
        except (asyncio.TimeoutError, Exception):
            writer.cancel()
