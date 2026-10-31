"""Linh Phong — spirit bees and their hive (spec 10).

A bee hatches from a Trứng Ong (gacha, quests) into one cell of the hexagon hive in the
abode. Every bee has exactly one role at a time:
  * hive      — makes Linh Mật (and a little Sáp Ong), counted lazily when the hive is opened;
  * pollinate — fills the pollen bar of flowering plants (stage >= 3) in the garden. A full
                bar marks the plant "pollinated": 5 fruits instead of 3, a chance of Linh Quả,
                and the review wait that is running (or the next one) is cut by at most 25 %.
                Pollination never moves a plant to its next stage: only a right answer does;
  * guard     — 2-5 of them (by realm) follow the character in the shared world and attack
                monsters whose Mặc Thuẫn is already broken (realtime/combat.py).
Feeding (Linh Mật, word fruits, Linh Quả) gives XP and, with the species' favourite food,
bond. Bees of the same element in neighbouring cells resonate (small bonus to everything).
"""
from __future__ import annotations

import datetime as dt
import math
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..config import settings
from ..learning.wordbank import bank
from ..models import Bee, Character, CodexEntry, Collection, Fruit, Hive, Plot, User
from . import catalog, inventory

ROLES = ("hive", "pollinate", "guard")
MAX_REVIEW_CUT = 0.25   # spec 10.2: hard cap, whatever balance/bees.json says (see DECISIONS.md)


class BeeError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("bees")


def species() -> dict:
    return catalog.bees()


def sp(bee: Bee) -> dict:
    return species()[bee.bee_type]


# ------------------------------------------------------------------ the hexagon hive
def _hex_cfg() -> tuple[int, int]:
    h = cfg()["hive"]
    return h["columns"], h["rows"]


def cell_xy(idx: int) -> tuple[int, int]:
    cols, _ = _hex_cfg()
    return idx % cols, idx // cols


def neighbours(idx: int) -> list[int]:
    """Hexagon neighbours in an "odd-r" offset grid (odd rows are shifted right)."""
    cols, rows = _hex_cfg()
    c, r = cell_xy(idx)
    if r % 2 == 0:
        deltas = [(-1, 0), (1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1)]
    else:
        deltas = [(-1, 0), (1, 0), (0, -1), (1, -1), (0, 1), (1, 1)]
    out = []
    for dc, dr in deltas:
        nc, nr = c + dc, r + dr
        if 0 <= nc < cols and 0 <= nr < rows:
            out.append(nr * cols + nc)
    return out


def _cell_center(idx: int) -> tuple[float, float]:
    c, r = cell_xy(idx)
    return c + (0.5 if r % 2 else 0.0), r * 0.866


def cell_order() -> list[int]:
    """Order in which cells open: from the middle of the comb outwards."""
    cols, rows = _hex_cfg()
    n = cols * rows
    mx = sum(_cell_center(i)[0] for i in range(n)) / n
    my = sum(_cell_center(i)[1] for i in range(n)) / n
    return sorted(range(n), key=lambda i: (round(math.hypot(_cell_center(i)[0] - mx, _cell_center(i)[1] - my), 3), i))


def open_cells(hive: Hive) -> list[int]:
    return cell_order()[:max(0, min(hive.cells, cfg()["hive"]["cells_max"]))]


# ------------------------------------------------------------------ numbers
def rarity_mult(rarity: str) -> float:
    return cfg()["rarity_mult"][rarity]


def xp_to_next(level: int) -> int | None:
    lv = cfg()["level"]
    if level >= lv["max"]:
        return None
    return lv["xp_base"] + lv["xp_per_level"] * level


def power(bee: Bee, mastery: int = 0) -> float:
    """How strong this bee is compared with a level-1 Phàm bee of the same species."""
    c = cfg()
    s = sp(bee)
    lvl = 1 + c["level"]["stat_per_level"] * (bee.level - 1)
    bond = 1 + c["bond"]["stat_bonus_at_max"] * min(bee.bond, c["bond"]["max"]) / c["bond"]["max"]
    word = 1 + c["word_mastery_bonus_at_100"] * max(0, min(100, mastery)) / 100
    return rarity_mult(s["rarity"]) * lvl * bond * word


def resonance(bee: Bee, by_slot: dict[int, Bee]) -> float:
    """Đồng hệ cộng hưởng: +5 % per neighbouring bee of the same element (at most 3)."""
    if bee.hive_slot is None:
        return 0.0
    h = cfg()["hive"]
    el = sp(bee)["element"]
    n = sum(1 for nb in neighbours(bee.hive_slot) if nb in by_slot and sp(by_slot[nb])["element"] == el)
    return h["resonance_per_neighbour"] * min(n, h["resonance_max_neighbours"])


def hive_level_info(level: int) -> dict:
    levels = cfg()["hive"]["levels"]
    return levels[max(0, min(len(levels), level) - 1)]


def honey_per_hour(bee: Bee, res: float, hive_level: int, mastery: int = 0) -> float:
    return sp(bee)["honey"] * power(bee, mastery) * (1 + res) * hive_level_info(hive_level)["honey_mult"]


def pollen_per_hour(bee: Bee, res: float, mastery: int = 0) -> float:
    return sp(bee)["pollen"] * power(bee, mastery) * (1 + res)


def guard_stats(bee: Bee, res: float = 0.0, mastery: int = 0) -> dict:
    s = sp(bee)
    k = power(bee, mastery) * (1 + res)
    g = s["guard"]
    return {"hp": int(round(g["hp"] * k)), "atk": round(g["atk"] * k, 1), "cd": g["cd"]}


def guard_slots(realm: str) -> int:
    return int(cfg()["guard"]["slots_by_realm"].get(realm, 0))


def review_cut() -> float:
    """Share of a review wait that pollination removes; never more than 25 % (spec 10.2)."""
    return max(0.0, min(MAX_REVIEW_CUT, float(cfg()["pollination"]["review_wait_cut"])))


def _speed() -> float:
    """Production follows TIME_SCALE, like the SRS waits it is meant to fit into."""
    return float(settings.time_scale)


# ------------------------------------------------------------------ loading
async def bees_of(db: AsyncSession, user_id: int) -> list[Bee]:
    return list((await db.execute(select(Bee).where(Bee.user_id == user_id).order_by(Bee.id))).scalars().all())


async def masteries(db: AsyncSession, user_id: int, bees: list[Bee]) -> dict[str, int]:
    ids = {sp(b)["word_id"] for b in bees}
    if not ids:
        return {}
    rows = (await db.execute(select(Collection.word_id, Collection.mastery).where(
        Collection.user_id == user_id, Collection.word_id.in_(ids), Collection.introduced.is_(True)))).all()
    return {w: m for w, m in rows}


def _mastery(bee: Bee, mast: dict[str, int]) -> int:
    return mast.get(sp(bee)["word_id"], 0)


async def get_hive(db: AsyncSession, user_id: int) -> Hive | None:
    return await db.get(Hive, user_id)


async def ensure_hive(db: AsyncSession, user: User) -> Hive:
    """The comb exists from the first visit; Trúc Lão gives one Phàm egg to start with."""
    hive = await db.get(Hive, user.id)
    now = clock.now()
    if hive is None:
        hive = Hive(user_id=user.id, layout={}, level=1, decorations=[], honey=0.0, wax=0.0,
                    cells=cfg()["hive"]["cells_start"], honey_checked_at=now, pollen_checked_at=now)
        db.add(hive)
        await db.flush()
    flags = dict(user.flags or {})
    if not flags.get("starter_egg"):
        flags["starter_egg"] = True
        user.flags = flags
        await inventory.change_item(db, user.id, cfg()["starter_egg"], 1, "starter_egg", None, bound=True)
    return hive


# ------------------------------------------------------------------ honey (role: hive)
def refresh_honey(hive: Hive, bees: list[Bee], mast: dict[str, int], now: dt.datetime) -> float:
    """Lazy production since the last look (spec 10.2.1). Returns Linh Mật made now."""
    last = hive.honey_checked_at or now
    hive.honey_checked_at = now
    secs = max(0.0, (now - last).total_seconds())
    if secs <= 0:
        return 0.0
    by_slot = {b.hive_slot: b for b in bees if b.hive_slot is not None}
    rate = sum(honey_per_hour(b, resonance(b, by_slot), hive.level, _mastery(b, mast))
               for b in bees if b.role == "hive") / 3600 * _speed()
    cap = hive_level_info(hive.level)["capacity"]
    made = max(0.0, min(cap - (hive.honey or 0.0), rate * secs))
    hive.honey = (hive.honey or 0.0) + made
    hive.wax = (hive.wax or 0.0) + made * cfg()["hive"]["wax_per_honey"]
    return made


# ------------------------------------------------------------------ pollination (role: pollinate)
def plant_elements(hanzi: str) -> set[str]:
    return {el for el, words in cfg()["pollination"]["plant_elements"].items() if hanzi in words}


def _affinity(element: str, p: Plot, plots_by_xy: dict) -> float:
    """Ong hệ Thủy thụ phấn nhanh hơn cạnh cây 水: the plant itself or a neighbour shares the element."""
    from ..garden import combos
    near = [p] + [plots_by_xy.get((p.x + dx, p.y + dy)) for dx, dy in combos.NEIGHBOURS]
    for q in near:
        if q is not None and q.word_id and element in plant_elements(bank().get(q.word_id).hanzi):
            return float(cfg()["pollination"]["affinity_mult"])
    return 1.0


def eligible(p: Plot) -> bool:
    return bool(p.unlocked and p.word_id and p.stage >= cfg()["pollination"]["min_stage"] and not p.pollinated)


def _on_pollinated(p: Plot, at: dt.datetime, plots: list[Plot]) -> None:
    """Full bar: cut the review wait that is running now by at most 25 %, or keep the cut
    for the next wait if the plant is already due (spec 10.2.2)."""
    from ..garden import combos
    from ..learning import srs
    p.pollinated, p.pollen = True, 100.0
    p.pollen_boost = False
    if p.stage >= srs.RIPE:
        return
    full = srs.wait_after_reaching(p.stage)
    if p.next_review_at is not None and p.next_review_at > at and full is not None:
        wait = full * combos.wait_multiplier(plots, p)
        p.next_review_at = max(at, p.next_review_at - wait * review_cut())
    else:
        p.pollen_boost = True


def run_pollination(plots: list[Plot], rates: list[tuple[str, float]], t0: dt.datetime,
                    t1: dt.datetime) -> list[tuple[Plot, dt.datetime]]:
    """Advances every eligible plant's pollen from t0 to t1. rates = (element, % per second)
    for each pollinating bee; each bee spreads its work evenly over the eligible plants.
    Returns the plants that filled up and when. Only pollen changes — never the stage."""
    done: list[tuple[Plot, dt.datetime]] = []
    if not rates or t1 <= t0:
        return done
    by_xy = {(p.x, p.y): p for p in plots}
    t = t0
    for _ in range(len(plots) + 1):
        el = [p for p in plots if eligible(p)]
        if not el:
            break
        per = {p.id: sum(r * _affinity(e, p, by_xy) for e, r in rates) / len(el) for p in el}
        need = {p.id: max(0.0, 100.0 - (p.pollen or 0.0)) / per[p.id] for p in el if per[p.id] > 0}
        if not need:
            break
        step = min(need.values())
        left = (t1 - t).total_seconds()
        if step >= left:
            for p in el:
                p.pollen = min(100.0, (p.pollen or 0.0) + per[p.id] * left)
            break
        t = t + dt.timedelta(seconds=step)
        for p in el:
            p.pollen = min(100.0, (p.pollen or 0.0) + per[p.id] * step)
            if need.get(p.id, 1e18) <= step + 1e-9:
                _on_pollinated(p, t, plots)
                done.append((p, t))
    return done


async def sync_garden(db: AsyncSession, user_id: int, plots: list[Plot], now: dt.datetime | None = None) -> list[dict]:
    """Brings pollination up to now. Called before anything reads or changes the garden."""
    now = now or clock.now()
    hive = await db.get(Hive, user_id)
    if hive is None:
        return []
    last = hive.pollen_checked_at or now
    hive.pollen_checked_at = now
    bees = [b for b in await bees_of(db, user_id) if b.role == "pollinate"]
    if not bees or now <= last:
        return []
    mast = await masteries(db, user_id, bees)
    all_bees = await bees_of(db, user_id)
    by_slot = {b.hive_slot: b for b in all_bees if b.hive_slot is not None}
    rates = [(sp(b)["element"], pollen_per_hour(b, resonance(b, by_slot), _mastery(b, mast)) / 3600 * _speed())
             for b in bees]
    done = run_pollination(plots, rates, last, now)
    out = []
    for p, _ in done:
        out.append({"plot_id": p.id, "hanzi": bank().get(p.word_id).hanzi})
    if done:
        for b in bees:
            await add_bee_xp(db, b, cfg()["xp_pollinated_plant"] * len(done))
        from . import quests
        await quests.on_event(db, user_id, "pollinate", "", len(done))
    return out


def harvest_bonus(p: Plot, rng: random.Random) -> tuple[int, int]:
    """(fruits, Linh Quả) for a harvest; a pollinated plant gives more (spec 10.2.2)."""
    po = cfg()["pollination"]
    if not p.pollinated:
        return balance.garden()["harvest_fruits"], 0
    rar = bank().get(p.word_id).rarity
    return po["harvest_fruits_pollinated"], int(rng.random() < po["spirit_fruit_chance"].get(rar, 0.25))


# ------------------------------------------------------------------ XP, levels, codex
async def add_bee_xp(db: AsyncSession, bee: Bee, n: int) -> int:
    """Returns levels gained."""
    if n <= 0:
        return 0
    gained = 0
    bee.xp += int(n)
    for _ in range(100):
        need = xp_to_next(bee.level)
        if need is None:
            bee.xp = 0
            break
        if bee.xp < need:
            break
        bee.xp -= need
        bee.level += 1
        gained += 1
    if gained:
        e = await db.get(CodexEntry, (bee.user_id, "bee", bee.bee_type))
        if e is not None:
            prog = dict(e.progress or {})
            prog["best_level"] = max(int(prog.get("best_level", 1)), bee.level)
            e.progress = prog
    return gained


async def species_found(db: AsyncSession, user_id: int) -> int:
    return len((await db.execute(select(CodexEntry.entry_id).where(
        CodexEntry.user_id == user_id, CodexEntry.codex == "bee"))).scalars().all())


async def _discover(db: AsyncSession, user: User, kind: str) -> tuple[bool, list[dict]]:
    """Ong Phổ: first hatch of a species. Returns (new, milestone rewards granted)."""
    e = await db.get(CodexEntry, (user.id, "bee", kind))
    if e is not None:
        e.progress = {**(e.progress or {}), "hatched": int((e.progress or {}).get("hatched", 0)) + 1}
        return False, []
    db.add(CodexEntry(user_id=user.id, codex="bee", entry_id=kind, discovered_at=clock.now(),
                      progress={"hatched": 1, "favorite_known": False, "best_level": 1}))
    await db.flush()
    found = await species_found(db, user.id)
    from . import quests
    await quests.on_event(db, user.id, "bee_species", "", 1)
    return True, await _milestones(db, user, found)


async def _milestones(db: AsyncSession, user: User, found: int) -> list[dict]:
    from . import items
    flags = dict(user.flags or {})
    got = set(flags.get("bee_milestones", []))
    out = []
    for m in cfg().get("codex_milestones", []):
        if found >= m["species"] and m["species"] not in got:
            got.add(m["species"])
            r = {"species": m["species"], "items": []}
            for cur in ("spirit_stones", "immortal_jade"):
                if m.get(cur):
                    await inventory.change_currency(db, user.id, cur, m[cur], "bee_codex", str(m["species"]))
                    r[cur] = m[cur]
            r["items"] = await items.grant_items(db, user.id, [{"item": k, "qty": v} for k, v in m.get("items", {}).items()],
                                                 "bee_codex", str(m["species"]))
            out.append(r)
    if out:
        flags["bee_milestones"] = sorted(got)
        user.flags = flags
    return out


# ------------------------------------------------------------------ views
def species_public(kind: str) -> dict:
    s = species()[kind]
    c = cfg()
    return {"id": kind, "name_vi": s["name_vi"], "hanzi": s["hanzi"], "pinyin": s["pinyin"],
            "rarity": s["rarity"], "rarity_vi": c["rarity_names_vi"][s["rarity"]],
            "rarity_color": c["rarity_colors"][s["rarity"]],
            "element": s["element"], "element_vi": c["element_names_vi"][s["element"]],
            "element_color": c["element_colors"][s["element"]],
            "skill": s["skill"]["type"], "skill_vi": s["skill"]["desc_vi"], "look": s["look"],
            "word": {"id": s["word_id"], "hanzi": s["word_hanzi"], "pinyin": s["word_pinyin"], "vi": s["word_vi"]},
            "real_word": s["real_word"], "desc_vi": s["desc_vi"]}


def bee_view(b: Bee, by_slot: dict[int, Bee], hive_level: int, mast: dict[str, int],
             favorite_known: bool = False) -> dict:
    res = resonance(b, by_slot)
    m = _mastery(b, mast)
    s = sp(b)
    return {**species_public(b.bee_type), "id": b.id, "species": b.bee_type, "level": b.level, "xp": b.xp,
            "xp_next": xp_to_next(b.level), "bond": b.bond, "bond_max": cfg()["bond"]["max"], "role": b.role,
            "role_vi": cfg()["role_names_vi"][b.role], "slot": b.hive_slot,
            "resonance_pct": int(round(res * 100)), "word_mastery": m,
            "honey_per_hour": round(honey_per_hour(b, res, hive_level, m) * _speed(), 2),
            "pollen_per_hour": round(pollen_per_hour(b, res, m) * _speed(), 1),
            "guard": guard_stats(b, res, m),
            "favorite_known": favorite_known,
            "favorite": _food_label(s["favorite"]) if favorite_known else None,
            "favorite_hint_vi": s["favorite_hint_vi"]}


def _food_label(food: str) -> str:
    if food.startswith("fruit:"):
        return f"Quả chữ {food[6:]}"
    return catalog.item_name(food)


async def _favorites_known(db: AsyncSession, user_id: int) -> set[str]:
    rows = (await db.execute(select(CodexEntry).where(CodexEntry.user_id == user_id,
                                                      CodexEntry.codex == "bee"))).scalars().all()
    return {e.entry_id for e in rows if (e.progress or {}).get("favorite_known")}


async def hive_view(db: AsyncSession, user: User) -> dict:
    now = clock.now()
    hive = await ensure_hive(db, user)
    bees = await bees_of(db, user.id)
    mast = await masteries(db, user.id, bees)
    refresh_honey(hive, bees, mast, now)
    c = cfg()
    h = c["hive"]
    by_slot = {b.hive_slot: b for b in bees if b.hive_slot is not None}
    fav = await _favorites_known(db, user.id)
    ch = await db.get(Character, user.id)
    realm = ch.realm if ch else "pham_nhan"
    st = await _stacks(db, user.id)
    lvl = hive_level_info(hive.level)
    nxt_level = h["levels"][hive.level] if hive.level < len(h["levels"]) else None
    found = await species_found(db, user.id)
    unlocked_decor = [lv["decoration"] for lv in h["levels"][:hive.level] if lv.get("decoration")]
    eggs = [{"item_id": iid, "rarity": r, "name_vi": catalog.item_name(iid), "qty": st.get(iid, 0)}
            for r, iid in c["eggs"].items() if st.get(iid, 0) > 0]
    fruits = (await db.execute(select(Fruit).where(Fruit.user_id == user.id, Fruit.count > 0))).scalars().all()
    b = bank()
    rate = sum(honey_per_hour(x, resonance(x, by_slot), hive.level, _mastery(x, mast))
               for x in bees if x.role == "hive") * _speed()
    return {
        "level": hive.level, "level_max": len(h["levels"]),
        "cells": hive.cells, "cells_max": h["cells_max"], "columns": h["columns"], "rows": h["rows"],
        "open_cells": open_cells(hive), "next_cell": _next_cell_info(hive, found),
        "honey": round(hive.honey or 0.0, 2), "wax": round(hive.wax or 0.0, 2),
        "capacity": lvl["capacity"], "honey_per_hour": round(rate, 2),
        "next_level": ({"level": nxt_level["level"], "spirit_stones": nxt_level["cost"]["spirit_stones"],
                        "items": [{"item": k, "name_vi": catalog.item_name(k), "qty": v, "have": st.get(k, 0)}
                                  for k, v in nxt_level["cost"]["items"].items()],
                        "capacity": nxt_level["capacity"], "honey_mult": nxt_level["honey_mult"],
                        "decoration_vi": h["decorations_vi"].get(nxt_level.get("decoration") or "", "")}
                       if nxt_level else None),
        "decorations": [{"id": d, "name_vi": h["decorations_vi"][d], "on": d in (hive.decorations or [])}
                        for d in unlocked_decor],
        "bees": [bee_view(x, by_slot, hive.level, mast, x.bee_type in fav) for x in bees],
        "eggs": eggs,
        "foods": [{"food": k, "name_vi": catalog.item_name(k), "qty": st.get(k, 0)}
                  for k in ("linh_mat", "linh_qua", "ca_nho") if st.get(k, 0) > 0]
                 + [{"food": f"fruit:{r.word_id}", "name_vi": f"Quả {b.get(r.word_id).hanzi}",
                     "hanzi": b.get(r.word_id).hanzi, "qty": r.count} for r in fruits],
        "guard_slots": guard_slots(realm), "guard_used": sum(1 for x in bees if x.role == "guard"),
        "pollinate_max": c["pollination"]["max_pollinators"],
        "pollinate_used": sum(1 for x in bees if x.role == "pollinate"),
        "species_found": found, "species_total": len(species()),
        "server_time": now.isoformat() + "Z",
    }


async def _stacks(db: AsyncSession, user_id: int) -> dict[str, int]:
    from . import items
    return await items.stacks(db, user_id)


def _next_cell_info(hive: Hive, found: int) -> dict | None:
    h = cfg()["hive"]
    if hive.cells >= h["cells_max"]:
        return None
    n = hive.cells + 1                      # the n-th cell (1-based)
    i = n - h["cells_start"] - 1
    cost = h["cell_costs"][min(i, len(h["cell_costs"]) - 1)]
    need = max([s for c_, s in h["cell_species_required"] if n >= c_] or [0])
    return {"cell": n, "spirit_stones": cost, "species_required": need, "ok": found >= need}


# ------------------------------------------------------------------ actions
async def _bee(db: AsyncSession, user: User, bee_id: int) -> Bee:
    b = await db.get(Bee, bee_id)
    if b is None or b.user_id != user.id:
        raise BeeError(404, "no_bee", "Không tìm thấy con ong này.")
    return b


async def _sync_all(db: AsyncSession, user: User, now: dt.datetime) -> tuple[Hive, list[Bee]]:
    """Counts honey and pollen up to now with the current roles, before anything changes them."""
    from ..garden import garden as gd
    hive = await ensure_hive(db, user)
    bees = await bees_of(db, user.id)
    refresh_honey(hive, bees, await masteries(db, user.id, bees), now)
    plots = await gd.ensure_plots(db, user.id)
    await sync_garden(db, user.id, plots, now)
    return hive, bees


async def collect(db: AsyncSession, user: User) -> dict:
    hive, _ = await _sync_all(db, user, clock.now())
    honey, wax = int(hive.honey or 0), int(hive.wax or 0)
    if honey <= 0 and wax <= 0:
        raise BeeError(400, "no_honey", "Tổ chưa có mật để lấy. Hãy để vài con ong ở tổ làm mật.")
    hive.honey -= honey
    hive.wax -= wax
    got = {}
    from . import pets
    bonus = int(honey * await pets.skill_value(db, user.id, "honey"))   # Dê (stage 8), on what is collected
    honey += bonus
    if honey:
        got["linh_mat"] = await inventory.change_item(db, user.id, "linh_mat", honey, "hive_collect")
    if wax:
        got["sap_ong"] = await inventory.change_item(db, user.id, "sap_ong", wax, "hive_collect")
    return {"honey": honey, "wax": wax, "totals": got, "hive_honey": round(hive.honey, 2), "pet_bonus": bonus}


async def hatch(db: AsyncSession, user: User, item_id: str, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    c = cfg()
    rarity = next((r for r, iid in c["eggs"].items() if iid == item_id), None)
    if rarity is None:
        raise BeeError(400, "not_egg", "Đây không phải trứng ong.")
    hive, bees = await _sync_all(db, user, clock.now())
    used = {b.hive_slot for b in bees if b.hive_slot is not None}
    free = [i for i in open_cells(hive) if i not in used]
    if not free:
        raise BeeError(400, "hive_full", "Tổ ong hết ô trống. Mở thêm ô hoặc thả bớt ong.")
    try:
        await inventory.consume_item(db, user.id, item_id, 1, "hatch")
    except inventory.InsufficientFunds:
        raise BeeError(400, "no_egg", "Bạn không có quả trứng này.")
    have = set((await db.execute(select(CodexEntry.entry_id).where(
        CodexEntry.user_id == user.id, CodexEntry.codex == "bee"))).scalars().all())
    pool = [k for k, s in species().items() if s["rarity"] == rarity]
    weights = [c["hatch_new_species_weight"] if k not in have else 1.0 for k in pool]
    kind = rng.choices(pool, weights)[0]
    bee = Bee(user_id=user.id, bee_type=kind, level=1, xp=0, hive_slot=free[0], role="hive", bond=0,
              obtained_at=clock.now())
    db.add(bee)
    await db.flush()
    new, milestones = await _discover(db, user, kind)
    from . import quests
    await quests.on_event(db, user.id, "hatch", "", 1)
    bees.append(bee)
    by_slot = {b.hive_slot: b for b in bees if b.hive_slot is not None}
    mast = await masteries(db, user.id, bees)
    return {"bee": bee_view(bee, by_slot, hive.level, mast, False), "new_species": new, "milestones": milestones}


async def move(db: AsyncSession, user: User, bee_id: int, slot: int) -> dict:
    hive, bees = await _sync_all(db, user, clock.now())
    b = next((x for x in bees if x.id == bee_id), None)
    if b is None:
        raise BeeError(404, "no_bee", "Không tìm thấy con ong này.")
    if slot not in open_cells(hive):
        raise BeeError(400, "cell_locked", "Ô này của tổ chưa mở.")
    other = next((x for x in bees if x.hive_slot == slot and x.id != b.id), None)
    if other is not None:  # swap
        other.hive_slot, b.hive_slot = b.hive_slot, slot
    else:
        b.hive_slot = slot
    await db.flush()
    return await hive_view(db, user)


async def set_role(db: AsyncSession, user: User, bee_id: int, role: str) -> dict:
    if role not in ROLES:
        raise BeeError(400, "bad_role", "Vai trò không hợp lệ.")
    hive, bees = await _sync_all(db, user, clock.now())
    b = next((x for x in bees if x.id == bee_id), None)
    if b is None:
        raise BeeError(404, "no_bee", "Không tìm thấy con ong này.")
    if b.role == role:
        return await hive_view(db, user)
    if role == "guard":
        ch = await db.get(Character, user.id)
        slots = guard_slots(ch.realm if ch else "pham_nhan")
        if slots <= 0:
            raise BeeError(400, "no_guard_slot", "Phàm Nhân chưa điều khiển được ong hộ vệ. Lên Luyện Khí đã nhé!")
        if sum(1 for x in bees if x.role == "guard") >= slots:
            raise BeeError(400, "guard_full", f"Cảnh giới hiện tại chỉ cho {slots} ong hộ vệ.")
    if role == "pollinate":
        mx = cfg()["pollination"]["max_pollinators"]
        if sum(1 for x in bees if x.role == "pollinate") >= mx:
            raise BeeError(400, "pollinate_full", f"Vườn chỉ cần tối đa {mx} ong thụ phấn.")
    b.role = role
    await db.flush()
    if role == "guard":
        from . import quests
        await quests.on_event(db, user.id, "guard", "", 1)
    await push_guards(db, user.id)
    return await hive_view(db, user)


def _pill_foods() -> dict:
    """Pills brewed for bees (balance/alchemy.json bee_food)."""
    return balance.load("alchemy")["bee_food"]


async def feed(db: AsyncSession, user: User, bee_id: int, food: str) -> dict:
    c = cfg()
    b = await _bee(db, user, bee_id)
    s = sp(b)
    if food.startswith("fruit:"):
        word_id = food[6:]
        w = bank().words.get(word_id)
        if w is None:
            raise BeeError(400, "bad_food", "Ong không ăn được thứ này.")
        try:
            await inventory.change_fruit(db, user.id, word_id, -1, "feed_bee", str(b.id))
        except inventory.InsufficientFunds:
            raise BeeError(400, "no_food", "Không còn quả chữ này.")
        xp = c["feed"]["fruit"].get(w.rarity, 12)
        fav = s["favorite"] == f"fruit:{w.hanzi}"
    elif food in ("linh_mat", "linh_qua", "ca_nho") or food in _pill_foods():
        try:
            await inventory.consume_item(db, user.id, food, 1, "feed_bee", str(b.id))
        except inventory.InsufficientFunds:
            raise BeeError(400, "no_food", f"Không còn {catalog.item_name(food)}.")
        if food in _pill_foods():   # Phong Vương Đan (stage 8)
            xp = _pill_foods()[food]["xp"]
            b.bond = min(c["bond"]["max"], b.bond + _pill_foods()[food]["bond"])
        else:
            xp = c["feed"][food]["xp"]
        fav = s["favorite"] == food
    else:
        raise BeeError(400, "bad_food", "Ong không ăn được thứ này.")
    if fav:
        xp *= 2
    before = b.bond
    b.bond = min(c["bond"]["max"], b.bond + (c["bond"]["per_favorite"] if fav else c["bond"]["per_feed"]))
    levels = await add_bee_xp(db, b, xp)
    first_fav = False
    if fav:
        e = await db.get(CodexEntry, (user.id, "bee", b.bee_type))
        if e is not None and not (e.progress or {}).get("favorite_known"):
            e.progress = {**(e.progress or {}), "favorite_known": True}
            first_fav = True
    from . import quests
    await quests.on_event(db, user.id, "feed", "", 1)
    if levels and b.role == "guard":
        await push_guards(db, user.id)
    return {"bee_id": b.id, "xp_gained": xp, "favorite": fav, "favorite_discovered": first_fav,
            "levels_gained": levels, "level": b.level, "xp": b.xp, "xp_next": xp_to_next(b.level),
            "bond": b.bond, "bond_gained": b.bond - before,
            "favorite_vi": _food_label(s["favorite"]) if first_fav else None}


async def release(db: AsyncSession, user: User, bee_id: int) -> dict:
    hive, bees = await _sync_all(db, user, clock.now())
    b = next((x for x in bees if x.id == bee_id), None)
    if b is None:
        raise BeeError(404, "no_bee", "Không tìm thấy con ong này.")
    wax = cfg()["release_wax"][sp(b)["rarity"]]
    was_guard = b.role == "guard"
    await db.delete(b)
    await db.flush()
    total = await inventory.change_item(db, user.id, "sap_ong", wax, "release_bee", str(bee_id))
    if was_guard:
        await push_guards(db, user.id)
    return {"released": bee_id, "wax": wax, "wax_total": total}


async def unlock_cell(db: AsyncSession, user: User) -> dict:
    hive = await ensure_hive(db, user)
    info = _next_cell_info(hive, await species_found(db, user.id))
    if info is None:
        raise BeeError(400, "hive_max", "Tổ ong đã mở hết 30 ô.")
    if not info["ok"]:
        raise BeeError(400, "need_species", f"Cần phát hiện {info['species_required']} loài ong trong Ong Phổ "
                                            "mới mở được ô này.")
    try:
        await inventory.change_currency(db, user.id, "spirit_stones", -info["spirit_stones"], "hive_cell",
                                        str(info["cell"]))
    except inventory.InsufficientFunds as e:
        raise BeeError(400, "insufficient_funds", e.message_vi)
    hive.cells += 1
    await db.flush()
    return await hive_view(db, user)


async def upgrade(db: AsyncSession, user: User) -> dict:
    hive, _ = await _sync_all(db, user, clock.now())
    levels = cfg()["hive"]["levels"]
    if hive.level >= len(levels):
        raise BeeError(400, "hive_max_level", "Tổ ong đã nâng cấp tối đa.")
    nxt = levels[hive.level]
    st = await _stacks(db, user.id)
    for item, qty in nxt["cost"]["items"].items():
        if st.get(item, 0) < qty:
            raise BeeError(400, "no_material", f"Cần {qty} {catalog.item_name(item)} (đang có {st.get(item, 0)}).")
    try:
        await inventory.change_currency(db, user.id, "spirit_stones", -nxt["cost"]["spirit_stones"], "hive_upgrade",
                                        str(nxt["level"]))
    except inventory.InsufficientFunds as e:
        raise BeeError(400, "insufficient_funds", e.message_vi)
    for item, qty in nxt["cost"]["items"].items():
        await inventory.consume_item(db, user.id, item, qty, "hive_upgrade", str(nxt["level"]))
    hive.level = nxt["level"]
    if nxt.get("decoration"):
        hive.decorations = sorted(set(hive.decorations or []) | {nxt["decoration"]})
    await db.flush()
    return await hive_view(db, user)


async def set_decoration(db: AsyncSession, user: User, decoration: str, on: bool) -> dict:
    hive = await ensure_hive(db, user)
    unlocked = {lv["decoration"] for lv in cfg()["hive"]["levels"][:hive.level] if lv.get("decoration")}
    if decoration not in unlocked:
        raise BeeError(400, "decoration_locked", "Trang trí này chưa mở. Nâng cấp tổ ong để mở thêm.")
    cur = set(hive.decorations or [])
    (cur.add if on else cur.discard)(decoration)
    hive.decorations = sorted(cur)
    await db.flush()
    return await hive_view(db, user)


# ------------------------------------------------------------------ Ong Phổ
async def bee_book(db: AsyncSession, user: User) -> dict:
    rows = {e.entry_id: e for e in (await db.execute(select(CodexEntry).where(
        CodexEntry.user_id == user.id, CodexEntry.codex == "bee"))).scalars().all()}
    owned: dict[str, int] = {}
    for b in await bees_of(db, user.id):
        owned[b.bee_type] = owned.get(b.bee_type, 0) + 1
    order = cfg()["rarities"]
    out = []
    for kind, s in sorted(species().items(), key=lambda kv: (order.index(kv[1]["rarity"]), kv[0])):
        e = rows.get(kind)
        entry = {"id": kind, "found": e is not None, "rarity": s["rarity"],
                 "rarity_vi": cfg()["rarity_names_vi"][s["rarity"]], "rarity_color": cfg()["rarity_colors"][s["rarity"]],
                 "look": s["look"] if e is not None else None}
        if e is not None:
            prog = e.progress or {}
            entry.update(species_public(kind))
            entry.update({"hatched": int(prog.get("hatched", 1)), "best_level": int(prog.get("best_level", 1)),
                          "owned": owned.get(kind, 0), "favorite_known": bool(prog.get("favorite_known")),
                          "favorite": _food_label(s["favorite"]) if prog.get("favorite_known") else None,
                          "favorite_hint_vi": s["favorite_hint_vi"],
                          "honey": s["honey"], "pollen": s["pollen"], "guard": s["guard"]})
        out.append(entry)
    found = sum(1 for x in out if x["found"])
    claimed = set((user.flags or {}).get("bee_milestones", []))
    ms = [{"species": m["species"], "reached": found >= m["species"], "claimed": m["species"] in claimed,
           "reward_vi": _milestone_vi(m)} for m in cfg().get("codex_milestones", [])]
    return {"entries": out, "found": found, "total": len(out), "milestones": ms}


def _milestone_vi(m: dict) -> str:
    parts = []
    if m.get("spirit_stones"):
        parts.append(f"{m['spirit_stones']} Linh Thạch")
    if m.get("immortal_jade"):
        parts.append(f"{m['immortal_jade']} Tiên Ngọc")
    for k, v in m.get("items", {}).items():
        parts.append(f"{catalog.item_name(k)} ×{v}")
    return ", ".join(parts)


def species_catalog() -> dict:
    """Public, static: what each species looks like (the client draws other players' bees)."""
    return {"species": {k: {"name_vi": s["name_vi"], "hanzi": s["hanzi"], "rarity": s["rarity"],
                            "element": s["element"], "skill": s["skill"]["type"], "look": s["look"]}
                        for k, s in species().items()}}


# ------------------------------------------------------------------ guards in the world
async def guard_loadout(db: AsyncSession, user_id: int) -> list[dict]:
    """What the shared world needs to simulate this player's guard bees."""
    bees = await bees_of(db, user_id)
    ch = await db.get(Character, user_id)
    slots = guard_slots(ch.realm if ch else "pham_nhan")
    guards = [b for b in bees if b.role == "guard"][:slots]
    if not guards:
        return []
    mast = await masteries(db, user_id, guards)
    by_slot = {b.hive_slot: b for b in bees if b.hive_slot is not None}
    out = []
    for b in guards:
        s = sp(b)
        st = guard_stats(b, resonance(b, by_slot), _mastery(b, mast))
        out.append({"id": b.id, "sp": b.bee_type, "level": b.level, "hp": st["hp"], "atk": st["atk"], "cd": st["cd"],
                    "skill": dict(s["skill"]), "element": s["element"]})
    return out


async def push_guards(db: AsyncSession, user_id: int) -> None:
    from ..realtime.world import world
    world.set_bees(user_id, await guard_loadout(db, user_id))


async def combat_xp(user_id: int, bee_ids: list[int]) -> None:
    """Guard bees that helped bring a monster down grow a little (background task)."""
    from .. import db as dbm
    n = cfg()["xp_kill_assist"]
    async with dbm.SessionLocal() as db:
        leveled = False
        for bid in bee_ids:
            b = await db.get(Bee, bid)
            if b is not None and b.user_id == user_id:
                leveled = (await add_bee_xp(db, b, n)) > 0 or leveled
        if leveled:
            await push_guards(db, user_id)
        await db.commit()
