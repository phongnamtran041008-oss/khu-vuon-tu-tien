"""Loads server/data/balance/*.json (spec 0: every balance number lives in data files)."""
from __future__ import annotations

import json
from functools import lru_cache

from .config import DATA_DIR


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if k.startswith("_"):
            continue
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """balance/<name>.json, with balance/<BALANCE_PROFILE>/<name>.json merged on top
    (e.g. BALANCE_PROFILE=dev for fast testing; only allowed in the dev environment)."""
    from .config import settings
    data = json.loads((DATA_DIR / "balance" / f"{name}.json").read_text("utf-8"))
    if settings.balance_profile:
        over = DATA_DIR / "balance" / settings.balance_profile / f"{name}.json"
        if over.exists():
            data = _merge(data, json.loads(over.read_text("utf-8")))
    return data


def gacha() -> dict:
    return load("gacha")


def garden() -> dict:
    return load("garden")


def quiz() -> dict:
    return load("quiz")


def economy() -> dict:
    return load("economy")
