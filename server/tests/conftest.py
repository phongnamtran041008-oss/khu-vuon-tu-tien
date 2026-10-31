import os
import sys
import tempfile
from pathlib import Path

if "KVTT_TEST_DB" not in os.environ:  # guard: this module must configure the DB only once
    os.environ["KVTT_TEST_DB"] = str(Path(tempfile.mkdtemp(prefix="kvtt_test_")) / "test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.environ['KVTT_TEST_DB']}"
os.environ["TIME_SCALE"] = "1"
os.environ["ENV"] = "dev"
os.environ["ALLOW_UNREVIEWED"] = "1"
os.environ["AUTO_MIGRATE"] = "0"
os.environ["RATE_LIMIT"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app import clock, models  # noqa: E402
from app import db as dbm  # noqa: E402
from app.auth import limiter  # noqa: E402
from app.main import create_app, run_migrations, sync_words  # noqa: E402


@pytest.fixture(scope="session")
def migrated():
    run_migrations(os.environ["DATABASE_URL"])  # the real Alembic migration, not create_all
    return True


@pytest.fixture
def frozen():
    c = clock.FrozenClock()
    clock.set_clock(c)
    yield c
    clock.set_clock(clock.Clock())


@pytest_asyncio.fixture
async def app(migrated, frozen):
    await sync_words()
    yield create_app(use_lifespan=False)
    async with dbm.SessionLocal() as db:  # clean tables between tests
        for t in reversed(models.Base.metadata.sorted_tables):
            if t.name != "words":
                await db.execute(delete(t))
        await db.commit()
    limiter.reset()


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db():
    async with dbm.SessionLocal() as s:
        yield s


