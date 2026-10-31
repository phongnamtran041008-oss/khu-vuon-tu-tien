"""Quest chains (spec 7.4): Nhập Môn, Linh Phong, Ngư Ông, Đan Đạo. Steps of a chain unlock one after another.
Progress is pushed from the places where things happen (kills, meditation, talking, realms, brewing...).

Daily tasks (stage 8): every day (UTC+7) each player gets the `always` tasks of quests.json "daily" plus a few
more picked from its pool (the same pick for the whole day, from the user id and the date). They are rows of
the same quests table with the id "d<date>:<task>"; yesterday's are removed when today's are made. Claiming
all of today's gives a small bonus once."""
from __future__ import annotations

import random

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..models import Character, Quest, User
from . import catalog, inventory, items

ACTIVE, DONE, CLAIMED = "active", "done", "claimed"


class QuestError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def _steps() -> list[tuple[str, dict]]:
    out = []
    for cid, chain in catalog.quests()["chains"].items():
        for st in chain["steps"]:
            out.append((cid, st))
    return out


def _step(quest_id: str) -> tuple[str, dict] | None:
    if _is_daily(quest_id):
        tid = quest_id.split(":", 1)[1]
        t = next((x for x in _daily()["pool"] if x["id"] == tid), None)
        return ("daily", t) if t else None
    return next(((c, s) for c, s in _steps() if s["id"] == quest_id), None)


# ------------------------------------------------------------------ daily tasks
def _daily() -> dict:
    return catalog.quests()["daily"]


def _is_daily(quest_id: str) -> bool:
    return quest_id.startswith("d2") and ":" in quest_id


def _today() -> str:
    return clock.local_date(clock.now())


def daily_ids(user_id: int, date: str) -> list[str]:
    """Today's tasks of one player: the fixed ones, then a pick from the rest."""
    d = _daily()
    rest = [t["id"] for t in d["pool"] if t["id"] not in d["always"]]
    pick = random.Random(f"{user_id}|{date}").sample(rest, min(d["count"], len(rest)))
    return [f"d{date}:{t}" for t in list(d["always"]) + pick]


async def _ensure_daily(db: AsyncSession, user_id: int, rows: dict[str, Quest]) -> None:
    today = _today()
    old = [qid for qid in rows if _is_daily(qid) and not qid.startswith(f"d{today}:")]
    if old:
        await db.execute(delete(Quest).where(Quest.user_id == user_id, Quest.quest_id.in_(old)))
        for qid in old:
            rows.pop(qid, None)
    missing = [qid for qid in daily_ids(user_id, today) if qid not in rows]
    if not missing:
        return
    try:   # two requests of the same player at the turn of the day may both try: the second one reads them
        async with db.begin_nested():
            for qid in missing:
                db.add(Quest(user_id=user_id, quest_id=qid, state=ACTIVE, progress={"n": 0}))
    except IntegrityError:
        pass
    for qid in missing:
        q = await db.get(Quest, (user_id, qid))
        if q is not None:
            rows[qid] = q


async def _realm_reached(db: AsyncSession, user_id: int, realm: str) -> bool:
    from .cultivation import order
    ch = await db.get(Character, user_id)
    return ch is not None and order().index(ch.realm) >= order().index(realm)


async def _open(db: AsyncSession, user_id: int, quest_id: str) -> Quest:
    q = Quest(user_id=user_id, quest_id=quest_id, state=ACTIVE, progress={"n": 0})
    db.add(q)
    await db.flush()
    _, st = _step(quest_id)
    obj = st["objective"]
    if obj["type"] == "realm" and await _realm_reached(db, user_id, obj["target"]):
        q.progress, q.state = {"n": obj["count"]}, DONE
    elif obj["type"] in ("bee_species", "guard", "fish_species"):  # what was done before the step opened counts
        from ..models import Bee, FishCatch
        from . import bees
        if obj["type"] == "bee_species":
            have = await bees.species_found(db, user_id)
        elif obj["type"] == "fish_species":
            have = len((await db.execute(select(FishCatch.fish_id).where(FishCatch.user_id == user_id))).all())
        else:
            have = len((await db.execute(select(Bee.id).where(Bee.user_id == user_id, Bee.role == "guard"))).all())
        if have:
            q.progress = {"n": min(have, obj["count"])}
            if have >= obj["count"]:
                q.state = DONE
    return q


async def ensure(db: AsyncSession, user_id: int) -> list[Quest]:
    rows = {q.quest_id: q for q in (await db.execute(select(Quest).where(Quest.user_id == user_id))).scalars().all()}
    for cid, chain in catalog.quests()["chains"].items():
        first = chain["steps"][0]["id"]
        if first not in rows:
            rows[first] = await _open(db, user_id, first)
    await _ensure_daily(db, user_id, rows)
    return list(rows.values())


def view(q: Quest) -> dict:
    cid, st = _step(q.quest_id)
    obj = st["objective"]
    rw = st["rewards"]
    reward_list = []
    if rw.get("spirit_stones"):
        reward_list.append(f"{rw['spirit_stones']} Linh Thạch")
    if rw.get("immortal_jade"):
        reward_list.append(f"{rw['immortal_jade']} Tiên Ngọc")
    if rw.get("xp"):
        reward_list.append(f"{rw['xp']} Tu Vi")
    for it in rw.get("items", []):
        reward_list.append(f"{catalog.item_name(it['item'])} ×{it['qty']}")
    for e in rw.get("equipment", []):
        reward_list.append(catalog.item_name(e["item"]))
    target_vi = ""
    if obj["type"] == "kill" and obj["target"] != "*":
        target_vi = catalog.monsters().get(obj["target"], {}).get("name_vi", obj["target"])
    chain_vi = _daily()["title_vi"] if cid == "daily" else catalog.quests()["chains"][cid]["title_vi"]
    return {"id": q.quest_id, "chain": cid, "chain_vi": chain_vi,
            "title_vi": st["title_vi"], "desc_vi": st["desc_vi"], "state": q.state,
            "objective": {**obj, "target_vi": target_vi}, "progress": int((q.progress or {}).get("n", 0)),
            "rewards_vi": reward_list}


async def list_quests(db: AsyncSession, user: User) -> dict:
    qs = await ensure(db, user.id)
    order = {s["id"]: i for i, (_, s) in enumerate(_steps())}
    chains = [q for q in qs if not _is_daily(q.quest_id) and _step(q.quest_id)]
    chains.sort(key=lambda q: order.get(q.quest_id, 999))
    today = daily_ids(user.id, _today())
    daily = sorted((q for q in qs if q.quest_id in today), key=lambda q: today.index(q.quest_id))
    bonus = _daily()["all_done_bonus"]
    return {"quests": [view(q) for q in chains if q.state != CLAIMED],
            "claimed": [q.quest_id for q in chains if q.state == CLAIMED],
            "daily": [view(q) for q in daily],
            "daily_bonus": {"rewards_vi": _rewards_vi(bonus),
                            "claimed": (user.flags or {}).get("daily_bonus") == _today()}}


def _rewards_vi(rw: dict) -> list[str]:
    out = []
    if rw.get("spirit_stones"):
        out.append(f"{rw['spirit_stones']} Linh Thạch")
    if rw.get("immortal_jade"):
        out.append(f"{rw['immortal_jade']} Tiên Ngọc")
    return out


async def on_event(db: AsyncSession, user_id: int, kind: str, target: str, n: int = 1) -> list[dict]:
    """Advance every active step whose objective matches; returns the steps finished now."""
    await ensure(db, user_id)   # a chain added in a later version starts counting at once
    rows = (await db.execute(select(Quest).where(Quest.user_id == user_id, Quest.state == ACTIVE))).scalars().all()
    finished = []
    for q in rows:
        found = _step(q.quest_id)
        if not found:
            continue
        obj = found[1]["objective"]
        want = obj.get("target") or ""
        if obj["type"] != kind or (want != "*" and want != (target or "")):
            continue
        cur = int((q.progress or {}).get("n", 0)) + n
        q.progress = {"n": min(cur, obj["count"])}
        if cur >= obj["count"]:
            q.state = DONE
            finished.append(view(q))
    if finished:
        from ..realtime.world import world
        for f in finished:
            world.notify(user_id, {"t": "quest", "event": "done", "quest": f})
    return finished


async def talk(db: AsyncSession, user: User, npc: str) -> dict:
    """Talking to an NPC (the client calls this when the player presses E on them)."""
    from ..realtime.world import world
    await ensure(db, user.id)
    if not world.near_npc(user.id, npc):
        raise QuestError(400, "too_far", "Hãy lại gần người đó để nói chuyện.")
    done = await on_event(db, user.id, "talk", npc)
    return {"finished": done}


async def claim(db: AsyncSession, user: User, quest_id: str) -> dict:
    q = await db.get(Quest, (user.id, quest_id))
    found = _step(quest_id)
    if q is None or found is None:
        raise QuestError(404, "no_quest", "Không có nhiệm vụ này.")
    if q.state != DONE:
        raise QuestError(400, "not_done", "Nhiệm vụ chưa hoàn thành." if q.state == ACTIVE else "Đã nhận thưởng rồi.")
    cid, st = found
    rw = st["rewards"]
    got: dict = {"items": [], "equipment": []}
    for cur in ("spirit_stones", "immortal_jade"):
        if rw.get(cur):
            got[cur] = await inventory.change_currency(db, user.id, cur, rw[cur], "quest", quest_id)
    got["items"] = await items.grant_items(db, user.id, rw.get("items", []), "quest", quest_id)
    for e in rw.get("equipment", []):
        got["equipment"].append(await items.grant_equipment(db, user.id, e["item"], e.get("rarity", "pham"),
                                                            "quest", quest_id))
    q.state = CLAIMED
    if rw.get("xp"):
        from . import cultivation
        got["xp"] = await cultivation.add_xp(db, user.id, rw["xp"], "quest")
    if cid == "daily":
        got["bonus"] = await _daily_bonus(db, user)
        return {"claimed": quest_id, "rewards": got, "next": None}
    steps = catalog.quests()["chains"][cid]["steps"]
    idx = next(i for i, s in enumerate(steps) if s["id"] == quest_id)
    nxt = None
    if idx + 1 < len(steps) and await db.get(Quest, (user.id, steps[idx + 1]["id"])) is None:
        nxt = view(await _open(db, user.id, steps[idx + 1]["id"]))
    return {"claimed": quest_id, "rewards": got, "next": nxt}


async def _daily_bonus(db: AsyncSession, user: User) -> dict | None:
    """Every task of today claimed: the bonus, once a day."""
    today = _today()
    if (user.flags or {}).get("daily_bonus") == today:
        return None
    for qid in daily_ids(user.id, today):
        q = await db.get(Quest, (user.id, qid))
        if q is None or q.state != CLAIMED:
            return None
    bonus = _daily()["all_done_bonus"]
    out = {}
    for cur in ("spirit_stones", "immortal_jade"):
        if bonus.get(cur):
            out[cur] = await inventory.change_currency(db, user.id, cur, bonus[cur], "daily_bonus", today)
    flags = dict(user.flags or {})
    flags["daily_bonus"] = today
    user.flags = flags
    return {"rewards_vi": _rewards_vi(bonus), **out}
