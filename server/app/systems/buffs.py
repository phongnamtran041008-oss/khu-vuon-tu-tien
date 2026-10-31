"""Pill buffs (spec 12.3): Tụ Linh (more Tu Vi per right answer), Kháng Mực (+ink resistance),
Ngộ Tính (+3 s for every question). Each lasts balance/alchemy.json buff_seconds of real
time, kept in users.flags["buffs"] as {kind: until} so it survives a reconnect. Taking the
same pill again adds the time on top, up to twice one dose."""
from __future__ import annotations

import datetime as dt

from .. import balance
from ..models import User


def cfg() -> dict:
    return balance.load("alchemy")


def _until(user: User) -> dict[str, dt.datetime]:
    out = {}
    for k, v in ((user.flags or {}).get("buffs") or {}).items():
        try:
            out[k] = dt.datetime.fromisoformat(v)
        except (TypeError, ValueError):
            continue
    return out


def active(user: User, now: dt.datetime) -> dict[str, int]:
    """kind -> whole seconds left, only the buffs still running."""
    return {k: int((t - now).total_seconds()) + 1 for k, t in _until(user).items() if t > now}


def add(user: User, kind: str, now: dt.datetime) -> int:
    """Starts or extends a buff; returns the seconds left."""
    length = dt.timedelta(seconds=cfg()["buff_seconds"])
    cur = _until(user)
    base = max(cur.get(kind, now), now)
    until = min(base + length, now + 2 * length)
    flags = dict(user.flags or {})
    flags["buffs"] = {k: t.isoformat() for k, t in {**cur, kind: until}.items() if t > now}
    user.flags = flags
    return int((until - now).total_seconds())


def xp_mult(user: User, now: dt.datetime) -> float:
    return float(cfg()["buffs"]["tu_linh"]["xp_mult"]) if "tu_linh" in active(user, now) else 1.0


def extra_seconds(user: User, now: dt.datetime) -> float:
    return float(cfg()["buffs"]["ngo_tinh"]["extra_seconds"]) if "ngo_tinh" in active(user, now) else 0.0


def ink_res(seconds_left: dict[str, float]) -> float:
    """Kháng Mực of a player in the world (the world keeps its own copy of the deadlines)."""
    return float(cfg()["buffs"]["khang_muc"]["ink_res"]) if seconds_left.get("khang_muc", 0) > 0 else 0.0


def view(user: User, now: dt.datetime) -> list[dict]:
    c = cfg()["buffs"]
    return [{"id": k, "name_vi": c[k]["name_vi"], "seconds_left": s} for k, s in active(user, now).items() if k in c]
