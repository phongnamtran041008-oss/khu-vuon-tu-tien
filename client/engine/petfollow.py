"""A Linh Thú trotting after its owner (stage 8): it keeps a few steps behind, turns to face
where it goes and stops when the owner stops. Purely visual; nothing here is sent."""
from __future__ import annotations

import math


class PetFollower:
    def __init__(self, x: float, y: float, kind: str = ""):
        self.kind = kind
        self.x, self.y = x - 12, y
        self.left = False
        self.moving = False
        self.walk_t = 0.0

    def update(self, dt: float, ox: float, oy: float, owner_facing: str = "down") -> None:
        back = {"up": (0, 10), "down": (-10, -4), "left": (12, 0), "right": (-12, 0)}.get(owner_facing, (-12, 0))
        tx, ty = ox + back[0], oy + back[1]
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d > 120:                          # left far behind (a portal, a respawn): jump there
            self.x, self.y = tx, ty
            d = 0
        self.moving = d > 3
        if self.moving:
            speed = min(d * 6, 140) * dt
            self.x += dx / d * speed
            self.y += dy / d * speed
            if abs(dx) > 1:
                self.left = dx < 0
            self.walk_t += dt
        else:
            self.walk_t = 0.0

    @property
    def frame(self) -> int:
        return int(self.walk_t * 8) % 2 if self.moving else 0
