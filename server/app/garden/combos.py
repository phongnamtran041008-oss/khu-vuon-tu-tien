"""Adjacency reactions in the garden (spec 6.5), driven by data/combos.json.

* auras:  水 shortens the review wait of neighbours, 火 makes neighbours grow faster
* hazard: 火 next to 木 has a daily chance to scorch the wood (wither +30)
* unlocks: the right characters side by side reveal a hidden character (明 林 森 好 休 吗)

Only plants at stage >= 1 take part. Discoveries are recorded once per player in
codex_entries (codex="discovery") and are never listed in advance.
"""
from __future__ import annotations

import datetime as dt
import json
import random
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..config import DATA_DIR
from ..learning import srs
from ..learning.wordbank import bank
from ..models import CodexEntry, Collection, Plot, Seed, User
from ..systems import inventory

NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


@lru_cache(maxsize=1)
def combos() -> list[dict]:
    return json.loads((DATA_DIR / "combos.json").read_text("utf-8"))["combos"]


def _cfg() -> dict:
    return balance.garden()["combo"]


def active_grid(plots: list[Plot]) -> dict[tuple[int, int], str]:
    """(x, y) -> hanzi for plants that count for reactions."""
    b = bank()
    return {(p.x, p.y): b.get(p.word_id).hanzi for p in plots
            if p.word_id and p.unlocked and p.stage >= _cfg()["active_min_stage"]}


def neighbours(grid: dict, x: int, y: int) -> list[str]:
    return [grid[(x + dx, y + dy)] for dx, dy in NEIGHBOURS if (x + dx, y + dy) in grid]


def wait_multiplier(plots: list[Plot], plot: Plot) -> float:
    grid = active_grid(plots)
    m = 1.0
    for h in neighbours(grid, plot.x, plot.y):
        if h == "水":
            m *= _cfg()["water_wait_mult"]
        elif h == "火":
            m *= _cfg()["fire_wait_mult"]
    return m


def auras_for(plots: list[Plot], plot: Plot) -> list[str]:
    grid = active_grid(plots)
    return sorted({ {"水": "water", "火": "fire"}[h] for h in neighbours(grid, plot.x, plot.y) if h in ("水", "火")})


def _connected_groups(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    groups, seen = [], set()
    for c in cells:
        if c in seen:
            continue
        stack, g = [c], set()
        while stack:
            cur = stack.pop()
            if cur in g:
                continue
            g.add(cur)
            for dx, dy in NEIGHBOURS:
                n = (cur[0] + dx, cur[1] + dy)
                if n in cells and n not in g:
                    stack.append(n)
        seen |= g
        groups.append(g)
    return groups


def matched_unlocks(grid: dict[tuple[int, int], str]) -> list[dict]:
    out = []
    for c in combos():
        if c["kind"] != "unlock":
            continue
        comps = c["components"]
        if c["pattern"] == "adjacent":
            a, b = comps
            for (x, y), h in grid.items():
                if h != a:
                    continue
                if any(grid.get((x + dx, y + dy)) == b for dx, dy in NEIGHBOURS):
                    out.append(c)
                    break
        elif c["pattern"] == "three_line_or_l":
            # any 3 orthogonally connected cells are a straight line or an L
            cells = {pos for pos, h in grid.items() if h == comps[0]}
            if any(len(g) >= 3 for g in _connected_groups(cells)):
                out.append(c)
    return out


async def check_discoveries(db: AsyncSession, user: User, plots: list[Plot]) -> list[dict]:
    """Grant every newly matched unlock once. Returns popup data for the client."""
    matched = matched_unlocks(active_grid(plots))
    if not matched:
        return []
    found = set((await db.execute(select(CodexEntry.entry_id).where(
        CodexEntry.user_id == user.id, CodexEntry.codex == "discovery"))).scalars().all())
    now = clock.now()
    b = bank()
    out = []
    for c in matched:
        if c["id"] in found:
            continue
        w = b.by_hanzi[c["result"]]
        db.add(CodexEntry(user_id=user.id, codex="discovery", entry_id=c["id"], discovered_at=now, progress={}))
        owned = (await db.execute(select(Collection).where(
            Collection.user_id == user.id, Collection.word_id == w.id))).scalar_one_or_none()
        seed_id = None
        if owned is None:
            db.add(Collection(user_id=user.id, word_id=w.id, first_seen_at=now))
            seed = Seed(user_id=user.id, word_id=w.id, duplicate=False, source="combo", obtained_at=now)
            db.add(seed)
            await db.flush()
            seed_id = seed.id
        reward = {}
        if c.get("reward_stones_key"):
            amount = _cfg()[c["reward_stones_key"]]
            await inventory.change_currency(db, user.id, "spirit_stones", amount, "combo", c["id"])
            reward["spirit_stones"] = amount
        if c.get("reward_decoration"):
            flags = dict(user.flags or {})
            decos = list(flags.get("decorations", []))
            if c["reward_decoration"] not in decos:
                decos.append(c["reward_decoration"])
            flags["decorations"] = decos
            user.flags = flags
            reward["decoration"] = c["reward_decoration"]
        out.append(discovery_view(c, seed_id=seed_id, reward=reward))
    await db.flush()
    return out


def discovery_view(c: dict, seed_id: int | None = None, reward: dict | None = None) -> dict:
    w = bank().by_hanzi[c["result"]]
    return {"combo_id": c["id"], "components": c["components"], "result": c["result"],
            "result_word_id": w.id, "pinyin": w.pinyin, "meaning_vi": w.meaning_vi,
            "text_vi": c["text_vi"], "etymology_verified": c.get("etymology_verified", False),
            "decomposition": c.get("decomposition"), "seed_id": seed_id, "reward": reward or {}}


async def discoveries(db: AsyncSession, user: User) -> dict:
    rows = (await db.execute(select(CodexEntry).where(
        CodexEntry.user_id == user.id, CodexEntry.codex == "discovery"))).scalars().all()
    by_id = {c["id"]: c for c in combos()}
    found = [dict(discovery_view(by_id[r.entry_id]), discovered_at=r.discovered_at.isoformat() + "Z")
             for r in rows if r.entry_id in by_id]
    total = sum(1 for c in combos() if c["kind"] == "unlock")
    return {"found": found, "total": total}


def apply_fire(plots: list[Plot], today: str) -> list[dict]:
    """Daily scorch roll for wood next to fire (lazy, deterministic per plot and day so
    reloading never re-rolls a day)."""
    cfg = _cfg()
    grid = active_grid(plots)
    events = []
    for p in plots:
        if (p.x, p.y) not in grid or grid[(p.x, p.y)] != "木":
            p.fire_checked_date = today if p.word_id else None
            continue
        if "火" not in neighbours(grid, p.x, p.y):
            p.fire_checked_date = today
            continue
        last = p.fire_checked_date or today
        d = dt.date.fromisoformat(last)
        end = dt.date.fromisoformat(today)
        while d < end:
            d += dt.timedelta(days=1)
            if random.Random(f"fire:{p.id}:{d.isoformat()}").random() < cfg["fire_wood_chance_per_day"]:
                p.wither = min(100.0, p.wither + cfg["fire_wood_wither"])
                events.append({"plot_id": p.id, "date": d.isoformat()})
                if p.wither >= balance.garden()["wither_regress_at"]:
                    srs.regress(p, clock.now())
        p.fire_checked_date = today
    return events
