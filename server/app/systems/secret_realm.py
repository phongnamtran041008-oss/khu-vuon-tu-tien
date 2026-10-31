"""Bí cảnh, the database side (spec 14): daily entries, runs, loot and the forge for Mảnh Bảo Vật.

The live run (rooms, puzzles, the boss) is app/realtime/realm.py and never touches the
database in its tick; it calls the coroutines here as background tasks. Loot is written
together with a RealmClaim row whose primary key is (run, player, stage), so a room or the
final chest can pay each player once and only once, however often it is asked (spec 14.3).
"""
from __future__ import annotations

import json
import random
from functools import lru_cache

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from .. import db as dbm
from ..config import DATA_DIR
from ..learning import quiz
from ..models import Character, Collection, RealmClaim, RealmMember, RealmRun, User
from . import catalog, cultivation, inventory, items


class RealmError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("realm")


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads((DATA_DIR / "realms.json").read_text("utf-8"))


def realms() -> dict:
    return data()["realms"]


def puzzle_info(kind: str) -> dict:
    return data()["puzzles"].get(kind, {})


# ------------------------------------------------------------------ entries
async def entries_used(db: AsyncSession, user_id: int, day: str | None = None) -> dict[str, int]:
    day = day or clock.local_date(clock.now())
    rows = (await db.execute(select(RealmMember.realm_id, func.count()).where(
        RealmMember.user_id == user_id, RealmMember.day == day).group_by(RealmMember.realm_id))).all()
    return {r: int(n) for r, n in rows}


async def over_limit(db: AsyncSession, user_ids: list[int], realm_id: str) -> list[int]:
    """Spec 14.1: each player may enter each realm at most N times a day."""
    day = clock.local_date(clock.now())
    limit = cfg()["daily_entries"]
    out = []
    for uid in user_ids:
        if (await entries_used(db, uid, day)).get(realm_id, 0) >= limit:
            out.append(uid)
    return out


async def create_run(db: AsyncSession, realm_id: str, user_ids: list[int]) -> int:
    now = clock.now()
    run = RealmRun(realm_id=realm_id, started_at=now, members=list(user_ids))
    db.add(run)
    await db.flush()
    day = clock.local_date(now)
    for uid in user_ids:
        db.add(RealmMember(run_id=run.id, user_id=uid, realm_id=realm_id, day=day, joined_at=now))
    await db.flush()
    return run.id


async def learned_words(db: AsyncSession, user_ids: list[int]) -> dict[int, dict[str, int]]:
    """Which words each member has been introduced to (puzzles only use those, spec 14.2)."""
    out: dict[int, dict[str, int]] = {uid: {} for uid in user_ids}
    rows = (await db.execute(select(Collection.user_id, Collection.word_id, Collection.mastery).where(
        Collection.user_id.in_(user_ids), Collection.introduced.is_(True)))).all()
    for uid, wid, mastery in rows:
        out[uid][wid] = int(mastery or 0)
    return out


async def abort_run(run_id: int) -> None:
    """The party fell apart before stepping in: the entry is given back."""
    async with dbm.SessionLocal() as db:
        run = await db.get(RealmRun, run_id)
        if run is not None:
            await db.delete(run)
        await db.commit()


async def member_left(run_id: int, user_id: int, result: str = "left") -> None:
    async with dbm.SessionLocal() as db:
        await db.execute(update(RealmMember).where(
            RealmMember.run_id == run_id, RealmMember.user_id == user_id, RealmMember.left_at.is_(None))
            .values(left_at=clock.now(), result=result))
        await db.commit()


async def finish_run(run_id: int, result: str, user_ids: list[int]) -> None:
    async with dbm.SessionLocal() as db:
        run = await db.get(RealmRun, run_id)
        if run is not None:
            run.ended_at, run.result = clock.now(), result
        if user_ids:
            await db.execute(update(RealmMember).where(
                RealmMember.run_id == run_id, RealmMember.user_id.in_(user_ids), RealmMember.left_at.is_(None))
                .values(left_at=clock.now(), result=result))
        await db.commit()


# ------------------------------------------------------------------ loot
async def _claim(user_id: int, run_id: int, stage: str, roll) -> dict | None:
    """Writes the claim and what `roll(db, rng)` grants in one transaction. Returns None when
    this stage was already paid to this player."""
    rng = random.Random()
    async with dbm.SessionLocal() as db:
        claim = RealmClaim(run_id=run_id, user_id=user_id, stage=stage, loot={}, created_at=clock.now())
        db.add(claim)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            return None
        loot = await roll(db, rng)
        claim.loot = {k: v for k, v in loot.items() if k != "xp"}
        try:
            await db.commit()
        except IntegrityError:   # a twin request won the race
            await db.rollback()
            return None
    return loot


async def _grant_table(db: AsyncSession, uid: int, rng: random.Random, entries: list[dict], ref: str,
                       out: dict) -> None:
    total = sum(e["weight"] for e in entries)
    x = rng.uniform(0, total)
    for e in entries:
        x -= e["weight"]
        if x <= 0:
            break
    if "item" in e:
        qty = rng.randint(*e.get("qty", [1, 1]))
        out["items"] += await items.grant_items(db, uid, [{"item": e["item"], "qty": qty}], "realm", ref)
    else:
        rar = items.roll_rarity(rng, e.get("min_rarity"))
        out["equipment"].append(await items.grant_equipment(db, uid, rng.choice(e["equipment"]), rar, "realm", ref))


async def claim_room(run_id: int, user_id: int, room_index: int, room_kind: str) -> dict | None:
    c = cfg()["room_loot"]
    ref = f"run{run_id}:room{room_index}"

    async def roll(db, rng):
        out = {"stage": f"room{room_index}", "room": room_kind, "items": [], "equipment": []}
        stones = rng.randint(*c["stones"])
        out["spirit_stones"] = await inventory.change_currency(db, user_id, "spirit_stones", stones, "realm", ref)
        out["stones"] = stones
        for d in c["items"]:
            if rng.random() < d["chance"]:
                out["items"] += await items.grant_items(
                    db, user_id, [{"item": d["item"], "qty": rng.randint(*d.get("qty", [1, 1]))}], "realm", ref)
        out["xp"] = await cultivation.add_xp(db, user_id, c["xp"], "realm")
        return out
    return await _claim(user_id, run_id, f"room{room_index}", roll)


async def claim_chest(run_id: int, user_id: int, realm_id: str, fragments: int, fast: bool) -> dict | None:
    """The final chest (spec 14.3): every player rolls on their own; the Mảnh Bảo Vật count is
    the same for the whole team. Finishing fast adds stones and a roll."""
    c = cfg()
    chest = c["chest"][realm_id]
    ref = f"run{run_id}:chest"

    async def roll(db, rng):
        out = {"stage": "chest", "items": [], "equipment": [], "fast": fast}
        stones = rng.randint(*chest["stones"])
        if fast:
            stones = int(round(stones * c["fast_bonus"]["stones_mult"]))
        out["spirit_stones"] = await inventory.change_currency(db, user_id, "spirit_stones", stones, "realm", ref)
        out["stones"] = stones
        jade = rng.randint(*chest["jade"])
        if jade:
            out["immortal_jade"] = await inventory.change_currency(db, user_id, "immortal_jade", jade, "realm", ref)
            out["jade"] = jade
        if fragments:
            out["items"] += await items.grant_items(db, user_id, [{"item": "manh_bao_vat", "qty": fragments}],
                                                    "realm", ref)
        for _ in range(chest["rolls"] + (c["fast_bonus"]["extra_rolls"] if fast else 0)):
            await _grant_table(db, user_id, rng, chest["table"], ref, out)
        out["xp"] = await cultivation.add_xp(db, user_id, chest["xp"], "realm")
        from . import quests
        out["quests"] = await quests.on_event(db, user_id, "realm", realm_id)
        return out
    return await _claim(user_id, run_id, "chest", roll)


async def claims(db: AsyncSession, run_id: int, user_id: int) -> list[dict]:
    rows = (await db.execute(select(RealmClaim).where(RealmClaim.run_id == run_id, RealmClaim.user_id == user_id)
                             .order_by(RealmClaim.created_at))).scalars().all()
    return [{"stage": r.stage, **(r.loot or {})} for r in rows]


# ------------------------------------------------------------------ learning
async def record_answer(user_id: int, word_id: str, correct: bool) -> int | None:
    """A puzzle move about a word counts like a combat answer (spec 8.3): mastery ±2, the
    garden stage never changes. Only for words the player owns."""
    q = balance.quiz()
    async with dbm.SessionLocal() as db:
        col = await quiz.get_collection(db, user_id, word_id)
        if col is None:
            return None
        col.times_correct += int(correct)
        col.times_wrong += int(not correct)
        col.last_answered_at = clock.now()
        quiz.bump_mastery(col, q["non_garden_mastery_correct"] if correct else q["non_garden_mastery_wrong"])
        if not correct:
            col.needs_review = True
        mastery = col.mastery
        await db.commit()
    from ..realtime.world import world
    world.word_mastery_changed(user_id, word_id, mastery)
    return mastery


# ------------------------------------------------------------------ the gate
async def view(db: AsyncSession, user: User) -> dict:
    from ..realtime.realm import window_status
    from ..realtime.world import world
    ch = await db.get(Character, user.id)
    used = await entries_used(db, user.id)
    order = cultivation.order()
    limit = cfg()["daily_entries"]
    out = []
    for rid, r in realms().items():
        st = window_status(clock.now()) if r["kind"] == "scheduled" else {"open": None}
        out.append({"id": rid, "name_vi": r["name_vi"], "hanzi": r.get("hanzi", ""), "kind": r["kind"],
                    "min_realm": r["min_realm"], "min_realm_vi": cultivation.realm_name(r["min_realm"]),
                    "realm_ok": ch is not None and order.index(ch.realm) >= order.index(r["min_realm"]),
                    "tier": r["tier"], "puzzles": r["puzzles"], "time_limit_minutes": r["time_limit_minutes"],
                    "desc_vi": r.get("desc_vi", ""), "entries_left": max(0, limit - used.get(rid, 0)),
                    "daily": limit, **st})
    fc = cfg()["forge"]
    eq = catalog.equipment()
    s = eq["sets"]["mac_anh"]
    have = (await items.stacks(db, user.id)).get("manh_bao_vat", 0)
    return {"realms": out, "party": world.parties.view_for(user.id), "queue": world.realms.queue_of(user.id),
            "puzzles": data()["puzzles"],
            "forge": {"fragments": fc["fragments"], "stones": fc["stones"], "have": have,
                      "rarity": fc["rarity"], "rarity_vi": eq["rarities"][fc["rarity"]]["name_vi"],
                      "set_vi": s["name_vi"], "bonus_vi": s["bonus_vi"],
                      "pieces": [{"id": pid, "name_vi": eq["items"][pid]["name_vi"],
                                  "slot_vi": eq["slots"][eq["items"][pid]["slot"]]} for pid in s["pieces"]]}}


async def forge(db: AsyncSession, user: User, piece: str) -> dict:
    """Mảnh Bảo Vật -> one piece of the Mặc Ảnh set at Thiên rarity (spec 14.3)."""
    fc = cfg()["forge"]
    if piece not in catalog.equipment()["sets"]["mac_anh"]["pieces"]:
        raise RealmError(400, "bad_piece", "Không có món đồ này trong bộ.")
    try:
        await inventory.consume_item(db, user.id, "manh_bao_vat", fc["fragments"], "realm_forge", piece)
        await inventory.charge(db, user.id, {"spirit_stones": fc["stones"]}, "realm_forge", piece)
    except inventory.InsufficientFunds:
        raise RealmError(400, "not_enough", f"Cần {fc['fragments']} Mảnh Bảo Vật và {fc['stones']} Linh Thạch.")
    gear = await items.grant_equipment(db, user.id, piece, fc["rarity"], "realm_forge")
    stones = (await db.execute(select(User.spirit_stones).where(User.id == user.id))).scalar_one()
    return {"equipment": gear, "spirit_stones": stones}
