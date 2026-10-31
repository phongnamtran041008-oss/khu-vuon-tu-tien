"""Stage 4 acceptance (spec 20): one player goes from Phàm Nhân to Trúc Cơ through the real
server (WebSocket + REST), with BALANCE_PROFILE=dev and TIME_SCALE.

The bot walks with a path search on the same Tiled maps, finishes the main quest chain
(talk to Trúc Lão, hunt Mực Con and Thanh Điệu Yêu, meditate at home, beat the Mặc Hồ
for a Trúc Cơ Đan) and passes Thiên Kiếp. It reads answers from the database, as a
player who knows the words would."""
from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

import httpx
import pytest
from websockets.asyncio.client import connect

from app.config import PROTOCOL_VERSION
from app.realtime import maps, movement
from tests.helpers import correct_answer
from tests.test_ws import LOOK, SERVER_DIR, free_port

SPEED = 74.0


@pytest.fixture(scope="module")
def dev_server():
    tmp = Path(tempfile.mkdtemp(prefix="kvtt_journey_"))
    db = tmp / "j.db"
    port = free_port()
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{db}", AUTO_MIGRATE="1", RATE_LIMIT="0",
               ENV="dev", TIME_SCALE="100", BALANCE_PROFILE="dev", ALLOW_UNREVIEWED="1")
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
    yield {"url": url, "ws": f"ws://127.0.0.1:{port}/ws", "db": db, "log": tmp / "server.log"}
    proc.terminate()
    proc.wait(10)
    log.close()


def sql(db: Path, q: str, args=()):
    con = sqlite3.connect(db)
    try:
        rows = con.execute(q, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


class Bot:
    def __init__(self, server, token: str, uid: int):
        self.s, self.token, self.uid = server, token, uid
        self.h = {"Authorization": f"Bearer {token}"}
        self.http = httpx.AsyncClient(base_url=server["url"], headers=self.h, timeout=20)
        self.ws = None
        self.seq = 0
        self.zone = "abode"
        self.x = self.y = 0.0
        self.me = None
        self.ents: dict[str, dict] = {}
        self.questions: deque = deque()
        self.log: list[dict] = []
        self.kills: dict[str, int] = {}
        self.map = None

    # ---------------------------------------------------------------- network
    async def open(self):
        self.ws = await connect(self.s["ws"], max_size=1 << 20)
        await self.ws.send(json.dumps({"t": "hello", "v": PROTOCOL_VERSION, "token": self.token}))
        self.reader = asyncio.create_task(self._read())
        await self.wait_for(lambda: any(m["t"] == "welcome" for m in self.log), 5, "welcome")

    async def _read(self):
        names = {"Mực Con": "ink_slime", "Thanh Điệu Yêu": "tone_wisp", "Mặc Hồ": "ink_fox"}
        async for raw in self.ws:
            m = json.loads(raw)
            t = m.get("t")
            if t == "snap":
                self.me = m["me"]
                for e in m.get("add", []):
                    self.ents[e["id"]] = {"k": e["k"], "type": e.get("type"), "x": e["x"], "y": e["y"],
                                          "alive": e.get("alive", 1), "sh": e.get("sh", 0)}
                for e in m.get("e", []):
                    if e[0] in self.ents:
                        d = self.ents[e[0]]
                        d["x"], d["y"] = e[1], e[2]
                        if len(e) >= 8:
                            d["sh"], d["alive"] = e[6], e[7]
                for eid in m.get("rm", []):
                    self.ents.pop(eid, None)
                continue
            self.log.append(m)
            if t == "q":
                self.questions.append(m["q"])
            elif t == "zone":
                self.zone = m["zone"]
                self.x, self.y = float(m["x"]), float(m["y"])
                self.seq = max(self.seq, m.get("ack", -1) + 1)
                self.ents.clear()
                if self.zone != "abode":
                    self.map = maps.load(self.zone)
            elif t == "loot":
                k = names[m["monster"]]
                self.kills[k] = self.kills.get(k, 0) + 1
            elif t == "dead":
                raise AssertionError(f"the bot died: {self.log[-10:]}")

    async def wait_for(self, pred, timeout, what):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if pred():
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"timed out waiting for {what}; last: {self.log[-8:]}")

    async def answer_questions(self):
        while self.questions:
            q = self.questions.popleft()
            key = json.loads(sql(self.s["db"], "select answer_key from quiz_sessions where id=?",
                                 (q["session_id"],))[0][0])
            r = await self.http.post("/quiz/answer", json={"session_id": q["session_id"],
                                                          "answer": correct_answer(q["qtype"], key)})
            assert r.status_code in (200, 409), r.text   # 409: the shield broke from another question
        await asyncio.sleep(0)

    # ---------------------------------------------------------------- walking
    def _path(self, goal_ok) -> list[tuple[float, float]]:
        col, cell = self.map.collider, 8
        w, h = self.map.width_px // cell, self.map.height_px // cell

        def free(cx, cy):
            return 0 <= cx < w and 0 <= cy < h and not col.blocked(cx * cell + 4, cy * cell + 6)
        start = (int(self.x // cell), int(self.y // cell))
        prev = {start: None}
        dq = deque([start])
        goal = None
        while dq:
            c = dq.popleft()
            if goal_ok(c[0] * cell + 4, c[1] * cell + 6):
                goal = c
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n not in prev and free(*n):
                    prev[n] = c
                    dq.append(n)
        assert goal is not None, "no path"
        out = []
        while goal is not None:
            out.append((goal[0] * cell + 4, goal[1] * cell + 6))
            goal = prev[goal]
        return out[::-1]

    async def step_towards(self, wx, wy):
        dx = 0 if abs(wx - self.x) < 1.5 else (1 if wx > self.x else -1)
        dy = 0 if abs(wy - self.y) < 1.5 else (1 if wy > self.y else -1)
        if dx or dy:
            ms = 50
            self.x, self.y = movement.step(self.x, self.y, dx, dy, ms, SPEED, self.map.collider)
            await self.ws.send(json.dumps({"t": "in", "s": self.seq, "k": [[dx, dy, ms]]}))
            self.seq += 1
        await asyncio.sleep(0.05)

    async def resync(self):
        await asyncio.sleep(0.25)
        if self.me:
            self.x, self.y = float(self.me[0]), float(self.me[1])

    async def walk(self, goal_ok, timeout=60, stop=lambda: False):
        end = time.monotonic() + timeout
        path = self._path(goal_ok)
        i = 0
        while i < len(path) and time.monotonic() < end:
            if stop():
                return
            if self.questions:  # Hộ Thể: answer first, then go on from where the server has us
                await self.answer_questions()
                await self.resync()
                path, i = self._path(goal_ok), 0
                continue
            wx, wy = path[i]
            if abs(wx - self.x) < 2 and abs(wy - self.y) < 2:
                i += 1
                continue
            bx, by = self.x, self.y
            await self.step_towards(wx, wy)
            if (self.x, self.y) == (bx, by):  # stuck on a corner: skip ahead
                i += 1
        await self.resync()

    async def go_portal(self, target: str):
        zone_map = self.map
        portal = next(a for a in zone_map.portals if a.props["target"] == target)
        inner = lambda x, y: portal.x + 4 <= x <= portal.x + portal.w - 4 and portal.y + 4 <= y <= portal.y + portal.h - 4  # noqa: E731
        await self.walk(inner, timeout=90)
        cx, cy = portal.x + portal.w / 2, portal.y + portal.h / 2
        for _ in range(30):  # the last few pixels into the gate
            if portal.contains(self.x, self.y):
                break
            await self.step_towards(cx, cy)
        await self.resync()
        await self.ws.send(json.dumps({"t": "join", "zone": target, "via": "portal"}))
        await self.wait_for(lambda: self.zone == target, 10, f"zone {target}")

    # ---------------------------------------------------------------- fighting
    async def hunt(self, kind: str, count: int, timeout=150):
        end = time.monotonic() + timeout
        while self.kills.get(kind, 0) < count:
            assert time.monotonic() < end, f"hunting {kind}: {self.kills}; {self.log[-6:]}"
            await self.answer_questions()
            alive = [(eid, e) for eid, e in self.ents.items() if e["k"] == "m" and e["type"] == kind and e["alive"]]
            if not alive:  # walk around the forest until one shows up
                area = next(a for a in self.map.monster_areas if a.props["monster"] == kind)
                await self.walk(lambda x, y: area.contains(x, y), timeout=30,
                                stop=lambda: any(e["type"] == kind and e["alive"] for e in self.ents.values()))
                await asyncio.sleep(0.3)
                continue
            eid, e = min(alive, key=lambda it: math.hypot(it[1]["x"] - self.x, it[1]["y"] - self.y))
            if math.hypot(e["x"] - self.x, e["y"] - self.y) > 30:
                ex, ey = e["x"], e["y"]
                await self.walk(lambda x, y: math.hypot(x - ex, y - ey) < 24, timeout=20,
                                stop=lambda: math.hypot(e["x"] - self.x, e["y"] - self.y) < 30)
                continue
            await self.ws.send(json.dumps({"t": "atk", "id": eid}))
            await asyncio.sleep(0.75)

    async def claim(self, quest_id: str) -> dict:
        r = await self.http.post("/quests/claim", json={"quest_id": quest_id})
        assert r.status_code == 200, r.text
        return r.json()


async def test_pham_nhan_to_truc_co(dev_server):
    s = dev_server
    r = httpx.post(s["url"] + "/auth/register", json={"username": "hanhtrinh", "password": "matkhau1"}).json()
    token, uid = r["token"], r["user_id"]
    h = {"Authorization": f"Bearer {token}"}
    httpx.post(s["url"] + "/character/create", json={"display_name": "Lữ Khách", "appearance": LOOK},
               headers=h).raise_for_status()
    # words the player has learned in the garden (the garden flow itself is tested in stage 2)
    words = sql(s["db"], "select id from words where tier=1 and hanzi in ('水','火','木','山','人','日','口','大')")
    for (wid,) in words:
        sql(s["db"], "insert or replace into collection(user_id, word_id, introduced, mastery, times_correct, "
                     "times_wrong, needs_review, first_seen_at) values (?, ?, 1, 60, 0, 0, 0, datetime('now'))",
            (uid, wid))
    bot = Bot(s, token, uid)
    await bot.open()
    assert (await bot.http.get("/cultivation")).json()["label"] == "Phàm Nhân"

    # 1. down to the village, Trúc Lão gives the Bút Lông Gỗ
    await bot.ws.send(json.dumps({"t": "join", "zone": "truc_lam_thon", "via": "abode"}))
    await bot.wait_for(lambda: bot.zone == "truc_lam_thon", 5, "village")
    await bot.http.get("/quests")
    tx, ty = bot.map.npcs["truc_lao"]
    await bot.walk(lambda x, y: math.hypot(x - tx, y - ty) < 40, timeout=60)
    r = await bot.http.post("/quests/talk", json={"npc": "truc_lao"})
    assert r.json()["finished"][0]["id"] == "nm1_xuong_lang", r.text
    got = await bot.claim("nm1_xuong_lang")
    brush = got["rewards"]["equipment"][0]
    assert (await bot.http.post("/equipment/equip", json={"instance_id": brush["id"]})).json()["stats"]["weapon"] \
        == "brush"

    # 2-3. the forest: Mực Con and Thanh Điệu Yêu
    await bot.go_portal("rung_muc_loang")
    await bot.hunt("ink_slime", 3)
    await bot.claim("nm2_muc_con")
    await bot.hunt("tone_wisp", 2)
    await bot.claim("nm3_thanh_dieu")

    # 4. home to meditate (one question every 2 minutes, divided by TIME_SCALE)
    await bot.go_portal("truc_lam_thon")
    await bot.go_portal("abode")
    for _ in range(2):
        for _try in range(50):
            r = await bot.http.post("/cultivation/meditate")
            if r.status_code == 200:
                break
            assert r.json()["error"]["code"] == "meditate_wait", r.text
            await asyncio.sleep(0.2)
        q = r.json()
        key = json.loads(sql(s["db"], "select answer_key from quiz_sessions where id=?", (q["session_id"],))[0][0])
        res = (await bot.http.post("/quiz/answer", json={"session_id": q["session_id"],
                                                        "answer": correct_answer(q["qtype"], key)})).json()
        assert res["correct"]
    await bot.claim("nm4_da_toa")

    # 5. the Mặc Hồ (elite: its shield comes back at half health)
    await bot.ws.send(json.dumps({"t": "join", "zone": "truc_lam_thon", "via": "abode"}))
    await bot.wait_for(lambda: bot.zone == "truc_lam_thon", 5, "village again")
    await bot.go_portal("rung_muc_loang")
    await bot.hunt("ink_fox", 1, timeout=200)
    await bot.claim("nm5_mac_ho")
    cult = (await bot.http.get("/cultivation")).json()
    assert cult["realm"] == "luyen_khi" and cult["stage"] == 9 and cult["xp"] == cult["need"], cult
    assert cult["can_tribulation"] and cult["has_pill"]

    # 6. Thiên Kiếp: 20 questions over the whole HSK 1 list, 30 s each
    q = (await bot.http.post("/cultivation/breakthrough/start")).json()["question"]
    res = None
    while q:
        key = json.loads(sql(s["db"], "select answer_key from quiz_sessions where id=?", (q["session_id"],))[0][0])
        res = (await bot.http.post("/quiz/answer", json={"session_id": q["session_id"],
                                                        "answer": correct_answer(q["qtype"], key)})).json()
        q = res.get("next")
    assert res["tribulation"]["passed"] and res["tribulation"]["realm"] == "truc_co"
    await bot.wait_for(lambda: any(m["t"] == "stats" and m["realm"] == "truc_co" for m in bot.log), 5, "stats")
    done = (await bot.http.get("/quests")).json()["quests"]
    assert done[0]["id"] == "nm6_thien_kiep" and done[0]["state"] == "done"
    got = await bot.claim("nm6_thien_kiep")
    assert got["rewards"]["immortal_jade"] > 0
    cult = (await bot.http.get("/cultivation")).json()
    assert cult["label"] == "Trúc Cơ sơ kỳ"
    book = (await bot.http.get("/codex/monster")).json()
    met = [e for e in book["entries"] if e.get("kills")]          # (Thủ Vườn and bí cảnh monsters are not met here)
    assert book["found"] == 3 and len(met) == 3
    bot.reader.cancel()
    await bot.ws.close()
    await bot.http.aclose()
