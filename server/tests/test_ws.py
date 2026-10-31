"""Stage 3 end to end: a real server process, real WebSocket clients (spec 15.1)."""
import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.config import PROTOCOL_VERSION

SERVER_DIR = Path(__file__).resolve().parents[1]
LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    tmp = Path(tempfile.mkdtemp(prefix="kvtt_ws_"))
    db = tmp / "ws.db"
    port = free_port()
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{db}", AUTO_MIGRATE="1", RATE_LIMIT="0",
               ACCOUNTS_PER_IP="100", ENV="dev", TIME_SCALE="1")
    log = open(tmp / "server.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=SERVER_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
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
    yield {"url": url, "ws": f"ws://127.0.0.1:{port}/ws", "db": db, "log": tmp / "server.log"}
    proc.terminate()
    proc.wait(10)
    log.close()


def make_player(server, username: str, display: str) -> str:
    r = httpx.post(server["url"] + "/auth/register", json={"username": username, "password": "matkhau1"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    r = httpx.post(server["url"] + "/character/create", json={"display_name": display, "appearance": LOOK},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return token


class Client:
    def __init__(self, ws):
        self.ws = ws
        self.seq = 0
        self.inbox: list[dict] = []

    @classmethod
    async def open(cls, server, token, v=PROTOCOL_VERSION):
        ws = await connect(server["ws"])
        c = cls(ws)
        await c.send({"t": "hello", "v": v, "token": token})
        return c

    async def send(self, msg):
        await self.ws.send(json.dumps(msg))

    async def expect(self, t: str, timeout: float = 5.0, pred=lambda m: True) -> dict:
        end = time.monotonic() + timeout
        for i, m in enumerate(self.inbox):
            if m.get("t") == t and pred(m):
                return self.inbox.pop(i)
        while time.monotonic() < end:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), max(0.01, end - time.monotonic()))
            except asyncio.TimeoutError:
                break
            m = json.loads(raw)
            if m.get("t") == t and pred(m):
                return m
            self.inbox.append(m)
        raise AssertionError(f"no {t!r} message; got {[m.get('t') for m in self.inbox][-15:]}; "
                             f"errors {[m for m in self.inbox if m.get('t') == 'error']}")

    async def walk(self, dx, dy, seconds):
        for _ in range(int(seconds / 0.05)):
            await self.send({"t": "in", "s": self.seq, "k": [[dx, dy, 17], [dx, dy, 17], [dx, dy, 16]]})
            self.seq += 1
            await asyncio.sleep(0.05)

    async def close(self):
        await self.ws.close()


async def test_bad_token_and_old_version(server):
    c = await Client.open(server, "not-a-token")
    err = await c.expect("error")
    assert err["code"] == "bad_token"
    with pytest.raises(ConnectionClosed):
        await c.ws.recv()
    assert c.ws.close_code == 4003
    tok = make_player(server, "ws_old", "Bản Cũ")
    c = await Client.open(server, tok, v=PROTOCOL_VERSION - 1)   # a stage-3 game
    assert (await c.expect("error"))["code"] == "version"


async def test_two_players_see_each_other_and_chat(server):
    ta, tb = make_player(server, "ws_an", "An An"), make_player(server, "ws_binh", "Bình Bình")
    a, b = await Client.open(server, ta), await Client.open(server, tb)
    wa = await a.expect("welcome")
    await b.expect("welcome")
    assert wa["zone"] == "abode" and wa["you"]["name"] == "An An"
    await a.send({"t": "join", "zone": "truc_lam_thon", "via": "abode"})
    za = await a.expect("zone")
    await b.send({"t": "join", "zone": "truc_lam_thon", "via": "abode"})
    await b.expect("zone")
    assert za["zone"] == "truc_lam_thon" and za["channel"] == 1
    snap = await b.expect("snap", pred=lambda m: any(e["id"] == f"p{wa['you']['uid']}" for e in m.get("add", [])))
    start = next(e for e in snap["add"] if e["k"] == "p")["y"]
    await a.walk(0, -1, 0.6)
    moved = await b.expect("snap", pred=lambda m: any(e[0] == wa["you"]["id"] and e[2] < start - 20
                                                      for e in m.get("e", [])))
    assert moved["st"] > snap["st"]
    me = await a.expect("snap", pred=lambda m: m["ack"] >= a.seq - 1, timeout=3)
    assert me["me"][1] < za["y"] - 20
    await a.send({"t": "chat", "ch": "zone", "text": "Chào đạo hữu!"})
    msg = await b.expect("chat")
    assert msg["text"] == "Chào đạo hữu!" and msg["from"]["name"] == "An An" and msg["ch"] == "zone"
    await asyncio.sleep(2.1)
    await b.send({"t": "chat", "ch": "world", "text": "vcl"})
    assert (await a.expect("chat", pred=lambda m: m["ch"] == "world"))["text"] == "***"
    await a.send({"t": "ping", "c": 1.5})
    assert (await a.expect("pong"))["c"] == 1.5
    await a.close()
    await b.close()


async def test_new_login_kicks_old_and_resumes(server):
    tok = make_player(server, "ws_kick", "Hai Máy")
    a = await Client.open(server, tok)
    await a.expect("welcome")
    await a.send({"t": "join", "zone": "truc_lam_thon", "via": "abode"})
    z = await a.expect("zone")
    a2 = await Client.open(server, tok)
    kicked = await a.expect("kicked")
    assert kicked["reason"] == "elsewhere"
    w2 = await a2.expect("welcome")
    assert w2["zone"] == "truc_lam_thon"   # still standing there: resume
    await a2.send({"t": "join", "zone": "truc_lam_thon", "via": "resume"})
    z2 = await a2.expect("zone")
    assert (z2["x"], z2["y"]) == (z["x"], z["y"])
    await a2.close()


async def test_flooding_closes_the_connection(server):
    tok = make_player(server, "ws_flood", "Gõ Nhanh")
    c = await Client.open(server, tok)
    await c.expect("welcome")
    for _ in range(45):
        await c.send({"t": "ping"})
    kicked = await c.expect("kicked")
    assert kicked["reason"] == "flood"


async def test_back_to_abode_saves_position(server):
    tok = make_player(server, "ws_home", "Về Nhà")
    c = await Client.open(server, tok)
    welcome = await c.expect("welcome")
    await c.send({"t": "join", "zone": "truc_lam_thon", "via": "abode"})
    await c.expect("zone")
    await c.walk(0, 1, 0.8)  # the gate is just south of where you arrive
    await c.send({"t": "join", "zone": "abode", "via": "portal"})
    z = await c.expect("zone", pred=lambda m: m["zone"] == "abode")
    assert z["f"] == "up"
    uid = welcome["you"]["uid"]
    for _ in range(50):
        con = sqlite3.connect(server["db"])
        row = con.execute("select zone_id from characters where user_id=?", (uid,)).fetchone()
        con.close()
        if row[0] == "abode":
            break
        await asyncio.sleep(0.1)
    assert row[0] == "abode"
    await c.close()


async def test_zone_saved_on_disconnect_and_resumed_next_login(server):
    tok = make_player(server, "ws_resume", "Ở Lại")
    c = await Client.open(server, tok)
    await c.expect("welcome")
    await c.send({"t": "join", "zone": "truc_lam_thon", "via": "abode"})
    await c.expect("zone")
    await c.close()
    # lingering: a new connection resumes in the village
    c = await Client.open(server, tok)
    assert (await c.expect("welcome"))["zone"] == "truc_lam_thon"
    await c.close()


async def test_admin_ban_over_the_real_socket(server):
    """Stage 10: `/admin ...` typed in chat by an admin bans and kicks a live player."""
    ta, tb = make_player(server, "ws_admin", "Chưởng Môn"), make_player(server, "ws_phamnhan", "Phàm Nhân")
    con = sqlite3.connect(server["db"])
    con.execute("UPDATE users SET is_admin = 1 WHERE username = 'ws_admin'")
    con.commit()
    con.close()
    a, b = await Client.open(server, ta), await Client.open(server, tb)
    await a.expect("welcome")
    await b.expect("welcome")
    await b.send({"t": "chat", "ch": "world", "text": "/admin announce ta là admin"})
    assert (await b.expect("admin"))["ok"] is False
    await a.send({"t": "chat", "ch": "world", "text": "/admin ban Phàm Nhân 1h thử nghiệm"})
    reply = await a.expect("admin")
    assert reply["ok"], reply
    kicked = await b.expect("kicked")
    assert kicked["reason"] == "banned" and "thử nghiệm" in kicked["message_vi"]
    assert not [m for m in a.inbox if m.get("t") == "chat" and "/admin" in m.get("text", "")]
    r = httpx.post(server["url"] + "/auth/login", json={"username": "ws_phamnhan", "password": "matkhau1"})
    assert r.status_code == 403
    b2 = await Client.open(server, tb)
    assert (await b2.expect("error"))["code"] == "banned"
    await a.close()


def test_stats_endpoint(server):
    s = httpx.get(server["url"] + "/server/stats").json()
    assert s["ticks"] > 0 and s["tick_max_ms"] < 1000
