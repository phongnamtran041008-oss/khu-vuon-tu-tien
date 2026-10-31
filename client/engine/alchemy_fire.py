"""The canh lửa minigame of luyện đan (spec 12.3), shared byte for byte by the server
(app/systems/alchemy_fire.py) and the client (client/engine/alchemy_fire.py).

A needle sweeps the heat bar from 0 to `bar` and back, one sweep every `period_ms`. Each
press stops it; the next round starts from 0 again. The client only sends how long the
needle ran before each press (needle time, typing pinyin does not count); the server puts
those times through the same functions to know where the needle stood. Whole milliseconds
and one division, so both sides always get the same number.
"""
from __future__ import annotations

PERFECT, GOOD, MISS = "perfect", "good", "miss"


def needle(t_ms: int, period_ms: int, bar: int = 100) -> float:
    """Where the needle is t_ms after a round started (0 -> bar -> 0 -> ...)."""
    period_ms = max(2, int(period_ms))
    half = period_ms // 2
    t = int(t_ms) % (half * 2)
    if t <= half:
        return bar * t / half
    return bar * (2 * half - t) / half


def judge(pos: float, center: float, width: float, perfect_width: float) -> str:
    """perfect: within the bright middle of the văn hỏa zone; good: inside the zone."""
    d = abs(pos - center)
    if d <= perfect_width / 2:
        return PERFECT
    if d <= width / 2:
        return GOOD
    return MISS


def press_points(hits: list[str], points: dict) -> int:
    return sum(int(points[h]) for h in hits)


def total(hits: list[str], pinyin: list[bool | None], points: dict) -> tuple[int, int]:
    """(points scored, best possible). pinyin: True right, False wrong, None not asked."""
    got = press_points(hits, points)
    best = len(hits) * int(points[PERFECT])
    for p in pinyin:
        if p is None:
            continue
        best += int(points["pinyin_right"])
        got += int(points["pinyin_right"] if p else points["pinyin_wrong"])
    return got, best


def quality(got: int, best: int, table: list[dict]) -> str:
    share = got / best if best > 0 else 0.0
    for q in table:
        if share >= q["min"]:
            return q["id"]
    return table[-1]["id"]
