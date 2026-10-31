"""Linh Thú (spec 13, 6.8): 12 zodiac pets from the Linh Thú banner of Thiên Cơ Các. One pet
is worn at a time; it follows its owner (in the abode and out in the world, where others
see it too), gives a small combat bonus and one passive skill. Skills only change rewards
and timings around a question, never the question itself.

The skills are read where they act (garden, gacha, fishing, hive, combat, Thủ Vườn) through
`skill_value(db, user_id, type)`."""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..models import CodexEntry, Pet, User
from . import catalog, inventory

RARITY_VI = {"common": "Thường", "rare": "Hiếm", "epic": "Quý", "legendary": "Huyền thoại"}


class PetError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return catalog.pets()


def species() -> dict[str, dict]:
    return cfg()["species"]


def stats_of(pet_type: str, level: int) -> dict:
    sp = species().get(pet_type)
    if sp is None:
        return {}
    mult = 1 + cfg()["stat_per_level"] * (max(1, level) - 1)
    return {k: int(round(v * mult)) for k, v in sp["stats"].items()}


async def worn(db: AsyncSession, user_id: int) -> Pet | None:
    return (await db.execute(select(Pet).where(Pet.user_id == user_id, Pet.equipped.is_(True)))).scalars().first()


async def worn_stats(db: AsyncSession, user_id: int) -> dict:
    p = await worn(db, user_id)
    return stats_of(p.pet_type, p.level) if p else {}


async def skill(db: AsyncSession, user_id: int) -> dict | None:
    p = await worn(db, user_id)
    if p is None or p.pet_type not in species():
        return None
    return species()[p.pet_type]["skill"]


async def skill_value(db: AsyncSession, user_id: int, kind: str) -> float:
    """The worn pet's skill value if it is of this kind, else 0."""
    sk = await skill(db, user_id)
    if not sk or sk.get("type") != kind:
        return 0.0
    return float(sk.get("value", sk.get("every", 0)))


def view(p: Pet) -> dict:
    sp = species()[p.pet_type]
    return {"id": p.id, "pet_type": p.pet_type, "name_vi": sp["name_vi"], "zodiac_vi": sp["zodiac_vi"],
            "hanzi": sp["hanzi"], "pinyin": sp["pinyin"], "rarity": sp["rarity"],
            "rarity_vi": RARITY_VI.get(sp["rarity"], sp["rarity"]), "level": p.level, "max_level": cfg()["max_level"],
            "equipped": bool(p.equipped), "skill_vi": sp["skill_vi"], "stats": stats_of(p.pet_type, p.level),
            "look": sp["look"]}


async def owned(db: AsyncSession, user_id: int) -> list[Pet]:
    return list((await db.execute(select(Pet).where(Pet.user_id == user_id).order_by(Pet.id))).scalars().all())


async def overview(db: AsyncSession, user: User) -> dict:
    """The pets owned, and the Linh Thú Phổ: every species, the ones never met as a shadow."""
    mine = await owned(db, user.id)
    have = {p.pet_type for p in mine}
    book = []
    for pid, sp in species().items():
        if pid in have:
            book.append({"id": pid, "found": True, "name_vi": sp["name_vi"], "zodiac_vi": sp["zodiac_vi"],
                         "hanzi": sp["hanzi"], "pinyin": sp["pinyin"], "rarity": sp["rarity"],
                         "skill_vi": sp["skill_vi"], "look": sp["look"]})
        else:
            book.append({"id": pid, "found": False, "zodiac_vi": sp["zodiac_vi"], "rarity": sp["rarity"],
                         "look": {"plan": sp["look"]["plan"]}})
    w = next((p for p in mine if p.equipped), None)
    return {"pets": [view(p) for p in mine], "equipped": w.id if w else None, "book": book,
            "found": len(have), "total": len(species()),
            # every species' look, to draw the pets other players walk with
            "looks": {pid: sp["look"] for pid, sp in species().items()}}


async def _after_change(db: AsyncSession, user_id: int) -> None:
    from ..models import Character
    from . import cultivation
    from ..realtime.world import world
    ch = await db.get(Character, user_id)
    if ch is not None:
        st = await cultivation.current_stats(db, ch)
        ch.max_hp = st["max_hp"]
        ch.hp = min(ch.hp, st["max_hp"])
        await cultivation.push_to_world(db, ch)
    p = await worn(db, user_id)
    world.set_pet(user_id, p.pet_type if p else None)


async def equip(db: AsyncSession, user: User, pet_id: int | None) -> dict:
    """Wear one pet (or none with pet_id null). Only one at a time (spec 13)."""
    target = None
    if pet_id is not None:
        target = await db.get(Pet, pet_id)
        if target is None or target.user_id != user.id:
            raise PetError(404, "no_pet", "Không tìm thấy linh thú này.")
    for p in await owned(db, user.id):
        p.equipped = target is not None and p.id == target.id
    await db.flush()
    await _after_change(db, user.id)
    return await overview(db, user)


async def resolve_gacha(db: AsyncSession, user: User, rarities: list[str], rng: random.Random) -> list[dict]:
    """A rolled rarity becomes one pet of that rarity. A new species joins the Linh Thú Phổ;
    a species already owned gains a level, and past the top level turns into Linh Thạch."""
    c = cfg()
    pool: dict[str, list[str]] = {}
    for pid, sp in species().items():
        pool.setdefault(sp["rarity"], []).append(pid)
    out = []
    for r in rarities:
        pid = rng.choice(pool[r])
        sp = species()[pid]
        row = (await db.execute(select(Pet).where(Pet.user_id == user.id, Pet.pet_type == pid))).scalars().first()
        res = {"rarity": r, "pet_type": pid, "name_vi": sp["name_vi"], "hanzi": sp["hanzi"], "pinyin": sp["pinyin"],
               "zodiac_vi": sp["zodiac_vi"], "look": sp["look"]}
        if row is None:
            row = Pet(user_id=user.id, pet_type=pid, level=1, equipped=False)
            db.add(row)
            await db.flush()
            db.add(CodexEntry(user_id=user.id, codex="pet", entry_id=pid, discovered_at=clock.now(), progress={}))
            res.update({"new": True, "level": 1})
        elif row.level < c["max_level"]:
            row.level += 1
            res.update({"new": False, "level": row.level, "level_up": True})
            if row.equipped:
                await db.flush()
                await _after_change(db, user.id)
        else:
            stones = c["dupe_stones"][r]
            await inventory.change_currency(db, user.id, "spirit_stones", stones, "pet_dupe", pid)
            res.update({"new": False, "level": row.level, "stones": stones})
        await db.flush()
        res["pet_id"] = row.id
        out.append(res)
    return out
