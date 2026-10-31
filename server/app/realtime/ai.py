"""Monster behaviour (spec 15.1: server-side AI). Stage 3: Mặc Quái wander inside their
area, pausing now and then. Aggro, attacks and Mặc Thuẫn arrive with combat in stage 4."""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import DATA_DIR
from .maps import Area, ZoneMap
from .movement import Collider
from .protocol import FACING_CODE


@lru_cache(maxsize=1)
def monster_types() -> dict:
    data = json.loads((DATA_DIR / "creatures" / "monsters.json").read_text("utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@dataclass
class Monster:
    eid: str
    kind: str
    area: Area
    x: float
    y: float
    facing: str = "down"
    target: tuple[float, float] | None = None
    idle: float = 0.0
    moving: bool = False
    # ---- combat (stage 4) ----
    hp: float = 1.0
    max_hp: float = 1.0
    shield: bool = True                 # Mặc Thuẫn: cannot die while it is up (spec 8.1)
    regen: list = field(default_factory=list)   # HP % at which the shield comes back
    mode: str = "wander"                # wander | chase | return | dead
    engaged: set = field(default_factory=set)   # user ids fighting this monster
    atk_ready: float = 0.0
    tele: tuple | None = None           # (x, y, radius, lands_at) of a telegraphed attack
    slow_until: float = 0.0
    slow_mult: float = 1.0
    respawn_at: float = 0.0
    # ---- guard bees (stage 5) ----
    stun_until: float = 0.0
    burn: tuple | None = None           # (until, damage per second, owner uid, bee id)
    burn_acc: float = 0.0
    bee_assist: dict = field(default_factory=dict)   # owner uid -> ids of bees that stung it
    # ---- bí cảnh (stage 9) ----
    hp_scale: float = 1.0               # the boss grows with the size of the party
    group_hits: set = field(default_factory=set)     # who already answered right against the big shield

    def __post_init__(self):
        self.reset()

    def reset(self) -> None:
        i = self.info
        self.max_hp = float(i.get("hp", 1)) * self.hp_scale
        self.hp = self.max_hp
        self.shield = True
        self.regen = sorted(i.get("shield_regen", []), reverse=True)
        self.mode = "wander"
        self.engaged = set()
        self.tele = None
        self.slow_until = 0.0
        self.target = None
        self.stun_until = 0.0
        self.burn = None
        self.burn_acc = 0.0
        self.bee_assist = {}
        self.group_hits = set()

    @property
    def info(self) -> dict:
        return monster_types()[self.kind]

    @property
    def alive(self) -> bool:
        return self.mode != "dead"

    def hp_pct(self) -> int:
        return max(0, min(100, int(round(100 * self.hp / max(1.0, self.max_hp)))))

    def state(self) -> list:
        return [self.eid, round(self.x, 1), round(self.y, 1), FACING_CODE[self.facing], int(self.moving),
                self.hp_pct(), int(self.shield), int(self.alive)]

    def full(self) -> dict:
        return {"id": self.eid, "k": "m", "type": self.kind, "n": self.info["name_vi"],
                "rank": self.info.get("rank", "normal"), "x": round(self.x, 1), "y": round(self.y, 1),
                "f": FACING_CODE[self.facing], "m": int(self.moving), "hp": self.hp_pct(),
                "sh": int(self.shield), "alive": int(self.alive)}

    @property
    def home(self) -> tuple[float, float]:
        a = self.area
        return a.x + a.w / 2, a.y + a.h / 2

    def _pick_target(self, col: Collider, rng: random.Random) -> None:
        a = self.area
        for _ in range(8):
            tx, ty = rng.uniform(a.x + 8, a.x + a.w - 8), rng.uniform(a.y + 8, a.y + a.h - 8)
            if not col.blocked(tx, ty):
                self.target = (tx, ty)
                return
        self.target = None

    def update(self, dt: float, col: Collider, rng: random.Random) -> None:
        if self.idle > 0:
            self.idle -= dt
            self.moving = False
            return
        if self.target is None:
            self._pick_target(col, rng)
            if self.target is None:
                self.idle = 1.0
                return
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        sp = self.info["speed"] * dt
        if dist <= sp:
            self.x, self.y, self.target = tx, ty, None
            lo, hi = self.info["idle_seconds"]
            self.idle = rng.uniform(lo, hi)
            self.moving = False
            return
        nx, ny = self.x + dx / dist * sp, self.y + dy / dist * sp
        if col.blocked(nx, ny):
            self.target = None  # walked into something: think again next tick
            self.moving = False
            return
        self.x, self.y = nx, ny
        self.moving = True
        if abs(dx) > abs(dy):
            self.facing = "right" if dx > 0 else "left"
        else:
            self.facing = "down" if dy > 0 else "up"


def spawn_all(zmap: ZoneMap, rng: random.Random, prefix: str = "m") -> list[Monster]:
    out: list[Monster] = []
    types = monster_types()
    for area in zmap.monster_areas:
        kind = area.props.get("monster")
        if kind not in types:
            continue
        for _ in range(int(area.props.get("count", 1))):
            for _try in range(20):
                x = rng.uniform(area.x + 8, area.x + area.w - 8)
                y = rng.uniform(area.y + 8, area.y + area.h - 8)
                if not zmap.collider.blocked(x, y):
                    break
            m = Monster(f"{prefix}{len(out)}", kind, area, x, y)
            m.idle = rng.uniform(0, 2)
            out.append(m)
    return out
