"""FastAPI entry point: `uvicorn app.main:app` from the server/ folder."""
from __future__ import annotations

import asyncio
import gc
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import admin
from . import db as dbm
from .config import GAME_VERSION, SERVER_DIR, settings
from .garden import garden as _garden  # noqa: F401  (registers the garden quiz handler)
from .learning.wordbank import bank
from .models import Word
from .realtime import ws as ws_routes
from .realtime.world import world
from .routers import (auth_routes, bee_routes, economy_routes, fishing_routes, game_routes, realm_routes,
                      rpg_routes, server_routes, social_routes, td_routes)
from .systems import cultivation as _cultivation  # noqa: F401  (registers meditate/tribulation handlers)
from .systems import inscription as _inscription  # noqa: F401  (registers the khắc văn handler)

log = logging.getLogger("khu_vuon")


def run_migrations(url: str | None = None) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


async def sync_words() -> None:
    """Mirror the word JSON into the words table so seeds/plots can reference it."""
    b = bank()
    async with dbm.SessionLocal() as db:
        existing = {w.id: w for w in (await db.execute(select(Word))).scalars().all()}
        for w in b.words.values():
            row = existing.get(w.id)
            if row is None:
                db.add(Word(id=w.id, hanzi=w.hanzi, tier=w.tier, rarity=w.rarity))
            elif (row.hanzi, row.tier, row.rarity) != (w.hanzi, w.tier, w.rarity):
                row.hanzi, row.tier, row.rarity = w.hanzi, w.tier, w.rarity
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_migrate:
        await asyncio.to_thread(run_migrations, None)
    await sync_words()
    if await admin.sync_admin_usernames():
        log.info("ADMIN_USERNAMES: admin rights granted")
    world.preload()
    # everything loaded so far lives for the whole process: keep it out of the garbage
    # collector's full passes, which would otherwise pause the 20 Hz world tick
    gc.collect()
    gc.freeze()
    await world.start()
    idle_closer = asyncio.create_task(dbm.close_idle_connections(), name="db-idle-closer")
    lan_task = None
    if settings.lan_beacon:
        from . import lan
        lan_task = asyncio.create_task(lan.run(), name="lan-beacon")
    log.info("Khu Vườn Tu Tiên server ready (%d words)", len(bank().words))
    yield
    idle_closer.cancel()
    if lan_task:
        lan_task.cancel()
    await world.stop()  # saves every character still standing in the world
    await dbm.engine.dispose()


def create_app(use_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="Khu Vườn Tu Tiên", version=GAME_VERSION, lifespan=lifespan if use_lifespan else None)
    app.include_router(server_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(game_routes.router)
    app.include_router(social_routes.router)
    app.include_router(rpg_routes.router)
    app.include_router(bee_routes.router)
    app.include_router(fishing_routes.router)
    app.include_router(td_routes.router)
    app.include_router(economy_routes.router)
    app.include_router(realm_routes.router)
    app.include_router(ws_routes.router)

    @app.exception_handler(HTTPException)
    async def http_exc(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message_vi": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {
            "code": "bad_request", "message_vi": "Dữ liệu gửi lên không hợp lệ.",
            "details": [e.get("msg") for e in exc.errors()][:5]}})

    return app


app = create_app()
