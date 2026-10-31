"""Server clock. All game time comes from here (spec 6.2: always server time).

Datetimes are naive UTC everywhere (SQLite stores no time zone). Tests replace the
clock with a FrozenClock to move time forward without sleeping.
"""
from __future__ import annotations

import datetime as dt

VN_OFFSET = dt.timedelta(hours=7)  # daily resets use UTC+7 (spec 6.1)


class Clock:
    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class FrozenClock(Clock):
    def __init__(self, start: dt.datetime | None = None):
        self._now = start or dt.datetime(2026, 1, 1, 8, 0, 0)

    def now(self) -> dt.datetime:
        return self._now

    def advance(self, **kwargs) -> dt.datetime:
        self._now += dt.timedelta(**kwargs)
        return self._now


_clock: Clock = Clock()


def now() -> dt.datetime:
    return _clock.now()


def set_clock(c: Clock) -> None:
    global _clock
    _clock = c


def local_date(t: dt.datetime) -> str:
    """Calendar date in UTC+7 as ISO string, used for daily limits."""
    return (t + VN_OFFSET).date().isoformat()
