"""One running copy of a zone map: a *channel* (spec 7.1: at most 40 players each).

Holds players and monsters, applies movement intents every tick (server-authoritative,
spec 15.1/17), keeps an area-of-interest grid (cells of 16 tiles) and builds the delta
snapshots each connected player receives. No database access happens here: the world
loop calls `tick()` 20 times a second and it must stay fast.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import balance
from . import ai
from .maps import ZoneMap
from .movement import facing_for, step
from .protocol import FACING_CODE

if TYPE_CHECKING:
    from .world import Session


def cfg() -> dict:
    return balance.load("world")


def cfg_combat() -> dict:
    return balance.load("combat")


@dataclass
class Player:
    user_id: int
    name: str
    appearance: dict
    realm: str
    x: float
    y: float
    facing: str = "down"
    session: "Session | None" = None
    channel: "ChannelZone | None" = None
    inputs: deque = field(default_factory=deque)     # (seq, steps, total_ms)
    queued_ms: int = 0
    budget_ms: float = 0.0
    ack: int = -1
    moving: bool = False
    moved_this_tick: bool = False
    linger_until: float | None = None                 # set while disconnected (spec 15.1)
    dirty: bool = False                                # position changed since the last DB save
    known: dict = field(default_factory=dict)          # entity id -> last state sent to this player
    rejected_ms: int = 0                               # movement the server refused (speed checks)
    pending_join: tuple | None = None                  # (zone_id, deadline) waiting for queued steps
    # ---- combat (stage 4) ----
    stats: dict = field(default_factory=dict)
    hp: float = 100.0
    max_hp: float = 100.0
    qi: float = 50.0
    max_qi: float = 50.0
    stage: int = 0
    skills: dict = field(default_factory=dict)         # skill id -> {"level", "word_id"} (learned only)
    skill_ready: dict = field(default_factory=dict)    # skill id -> time it can be cast again
    next_attack_at: float = 0.0
    question: dict | None = None                       # the open Vấn Đạo question
    q_pending: bool = False                            # a question is being created
    next_q: tuple | None = None                        # (monster eid, time) of the next question
    no_words_until: float = 0.0                        # nothing learned yet: do not ask again at once
    protect_until: float = 0.0                         # Hộ Thể while answering (spec 8.1)
    guard_until: float = 0.0
    guard_reduce: float = 0.0
    last_combat: float = -1e9
    pill_ready_at: float = 0.0
    dead: bool = False
    respawn_at: float = 0.0
    # ---- guard bees (stage 5) ----
    bees: list = field(default_factory=list)            # realtime.guard.GuardBee
    now: float = 0.0                                    # set each tick, for the bee state in snapshots
    # ---- Linh Thú and pill buffs (stage 8) ----
    pet: str | None = None                              # worn pet species, drawn following the player
    buffs: dict = field(default_factory=dict)           # buff kind -> monotonic time it ends
    # ---- bí cảnh (stage 9) ----
    ghost: bool = False                                 # out of health in a realm: follows the party, cannot act

    @property
    def eid(self) -> str:
        return f"p{self.user_id}"

    @property
    def weapon(self) -> str | None:
        return self.stats.get("weapon")

    def hp_pct(self) -> int:
        return max(0, min(100, int(round(100 * self.hp / max(1.0, self.max_hp)))))

    def protected(self, now: float) -> bool:
        return now < self.protect_until

    def bee_states(self) -> list:
        return [b.state(self.now) for b in self.bees]

    def state(self) -> list:
        return [self.eid, round(self.x, 2), round(self.y, 2), FACING_CODE[self.facing], int(self.moving),
                self.hp_pct(), self.bee_states()]

    def full(self) -> dict:
        return {"id": self.eid, "k": "p", "uid": self.user_id, "n": self.name, "ap": self.appearance,
                "realm": self.realm, "x": round(self.x, 2), "y": round(self.y, 2),
                "f": FACING_CODE[self.facing], "m": int(self.moving), "hp": self.hp_pct(), "wp": self.weapon,
                "bees": self.bee_states(), "pet": self.pet, "gh": int(self.ghost)}

    def apply_stats(self, stats: dict, heal: bool = False) -> None:
        self.stats = dict(stats)
        self.max_hp = float(stats.get("max_hp", self.max_hp))
        self.max_qi = float(stats.get("max_qi", self.max_qi))
        if heal:
            self.hp, self.qi = self.max_hp, self.max_qi
        self.hp = min(self.hp, self.max_hp)
        self.qi = min(self.qi, self.max_qi)


class ChannelZone:
    instance = False   # a bí cảnh run (realtime/realm.py) says True

    def __init__(self, zone_id: str, number: int, zmap: ZoneMap, rng: random.Random | None = None):
        self.zone_id, self.number, self.map = zone_id, number, zmap
        self.players: dict[int, Player] = {}
        self.rng = rng or random.Random()
        self.monsters: list[ai.Monster] = ai.spawn_all(zmap, self.rng, prefix=f"m{number}_")
        c = cfg()
        self.cell_px = c["aoi_cell_tiles"] * 16
        self.radius = c["aoi_radius_cells"]
        self.speed = float(c["move_speed"])
        self.tick_count = 0
        self.grid: dict[tuple[int, int], list] = {}
        self.events: list[dict] = []          # combat effects since the last snapshot
        self.extras: list = []                # other things seen in the AOI: Khe Nứt Mực rifts (stage 9)
        self.safe = False                     # set by the world from zones.json

    def monster(self, eid: str):
        return next((m for m in self.monsters if m.eid == eid), None)

    def event(self, **ev) -> None:
        self.events.append(ev)

    @property
    def key(self) -> str:
        return f"{self.zone_id}#{self.number}"

    @property
    def awake(self) -> bool:
        """A channel nobody stands in sleeps: monsters are not simulated (spec 15.1)."""
        return bool(self.players)

    def count(self) -> int:
        return len(self.players)

    # ------------------------------------------------------------ membership
    def add(self, p: Player) -> None:
        p.channel = self
        p.inputs.clear()
        p.queued_ms = 0
        p.budget_ms = 0.0
        p.known = {}
        p.moving = False
        self.players[p.user_id] = p

    def remove(self, p: Player) -> None:
        self.players.pop(p.user_id, None)
        if p.channel is self:
            p.channel = None
        # the others' next snapshot notices it is gone and sends 'rm'

    # ------------------------------------------------------------ movement
    def queue_input(self, p: Player, seq: int, steps: list[tuple[int, int, int]]) -> None:
        c = cfg()
        if seq <= p.ack or (p.inputs and seq <= p.inputs[-1][0]):
            return  # duplicate or out of order
        steps = steps[:c["move_steps_per_message_max"]]
        total = sum(s[2] for s in steps)
        if total > c["move_message_max_ms"]:
            # more time than a message may cover: keep the first part, drop the rest
            kept, acc = [], 0
            for s in steps:
                if acc + s[2] > c["move_message_max_ms"]:
                    break
                kept.append(s)
                acc += s[2]
            p.rejected_ms += total - acc
            steps, total = kept, acc
        if p.queued_ms + total > c["move_queue_max_ms"]:
            p.rejected_ms += total  # client is sending faster than real time
            p.ack = max(p.ack, seq)
            return
        p.inputs.append((seq, steps, total))
        p.queued_ms += total

    def _move_players(self, dt: float, now: float = 0.0) -> None:
        cap = cfg()["move_budget_max_ms"]
        col = self.map.collider
        for p in self.players.values():
            p.moved_this_tick = False
            if (p.dead and not p.ghost) or p.protected(now):  # Hộ Thể / fallen: steps are dropped, not saved for later
                while p.inputs:
                    p.ack = p.inputs.popleft()[0]
                p.queued_ms = 0
                p.budget_ms = 0.0
                p.moving = False
                continue
            # time budget: a player can never move for longer than real time has passed
            p.budget_ms = min(cap, p.budget_ms + dt * 1000.0)
            while p.inputs and p.inputs[0][2] <= p.budget_ms:
                seq, steps, total = p.inputs.popleft()
                p.queued_ms -= total
                p.budget_ms -= total
                for dx, dy, ms in steps:
                    if dx or dy:
                        p.facing = facing_for(dx, dy, p.facing)
                        nx, ny = step(p.x, p.y, dx, dy, ms, self.speed, col)
                        if (nx, ny) != (p.x, p.y):
                            p.x, p.y = nx, ny
                            p.dirty = True
                        p.moved_this_tick = True
                p.ack = seq
            p.moving = p.moved_this_tick or (bool(p.inputs) and any(
                dx or dy for dx, dy, _ in p.inputs[0][1]))

    # ------------------------------------------------------------ tick
    def tick(self, dt: float, now: float) -> None:
        self.tick_count += 1
        if not self.awake:
            return
        self._move_players(dt, now)
        from . import combat, guard
        combat.tick(self, dt, now)
        guard.tick(self, dt, now, self.rng)
        for p in self.players.values():
            p.now = now
        self._rebuild_grid()

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell_px), int(y // self.cell_px)

    def _rebuild_grid(self) -> None:
        g: dict[tuple[int, int], list] = {}
        for p in self.players.values():
            g.setdefault(self._cell(p.x, p.y), []).append(p)
        for m in self.monsters:
            g.setdefault(self._cell(m.x, m.y), []).append(m)
        for e in self.extras:
            g.setdefault(self._cell(e.x, e.y), []).append(e)
        self.grid = g

    def visible_to(self, p: Player) -> list:
        """Entities in the 3x3 cells around the player (spec 15.1 AOI), not the player."""
        cx, cy = self._cell(p.x, p.y)
        out = []
        r = self.radius
        for gy in range(cy - r, cy + r + 1):
            for gx in range(cx - r, cx + r + 1):
                for e in self.grid.get((gx, gy), ()):
                    if e is not p:
                        out.append(e)
        return out

    def snapshot_for(self, p: Player, server_time: float) -> dict:
        """Only what changed since the last snapshot sent to this player."""
        add, upd, seen = [], [], set()
        for e in self.visible_to(p):
            st = e.state()
            seen.add(st[0])
            last = p.known.get(st[0])
            if last is None:
                add.append(e.full())
            elif last != st:
                upd.append(st)
            p.known[st[0]] = st
        gone = [eid for eid in p.known if eid not in seen]
        for eid in gone:
            del p.known[eid]
        snap = {"t": "snap", "st": round(server_time, 3), "ack": p.ack,
                "me": [p.x, p.y, FACING_CODE[p.facing], round(p.hp, 1), p.max_hp, round(p.qi, 1), p.max_qi,
                       [[b.id, b.sp, int(round(b.hp)), int(b.max_hp), round(max(0.0, b.down_until - p.now), 1),
                         b.target or ""] for b in p.bees], int(p.ghost)]}
        # (exact x, y: the client replays its unconfirmed steps from there)
        if self.events:
            r2 = cfg_combat()["event_radius"] ** 2
            fx = [e for e in self.events if e.get("id") == p.eid or e.get("by") == p.eid
                  or (e.get("x", 0) - p.x) ** 2 + (e.get("y", 0) - p.y) ** 2 <= r2]
            if fx:
                snap["fx"] = fx
        if add:
            snap["add"] = add
        if upd:
            snap["e"] = upd
        if gone:
            snap["rm"] = gone
        return snap
