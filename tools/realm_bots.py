#!/usr/bin/env python3
"""Bots that clear a bí cảnh together over a real WebSocket (stage 9 criterion: three clients or
bots clear one realm). Each bot is a separate connection that only knows what the server sends
it (snapshots, its own puzzle pieces) plus the map file and the word list every client has. They
"talk" to each other the way a party would in chat, through a shared Team object.

    # a server with the dev balance (the scheduled realm is always open):
    #   cd server && BALANCE_PROFILE=dev python -m uvicorn app.main:app --port 8000
    python tools/realm_bots.py --url http://127.0.0.1:8000 --db server/dev.db

The bots read Vấn Đạo answer keys from the server's database file (a stand-in for players who
know their words), so this only works next to a local server.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import httpx  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

from app.config import PROTOCOL_VERSION  # noqa: E402
from app.realtime import maps  # noqa: E402
from app.realtime.movement import step as move_step  # noqa: E402
from tests.helpers import correct_answer  # noqa: E402
from tests.realm_bot import Bot, Team  # noqa: E402

SPEED = 74.0
LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}


class Room:
    """What a bot knows about the room it stands in (the same questions realm_bot asks the
    in-process instance, answered from messages instead)."""

    def __init__(self, bot: "NetBot"):
        self.bot = bot
        self.map = maps.load("bi_canh")

    @property
    def kind(self):
        return self.bot.room["kind"] if self.bot.room else None

    @property
    def phase(self):
        b = self.bot
        return "running" if b.room and not b.cleared and not b.ended else "waiting"

    def objs(self, kind):
        return [o for o in self.map.realm_objs if o.props.get("room") == self.kind and o.props.get("kind") == kind]

    def room_center(self):
        a = self.map.rooms[self.kind]
        return a.x + a.w / 2, a.y + a.h / 2

    @property
    def monsters(self):
        return [SimpleNamespace(eid=e["id"], x=e["x"], y=e["y"], alive=bool(e["alive"]))
                for e in self.bot.ents.values() if e["k"] == "m"]

    @property
    def boss(self):
        return next((m for m in self.monsters if self.bot.ents[m.eid].get("type") == "nghien_ma"), None)


class NetBot(Bot):
    def __init__(self, url: str, token: str, uid: int, name: str, team: Team, keyfn, record: bool = False):
        self.url, self.token, self.name = url, token, name
        self.http = httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        self.keyfn = keyfn
        super().__init__(SimpleNamespace(mono=time.monotonic), None, None, uid, SimpleNamespace(sent=[]), team,
                         self._answer)
        self.ws = None
        self.zone = None
        self.me = SimpleNamespace(x=0.0, y=0.0, dead=False, ghost=False, hp=1.0,
                                  channel=SimpleNamespace(map=maps.load("bi_canh")), protected=lambda now: False)
        self.pending: deque = deque()
        self.ents: dict[str, dict] = {}
        self.q_open = False
        self.cleared = False
        self.record: list | None = [] if record else None
        self.room_view = Room(self)
        self.party_ok = asyncio.Event()

    # ------------------------------------------------------------ the bits realm_bot reads
    @property
    def p(self):
        return self.me if self.zone == "bi_canh" else None

    @property
    def inst(self):
        return self.room_view if self.zone == "bi_canh" else None

    async def send(self, msg: dict):
        await self.ws.send(json.dumps(msg))

    async def _answer(self, bot, q):
        key = self.keyfn(q["session_id"])
        r = await self.http.post("/quiz/answer", json={"session_id": q["session_id"],
                                                       "answer": correct_answer(q["qtype"], key)})
        self.q_open = False
        return r.json()

    async def move(self) -> None:
        """realm_bot's step, plus the client-side prediction a real game does."""
        p = self.p
        if p is None or not self.route or self.q_open or (p.dead and not p.ghost):
            return
        while self.route and math.hypot(self.route[0][0] - p.x, self.route[0][1] - p.y) < 0.2:
            self.route.pop(0)
        if not self.route:
            return
        tx, ty = self.route[0]
        dx, dy = tx - p.x, ty - p.y
        if abs(dy) > 0.1:
            d, st = abs(dy), (0, 1 if dy > 0 else -1)
        else:
            d, st = abs(dx), (1 if dx > 0 else -1, 0)
        ms = max(1, min(50, int(round(d / SPEED * 1000))))
        steps = [[st[0], st[1], ms]]
        await self.send({"t": "in", "s": self.seq, "k": steps})
        self.pending.append((self.seq, steps))
        self.seq += 1
        p.x, p.y = move_step(p.x, p.y, st[0], st[1], ms, SPEED, p.channel.map.collider)

    # ------------------------------------------------------------ the connection
    async def connect(self) -> None:
        ws_url = self.url.replace("http", "ws", 1) + "/ws"
        self.ws = await connect(ws_url, max_size=2 ** 22)
        await self.ws.send(json.dumps({"t": "hello", "v": PROTOCOL_VERSION, "token": self.token}))
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                if self.record is not None:
                    self.record.append((time.monotonic(), m))
                self.on_message(m)
        except Exception:
            pass

    def on_message(self, m: dict) -> None:
        t = m.get("t")
        if t == "welcome":
            asyncio.ensure_future(self.send({"t": "join", "zone": m["zone"], "via": "resume"}))
        elif t == "zone":
            self.zone = m["zone"]
            self.me.x, self.me.y = float(m["x"]), float(m["y"])
            self.pending.clear()
            self.ents.clear()
            self.route, self.goal = [], None
            if self.zone != "bi_canh":
                self.cleared = False
        elif t == "snap":
            ack = m.get("ack", -1)
            while self.pending and self.pending[0][0] <= ack:
                self.pending.popleft()
            me = m["me"]
            x, y = float(me[0]), float(me[1])
            col = self.me.channel.map.collider
            for _, steps in self.pending:
                for dx, dy, ms in steps:
                    x, y = move_step(x, y, dx, dy, ms, SPEED, col)
            self.me.x, self.me.y, self.me.hp = x, y, me[3]
            self.me.ghost = bool(me[8]) if len(me) > 8 else False
            self.me.dead = me[3] <= 0
            for e in m.get("add", []):
                self.ents[e["id"]] = {"id": e["id"], "k": e["k"], "type": e.get("type"), "x": e["x"], "y": e["y"],
                                      "alive": e.get("alive", 1)}
            for row in m.get("e", []):
                e = self.ents.get(row[0])
                if e is not None:
                    e["x"], e["y"] = row[1], row[2]
                    if len(row) >= 8:
                        e["alive"] = row[7]
            for eid in m.get("rm", []):
                self.ents.pop(eid, None)
        elif t == "q":
            self.q_open = True
            self.s.sent.append(m)
        elif t == "q_end":
            self.q_open = False
        elif t in ("error", "notice"):
            self.s.sent.append(m)
        elif t == "party":
            if m.get("event") == "invite":
                asyncio.ensure_future(self.send({"t": "party", "op": "accept", "uid": m["from"]["uid"]}))
            elif m.get("event") == "state":
                self.party = m["party"]
                self.party_ok.set()
        elif t == "realm":
            if m.get("event") == "cleared":
                self.cleared = True
            elif m.get("event") == "room":
                self.cleared = False
            self.s.sent.append(m)

    async def close(self) -> None:
        try:
            await self.ws.close()
        except Exception:
            pass
        await self.http.aclose()


# ------------------------------------------------------------------ setting up accounts
def sql(db: Path, q: str, args=()):
    con = sqlite3.connect(db)
    try:
        rows = con.execute(q, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def make_hero(url: str, db: Path, username: str, display: str, realm: str = "truc_co") -> tuple[str, int]:
    r = httpx.post(url + "/auth/register", json={"username": username, "password": "matkhau1"})
    if r.status_code == 409:
        r = httpx.post(url + "/auth/login", json={"username": username, "password": "matkhau1"})
    r.raise_for_status()
    token, uid = r.json()["token"], r.json()["user_id"]
    h = {"Authorization": f"Bearer {token}"}
    httpx.post(url + "/character/create", json={"display_name": display, "appearance": LOOK}, headers=h)
    gate = maps.load("truc_lam_thon").interacts["realm"]
    sql(db, "update characters set realm=?, realm_stage=1, zone_id='truc_lam_thon', x=?, y=?, hp=400 "
            "where user_id=?", (realm, gate[0], gate[1] + 14, uid))
    sql(db, "insert or ignore into collection(user_id, word_id, introduced, mastery, times_correct, times_wrong, "
            "needs_review, first_seen_at) select ?, id, 1, 60, 0, 0, 0, datetime('now') from words where tier=1", (uid,))
    # a good staff and robe, so a test run is about the rules rather than the fight
    for item, slot in (("gay_truc", "weapon"), ("mac_anh_bao", "body")):
        sql(db, "insert into equipment_instances(user_id, item_id, rarity, enhance_level, inscriptions, equipped_slot) "
                "values (?, ?, 'thien', 5, '[]', ?)", (uid, item, slot))
    return token, uid


def answer_keys(db: Path):
    def key(sid: str) -> dict:
        return json.loads(sql(db, "select answer_key from quiz_sessions where id=?", (sid,))[0][0])
    return key


# ------------------------------------------------------------------ a run
async def make_bots(url: str, db: Path, prefix: str, n: int, record: int | None = None) -> list[NetBot]:
    """n heroes at the Cổng Bí Cảnh, connected and standing in Trúc Lâm Thôn."""
    team = Team()
    keyfn = answer_keys(db)
    bots = []
    for i in range(n):
        token, uid = make_hero(url, db, f"{prefix}_{i}", f"Bot {prefix.upper()} {i}")
        bots.append(NetBot(url, token, uid, f"Bot {prefix.upper()} {i}", team, keyfn, record=(record == i)))
    for b in bots:
        await b.connect()
    end = time.monotonic() + 20
    while any(b.zone != "truc_lam_thon" for b in bots):
        if time.monotonic() > end:
            raise RuntimeError("bots did not reach the village")
        await asyncio.sleep(0.05)
    return bots


async def play(bots: list[NetBot], timeout: float = 900, stop=lambda: False) -> None:
    """Every bot inside a bí cảnh thinks 20 times a second until they are all done."""
    start = time.monotonic()
    while not stop() and time.monotonic() - start < timeout:
        for b in bots:
            if b.zone == "bi_canh" and not b.ended:
                await b.think()
        if bots and all(b.ended for b in bots):
            return
        await asyncio.sleep(0.05)


async def run_team(url: str, db: Path, prefix: str = "rb", n: int = 3, realm: str = "mac_anh_dong",
                   timeout: float = 900, record: int | None = None, log=print) -> list[NetBot]:
    bots = await make_bots(url, db, prefix, n, record)
    leader = bots[0]
    for b in bots[1:]:
        await leader.send({"t": "party", "op": "invite", "name": b.name})
    end = time.monotonic() + 10
    while len((getattr(leader, "party", None) or {}).get("members", [])) < n:
        if time.monotonic() > end:
            raise RuntimeError("party did not form")
        await asyncio.sleep(0.05)
    log(f"party: {[m['name'] for m in leader.party['members']]}")
    await leader.send({"t": "realm", "op": "enter", "realm": realm})
    end = time.monotonic() + 15
    while any(b.zone != "bi_canh" for b in bots):
        if time.monotonic() > end:
            errs = [m for m in leader.s.sent if m.get("t") in ("error", "realm")]
            raise RuntimeError(f"could not enter: {errs} zones {[b.zone for b in bots]}")
        await asyncio.sleep(0.05)
    log("entered " + realm)
    rooms_seen = []

    def progress() -> bool:
        if leader.room and (not rooms_seen or rooms_seen[-1] != (leader.room["i"], leader.room["kind"])):
            rooms_seen.append((leader.room["i"], leader.room["kind"]))
            log(f"  room {leader.room['i'] + 1}/{leader.room['n']}: {leader.room['kind']}")
        return False
    await play(bots, timeout, stop=progress)
    await asyncio.sleep(1.0)   # the chest is paid right after the end
    for b in bots:
        b.read()
    log("result: " + ", ".join(f"{b.name}={b.ended and b.ended['result']}" for b in bots))
    return bots


async def main_async(args) -> int:
    bots = await run_team(args.url, Path(args.db), prefix=args.prefix, n=args.bots, realm=args.realm,
                          timeout=args.minutes * 60)
    ok = all(b.ended and b.ended["result"] == "won" for b in bots)
    for b in bots:
        stages = sorted(lt["stage"] for lt in b.loot)
        print(f"{b.name}: loot {stages}")
        await b.send({"t": "realm", "op": "leave"})
        await b.close()
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--db", default=str(ROOT / "server" / "dev.db"))
    ap.add_argument("--bots", type=int, default=3)
    ap.add_argument("--realm", default="mac_anh_dong")
    ap.add_argument("--prefix", default="rb")
    ap.add_argument("--minutes", type=float, default=15)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
