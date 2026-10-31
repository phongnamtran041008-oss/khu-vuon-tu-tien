"""Sạp Tạp Hóa (spec 12.4): Bà Chủ Sạp in Trúc Lâm Thôn sells basic goods (pills, herbs,
Mực Tinh, bait, common seeds) with a daily limit per player and Phàm/Linh equipment, and
buys things back. There is no trading between players (v1); friends can give each other
small presents (systems/social.gift).

Buying is only possible standing next to her (the server checks the real position, as for
the Ngư Ông and the Thủ Thư). Selling stack items and quả chữ goes through the existing
/inventory/sell and /fruits/sell, which work anywhere; selling a piece of equipment is here.
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning.wordbank import bank
from ..models import AuditLog, Collection, EquipmentInstance, Seed, User
from . import catalog, gacha_service, inventory, items


class ShopError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("shop")


def at_shop(user_id: int) -> bool:
    from ..realtime.world import world
    return world.near_npc(user_id, "shopkeeper", cfg()["reach"])


def _bought_today(user: User) -> dict[str, int]:
    flags = user.flags or {}
    if flags.get("shop_day") != clock.local_date(clock.now()):
        return {}
    return dict(flags.get("shop_bought") or {})


def _stock_name(item_id: str) -> tuple[str, str]:
    c = cfg()
    if item_id == c["seed_item"]:
        return c["seed_name_vi"], c["seed_desc_vi"]
    info = catalog.stack_item(item_id) or {}
    return info.get("name_vi", item_id), info.get("desc_vi", "")


async def view(db: AsyncSession, user: User) -> dict:
    c = cfg()
    bought = _bought_today(user)
    st = await items.stacks(db, user.id)
    stock = []
    for s in c["stock"]:
        name, desc = _stock_name(s["item"])
        stock.append({"item_id": s["item"], "name_vi": name, "desc_vi": desc, "price": s["price"],
                      "daily": s["daily"], "left": max(0, s["daily"] - bought.get(s["item"], 0)),
                      "have": st.get(s["item"], 0)})
    eq = catalog.equipment()
    gear = []
    for iid in c["equipment"]["items"]:
        it = eq["items"][iid]
        for rar, price in c["equipment"]["price"].items():
            mult = eq["rarities"][rar]["mult"]
            gear.append({"item_id": iid, "rarity": rar, "rarity_vi": eq["rarities"][rar]["name_vi"],
                         "color": eq["rarities"][rar]["color"], "name_vi": it["name_vi"],
                         "slot_vi": eq["slots"][it["slot"]], "price": price, "desc_vi": it.get("desc_vi", ""),
                         "stats": {k: int(round(v * mult)) for k, v in it["stats"].items()}})
    inv = await items.inventory_view(db, user)
    return {"stock": stock, "equipment": gear, "at_shop": at_shop(user.id),
            "sell_items": [i for i in inv["items"] if i.get("sell_price")],
            "sell_equipment": [e for e in inv["equipment"] if not e["equipped"]],
            "spirit_stones": user.spirit_stones}


async def buy(db: AsyncSession, user: User, item_id: str, qty: int, rarity: str | None = None,
              rng: random.Random | None = None) -> dict:
    c = cfg()
    if not at_shop(user.id):
        raise ShopError(400, "too_far", "Muốn mua thì tới Sạp Tạp Hóa gặp Bà Chủ Sạp ở Trúc Lâm Thôn.")
    if rarity is not None:
        return await _buy_gear(db, user, item_id, rarity)
    line = next((s for s in c["stock"] if s["item"] == item_id), None)
    if line is None:
        raise ShopError(400, "not_sold", "Sạp không bán thứ này.")
    if qty <= 0 or qty > 99:
        raise ShopError(400, "bad_count", "Số lượng không hợp lệ.")
    bought = _bought_today(user)
    left = line["daily"] - bought.get(item_id, 0)
    if qty > left:
        raise ShopError(400, "sold_out", f"Hôm nay sạp chỉ còn bán cho con {max(0, left)} cái.")
    price = line["price"] * qty
    try:
        stones = await inventory.change_currency(db, user.id, "spirit_stones", -price, "shop_buy", item_id)
    except inventory.InsufficientFunds as e:
        raise ShopError(400, "insufficient_funds", e.message_vi)
    out: dict = {"bought": item_id, "qty": qty, "price": price, "spirit_stones": stones}
    if item_id == c["seed_item"]:
        out["seeds"] = await _seeds(db, user, qty, rng or random.Random())
    else:
        out["total"] = await inventory.change_item(db, user.id, item_id, qty, "shop_buy")
    flags = dict(user.flags or {})
    flags["shop_day"] = clock.local_date(clock.now())
    flags["shop_bought"] = {**bought, item_id: bought.get(item_id, 0) + qty}
    user.flags = flags
    await db.flush()
    return out


async def _seeds(db: AsyncSession, user: User, qty: int, rng: random.Random) -> list[dict]:
    """Common seeds count toward the 15 new seeds a day of the gacha (spec 6.1)."""
    now = clock.now()
    gacha_service.reset_daily(user, clock.local_date(now))
    limit = balance.gacha()["daily_roll_limit"]
    if user.daily_new_seeds_count + qty > limit:
        raise ShopError(400, "daily_limit", "Hôm nay con đã nhận đủ hạt mới rồi, mai quay lại nhé.")
    tier = await gacha_service.player_tier(db, user.id)
    b = bank()
    pool = b.gacha_pool(tier, "common")
    owned = set((await db.execute(select(Collection.word_id).where(Collection.user_id == user.id))).scalars().all())
    out = []
    for _ in range(qty):
        new = [w for w in pool if w.id not in owned]
        w = rng.choice(new or pool)
        dup = not new
        seed = Seed(user_id=user.id, word_id=w.id, duplicate=dup, source="shop", obtained_at=now)
        db.add(seed)
        if not dup:
            owned.add(w.id)
            db.add(Collection(user_id=user.id, word_id=w.id, first_seen_at=now))
        await db.flush()
        out.append({"seed_id": seed.id, "rarity": "common", "duplicate": dup, "word": {"id": w.id, "hanzi": w.hanzi}})
    user.daily_new_seeds_count += qty
    return out


async def _buy_gear(db: AsyncSession, user: User, item_id: str, rarity: str) -> dict:
    c = cfg()["equipment"]
    if item_id not in c["items"] or rarity not in c["price"]:
        raise ShopError(400, "not_sold", "Sạp chỉ bán đồ Phàm và Linh thường ngày.")
    price = c["price"][rarity]
    try:
        stones = await inventory.change_currency(db, user.id, "spirit_stones", -price, "shop_buy",
                                                 f"{item_id}:{rarity}")
    except inventory.InsufficientFunds as e:
        raise ShopError(400, "insufficient_funds", e.message_vi)
    piece = await items.grant_equipment(db, user.id, item_id, rarity, "shop_buy")
    return {"bought": item_id, "rarity": rarity, "price": price, "equipment": piece, "spirit_stones": stones}


async def sell_equipment(db: AsyncSession, user: User, instance_id: int) -> dict:
    e = await db.get(EquipmentInstance, instance_id)
    if e is None or e.user_id != user.id:
        raise ShopError(404, "no_item", "Không tìm thấy trang bị này.")
    if e.equipped_slot:
        raise ShopError(400, "equipped", "Tháo món đồ ra trước khi bán.")
    if not at_shop(user.id):
        raise ShopError(400, "too_far", "Muốn bán trang bị thì tới Sạp Tạp Hóa gặp Bà Chủ Sạp.")
    price = items.sell_price(e)
    name = catalog.item_name(e.item_id)
    db.add(AuditLog(user_id=user.id, currency_or_item=f"equip:{e.item_id}:{e.rarity}", delta=-1, balance_after=None,
                    reason="shop_sell", ref_id=str(e.id), created_at=clock.now()))
    await db.delete(e)
    stones = await inventory.change_currency(db, user.id, "spirit_stones", price, "shop_sell", str(instance_id))
    return {"sold": instance_id, "name_vi": name, "earned": price, "spirit_stones": stones}
