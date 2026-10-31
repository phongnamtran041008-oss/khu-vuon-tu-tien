"""Spaced repetition for garden plants (spec 6.2, 6.3). Pure functions on a plot-like
object (anything with stage, next_review_at, wither, wither_checked_at)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .. import balance
from ..config import settings

RIPE = 5


def _cfg() -> dict:
    return balance.garden()


def scaled(seconds: float) -> dt.timedelta:
    return dt.timedelta(seconds=seconds / settings.time_scale)


def wait_after_reaching(stage: int) -> dt.timedelta | None:
    w = _cfg()["review_wait_after_reaching_stage"].get(str(stage))
    return scaled(w) if w is not None else None


def question_types(stage: int) -> list[str]:
    return list(_cfg()["stage_question"][str(stage)])


def is_due(plot, now: dt.datetime) -> bool:
    return 1 <= plot.stage < RIPE and plot.next_review_at is not None and now >= plot.next_review_at


@dataclass
class Outcome:
    new_stage: int
    regressed: bool = False
    reward: int = 0
    mastery_delta: int = 0


def regress(plot, at: dt.datetime) -> None:
    c = _cfg()
    plot.stage = max(1, plot.stage - 1)
    plot.wither = float(c["wither_after_regress"])
    plot.next_review_at = at
    plot.wither_checked_at = at


def refresh_wither(plot, now: dt.datetime, rate: float = 1.0) -> bool:
    """Lazy wither accrual (spec 6.3): +N per day once a review is more than the grace
    period overdue. Replays regressions at the exact moments they would have happened,
    so loading the garden late gives the same result as watching it live.
    rate < 1: the owner's Hổ (stage 8) slows it down. Returns True if the plant lost a stage."""
    c = _cfg()
    regressed = False
    if not (1 <= plot.stage < RIPE) or plot.next_review_at is None:
        plot.wither_checked_at = now
        return False
    per_second = c["wither_per_day_overdue"] / scaled(86400).total_seconds() * max(0.0, rate)
    grace = scaled(c["wither_grace_seconds"])
    t = plot.wither_checked_at or plot.next_review_at
    for _ in range(1000):  # bounded: each pass either finishes or regresses once
        start = max(t, plot.next_review_at + grace)
        if now <= start:
            break
        need = (c["wither_regress_at"] - plot.wither) / per_second
        if (now - start).total_seconds() < need:
            plot.wither += (now - start).total_seconds() * per_second
            break
        hit = start + dt.timedelta(seconds=need)
        regress(plot, hit)
        regressed = True
        t = hit
    plot.wither = min(float(c["wither_regress_at"]), max(0.0, plot.wither))
    plot.wither_checked_at = now
    return regressed


def apply_correct(plot, now: dt.datetime, wait_mult: float = 1.0) -> Outcome:
    """wait_mult < 1 shortens the next wait (garden auras such as 水, spec 6.5)."""
    c = _cfg()
    plot.stage = min(RIPE, plot.stage + 1)
    w = wait_after_reaching(plot.stage)
    plot.next_review_at = now + w * wait_mult if w is not None else None
    plot.wither = max(0.0, plot.wither + c["wither_correct"])
    plot.wither_checked_at = now
    return Outcome(plot.stage, reward=c["reward_per_new_stage"] * plot.stage,
                   mastery_delta=c["mastery_correct"])


def apply_wrong(plot, now: dt.datetime) -> Outcome:
    c = _cfg()
    plot.wither = min(float(c["wither_regress_at"]), plot.wither + c["wither_wrong"])
    regressed = False
    if plot.wither >= c["wither_regress_at"]:
        regress(plot, now)
        regressed = True
    plot.next_review_at = now + scaled(c["wrong_retry_wait"])
    plot.wither_checked_at = now
    return Outcome(plot.stage, regressed=regressed, mastery_delta=c["mastery_wrong"])


def learn(plot, now: dt.datetime, wait_mult: float = 1.0) -> None:
    """Stage 0 -> 1 after the introduction card ("Đã nhớ")."""
    plot.stage = 1
    plot.next_review_at = now + wait_after_reaching(1) * wait_mult
    plot.wither = 0.0
    plot.wither_checked_at = now
