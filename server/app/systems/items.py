"""Inventory, equipment, enhancing, pills and skill manuals (spec 8.4, 12). Every change of
an item goes through inventory.change_item (audited, never negative); new equipment
pieces are audited too."""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning.wordbank import bank
from ..models import AuditLog, Character, Collection, EquipmentInstance, InventoryItem, Skill, User
from . import catalog, cultivation, inventory


class ItemError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


RARITY_ORDER = ["pham", "linh", "huyen", "dia", "thien"]


def roll_rarity(rng: random.Random, min_rarity: str | None = None) -> str:
    rar = catalog.equipment()["rarities"]
    lo = RARITY_ORDER.index(min_rarity) if min_rarity else 0
    choices = [(r, rar[r]["weight"]) for r in RARITY_ORDER[lo:] if rar[r]["weight"] > 0]
    total = sum(w for _, w in choices)
    x = rng.uniform(0, total)
    for r, w in choices:
        x -= w
        if x <= 0:
            return r
    return choices[-1][0]


def equipment_view(e: EquipmentInstance) -> dict:
    eq = catalog.equipment()
    item = eq["items"].get(e.item_id, {})
    rar = eq["rarities"][e.rarity]
    lvl = e.enhance_level
    nxt = None
    enh = eq["enhance"]
    if lvl < enh["max_level"]:
        nxt = {"success_pct": enh["success_pct"][lvl], "stones": enh["cost_stones"][lvl],
               "material": enh["material"], "material_name": catalog.item_name(enh["material"]),
               "material_qty": enh["material_qty"][lvl]}
    return {"id": e.id, "item_id": e.item_id, "name_vi": item.get("name_vi", e.item_id), "slot": item.get("slot"),
            "slot_vi": eq["slots"].get(item.get("slot"), ""), "kind": item.get("kind"),
            "rarity": e.rarity, "rarity_vi": rar["name_vi"], "color": rar["color"], "enhance": lvl,
            "stats": cultivation.instance_stats(e), "equipped": e.equipped_slot, "desc_vi": item.get("desc_vi", ""),
            "next_enhance": nxt, "inscriptions": list(e.inscriptions or []),
            "inscribe_slots": int(balance.load("inscription")["slots"].get(e.rarity, 1)),
            "sell_price": sell_price(e)}


def sell_price(e: EquipmentInstance) -> int:
    """What Bà Chủ Sạp pays for a piece (stage 8), always far below what any piece costs."""
    c = balance.load("shop")["equipment_sell"]
    return int(c["by_rarity"][e.rarity] * (1 + c["per_enhance"] * e.enhance_level))


async def grant_items(db: AsyncSession, user_id: int, items: list[dict], reason: str, ref: str | None = None) -> list:
    out = []
    for it in items:
        qty = int(it.get("qty", 1))
        if qty > 0 and catalog.stack_item(it["item"]):
            total = await inventory.change_item(db, user_id, it["item"], qty, reason, ref)
            out.append({"item": it["item"], "name_vi": catalog.item_name(it["item"]), "qty": qty, "total": total})
    return out


async def grant_equipment(db: AsyncSession, user_id: int, item_id: str, rarity: str, reason: str,
                          ref: str | None = None) -> dict:
    if item_id not in catalog.equipment()["items"]:
        raise ValueError(item_id)
    e = EquipmentInstance(user_id=user_id, item_id=item_id, rarity=rarity, enhance_level=0, inscriptions=[])
    db.add(e)
    await db.flush()
    db.add(AuditLog(user_id=user_id, currency_or_item=f"equip:{item_id}:{rarity}", delta=1, balance_after=None,
                    reason=reason, ref_id=ref or str(e.id), created_at=clock.now()))
    return equipment_view(e)


async def stacks(db: AsyncSession, user_id: int) -> dict[str, int]:
    rows = (await db.execute(select(InventoryItem).where(InventoryItem.user_id == user_id,
                                                         InventoryItem.quantity > 0))).scalars().all()
    out: dict[str, int] = {}
    for r in rows:
        out[r.item_id] = out.get(r.item_id, 0) + r.quantity
    return out


# ------------------------------------------------------------------ skills
async def skill_list(db: AsyncSession, user_id: int) -> list[dict]:
    """Learned Pháp Chữ with their level from the word's current mastery (spec 8.4)."""
    sk = catalog.skills()
    rows = {r.skill_id: r for r in (await db.execute(select(Skill).where(Skill.user_id == user_id))).scalars().all()}
    out = []
    b = bank()
    for sid, s in sk["skills"].items():
        w = b.by_hanzi.get(s["hanzi"])
        col = (await db.execute(select(Collection).where(Collection.user_id == user_id,
                                                         Collection.word_id == w.id))).scalar_one_or_none() if w else None
        mastery = col.mastery if col else 0
        level = sum(1 for m in sk["level_mastery"] if mastery >= m)
        row = rows.get(sid)
        if row is not None and row.level != max(1, level):
            row.level = max(1, level)
        out.append({"id": sid, "name_vi": s["name_vi"], "hanzi": s["hanzi"], "word_id": w.id if w else None,
                    "learned": row is not None, "mastery": mastery, "level": level if row else 0,
                    "qi": s["qi"], "cooldown": s["cooldown"], "effect": s["effect"], "desc_vi": s["desc_vi"]})
    return out


# ------------------------------------------------------------------ inventory view
async def inventory_view(db: AsyncSession, user: User) -> dict:
    st = await stacks(db, user.id)
    items = []
    for iid, qty in sorted(st.items()):
        info = catalog.stack_item(iid) or {}
        items.append({"item_id": iid, "qty": qty, "name_vi": info.get("name_vi", iid), "kind": info.get("kind"),
                      "desc_vi": info.get("desc_vi", ""), "usable": info.get("kind") in ("manual", "pill")
                      and info.get("effect") not in ("breakthrough", "bee_food"), "sell_price": info.get("sell_price"),
                      "hanzi": info.get("hanzi")})
    eq = (await db.execute(select(EquipmentInstance).where(EquipmentInstance.user_id == user.id)
                           .order_by(EquipmentInstance.id))).scalars().all()
    return {"items": items, "equipment": [equipment_view(e) for e in eq],
            "spirit_stones": user.spirit_stones, "immortal_jade": user.immortal_jade}


# ------------------------------------------------------------------ actions
async def _instance(db: AsyncSession, user: User, instance_id: int) -> EquipmentInstance:
    e = await db.get(EquipmentInstance, instance_id)
    if e is None or e.user_id != user.id:
        raise ItemError(404, "no_item", "Không tìm thấy trang bị này.")
    return e


async def _after_gear_change(db: AsyncSession, user_id: int) -> dict:
    ch = await db.get(Character, user_id)
    stats = await cultivation.current_stats(db, ch)
    ch.max_hp = stats["max_hp"]
    ch.hp = min(ch.hp, stats["max_hp"])
    await cultivation.push_to_world(db, ch)
    return stats


async def equip(db: AsyncSession, user: User, instance_id: int) -> dict:
    e = await _instance(db, user, instance_id)
    slot = catalog.equipment()["items"][e.item_id]["slot"]
    old = (await db.execute(select(EquipmentInstance).where(
        EquipmentInstance.user_id == user.id, EquipmentInstance.equipped_slot == slot))).scalars().all()
    for o in old:
        o.equipped_slot = None
    e.equipped_slot = slot
    await db.flush()
    return {"equipped": equipment_view(e), "stats": await _after_gear_change(db, user.id)}


async def unequip(db: AsyncSession, user: User, slot: str) -> dict:
    rows = (await db.execute(select(EquipmentInstance).where(
        EquipmentInstance.user_id == user.id, EquipmentInstance.equipped_slot == slot))).scalars().all()
    for o in rows:
        o.equipped_slot = None
    await db.flush()
    return {"stats": await _after_gear_change(db, user.id)}


async def enhance(db: AsyncSession, user: User, instance_id: int, rng: random.Random | None = None) -> dict:
    """+1..+10; the chance falls with each level; failing loses only the materials (spec 12.2)."""
    rng = rng or random.Random()
    e = await _instance(db, user, instance_id)
    enh = catalog.equipment()["enhance"]
    lvl = e.enhance_level
    if lvl >= enh["max_level"]:
        raise ItemError(400, "max_level", "Trang bị đã cường hóa tối đa.")
    try:
        await inventory.consume_item(db, user.id, enh["material"], enh["material_qty"][lvl], "enhance", str(e.id))
    except inventory.InsufficientFunds:
        raise ItemError(400, "no_material",
                        f"Cần {enh['material_qty'][lvl]} {catalog.item_name(enh['material'])}.")
    try:
        stones = await inventory.change_currency(db, user.id, "spirit_stones", -enh["cost_stones"][lvl], "enhance",
                                                 str(e.id))
    except inventory.InsufficientFunds as err:
        raise ItemError(400, "insufficient_funds", err.message_vi)
    ok = rng.random() * 100 < enh["success_pct"][lvl]
    if ok:
        e.enhance_level += 1
    await db.flush()
    stats = await _after_gear_change(db, user.id) if (ok and e.equipped_slot) else None
    return {"success": ok, "item": equipment_view(e), "spirit_stones": stones, "stats": stats}


async def use(db: AsyncSession, user: User, item_id: str) -> dict:
    info = catalog.stack_item(item_id)
    if info is None:
        raise ItemError(404, "no_item", "Không có vật phẩm này.")
    if info.get("kind") == "manual":
        return await _learn(db, user, item_id, info)
    if info.get("kind") == "pill" and info.get("effect") in ("heal", "qi"):
        from ..realtime.world import world
        if not world.in_world(user.id):
            raise ItemError(400, "not_in_world", "Ở động phủ thân thể tự hồi phục, chỉ cần dùng đan khi ra ngoài.")
        if not world.can_use_pill(user.id):
            raise ItemError(400, "pill_cooldown", "Đan dược đang hồi, chờ một chút.")
        try:
            left = await inventory.consume_item(db, user.id, item_id, 1, "use", None)
        except inventory.InsufficientFunds:
            raise ItemError(400, "no_item", "Hết đan này rồi.")
        world.apply_pill(user.id, info["effect"], info["pct"])
        return {"used": item_id, "left": left}
    if info.get("kind") == "pill" and info.get("effect") == "buff":
        return await _take_buff(db, user, item_id, info)
    if info.get("kind") == "pill" and info.get("effect") == "bee_food":
        raise ItemError(400, "bee_food", "Đan này để cho ong ăn: mở Linh Phong Sào, chọn ong rồi cho ăn.")
    raise ItemError(400, "not_usable", "Vật phẩm này không dùng trực tiếp được.")


async def _take_buff(db: AsyncSession, user: User, item_id: str, info: dict) -> dict:
    """Tụ Linh / Kháng Mực / Ngộ Tính Đan (stage 8). Out in the world they share the 15 s
    pill cooldown of a fight; at home they can be taken any time."""
    from ..realtime.world import world
    from . import buffs
    if world.in_world(user.id) and not world.can_use_pill(user.id):
        raise ItemError(400, "pill_cooldown", "Đan dược đang hồi, chờ một chút.")
    try:
        left = await inventory.consume_item(db, user.id, item_id, 1, "use", None)
    except inventory.InsufficientFunds:
        raise ItemError(400, "no_item", "Hết đan này rồi.")
    now = clock.now()
    seconds = buffs.add(user, info["buff"], now)
    if world.in_world(user.id):
        world.pill_taken(user.id)
    world.set_buffs(user.id, buffs.active(user, now))
    return {"used": item_id, "left": left, "buff": info["buff"], "seconds": seconds, "buffs": buffs.view(user, now)}


async def _learn(db: AsyncSession, user: User, item_id: str, info: dict) -> dict:
    sk = catalog.skills()
    sid = info["skill"]
    s = sk["skills"][sid]
    if await db.get(Skill, (user.id, sid)) is not None:
        raise ItemError(400, "already_learned", f"Bạn đã biết {s['name_vi']} rồi.")
    w = bank().by_hanzi[s["hanzi"]]
    col = (await db.execute(select(Collection).where(Collection.user_id == user.id,
                                                     Collection.word_id == w.id))).scalar_one_or_none()
    mastery = col.mastery if col else 0
    if mastery < sk["unlock_mastery"]:
        raise ItemError(400, "mastery_low",
                        f"Cần thông thạo chữ {s['hanzi']} từ {sk['unlock_mastery']}% (hiện {mastery}%). "
                        "Trồng và ôn chữ này trong vườn nhé.")
    await inventory.consume_item(db, user.id, item_id, 1, "learn_skill", sid)
    db.add(Skill(user_id=user.id, skill_id=sid, level=1, unlocked_at=clock.now()))
    await db.flush()
    from ..realtime.world import world
    world.set_skills(user.id, await skill_list(db, user.id))
    return {"learned": sid, "name_vi": s["name_vi"]}


async def sell(db: AsyncSession, user: User, item_id: str, qty: int) -> dict:
    """The village buys materials and foods that have a sell_price (Linh Mật, Sáp Ong...)."""
    info = catalog.stack_item(item_id)
    if info is None or not info.get("sell_price"):
        raise ItemError(400, "not_sellable", "Làng không thu mua thứ này.")
    if qty <= 0 or qty > 9999:
        raise ItemError(400, "bad_count", "Số lượng không hợp lệ.")
    try:
        left = await inventory.consume_item(db, user.id, item_id, qty, "sell_item")
    except inventory.InsufficientFunds as e:
        raise ItemError(400, "not_enough", f"Chỉ có {e.have} {info['name_vi']}.")
    earned = info["sell_price"] * qty
    stones = await inventory.change_currency(db, user.id, "spirit_stones", earned, "sell_item", item_id)
    return {"sold": qty, "item_id": item_id, "earned": earned, "left": left, "spirit_stones": stones}
