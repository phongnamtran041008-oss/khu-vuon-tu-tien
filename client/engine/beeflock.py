"""Client-side flight of spirit bees (spec 10.2: "bay theo đường cong mượt quanh chủ").

The server only says what each bee is doing (following, stinging monster X, pollinating);
where exactly it flies between snapshots is drawn here: every bee steers smoothly towards
a point that itself circles its anchor on a Lissajous curve, so a swarm never moves in step.
"""
from __future__ import annotations

import math
import random


class FlyingBee:
    def __init__(self, key: str, sp: str, x: float, y: float):
        self.key, self.sp = key, sp
        rnd = random.Random(key)
        self.x, self.y = x + rnd.uniform(-10, 10), y + rnd.uniform(-6, 6)
        self.vx = self.vy = 0.0
        self.phase = rnd.uniform(0, 6.283)
        self.f1, self.f2 = rnd.uniform(1.6, 2.4), rnd.uniform(2.6, 3.6)
        self.z = rnd.uniform(10, 16)            # height above the ground, pixels
        self.left = False
        self.t = rnd.uniform(0, 10)
        self.seen = 0.0
        self.task_until = 0.0                   # pollinators: when to pick the next flower
        self.task = None

    def update(self, dt: float, ax: float, ay: float, radius: float = 12.0, speed: float = 70.0,
               z: float | None = None) -> None:
        """Fly around the anchor (ax, ay) at about `radius` pixels."""
        self.t += dt
        tx = ax + math.cos(self.t * self.f1 + self.phase) * radius
        ty = ay + math.sin(self.t * self.f2 + self.phase) * radius * 0.55
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        want = min(speed, d * 4.0)
        wx, wy = (dx / d * want, dy / d * want) if d > 0.01 else (0.0, 0.0)
        k = min(1.0, dt * 5.0)
        self.vx += (wx - self.vx) * k
        self.vy += (wy - self.vy) * k
        self.x += self.vx * dt
        self.y += self.vy * dt
        if abs(self.vx) > 4:
            self.left = self.vx < 0
        if z is not None:
            self.z += (z - self.z) * min(1.0, dt * 3)

    def frame(self) -> int:
        return int(self.t * 14) % 2


class Flock:
    """Keeps one FlyingBee per key; bees that disappear are dropped after a moment."""

    def __init__(self):
        self.bees: dict[str, FlyingBee] = {}

    def get(self, key: str, sp: str, x: float, y: float, now: float) -> FlyingBee:
        b = self.bees.get(key)
        if b is None or b.sp != sp:
            b = FlyingBee(key, sp, x, y)
            self.bees[key] = b
        b.seen = now
        return b

    def prune(self, now: float, keep: float = 0.5) -> None:
        for k in [k for k, b in self.bees.items() if now - b.seen > keep]:
            del self.bees[k]
