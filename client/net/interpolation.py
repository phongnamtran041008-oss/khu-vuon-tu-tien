"""Smooth movement of other players and monsters (spec 15.1): snapshots arrive ten times
a second; everyone else is drawn 100 ms in the past, between the two snapshots around
that moment, so they glide instead of jumping."""
from __future__ import annotations

from collections import deque

DELAY = 0.1      # seconds behind the newest snapshot
KEEP = 1.5       # seconds of history per entity


class Interpolator:
    def __init__(self, delay: float = DELAY):
        self.delay = delay
        self._offsets: deque = deque(maxlen=60)
        self.offset: float | None = None   # local clock - server clock (smallest seen = least delayed)
        self.buffers: dict[str, deque] = {}

    def clock_sample(self, server_t: float, local_t: float) -> None:
        self._offsets.append(local_t - server_t)
        self.offset = min(self._offsets)

    def push(self, eid: str, server_t: float, x: float, y: float, facing: int, moving: int) -> None:
        buf = self.buffers.setdefault(eid, deque())
        if buf and server_t <= buf[-1][0]:
            buf[-1] = (server_t, x, y, facing, moving)
        else:
            buf.append((server_t, x, y, facing, moving))
        while len(buf) > 2 and buf[1][0] < server_t - KEEP:
            buf.popleft()

    def forget(self, eid: str) -> None:
        self.buffers.pop(eid, None)

    def clear(self) -> None:
        self.buffers.clear()

    def last(self, eid: str):
        buf = self.buffers.get(eid)
        return buf[-1] if buf else None

    def sample(self, eid: str, local_t: float):
        """(x, y, facing, moving) to draw now, or None if nothing is known yet."""
        buf = self.buffers.get(eid)
        if not buf:
            return None
        if self.offset is None or len(buf) == 1:
            _, x, y, f, m = buf[-1]
            return x, y, f, m
        rt = local_t - self.offset - self.delay
        if rt <= buf[0][0]:
            _, x, y, f, m = buf[0]
            return x, y, f, m
        if rt >= buf[-1][0]:
            _, x, y, f, m = buf[-1]
            return x, y, f, 0 if rt - buf[-1][0] > 0.25 else m
        for a, b in zip(buf, list(buf)[1:]):
            if a[0] <= rt <= b[0]:
                k = (rt - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 1.0
                return a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, b[3], b[4] or a[4]
        _, x, y, f, m = buf[-1]
        return x, y, f, m
