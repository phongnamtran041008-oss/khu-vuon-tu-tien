"""Server side of a gacha roll: limits, charging, pity persistence and turning rarities
into rewards: seeds (Hạt Chữ), bee eggs (Trứng Ong) and Linh Thú (stage 8)."""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning.wordbank import bank
from ..models import Character, Collection, Seed, User
from . import inventory
from .gacha import Banner, GachaError, expected_rate_with_pity

REALM_TIER = {"pham_nhan": 1, "luyen_khi": 1, "truc_co": 2, "kim_dan": 3, "nguyen_anh": 4}


def reset_daily(user: User, today: str) -> None:
    if user.daily_reset_date != today:
        user.daily_reset_date = today
        user.daily_new_seeds_count = 0
        user.daily_free_rolls_used = 0


async def player_tier(db: AsyncSession, user_id: int) -> int:
    ch = await db.get(Character, user_id)
    return REALM_TIER.get(ch.realm, 1) if ch else 1


def banner_info(user: User | None = None) -> list[dict]:
    cfg = balance.gacha()
    out = []
    for bid, b in cfg["banners"].items():
        banner = Banner.load(bid)
        effective = {p["min_rarity"]: round(expected_rate_with_pity(banner, p["min_rarity"], p["every"]), 4)
                     for p in b["pity"]}
        info = {"id": bid, "name_vi": b["name_vi"], "enabled": b["enabled"], "price": b["price"],
                "price_10": b.get("price_10"), "alt_price": b.get("alt_price"), "alt_price_10": b.get("alt_price_10"),
                "rarities": b["rarities"], "rates": b["rates"], "pity": b["pity"],
                "effective_rates_with_pity": effective,
                "ten_pull_min_rarity": b.get("ten_pull_min_rarity")}
        if user is not None:
            info["pity_counters"] = (user.pity or {}).get(bid, {})
        out.append(info)
    return out


async def roll(db: AsyncSession, user: User, banner_id: str, count: int, free: bool,
               rng: random.Random | None = None, currency: str = "spirit_stones") -> dict:
    rng = rng or random.SystemRandom()
    cfg = balance.gacha()
    bcfg = cfg["banners"].get(banner_id)
    if bcfg is None:
        raise GachaError("unknown_banner", "Không có quầy quay này.")
    if not bcfg["enabled"]:
        raise GachaError("banner_closed", f"Quầy {bcfg['name_vi']} chưa mở ở phiên bản này.")
    if count not in (1, 10):
        raise GachaError("bad_count", "Chỉ quay 1 hoặc 10 lần.")
    if free and count != 1:
        raise GachaError("bad_count", "Lượt miễn phí chỉ quay 1 lần.")
    banner = Banner.load(banner_id)
    if banner_id == "seeds":   # the Chuột (stage 8): a little more Rare, taken from Common
        from . import pets
        extra = await pets.skill_value(db, user.id, "seed_rare")
        if extra:
            shift = min(extra, banner.rates["common"])
            banner.rates = {**banner.rates, "common": banner.rates["common"] - shift,
                            "rare": banner.rates["rare"] + shift}

    now = clock.now()
    reset_daily(user, clock.local_date(now))
    if bcfg.get("counts_toward_daily_limit"):
        left = cfg["daily_roll_limit"] - user.daily_new_seeds_count
        if left <= 0:
            raise GachaError("daily_limit", "Hạt giống cần nghỉ ngơi, mai quay lại nhé.")
        if count > left:
            raise GachaError("daily_limit", f"Hôm nay chỉ còn {left} lượt hạt mới.")
    if free and banner_id != "seeds":
        raise GachaError("no_free_roll", "Lượt quay miễn phí hằng ngày chỉ dành cho Hạt Chữ.")
    if free:
        if user.daily_free_rolls_used >= cfg["daily_free_rolls"]:
            raise GachaError("no_free_roll", "Hôm nay đã dùng lượt quay miễn phí rồi.")
        user.daily_free_rolls_used += 1
    else:
        if currency == "immortal_jade":  # spec 13: bee eggs and Linh Thú also sell for Tiên Ngọc
            if not bcfg.get("alt_price"):
                raise GachaError("bad_currency", "Quầy này chỉ nhận Linh Thạch.")
            one, ten = bcfg["alt_price"], bcfg.get("alt_price_10")
        else:
            one, ten = bcfg["price"], bcfg.get("price_10")
        price = ten if count == 10 and ten else {k: v * count for k, v in one.items()}
        try:
            await inventory.charge(db, user.id, price, f"gacha_{banner_id}")
        except inventory.InsufficientFunds as e:
            raise GachaError("insufficient_funds", e.message_vi)

    pity_all = dict(user.pity or {})
    rarities, new_state = banner.roll(count, pity_all.get(banner_id, {}), rng)
    pity_all[banner_id] = new_state
    user.pity = pity_all  # reassign so the JSON column is marked dirty

    if banner_id == "seeds":
        rewards = await _resolve_seeds(db, user, rarities, rng, now)
    elif banner_id == "bees":
        rewards = await _resolve_eggs(db, user, rarities)
    elif banner_id == "pets":
        from . import pets
        rewards = await pets.resolve_gacha(db, user, rarities, rng)
    else:  # disabled above; kept explicit for safety
        raise GachaError("banner_closed", "Quầy này chưa mở.")
    if bcfg.get("counts_toward_daily_limit"):
        user.daily_new_seeds_count += count
    await db.flush()
    stones, jade = (await db.execute(select(User.spirit_stones, User.immortal_jade).where(User.id == user.id))).one()
    return {"banner": banner_id, "results": rewards, "pity": new_state, "spirit_stones": stones,
            "immortal_jade": jade,
            "daily_rolls_left": cfg["daily_roll_limit"] - user.daily_new_seeds_count}


async def _resolve_seeds(db: AsyncSession, user: User, rarities: list[str], rng: random.Random,
                         now) -> list[dict]:
    b = bank()
    tier = await player_tier(db, user.id)
    owned = set((await db.execute(select(Collection.word_id).where(Collection.user_id == user.id)))
                .scalars().all())
    out = []
    for r in rarities:
        pool = b.gacha_pool(tier, r) or b.gacha_pool(9, r)
        if not pool:
            raise RuntimeError(f"empty seed pool for rarity {r}")
        new = [w for w in pool if w.id not in owned]
        duplicate = not new
        w = rng.choice(new or pool)
        seed = Seed(user_id=user.id, word_id=w.id, duplicate=duplicate, source="gacha", obtained_at=now)
        db.add(seed)
        if not duplicate:
            owned.add(w.id)
            db.add(Collection(user_id=user.id, word_id=w.id, first_seen_at=now))
        await db.flush()
        out.append({"seed_id": seed.id, "rarity": r, "duplicate": duplicate,
                    # the seed is a mystery until planted; only the rarity glow and the
                    # character are shown (the intro card teaches it)
                    "word": {"id": w.id, "hanzi": w.hanzi}})
    return out


async def _resolve_eggs(db: AsyncSession, user: User, rarities: list[str]) -> list[dict]:
    """Bee banner: an egg of the rolled rarity goes to the bag; the species is decided when
    it hatches in the hive (systems/bees.hatch)."""
    from . import bees, catalog
    eggs = bees.cfg()["eggs"]
    out = []
    for r in rarities:
        item = eggs[r]
        total = await inventory.change_item(db, user.id, item, 1, "gacha_bees")
        out.append({"rarity": r, "item": item, "name_vi": catalog.item_name(item), "total": total})
    return out
