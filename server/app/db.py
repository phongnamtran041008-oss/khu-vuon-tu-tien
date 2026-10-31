from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

try:  # SQLAlchemy 2.1 no longer installs greenlet itself, and the async engine needs it
    import greenlet  # noqa: F401
except ImportError as e:  # pragma: no cover - environment problem, explained to the user
    raise SystemExit(
        "\n[LOI] Thieu thu vien 'greenlet' (SQLAlchemy can no de chay bat dong bo).\n"
        "Chay lenh:  python -m pip install -r requirements.txt\n"
        "(trong thu muc server), roi mo lai may chu.\n") from e

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None) -> AsyncEngine:
    url = url or settings.database_url
    if url.startswith("sqlite"):
        eng = create_async_engine(url, connect_args={"timeout": 30})

        @event.listens_for(eng.sync_engine, "connect")
        def _pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
        return eng
    # Small pool: free Postgres tiers (Neon) bill compute time per open connection.
    # Neon's "-pooler" host is PgBouncer in transaction mode, where asyncpg's prepared
    # statement cache breaks; the direct host is recommended, but both work.
    args = {"statement_cache_size": 0} if "-pooler." in url else {}
    eng = create_async_engine(url, pool_size=settings.db_pool_size, max_overflow=2,
                              pool_pre_ping=True, pool_recycle=300, connect_args=args)

    @event.listens_for(eng.sync_engine, "checkout")
    def _used(*_):  # noqa: ANN002
        _last_checkout[0] = time.monotonic()
    return eng


_last_checkout = [time.monotonic()]


async def close_idle_connections() -> None:
    """Background task: drop the pooled connections once nothing has used the database for
    DB_IDLE_CLOSE_SECONDS, so Neon can scale to zero. The next query simply reconnects."""
    idle = settings.db_idle_close_seconds
    if idle <= 0 or engine.url.get_backend_name() == "sqlite":
        return
    while True:
        await asyncio.sleep(min(30, idle))
        pool = engine.pool
        if pool.checkedout() == 0 and pool.checkedin() > 0 and time.monotonic() - _last_checkout[0] >= idle:
            await engine.dispose()


engine: AsyncEngine = make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def configure(url: str) -> None:
    """Re-point the app at another database (used by tests)."""
    global engine, SessionLocal
    engine = make_engine(url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
