"""Deterministic movement shared by server and client (client/engine/movement.py is a
line-for-line copy; tests check they agree). The client predicts with exactly the same
steps it sends, so the server's authoritative position matches unless the client cheats.

A step is (dx, dy, ms): direction keys held (-1/0/1 each) for `ms` milliseconds.
Positions are the character's feet; the collision box is FOOT_W x FOOT_H above them.
"""
from __future__ import annotations

DIAG = 0.7071
FOOT_W = 10
FOOT_H = 6


def foot_box(x: float, y: float) -> tuple[int, int, int, int]:
    """(left, top, width, height) like pygame.Rect(int(x - w/2), int(y - h), w, h)."""
    return int(x - FOOT_W / 2), int(y - FOOT_H), FOOT_W, FOOT_H


class Collider:
    """Map bounds + solid rectangles (x, y, w, h) with pygame.Rect overlap semantics."""

    def __init__(self, width_px: int, height_px: int, solids: list[tuple[int, int, int, int]], cell: int = 64):
        self.w, self.h = width_px, height_px
        self.solids = solids
        self.cell = cell
        self.grid: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}
        for r in solids:
            x, y, w, h = r
            for cy in range(y // cell, (y + h) // cell + 1):
                for cx in range(x // cell, (x + w) // cell + 1):
                    self.grid.setdefault((cx, cy), []).append(r)

    def blocked_box(self, left: int, top: int, w: int, h: int) -> bool:
        if left < 0 or top < 0 or left + w > self.w or top + h > self.h:
            return True
        c = self.cell
        seen = set()
        for cy in range(top // c, (top + h) // c + 1):
            for cx in range(left // c, (left + w) // c + 1):
                for r in self.grid.get((cx, cy), ()):
                    if r in seen:
                        continue
                    seen.add(r)
                    sx, sy, sw, sh = r
                    if left < sx + sw and left + w > sx and top < sy + sh and top + h > sy:
                        return True
        return False

    def blocked(self, x: float, y: float) -> bool:
        return self.blocked_box(*foot_box(x, y))


def facing_for(dx: int, dy: int, current: str) -> str:
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    if dy:
        return "down" if dy > 0 else "up"
    return current


def step(x: float, y: float, dx: int, dy: int, ms: int, speed: float, col: Collider) -> tuple[float, float]:
    fx, fy = float(dx), float(dy)
    if dx and dy:
        fx, fy = fx * DIAG, fy * DIAG
    dt = ms / 1000.0
    nx = x + fx * speed * dt
    if not col.blocked(nx, y):
        x = nx
    ny = y + fy * speed * dt
    if not col.blocked(x, ny):
        y = ny
    return x, y
