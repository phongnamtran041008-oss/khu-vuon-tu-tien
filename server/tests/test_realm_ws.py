"""Stage 9 end to end (spec 20): a real server process and three bots on three real WebSocket
connections form a party, enter a bí cảnh and clear it; each player gets their own loot, once.
The bots are tools/realm_bots.py (they only see what the server sends them)."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from tests.test_ws import free_port  # noqa: E402


@pytest.fixture(scope="module")
def dev_server():
    tmp = Path(tempfile.mkdtemp(prefix="kvtt_realm_"))
    db = tmp / "realm.db"
    port = free_port()
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{db}", AUTO_MIGRATE="1", RATE_LIMIT="0",
               ACCOUNTS_PER_IP="100", ENV="dev", TIME_SCALE="1", BALANCE_PROFILE="dev", ALLOW_UNREVIEWED="1")
    log = open(tmp / "server.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=ROOT / "server", env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if httpx.get(url + "/server/info", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError((tmp / "server.log").read_text())
    yield {"url": url, "db": db, "log": tmp / "server.log"}
    proc.terminate()
    proc.wait(10)
    log.close()


async def test_three_bots_clear_a_realm_over_websockets(dev_server):
    import realm_bots
    lines = []
    try:
        bots = await realm_bots.run_team(dev_server["url"], dev_server["db"], prefix="ws", timeout=600,
                                         log=lines.append)
    except RuntimeError as e:
        raise AssertionError(f"{e} / {dev_server['log'].read_text()[-4000:]}") from None
    try:
        assert all(b.ended and b.ended["result"] == "won" for b in bots), (lines, dev_server["log"].read_text()[-3000:])
        rooms = bots[0].ended["puzzles"] + 1
        con = sqlite3.connect(dev_server["db"])
        try:
            for b in bots:
                stages = sorted(r[0] for r in con.execute(
                    "select stage from realm_claims where user_id=?", (b.uid,)).fetchall())
                assert stages == sorted([f"room{i}" for i in range(rooms)] + ["chest"]), stages
                assert sorted(lt["stage"] for lt in b.loot) == stages      # told about their own loot only
                (result,) = con.execute("select result from realm_members where user_id=?", (b.uid,)).fetchone()
                assert result == "won"
        finally:
            con.close()
    finally:
        for b in bots:
            await b.close()
