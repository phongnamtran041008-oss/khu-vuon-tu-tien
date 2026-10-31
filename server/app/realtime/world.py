"""The shared world (spec 15.1): sessions, zones and their channels, the 20 Hz tick loop,
snapshots, zone changes, linger after disconnect and batched position saves.

Everything lives in this one process's memory (no Redis, spec 2). Only durable data goes
to the database: positions are saved every 60 s in one batch, and immediately on a zone
change or when a disconnected character leaves the world (spec 15.2).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import gc
import json
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import select, update

from .. import balance, clock
from .. import db as dbm
from ..config import DATA_DIR
from ..models import Block, Character, Friendship, User
from . import combat, maps, protocol
from .chat import ChatService
from .party import PartyService
from .realm import RealmInstance, RealmService
from .zone import ChannelZone, Player

log = logging.getLogger("khu_vuon.world")
ABODE = "abode"
CLOSE = object()  # outbox sentinel: close the socket after what is queued


def cfg() -> dict:
    return balance.load("world")


@lru_cache(maxsize=1)
def zone_defs() -> dict:
    data = json.loads((DATA_DIR / "zones.json").read_text("utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def realm_order() -> list[str]:
    data = json.loads((DATA_DIR / "realms_cultivation.json").read_text("utf-8"))
    return [r["id"] for r in data["realms"]]


def realm_index(realm: str) -> int:
    order = realm_order()
    return order.index(realm) if realm in order else 0


def may_enter(player_realm: str, zone_id: str) -> bool:
    """Spec 7.3: nobody enters a zone more than one realm above their own."""
    z = zone_defs().get(zone_id)
    if z is None:
        return False
    rec = z.get("recommended_realm")
    if rec is None:
        return True
    return realm_index(player_realm) >= realm_index(rec) - cfg()["realm_gate_margin"]


def world_zones() -> list[str]:
    return [k for k, v in zone_defs().items() if v.get("kind") not in ("private", "instance")]


# ------------------------------------------------------------------ sessions
class Session:
    """One authenticated WebSocket connection. Messages are queued here and written by the
    connection's writer task, so the tick loop never waits on a slow network."""

    def __init__(self, user_id: int, username: str, name: str, realm: str, appearance: dict,
                 is_admin: bool = False, outbox_max: int | None = None):
        self.user_id, self.username, self.name = user_id, username, name
        self.realm, self.appearance, self.is_admin = realm, appearance, is_admin
        self.outbox: asyncio.Queue = asyncio.Queue(maxsize=outbox_max or cfg()["outbox_max"])
        self.closed = False
        self.close_code = 1000
        self.friends: set[int] = set()
        self.blocks: set[int] = set()            # people this user blocked
        self.chat_banned_until: dt.datetime | None = None
        self.last_chat = -1e9
        self.player: Player | None = None
        self.saved_zone = ABODE
        self.saved_pos: tuple[float, float, str] | None = None
        self.dropped = 0
        self._win_start = 0.0
        self._win_count = 0
        self.sent: list | None = None            # tests: capture instead of queueing
        # character state used when the character steps into the world (stage 4)
        self.stage = 0
        self.stats: dict = {}
        self.skills: dict = {}
        self.hp: float | None = None
        self.qi: float | None = None
        self.bees: list[dict] = []               # guard bee loadout (stage 5)
        self.pet: str | None = None              # worn Linh Thú (stage 8)
        self.buffs: dict[str, int] = {}          # pill buffs: kind -> seconds left when loaded
        self.last_mark = -1e9                    # party ping icons (stage 9)

    def send(self, msg: dict) -> None:
        if self.closed:
            return
        if self.sent is not None:
            self.sent.append(msg)
            return
        try:
            self.outbox.put_nowait(msg)
        except asyncio.QueueFull:
            self.dropped += 1  # snapshots are replaced by the next one anyway

    def close(self, code: int = 1000, msg: dict | None = None) -> None:
        if self.closed:
            return
        if self.sent is not None:
            if msg:
                self.sent.append(msg)
            self.closed, self.close_code = True, code
            return
        while not self.outbox.empty():  # what was queued no longer matters
            self.outbox.get_nowait()
        if msg:
            self.outbox.put_nowait(msg)
        self.outbox.put_nowait(CLOSE)
        self.closed, self.close_code = True, code

    def allow_message(self, now: float) -> bool:
        """Spec 17: at most N messages per second, the connection is closed beyond that."""
        if now - self._win_start >= 1.0:
            self._win_start, self._win_count = now, 0
        self._win_count += 1
        return self._win_count <= cfg()["ws_messages_per_second"]


class GcWatch:
    """Measures garbage-collector pauses (they stop the tick loop like any other work)."""

    def __init__(self):
        self.max_ms = 0.0
        self.count = 0
        self._t0 = 0.0
        gc.callbacks.append(self._cb)

    def _cb(self, phase, info):
        if phase == "start":
            self._t0 = time.perf_counter()
        elif info.get("generation") == 2:
            self.count += 1
            self.max_ms = max(self.max_ms, (time.perf_counter() - self._t0) * 1000)


gc_watch = GcWatch()


@dataclass
class TickStats:
    ticks: int = 0
    durations: deque = field(default_factory=lambda: deque(maxlen=1200))
    late: deque = field(default_factory=lambda: deque(maxlen=1200))
    max_ms: float = 0.0
    max_late_ms: float = 0.0
    over_budget: int = 0

    max_late_tick: int = 0

    def record(self, dur_s: float, late_s: float, budget_s: float) -> None:
        self.ticks += 1
        d, l_ = dur_s * 1000, max(0.0, late_s * 1000)
        self.durations.append(d)
        self.late.append(l_)
        self.max_ms = max(self.max_ms, d)
        if l_ > self.max_late_ms:
            self.max_late_ms, self.max_late_tick = l_, self.ticks
        if dur_s > budget_s:
            self.over_budget += 1

    def view(self) -> dict:
        ds = sorted(self.durations) or [0.0]
        ls = sorted(self.late) or [0.0]
        return {"ticks": self.ticks, "tick_avg_ms": round(sum(ds) / len(ds), 3),
                "tick_p99_ms": round(ds[int(len(ds) * 0.99) - 1 if len(ds) > 1 else 0], 3),
                "tick_max_ms": round(self.max_ms, 3), "late_p99_ms": round(ls[int(len(ls) * 0.99) - 1 if len(ls) > 1 else 0], 3),
                "late_max_ms": round(self.max_late_ms, 3), "late_max_at_tick": self.max_late_tick,
                "ticks_over_budget": self.over_budget}


# ------------------------------------------------------------------ world
class World:
    def __init__(self, mono=time.monotonic):
        self.mono = mono
        self.started = mono()
        self.sessions: dict[int, Session] = {}
        self.players: dict[int, Player] = {}         # characters standing in a world zone
        self.channels: dict[str, list[ChannelZone]] = {}
        self.chat = ChatService(self)
        self.stats = TickStats()
        self.running = False
        self._task: asyncio.Task | None = None
        self._save_lock = asyncio.Lock()
        self._save_now: dict[int, dict] = {}         # user_id -> row to write soon
        self._last_periodic_save = mono()
        self._bg: set[asyncio.Task] = set()
        self.messages_in = 0
        self.rng = random.Random()
        self.parties = PartyService(self)            # tổ đội (stage 9)
        self.realms = RealmService(self)             # bí cảnh runs, rifts and the queue (stage 9)

    # ------------------------------------------------------------ time
    def server_time(self) -> float:
        return self.mono() - self.started

    @staticmethod
    def day_phase() -> float:
        """0..1 position in the in-game day (spec 7.1: one game day = two real hours)."""
        n = clock.now()
        secs = n.hour * 3600 + n.minute * 60 + n.second + n.microsecond / 1e6
        length = cfg()["day_length_seconds"]
        return round((secs % length) / length, 4)

    # ------------------------------------------------------------ lifecycle
    def preload(self) -> None:
        """Parse every zone map and open channel 1 now, so the first player to walk in
        does not stall the tick loop while a large map file is read."""
        for zone_id in world_zones():
            self._channels(zone_id)

    async def start(self) -> None:
        if self.running:
            return
        self.preload()
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="world-tick")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for s in list(self.sessions.values()):
            s.close(1001, {"t": "notice", "text": "Máy chủ đang bảo trì, hẹn gặp lại!"})
        for p in self.players.values():
            self._queue_save(p)
        await self.flush_saves()

    async def _loop(self) -> None:
        c = cfg()
        period = 1.0 / c["tick_hz"]
        next_t = self.mono()
        last = next_t
        while self.running:
            now = self.mono()
            late = now - next_t
            dt_ = min(0.25, now - last)
            last = now
            t0 = time.perf_counter()
            try:
                self.tick(dt_)
            except Exception:  # never let one bad tick stop the world
                log.exception("tick failed")
            self.stats.record(time.perf_counter() - t0, late, period)
            if self._save_now or self.mono() - self._last_periodic_save >= c["position_save_seconds"]:
                self.spawn(self.flush_saves(periodic=True))
            next_t += period
            if self.mono() - next_t > period * 5:  # far behind (machine slept): resync
                next_t = self.mono()
            await asyncio.sleep(max(0.0, next_t - self.mono()))

    def spawn(self, coro) -> None:
        """Run database work in the background so the tick never waits for it."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # no event loop (plain unit tests): nothing to run it on
            coro.close()
            return
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    # ------------------------------------------------------------ tick
    def tick(self, dt_: float) -> None:
        now = self.mono()
        st = self.server_time()
        snap_every = cfg()["snapshot_every_ticks"]
        for zone_id, chans in self.channels.items():
            for ch in chans:
                ch.tick(dt_, now)
                if ch.tick_count % snap_every == 0 and ch.awake:
                    for p in ch.players.values():
                        if p.session is not None:
                            p.session.send(ch.snapshot_for(p, st))
                    ch.events = []
                elif not ch.awake:
                    ch.events = []
        self.realms.tick(dt_, now, st, snap_every)
        self.parties.tick(now)
        # a gate request that waited for the player's last queued steps
        for p in list(self.players.values()):
            if p.pending_join and p.session is not None:
                zone_id, deadline = p.pending_join
                if not p.inputs or now >= deadline:
                    p.pending_join = None
                    self.join(p.session, zone_id, "portal")
        # characters whose player disconnected leave the world after the linger time
        for p in list(self.players.values()):
            if p.session is None and p.linger_until is not None and now >= p.linger_until:
                self._leave_world(p)
        # extra channels that emptied out are closed
        for zone_id, chans in self.channels.items():
            if len(chans) > 1:
                self.channels[zone_id] = [c for c in chans if c.number == 1 or c.players]

    # ------------------------------------------------------------ channels
    def _channels(self, zone_id: str) -> list[ChannelZone]:
        chans = self.channels.get(zone_id)
        if chans is None:
            chans = [ChannelZone(zone_id, 1, maps.load(zone_defs()[zone_id]["map"]))]
            self.channels[zone_id] = chans
        return chans

    def _pick_channel(self, zone_id: str, number: int | None = None) -> ChannelZone | None:
        c = cfg()
        chans = self._channels(zone_id)
        if number is not None:
            for ch in chans:
                if ch.number == number:
                    return ch if ch.count() < c["channel_capacity"] else None
            if number == max(ch.number for ch in chans) + 1 and len(chans) < c["channels_per_zone_max"]:
                ch = ChannelZone(zone_id, number, chans[0].map)
                chans.append(ch)
                return ch
            return None
        for ch in sorted(chans, key=lambda ch: ch.number):  # the lowest channel with room
            if ch.count() < c["channel_capacity"]:
                return ch
        if len(chans) >= c["channels_per_zone_max"]:
            return None
        ch = ChannelZone(zone_id, max(x.number for x in chans) + 1, chans[0].map)
        chans.append(ch)
        return ch

    def channel_list(self, zone_id: str) -> list[dict]:
        cap = cfg()["channel_capacity"]
        return [{"n": ch.number, "players": ch.count(), "cap": cap}
                for ch in sorted(self._channels(zone_id), key=lambda ch: ch.number)]

    # ------------------------------------------------------------ connect
    async def connect(self, user, character: Character) -> Session:
        old = self.sessions.get(user.id)
        if old is not None:  # spec 15.1: a new login kicks the old connection
            old.close(4001, {"t": "kicked", "reason": "elsewhere",
                             "message_vi": "Tài khoản vừa đăng nhập ở nơi khác."})
        s = Session(user.id, user.username, character.display_name, character.realm,
                    character.appearance or {}, bool(user.is_admin))
        s.chat_banned_until = user.chat_banned_until
        s.saved_zone = character.zone_id or ABODE
        s.saved_pos = (character.x, character.y, character.facing or "down")
        s.stage = character.realm_stage
        s.hp, s.qi = float(character.hp), float(character.qi)
        await self._load_social(s)
        await self._load_combat(s, character)
        self.sessions[user.id] = s
        p = self.players.get(user.id)
        zone = s.saved_zone
        if p is not None:  # reconnected while the character was still standing there
            zone = p.channel.zone_id if p.channel else zone
        s.send({"t": "welcome", "v": protocol.PROTOCOL_VERSION, "you": {"uid": user.id, "id": f"p{user.id}",
                                                                          "name": s.name},
                "zone": zone, "st": round(self.server_time(), 3), "day": self.day_phase(),
                "day_length": cfg()["day_length_seconds"]})
        self.chat.send_history(s, "world")
        for fid in s.friends:
            other = self.sessions.get(fid)
            if other is not None:
                other.send({"t": "friend", "event": "online", "user": {"uid": user.id, "name": s.name}})
        return s

    async def _load_social(self, s: Session) -> None:
        async with dbm.SessionLocal() as db:
            rows = (await db.execute(select(Friendship.friend_id).where(
                Friendship.user_id == s.user_id, Friendship.status == "accepted"))).scalars().all()
            s.friends = set(rows)
            s.blocks = set((await db.execute(select(Block.blocked_id).where(
                Block.user_id == s.user_id))).scalars().all())

    async def _load_combat(self, s: Session, character: Character) -> None:
        from ..systems import buffs, cultivation, items, pets
        async with dbm.SessionLocal() as db:
            s.stats = await cultivation.current_stats(db, character)
            worn = await pets.worn(db, s.user_id)
            s.pet = worn.pet_type if worn else None
            user = await db.get(User, s.user_id)
            s.buffs = buffs.active(user, clock.now()) if user else {}
            s.skills = {k["id"]: {"level": k["level"], "word_id": k["word_id"]}
                        for k in await items.skill_list(db, s.user_id) if k["learned"]}
            from ..systems import bees
            s.bees = await bees.guard_loadout(db, s.user_id)
            await db.commit()

    def disconnect(self, s: Session) -> None:
        if self.sessions.get(s.user_id) is s:
            del self.sessions[s.user_id]
            for fid in s.friends:
                other = self.sessions.get(fid)
                if other is not None:
                    other.send({"t": "friend", "event": "offline", "user": {"uid": s.user_id, "name": s.name}})
        p = s.player
        if p is not None and p.session is s:
            p.session = None
            p.moving = False
            p.inputs.clear()
            p.queued_ms = 0
            # spec 14.3: inside a bí cảnh the party waits longer for someone to come back
            linger = balance.load("realm")["reconnect_seconds"] if isinstance(p.channel, RealmInstance) \
                else cfg()["linger_seconds"]
            p.linger_until = self.mono() + linger
            self._queue_save(p)

    # ------------------------------------------------------------ messages
    async def handle(self, s: Session, data) -> None:
        self.messages_in += 1
        try:
            msg = protocol.parse(data)
        except protocol.BadMessage as e:
            s.send(protocol.error("bad_message", "Gói tin không hợp lệ.", detail=str(e)[:120]))
            return
        if isinstance(msg, protocol.Ping):
            s.send({"t": "pong", "c": msg.c, "st": round(self.server_time(), 3)})
        elif isinstance(msg, protocol.Input):
            p = s.player
            if p is not None and p.channel is not None:
                p.channel.queue_input(p, msg.s, [tuple(k) for k in msg.k])
        elif isinstance(msg, protocol.Face):
            p = s.player
            if p is not None and p.facing != msg.f:
                p.facing, p.dirty = msg.f, True
        elif isinstance(msg, protocol.Join):
            self.join(s, msg.zone, msg.via)
        elif isinstance(msg, protocol.Channel):
            self.switch_channel(s, msg.n)
        elif isinstance(msg, protocol.Chat):
            self.chat.handle(s, msg)
        elif isinstance(msg, protocol.Attack):
            p = s.player
            err = combat.attack(p, msg.id, self.mono(), self.rng) if p else "cannot"
            if err in ("too_far", "no_target", "not_learned", "no_qi"):
                s.send({"t": "act_fail", "code": err})
        elif isinstance(msg, protocol.Cast):
            p = s.player
            err = combat.cast(p, msg.k, msg.id, self.mono(), self.rng) if p else "cannot"
            s.send({"t": "cast", "k": msg.k, "ok": err is None, "code": err,
                    "ready_in": round(max(0.0, p.skill_ready.get(msg.k, 0) - self.mono()), 2) if p else 0})
        elif isinstance(msg, protocol.PartyCmd):
            self.parties.handle(s, msg)
        elif isinstance(msg, protocol.RealmCmd):
            self.realms.handle(s, msg)
        elif isinstance(msg, protocol.RealmAct):
            self.realms.act(s, msg)
        elif isinstance(msg, protocol.Mark):
            p = s.player
            if p is not None and p.channel is not None and self.mono() - s.last_mark >= 1.0:
                s.last_mark = self.mono()
                p.channel.event(k="mark", by=p.eid, x=round(msg.x, 1), y=round(msg.y, 1), i=msg.i)

    # ------------------------------------------------------------ zones
    def join(self, s: Session, zone_id: str, via: str) -> bool:
        p = self.players.get(s.user_id)
        current = p.channel.zone_id if (p is not None and p.channel is not None) else ABODE
        defs = zone_defs()
        if zone_id not in defs:
            s.send(protocol.error("no_zone", "Không có vùng đất này."))
            return False
        if via == "resume":
            if p is not None:  # still in the world (reconnect): take the character back
                self._attach(s, p)
                self._send_zone(s, p)
                if isinstance(p.channel, RealmInstance):   # back in the bí cảnh: puzzles and all
                    p.channel.resync(p)
                return True
            if zone_id != s.saved_zone or zone_id == ABODE or defs[zone_id].get("kind") == "instance":
                s.send(protocol.error("bad_resume", "Không thể quay lại vị trí cũ.", zone=ABODE))
                return False
            if not may_enter(s.realm, zone_id):
                s.send(protocol.error("realm_too_low", "Cảnh giới của bạn chưa đủ để vào nơi này.", zone=ABODE))
                return False
            zmap = maps.load(defs[zone_id]["map"])
            x, y, f = s.saved_pos or (*zmap.spawn("spawn"), "down")
            if zmap.collider.blocked(x, y):
                x, y = zmap.spawn("spawn")
            return self._place(s, zone_id, x, y, f)
        if via == "abode":
            if current != ABODE:
                s.send(protocol.error("not_in_abode", "Bạn không ở trong động phủ."))
                return False
            if zone_id != "truc_lam_thon":
                s.send(protocol.error("bad_exit", "Cổng động phủ chỉ dẫn về Trúc Lâm Thôn."))
                return False
            x, y = maps.load(defs[zone_id]["map"]).spawn("from_abode")
            return self._place(s, zone_id, x, y, "up")
        # through a portal: the character must stand inside it
        if p is None or p.channel is None:
            s.send(protocol.error("not_in_zone", "Bạn chưa ở trong thế giới."))
            return False
        portal = next((a for a in p.channel.map.portals
                       if a.props.get("target") == zone_id and a.contains(p.x, p.y)), None)
        if portal is None:
            if p.inputs:  # the last steps into the gate may still be queued: decide after them
                p.pending_join = (zone_id, self.mono() + 1.0)
                return False
            s.send(protocol.error("not_at_portal", "Hãy đứng ở cổng để đi tiếp."))
            return False
        if zone_id == ABODE:
            self._leave_world(p, to_abode=True)
            c = balance.load("character")["abode_spawn"]
            s.saved_zone, s.saved_pos = ABODE, (c["x"], c["y"], cfg()["abode_return_facing"])
            s.send({"t": "zone", "zone": ABODE, "name_vi": defs[ABODE]["name_vi"], "x": c["x"], "y": c["y"],
                    "f": cfg()["abode_return_facing"]})
            return True
        if not may_enter(s.realm, zone_id) or defs[zone_id].get("kind") == "instance":
            s.send(protocol.error("realm_too_low", "Cảnh giới của bạn chưa đủ để vào nơi này."))
            return False
        tx, ty = maps.load(defs[zone_id]["map"]).spawn(portal.props.get("target_spawn"))
        return self._place(s, zone_id, tx, ty, p.facing)

    def _attach(self, s: Session, p: Player) -> None:
        p.session, p.linger_until = s, None
        p.known = {}  # resend everything to the new connection
        s.player = p

    def _place(self, s: Session, zone_id: str, x: float, y: float, facing: str,
               channel: int | None = None) -> bool:
        ch = self._pick_channel(zone_id, channel)
        if ch is None:
            s.send(protocol.error("zone_full", "Khu vực này đã đông người, thử lại sau nhé."))
            return False
        return self.put(s, ch, x, y, facing)

    def put(self, s: Session, ch: ChannelZone, x: float, y: float, facing: str) -> bool:
        """Places the character in this channel (or bí cảnh instance), creating it in memory
        the first time it steps out of the abode."""
        p = self.players.get(s.user_id)
        if p is not None and p.channel is not None:
            p.channel.remove(p)
        if p is None:
            p = Player(s.user_id, s.name, s.appearance, s.realm, x, y, facing)
            p.stage, p.skills = s.stage, dict(s.skills)
            from . import guard
            p.bees = guard.build(s.bees)
            p.pet = s.pet
            p.buffs = {k: self.mono() + secs for k, secs in s.buffs.items()}
            p.apply_stats(s.stats or {"max_hp": 100, "max_qi": 50}, heal=True)
            if s.hp is not None:
                p.hp = max(1.0, min(p.max_hp, s.hp))
                p.qi = max(0.0, min(p.max_qi, s.qi or 0))
            self.players[s.user_id] = p
        p.x, p.y, p.facing = float(x), float(y), facing
        p.ack = -1
        ch.add(p)
        ch.safe = bool(zone_defs()[ch.zone_id].get("safe"))
        self._attach(s, p)
        s.saved_zone, s.saved_pos = ch.zone_id, (p.x, p.y, p.facing)
        self._queue_save(p)
        self._send_zone(s, p)
        return True

    def _send_zone(self, s: Session, p: Player) -> None:
        ch = p.channel
        z = zone_defs()[ch.zone_id]
        s.send({"t": "zone", "zone": ch.zone_id, "name_vi": z["name_vi"], "safe": bool(z.get("safe")),
                "channel": ch.number, "channels": [] if ch.instance else self.channel_list(ch.zone_id),
                "x": p.x, "y": p.y, "f": p.facing, "ack": p.ack, "st": round(self.server_time(), 3),
                "day": self.day_phase()})
        self.chat.send_history(s, "zone")

    def switch_channel(self, s: Session, number: int) -> None:
        p = s.player
        if p is None or p.channel is None:
            s.send(protocol.error("not_in_zone", "Bạn chưa ở trong thế giới."))
            return
        if number == p.channel.number or p.channel.instance:
            self._send_zone(s, p)
            return
        if not self._place(s, p.channel.zone_id, p.x, p.y, p.facing, channel=number):
            return

    def _leave_world(self, p: Player, to_abode: bool = False) -> None:
        realm = p.channel if isinstance(p.channel, RealmInstance) else None
        if realm is not None:   # gone from a bí cảnh for good: the loot so far is kept (spec 14.3)
            realm.member_lost(p)
            zone_id = "truc_lam_thon"
            p.x, p.y = realm.exit_pos()
            p.channel.remove(p)
        elif p.channel is not None:
            zone_id = p.channel.zone_id
            p.channel.remove(p)
        else:
            zone_id = ABODE
        self.players.pop(p.user_id, None)
        if p.session is not None and p.session.player is p:
            p.session.player = None
        if p.session is not None:  # remember the body for the next time it steps out
            p.session.hp, p.session.qi = p.hp, p.qi
        if to_abode:  # home: the body rests and recovers
            c = balance.load("character")["abode_spawn"]
            self._save_now[p.user_id] = {"user_id": p.user_id, "zone_id": ABODE, "x": float(c["x"]),
                                         "y": float(c["y"]), "facing": cfg()["abode_return_facing"],
                                         "hp": int(p.max_hp), "qi": int(p.max_qi)}
            if p.session is not None:
                p.session.hp, p.session.qi = p.max_hp, p.max_qi
        else:
            self._save_now[p.user_id] = {"user_id": p.user_id, "zone_id": zone_id, "x": p.x, "y": p.y,
                                         "facing": p.facing, "hp": max(1, int(p.hp)), "qi": int(p.qi)}

    # ------------------------------------------------------------ persistence
    def _queue_save(self, p: Player) -> None:
        if isinstance(p.channel, RealmInstance):   # a bí cảnh is never saved: next login is at its gate
            x, y = p.channel.exit_pos()
            self._save_now[p.user_id] = {"user_id": p.user_id, "zone_id": "truc_lam_thon", "x": x, "y": y,
                                         "facing": "down", "hp": max(1, int(p.hp)), "qi": int(p.qi)}
            p.dirty = False
        elif p.channel is not None:
            self._save_now[p.user_id] = {"user_id": p.user_id, "zone_id": p.channel.zone_id, "x": p.x,
                                         "y": p.y, "facing": p.facing, "hp": max(1, int(p.hp)), "qi": int(p.qi)}
            p.dirty = False

    async def flush_saves(self, periodic: bool = False) -> int:
        """Writes pending positions in one transaction (spec 15.2: batch writes, few DB calls)."""
        async with self._save_lock:
            if periodic and self.mono() - self._last_periodic_save >= cfg()["position_save_seconds"]:
                self._last_periodic_save = self.mono()
                for p in self.players.values():  # HP changes too, so everyone in the world
                    self._queue_save(p)
            rows = list(self._save_now.values())
            self._save_now = {}
            if not rows:
                return 0
            try:
                async with dbm.SessionLocal() as db:
                    await db.execute(update(Character), rows)
                    await db.commit()
            except Exception:
                log.exception("saving %d positions failed; will retry", len(rows))
                for r in rows:
                    self._save_now.setdefault(r["user_id"], r)
                return 0
            return len(rows)

    # ------------------------------------------------------------ used by REST routes
    def online(self, user_id: int) -> dict:
        s = self.sessions.get(user_id)
        if s is None:
            return {"online": False}
        p = self.players.get(user_id)
        zone = p.channel.zone_id if (p and p.channel) else ABODE
        return {"online": True, "zone_id": zone, "zone_name": zone_defs()[zone]["name_vi"]}

    # ------------------------------------------------------------ combat helpers (stage 4)
    def respawn(self, p: Player) -> None:
        """After death: back to Trúc Lâm Thôn with full health (spec 7.1)."""
        c = combat.cfg()
        p.dead = False
        p.hp, p.qi = p.max_hp, p.max_qi
        zmap = maps.load(zone_defs()[c["respawn_zone"]]["map"])
        x, y = zmap.spawn(c["respawn_spawn"])
        if p.session is not None:
            self._place(p.session, c["respawn_zone"], x, y, "down")
        else:
            p.x, p.y = x, y
            if p.channel is not None:
                p.channel.remove(p)
            self._save_now[p.user_id] = {"user_id": p.user_id, "zone_id": c["respawn_zone"], "x": x, "y": y,
                                         "facing": "down", "hp": int(p.max_hp), "qi": int(p.max_qi)}
            self.players.pop(p.user_id, None)

    def update_character(self, user_id: int, realm: str, stage: int, stats: dict) -> None:
        s = self.sessions.get(user_id)
        p = self.players.get(user_id)
        if s is not None:
            stage_up = (s.realm, s.stage) != (realm, stage)
            s.realm, s.stage, s.stats = realm, stage, dict(stats)
        else:
            stage_up = False
        if p is not None:
            stage_up = stage_up or (p.realm, p.stage) != (realm, stage)
            p.realm, p.stage = realm, stage
            p.apply_stats(stats, heal=stage_up)
            p.known = {}
        if s is not None:
            s.send({"t": "stats", "realm": realm, "stage": stage, "stats": stats, "stage_up": stage_up,
                    "hp": p.hp if p else None, "max_hp": stats.get("max_hp")})

    def set_skills(self, user_id: int, skill_list: list[dict]) -> None:
        learned = {k["id"]: {"level": k["level"], "word_id": k["word_id"]} for k in skill_list if k["learned"]}
        s = self.sessions.get(user_id)
        if s is not None:
            s.skills = learned
            s.send({"t": "skills", "skills": skill_list})
        p = self.players.get(user_id)
        if p is not None:
            p.skills = dict(learned)

    def set_bees(self, user_id: int, loadout: list[dict]) -> None:
        """Guard bees changed (role, level, release): the ones out in the world follow."""
        from . import guard
        s = self.sessions.get(user_id)
        if s is not None:
            s.bees = list(loadout)
        p = self.players.get(user_id)
        if p is not None:
            p.bees = guard.build(loadout, p.bees)

    def set_pet(self, user_id: int, pet_type: str | None) -> None:
        """The worn Linh Thú changed: everyone who sees this player gets them again with it."""
        s = self.sessions.get(user_id)
        if s is not None:
            s.pet = pet_type
        p = self.players.get(user_id)
        if p is None:
            return
        p.pet = pet_type
        if p.channel is not None:
            for other in p.channel.players.values():
                other.known.pop(p.eid, None)

    def set_buffs(self, user_id: int, seconds_left: dict[str, int]) -> None:
        """A pill buff was taken (stage 8): the fight uses it at once."""
        s = self.sessions.get(user_id)
        if s is not None:
            s.buffs = dict(seconds_left)
        p = self.players.get(user_id)
        if p is not None:
            p.buffs = {k: self.mono() + secs for k, secs in seconds_left.items()}

    def buffs_left(self, p: Player) -> dict[str, float]:
        now = self.mono()
        return {k: t - now for k, t in getattr(p, "buffs", {}).items() if t > now}

    def word_mastery_changed(self, user_id: int, word_id: str, mastery: int) -> None:
        """A skill grows or weakens with its word's mastery (spec 8.4)."""
        from ..systems import catalog
        sk = catalog.skills()
        level = sum(1 for m in sk["level_mastery"] if mastery >= m)
        for holder in (self.players.get(user_id), self.sessions.get(user_id)):
            if holder is None:
                continue
            for sid, info in holder.skills.items():
                if info.get("word_id") == word_id:
                    info["level"] = level

    def can_use_pill(self, user_id: int) -> bool:
        p = self.players.get(user_id)
        return p is not None and not p.dead and self.mono() >= p.pill_ready_at

    def pill_taken(self, user_id: int) -> None:
        """A buff pill out in the world: only the shared cooldown (stage 8)."""
        p = self.players.get(user_id)
        if p is not None:
            p.pill_ready_at = self.mono() + combat.cfg()["pill_cooldown"]

    def apply_pill(self, user_id: int, effect: str, pct: float) -> None:
        p = self.players.get(user_id)
        if p is None or p.channel is None:
            return
        p.pill_ready_at = self.mono() + combat.cfg()["pill_cooldown"]
        if effect == "heal":
            amount = p.max_hp * pct / 100
            p.hp = min(p.max_hp, p.hp + amount)
        else:
            amount = p.max_qi * pct / 100
            p.qi = min(p.max_qi, p.qi + amount)
        p.channel.event(k="heal", id=p.eid, v=int(amount), x=p.x, y=p.y, q=int(effect == "qi"))

    def near_npc(self, user_id: int, npc: str, radius: float = 56) -> bool:
        p = self.players.get(user_id)
        if p is None or p.channel is None:
            return False
        pos = p.channel.map.npcs.get(npc)
        return pos is not None and math.hypot(pos[0] - p.x, pos[1] - p.y) <= radius

    def in_world(self, user_id: int) -> bool:
        p = self.players.get(user_id)
        return p is not None and p.channel is not None

    def notify(self, user_id: int, msg: dict) -> None:
        s = self.sessions.get(user_id)
        if s is not None:
            s.send(msg)

    def set_friends(self, a: int, b: int, friends: bool) -> None:
        for x, y in ((a, b), (b, a)):
            s = self.sessions.get(x)
            if s is not None:
                (s.friends.add if friends else s.friends.discard)(y)

    def set_block(self, user_id: int, other: int, blocked: bool) -> None:
        s = self.sessions.get(user_id)
        if s is not None:
            (s.blocks.add if blocked else s.blocks.discard)(other)

    def status(self) -> dict:
        return {"online": len(self.sessions), "in_world": len(self.players),
                "realm_runs": len(self.realms.instances), "parties": len(self.parties.parties),
                "channels": {z: [{"n": c.number, "players": c.count(), "awake": c.awake} for c in chans]
                             for z, chans in self.channels.items()},
                "messages_in": self.messages_in, "gc_full_passes": gc_watch.count,
                "gc_max_ms": round(gc_watch.max_ms, 3), **self.stats.view()}


world = World()
