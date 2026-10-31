"""Câu cá (spec 11): rods, baits, the cast -> bite -> (question) -> reel flow, Ngư Phổ and
the server-wide size records.

The server decides everything that matters: when the fish bites, which species it is and
how big (picked when the hook is set), and whether it was caught (the client sends only
the steps on which it pressed or released the button; `fishing_sim.replay` plays them
again). A cast lives in memory like the rest of the real-time state (DECISIONS: one
process); a server restart just loses the cast in progress.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import random
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning import quiz, selection
from ..learning import question_bank as qb
from ..learning.wordbank import bank
from ..models import Character, FishCatch, QuizSession, User
from . import catalog, fishing_sim, inventory, items

RARITIES = ["pham", "linh", "huyen", "dia", "thien"]
STARTER_ROD = "can_truc_tho"
FISH_PREFIX = "fish_"
WAITING, QUIZ, REEL, DONE = "waiting", "quiz", "reel", "done"


class FishingError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("fishing")


def species() -> dict:
    return catalog.fish()


def fish_item(fid: str) -> str:
    return FISH_PREFIX + fid


# ------------------------------------------------------------------ day, night, rain
def game_hour(now: dt.datetime) -> float:
    """Same clock as the world's day/night (spec 7.1: one game day = two real hours)."""
    from ..realtime.world import cfg as world_cfg
    secs = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
    length = world_cfg()["day_length_seconds"]
    return (secs % length) / length * 24


def is_night(now: dt.datetime) -> bool:
    h = game_hour(now)
    return h >= 18 or h < 6


def is_raining(zone: str, now: dt.datetime) -> bool:
    """Rain comes and goes per zone in fixed periods; the same for every player and every
    call (a hash of zone + period, no state to save)."""
    c = cfg()
    chance = c["rain_chance"].get(zone, 0.0)
    period = int((now - dt.datetime(2026, 1, 1)).total_seconds() // c["weather_period_seconds"])
    h = int.from_bytes(hashlib.sha256(f"{zone}:{period}".encode()).digest()[:8], "big") / 2 ** 64
    return h < chance


def conditions(zone: str, now: dt.datetime) -> dict:
    return {"night": is_night(now), "rain": is_raining(zone, now), "hour": round(game_hour(now), 2)}


# ------------------------------------------------------------------ which fish
def _fits(f: dict, pool: str, cond: dict, bait_id: str | None) -> bool:
    if pool not in f["pools"]:
        return False
    if f["time"] == "day" and cond["night"] or f["time"] == "night" and not cond["night"]:
        return False
    if f["weather"] == "rain" and not cond["rain"] or f["weather"] == "clear" and cond["rain"]:
        return False
    if f["bait"] is not None and bait_id not in f["bait"]:
        return False
    bait = catalog.baits().get(bait_id) if bait_id else None
    if bait and bait.get("only_tag") and bait["only_tag"] not in f["tags"]:
        return False
    if bait_id is None and f["rarity"] not in cfg()["no_bait"]["rarities"]:
        return False
    return True


def eligible(pool: str, cond: dict, bait_id: str | None) -> list[str]:
    return [fid for fid, f in species().items() if _fits(f, pool, cond, bait_id)]


def rarity_odds(pool: str, cond: dict, bait_id: str | None, luck: float) -> dict[str, float]:
    """Chance of each rarity on the next bite. Rarer fish get weight x (1 + luck x scale);
    a rarity with no fish that can bite here and now drops out."""
    c = cfg()
    have = {species()[fid]["rarity"] for fid in eligible(pool, cond, bait_id)}
    w = {r: c["rarity_weight"][r] * (1 + luck * c["luck_scale"][r]) for r in RARITIES if r in have}
    total = sum(w.values())
    return {r: v / total for r, v in w.items()} if total else {}


def species_odds(pool: str, cond: dict, bait_id: str | None, luck: float) -> dict[str, float]:
    """Chance of each species: its rarity's chance shared by the species of that rarity,
    a species the bait attracts counting double."""
    c = cfg()
    bait = catalog.baits().get(bait_id) if bait_id else None
    attracts = set(bait["attracts"]) if bait else set()
    by_r: dict[str, dict[str, float]] = {}
    for fid in eligible(pool, cond, bait_id):
        by_r.setdefault(species()[fid]["rarity"], {})[fid] = c["attract_mult"] if fid in attracts else 1.0
    out = {}
    for r, p in rarity_odds(pool, cond, bait_id, luck).items():
        tot = sum(by_r[r].values())
        for fid, wt in by_r[r].items():
            out[fid] = p * wt / tot
    return out


def roll_fish(pool: str, cond: dict, bait_id: str | None, luck: float, rng: random.Random) -> str | None:
    odds = species_odds(pool, cond, bait_id, luck)
    if not odds:
        return None
    x = rng.random()
    acc = 0.0
    for fid, p in sorted(odds.items()):
        acc += p
        if x < acc:
            return fid
    return sorted(odds)[-1]


def roll_size(fid: str, rng: random.Random) -> tuple[float, float]:
    """Size in cm and its place in the species' range (0 smallest, 1 biggest); big ones are rare."""
    lo, hi = species()[fid]["size_cm"]
    frac = rng.random() ** cfg()["size_curve"]
    return round(lo + (hi - lo) * frac, 1), frac


# ------------------------------------------------------------------ rods, baits, the reel
def rod_stats(rod_id: str, level: int) -> dict:
    r = catalog.rods()[rod_id]
    up = cfg()["rod_upgrade"]["per_level"]
    return {"pull": round(r["pull"] * (1 + up["pull"] * level), 4), "line": round(r["line"] * (1 + up["line"] * level), 4),
            "luck": round(r["luck"] + up["luck"] * level, 4), "bite": r["bite"], "zone": r["zone"]}


def reel_params(rarity: str, size_frac: float, rod: dict, quiz_mult: float, seed: int) -> dict:
    """Everything fishing_sim.Reel needs; sent to the client as is."""
    c = cfg()["reel"]
    zone = c["zone"][rarity] * (1 + rod["zone"]) * quiz_mult
    tough = c["toughness"][rarity] * (1 + c["size_toughness"] * size_frac)
    return {"seed": seed, "zone": round(max(c["zone_min"], min(c["zone_max"], zone)), 4),
            "agility": c["agility"][rarity], "range": c["range"][rarity], "seg_ms": list(c["seg_ms"][rarity]),
            "gain": round(c["gain"] * rod["pull"] / tough, 5), "loss": c["loss"], "start": c["start"],
            "lift": c["lift"], "gravity": c["gravity"], "vmax": c["vmax"],
            "strain_up": round(c["strain_up"] / rod["line"], 5), "strain_down": c["strain_down"],
            "max_ms": c["max_ms"]}


def _state(user: User) -> dict:
    st = dict((user.flags or {}).get("fishing") or {})
    st.setdefault("rod", STARTER_ROD)
    st.setdefault("bait", None)
    st.setdefault("levels", {})
    return st


def _save_state(user: User, st: dict) -> None:
    user.flags = {**(user.flags or {}), "fishing": st}


async def _ensure_starter(db: AsyncSession, user: User) -> dict[str, int]:
    """Every player owns the Cần Trúc Thô (spec 11.2: starting rod, free)."""
    st = await items.stacks(db, user.id)
    if st.get(STARTER_ROD, 0) <= 0:
        await inventory.change_item(db, user.id, STARTER_ROD, 1, "fishing_starter", bound=True)
        st[STARTER_ROD] = 1
    return st


# ------------------------------------------------------------------ casts in progress
@dataclass
class Cast:
    id: str
    user_id: int
    zone: str
    pool: str
    bait: str | None
    rod: str
    rod_level: int
    cast_at: dt.datetime
    bite_at: dt.datetime
    state: str = WAITING
    fish: str | None = None
    size: float = 0.0
    frac: float = 0.0
    need: int = 0
    right: int = 0
    quiz_mult: float = 1.0
    params: dict | None = None
    reel_at: dt.datetime | None = None


_casts: dict[int, Cast] = {}


def active_cast(user_id: int) -> Cast | None:
    return _casts.get(user_id)


def _get(user_id: int, cast_id: str, state: str) -> Cast:
    c = _casts.get(user_id)
    if c is None or c.id != cast_id:
        raise FishingError(404, "no_cast", "Không còn lượt câu này nữa, quăng câu lại nhé.")
    if c.state != state:
        raise FishingError(409, "wrong_step", "Lượt câu không ở bước này.")
    return c


def _where(user: User, spot: str) -> tuple[str, str]:
    """(zone, pool) where the player can fish now, checked on the server: in the world from
    the character's live position, in the Động Phủ only while not standing in the world."""
    from ..realtime.world import world
    if spot == "abode":
        if world.in_world(user.id):
            raise FishingError(400, "not_here", "Con đang ở ngoài thế giới, đâu phải ao nhà.")
        return "abode", "ao"
    p = world.players.get(user.id)
    if p is None or p.channel is None:
        raise FishingError(400, "not_here", "Con không đứng cạnh nước.")
    reach = cfg()["spot_reach"]
    for a in p.channel.map.fishing:
        if a.x - reach <= p.x <= a.x + a.w + reach and a.y - reach <= p.y <= a.y + a.h + reach:
            return p.channel.map.name, a.props.get("pool", "ao")
    raise FishingError(400, "not_here", "Phải đứng sát mép nước mới quăng câu được.")


async def _char(db: AsyncSession, user: User) -> Character:
    ch = await db.get(Character, user.id)
    if ch is None:
        raise FishingError(400, "no_character", "Hãy tạo nhân vật trước.")
    return ch


# ------------------------------------------------------------------ views
def _rod_view(rod_id: str, level: int, owned: bool, equipped: bool) -> dict:
    r = catalog.rods()[rod_id]
    up = cfg()["rod_upgrade"]
    nxt = None
    if owned and level < up["max_level"]:
        nxt = {"spirit_stones": up["cost_stones"][level], "vay_linh_ngu": up["cost_scales"][level]}
    return {"id": rod_id, "name_vi": r["name_vi"], "rarity": r["rarity"], "desc_vi": r["desc_vi"],
            "owned": owned, "equipped": equipped, "level": level, "stats": rod_stats(rod_id, level),
            "price": r["price"], "min_realm": r["min_realm"], "source_vi": r.get("source_vi"),
            "upgrade_cost": nxt}


async def view(db: AsyncSession, user: User, zone: str | None = None) -> dict:
    from ..realtime.world import world
    st = await _ensure_starter(db, user)
    fs = _state(user)
    rods = [_rod_view(rid, int(fs["levels"].get(rid, 0)), st.get(rid, 0) > 0, rid == fs["rod"])
            for rid in sorted(catalog.rods(), key=lambda k: catalog.rods()[k]["order"])]
    baits = []
    for bid in sorted(catalog.baits(), key=lambda k: catalog.baits()[k]["order"]):
        b = catalog.baits()[bid]
        craft = None
        if b["craft"]:
            craft = {**b["craft"], "from_name_vi": catalog.item_name(b["craft"]["from"]),
                     "have": st.get(b["craft"]["from"], 0)}
        baits.append({"id": bid, "name_vi": b["name_vi"], "desc_vi": b["desc_vi"], "qty": st.get(bid, 0),
                      "buy": b["buy"], "craft": craft, "equipped": bid == fs["bait"]})
    if zone is None:
        p = world.players.get(user.id)
        zone = p.channel.map.name if p is not None and p.channel is not None else "abode"
    c = active_cast(user.id)
    return {"rod": fs["rod"], "bait": fs["bait"], "rods": rods, "baits": baits,
            "scales": st.get("vay_linh_ngu", 0), "conditions": {"zone": zone, **conditions(zone, clock.now())},
            "casting": c is not None and c.state != DONE}


async def equip(db: AsyncSession, user: User, rod: str | None, bait: str | None, clear_bait: bool) -> dict:
    st = await _ensure_starter(db, user)
    fs = _state(user)
    if rod is not None:
        if rod not in catalog.rods() or st.get(rod, 0) <= 0:
            raise FishingError(400, "no_rod", "Con chưa có cần câu này.")
        fs["rod"] = rod
    if clear_bait:
        fs["bait"] = None
    elif bait is not None:
        if bait not in catalog.baits():
            raise FishingError(400, "no_bait", "Không có loại mồi này.")
        fs["bait"] = bait
    _save_state(user, fs)
    return await view(db, user)


def _near_fisher(user_id: int) -> None:
    from ..realtime.world import world
    if not world.near_npc(user_id, "fisher", 64):
        raise FishingError(400, "too_far", "Hãy lại gần Ngư Ông ở Hồ Nghiên Mực.")


async def buy(db: AsyncSession, user: User, item_id: str, qty: int) -> dict:
    """Ngư Ông sells rods (once each) and Giun Đất."""
    from . import cultivation
    _near_fisher(user.id)
    st = await _ensure_starter(db, user)
    if item_id in catalog.rods():
        r = catalog.rods()[item_id]
        if st.get(item_id, 0) > 0:
            raise FishingError(400, "owned", "Con có cần này rồi.")
        if not r["price"]:
            raise FishingError(400, "not_sold", r.get("source_vi") or "Ngư Ông không bán cần này.")
        ch = await _char(db, user)
        order = cultivation.order()
        if order.index(ch.realm) < order.index(r["min_realm"]):
            raise FishingError(400, "realm_too_low",
                               f"Cần đạt {cultivation.realm_name(r['min_realm'])} mới cầm nổi {r['name_vi']}.")
        price = {"spirit_stones": r["price"].get("spirit_stones", 0)}
        try:
            for iid, n in (r["price"].get("items") or {}).items():
                await inventory.consume_item(db, user.id, iid, n, "buy_rod", item_id)
            await inventory.charge(db, user.id, price, "buy_rod", item_id)
        except inventory.InsufficientFunds:
            raise FishingError(400, "not_enough", "Chưa đủ Linh Thạch hoặc nguyên liệu (Vảy Linh Ngư, Thiên Tằm Ti).")
        await inventory.change_item(db, user.id, item_id, 1, "buy_rod", bound=True)
        return {"bought": item_id, "qty": 1, **(await view(db, user))}
    b = catalog.baits().get(item_id)
    if b is None or not b["buy"]:
        raise FishingError(400, "not_sold", "Ngư Ông không bán thứ này.")
    if not 1 <= qty <= 99:
        raise FishingError(400, "bad_count", "Số lượng không hợp lệ.")
    try:
        await inventory.charge(db, user.id, {"spirit_stones": b["buy"] * qty}, "buy_bait", item_id)
    except inventory.InsufficientFunds:
        raise FishingError(400, "not_enough", "Chưa đủ Linh Thạch.")
    await inventory.change_item(db, user.id, item_id, qty, "buy_bait")
    return {"bought": item_id, "qty": qty, **(await view(db, user))}


async def craft_bait(db: AsyncSession, user: User, bait_id: str, times: int) -> dict:
    _near_fisher(user.id)
    b = catalog.baits().get(bait_id)
    if b is None or not b["craft"]:
        raise FishingError(400, "not_craftable", "Mồi này không làm được.")
    if not 1 <= times <= 50:
        raise FishingError(400, "bad_count", "Số lượng không hợp lệ.")
    src = b["craft"]["from"]
    try:
        await inventory.consume_item(db, user.id, src, times, "craft_bait", bait_id)
    except inventory.InsufficientFunds as e:
        raise FishingError(400, "not_enough", f"Chỉ có {e.have} {catalog.item_name(src)}.")
    made = b["craft"]["makes"] * times
    await inventory.change_item(db, user.id, bait_id, made, "craft_bait")
    return {"made": made, "bait": bait_id, **(await view(db, user))}


async def upgrade_rod(db: AsyncSession, user: User, rod_id: str) -> dict:
    """Spec 11.2: rods are upgraded at the Lò Rèn."""
    from ..realtime.world import world
    if not world.near_npc(user.id, "smith", 72):
        raise FishingError(400, "too_far", "Mang cần câu tới Lò Rèn ở Trúc Lâm Thôn để nâng cấp.")
    st = await _ensure_starter(db, user)
    if rod_id not in catalog.rods() or st.get(rod_id, 0) <= 0:
        raise FishingError(400, "no_rod", "Con chưa có cần câu này.")
    fs = _state(user)
    lvl = int(fs["levels"].get(rod_id, 0))
    up = cfg()["rod_upgrade"]
    if lvl >= up["max_level"]:
        raise FishingError(400, "max_level", "Cần này đã nâng tới cấp cao nhất.")
    try:
        await inventory.consume_item(db, user.id, "vay_linh_ngu", up["cost_scales"][lvl], "rod_upgrade", rod_id)
        await inventory.charge(db, user.id, {"spirit_stones": up["cost_stones"][lvl]}, "rod_upgrade", rod_id)
    except inventory.InsufficientFunds:
        raise FishingError(400, "not_enough", "Chưa đủ Linh Thạch hoặc nguyên liệu (Vảy Linh Ngư, Thiên Tằm Ti).")
    fs["levels"] = {**fs["levels"], rod_id: lvl + 1}
    _save_state(user, fs)
    return {"rod": rod_id, "level": lvl + 1, **(await view(db, user))}


# ------------------------------------------------------------------ cast, hook, reel
async def cast(db: AsyncSession, user: User, spot: str, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    await _char(db, user)
    zone, pool = _where(user, spot)
    st = await _ensure_starter(db, user)
    fs = _state(user)
    rod = fs["rod"] if st.get(fs["rod"], 0) > 0 else STARTER_ROD
    bait_id = fs["bait"]
    now = clock.now()
    cond = conditions(zone, now)
    if bait_id is not None:
        b = catalog.baits()[bait_id]
        if st.get(bait_id, 0) <= 0:
            raise FishingError(400, "no_bait", f"Hết {b['name_vi']} rồi. Đổi mồi khác hoặc câu không mồi.")
        if b["night_only"] and not cond["night"]:
            raise FishingError(400, "bait_needs_night", f"{b['name_vi']} chỉ dùng được khi trời tối.")
    if not eligible(pool, cond, bait_id):
        raise FishingError(400, "nothing_bites", "Lúc này ở đây chẳng con cá nào chịu cắn mồi này.")
    if bait_id is not None:
        await inventory.consume_item(db, user.id, bait_id, 1, "fishing_bait", zone)
    c = cfg()
    lvl = int(fs["levels"].get(rod, 0))
    stats = rod_stats(rod, lvl)
    lo, hi = c["bite_seconds"]
    wait = (lo + (hi - lo) * rng.random()) * (1 - stats["bite"])
    wait *= catalog.baits()[bait_id]["bite"] if bait_id else c["no_bait"]["bite"]
    wait = max(c["bite_min_seconds"], wait)
    cst = Cast(id=uuid.uuid4().hex, user_id=user.id, zone=zone, pool=pool, bait=bait_id, rod=rod, rod_level=lvl,
               cast_at=now, bite_at=now + dt.timedelta(seconds=wait))
    _casts[user.id] = cst   # a new cast replaces an unfinished one
    return {"cast_id": cst.id, "bite_in": round(wait, 3), "window": c["hook_window"], "zone": zone, "pool": pool,
            "rod": rod, "bait": bait_id, "conditions": cond,
            "bait_left": (st.get(bait_id, 0) - 1) if bait_id else None}


async def hook(db: AsyncSession, user: User, cast_id: str, rng: random.Random | None = None) -> dict:
    """The player strikes. Too early scares the fish, too late it has eaten the bait. On time,
    the server decides the fish (species and size) now."""
    rng = rng or random.Random()
    c = cfg()
    cst = _get(user.id, cast_id, WAITING)
    now = clock.now()
    if now < cst.bite_at - dt.timedelta(seconds=c["hook_early_grace"]):
        cst.state = DONE
        return {"stage": "early"}
    if now > cst.bite_at + dt.timedelta(seconds=c["hook_window"] + balance.quiz()["network_grace"]):
        cst.state = DONE
        return {"stage": "late"}
    if cst.zone != "abode":
        _where(user, "world")   # still standing at the water
    luck = rod_stats(cst.rod, cst.rod_level)["luck"] + (catalog.baits()[cst.bait]["luck"] if cst.bait else 0)
    from . import pets
    luck += await pets.skill_value(db, user.id, "fish_luck")     # Mèo (stage 8)
    cond = conditions(cst.zone, cst.cast_at)
    fid = roll_fish(cst.pool, cond, cst.bait, luck, rng)
    if fid is None:
        cst.state = DONE
        return {"stage": "late"}
    cst.fish = fid
    cst.size, cst.frac = roll_size(fid, rng)
    rarity = species()[fid]["rarity"]
    cst.need = c["quiz_needed"][rarity]
    if cst.need:
        q = await _question(db, user, cst, rng)
        if q is not None:
            cst.state = QUIZ
            return {"stage": "quiz", "rarity": rarity, "need": cst.need, "question": q}
    return {"stage": "reel", "rarity": rarity, **_start_reel(cst, rng)}


async def _question(db: AsyncSession, user: User, cst: Cast, rng: random.Random) -> dict | None:
    """Spec 11.1: a Linh-or-rarer fish asks a question, harder for rarer fish."""
    from . import cultivation
    ch = await _char(db, user)
    tier = cultivation.tier_of(ch.realm)
    try:
        word_id = await selection.pick_word(db, user.id, tier, rng)
    except selection.NoWordAvailable:
        return None   # nothing learned yet: the fish just bites, normal zone
    w = bank().get(word_id)
    types = balance.quiz()["types"]
    rarity = species()[cst.fish]["rarity"]
    allowed = [q for q in cfg()["quiz_types"][rarity] if types[q]["min_tier"] <= tier] or ["Q1", "Q2"]
    question = qb.generate_any(allowed, w, quiz.gen_context(rng, max_tier=max(tier, w.tier)))
    return await quiz.create_session(db, user, "fishing", question, ref=cst.id)


def _start_reel(cst: Cast, rng: random.Random) -> dict:
    rarity = species()[cst.fish]["rarity"]
    stats = rod_stats(cst.rod, cst.rod_level)
    cst.params = reel_params(rarity, cst.frac, stats, cst.quiz_mult, rng.randrange(1, 2 ** 31))
    cst.state = REEL
    cst.reel_at = clock.now()
    return {"params": cst.params, "quiz_mult": cst.quiz_mult}


async def fishing_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool, now: dt.datetime) -> dict:
    """A fishing question answered: mastery as anywhere outside the garden; right widens the
    green zone, wrong narrows it (never costs health: fishing is for relaxing). A Thiên
    fish needs two right answers in a row."""
    out = await quiz.practice_handler(db, user, s, correct, now)
    cst = _casts.get(user.id)
    if cst is None or cst.id != s.ref or cst.state != QUIZ:
        return {**out, "fishing": {"lost": True}}
    c = cfg()
    if correct:
        cst.right += 1
        if cst.right < cst.need:
            q = await _question(db, user, cst, random.Random())
            if q is not None:
                return {**out, "fishing": {"stage": "quiz", "next_question": q, "right": cst.right, "need": cst.need}}
        cst.quiz_mult = c["zone_quiz_right"]
    else:
        cst.quiz_mult = c["zone_quiz_wrong"]
    return {**out, "fishing": {"stage": "reel", "right": cst.right, "need": cst.need,
                               "rarity": species()[cst.fish]["rarity"], **_start_reel(cst, random.Random())}}


quiz.register_handler("fishing", fishing_handler)


def _check_toggles(toggles: list) -> list[int]:
    if not isinstance(toggles, list) or len(toggles) > cfg()["toggles_max"]:
        raise FishingError(400, "bad_input", "Dữ liệu kéo cá không hợp lệ.")
    out, last = [], -1
    for t in toggles:
        if not isinstance(t, int) or isinstance(t, bool) or t <= last or t < 0:
            raise FishingError(400, "bad_input", "Dữ liệu kéo cá không hợp lệ.")
        out.append(t)
        last = t
    return out


async def reel(db: AsyncSession, user: User, cast_id: str, toggles: list) -> dict:
    """The client's button changes are played again here; only this decides the catch. A
    result that would need more time than has really passed is refused."""
    c = cfg()
    cst = _get(user.id, cast_id, REEL)
    flips = _check_toggles(toggles)
    r = fishing_sim.replay(cst.params, flips)
    now = clock.now()
    played = (now - cst.reel_at).total_seconds()
    needed = r.steps * fishing_sim.STEP_MS / 1000
    if played < needed * c["reel_time_slack"] - c["reel_time_grace"]:
        raise FishingError(400, "too_fast", "Kéo cá nhanh hơn thời gian thật, máy chủ không chấp nhận.")
    cst.state = DONE
    if played > cst.params["max_ms"] / 1000 + c["reel_late_seconds"]:
        return {"result": fishing_sim.ESCAPED, "steps": r.steps, "late": True}
    out = {"result": r.result, "steps": r.steps}
    if r.result == fishing_sim.CAUGHT:
        out.update(await _land(db, user, cst))
    return out


async def _land(db: AsyncSession, user: User, cst: Cast) -> dict:
    from . import quests
    c = cfg()
    f = species()[cst.fish]
    now = clock.now()
    small = f["rarity"] == "pham" and cst.frac < c["small_fish_fraction"]
    got = [{"item": "ca_nho" if small else fish_item(cst.fish), "qty": 1}]
    scales = c["scales"].get(f["rarity"], 0)
    if scales:
        got.append({"item": "vay_linh_ngu", "qty": scales})
    await items.grant_items(db, user.id, got, "fishing", cst.fish)
    row = await db.get(FishCatch, (user.id, cst.fish))
    new_species = row is None
    prev_best = row.best_size_cm if row else 0.0
    server_best = (await db.execute(select(func.max(FishCatch.best_size_cm)).where(
        FishCatch.fish_id == cst.fish))).scalar() or 0.0
    if row is None:
        row = FishCatch(user_id=user.id, fish_id=cst.fish, count=0, best_size_cm=0, first_caught_at=now)
        db.add(row)
    row.count += 1
    row.best_size_cm = max(row.best_size_cm, cst.size)
    await db.flush()
    milestones = []
    if new_species:
        found = (await db.execute(select(func.count()).select_from(FishCatch).where(
            FishCatch.user_id == user.id))).scalar_one()
        milestones = await _milestones(db, user, found)
        await quests.on_event(db, user.id, "fish_species", "", 1)
    await quests.on_event(db, user.id, "fish", "", 1)
    return {"fish": public_species(cst.fish), "size_cm": cst.size, "small": small,
            "items": got, "new_species": new_species, "personal_record": cst.size > prev_best,
            "server_record": cst.size > server_best, "milestones": milestones}


async def _milestones(db: AsyncSession, user: User, found: int) -> list[dict]:
    """Ngư Phổ milestones (spec 12.1: Tiên Ngọc comes from library milestones)."""
    flags = dict(user.flags or {})
    got = set(flags.get("fish_milestones", []))
    out = []
    for m in cfg()["milestones"]:
        if found >= m["species"] and m["species"] not in got:
            got.add(m["species"])
            for cur, n in m["reward"].items():
                await inventory.change_currency(db, user.id, cur, n, "fish_codex", str(m["species"]))
            out.append({"species": m["species"], **m["reward"]})
    if out:
        flags["fish_milestones"] = sorted(got)
        user.flags = flags
    return out


def cancel(user: User) -> dict:
    c = _casts.pop(user.id, None)
    return {"cancelled": c is not None}


# ------------------------------------------------------------------ Ngư Phổ, records
POOL_VI = {"ao": "ao nhỏ", "ho": "Hồ Nghiên Mực"}
TIME_VI = {"day": "ban ngày", "night": "ban đêm"}
WEATHER_VI = {"rain": "trời mưa", "clear": "trời quang"}


def hint_vi(f: dict) -> str:
    parts = [", ".join(POOL_VI[p] for p in f["pools"])]
    if f["time"] in TIME_VI:
        parts.append(TIME_VI[f["time"]])
    if f["weather"] in WEATHER_VI:
        parts.append(WEATHER_VI[f["weather"]])
    if f["bait"]:
        parts.append("mồi " + " / ".join(catalog.baits()[b]["name_vi"] for b in f["bait"]))
    return " · ".join(parts)


def public_species(fid: str) -> dict:
    f = species()[fid]
    return {"id": fid, "name_vi": f["name_vi"], "hanzi": f["hanzi"], "pinyin": f["pinyin"],
            "meaning_en": f["meaning_en"], "fictional": f["fictional"], "mythical": f["mythical"],
            "rarity": f["rarity"], "shape": f["shape"], "color": f["color"], "color2": f["color2"],
            "desc_vi": f["desc_vi"], "hint_vi": hint_vi(f), "size_cm": f["size_cm"], "sell_price": f["sell_price"]}


def silhouette(fid: str) -> dict:
    f = species()[fid]
    return {"id": fid, "rarity": f["rarity"], "shape": f["shape"], "hint_vi": hint_vi(f)}


async def book(db: AsyncSession, user: User) -> dict:
    rows = {r.fish_id: r for r in (await db.execute(select(FishCatch).where(FishCatch.user_id == user.id))).scalars()}
    out = []
    order = {r: i for i, r in enumerate(RARITIES)}
    for fid in sorted(species(), key=lambda k: (order[species()[k]["rarity"]], k)):
        row = rows.get(fid)
        if row is None:
            out.append({**silhouette(fid), "caught": False})
        else:
            out.append({**public_species(fid), "caught": True, "count": row.count, "best_size_cm": row.best_size_cm,
                        "first_caught_at": row.first_caught_at.isoformat() + "Z"})
    got = set((user.flags or {}).get("fish_milestones", []))
    ms = [{"species": m["species"], **m["reward"], "claimed": m["species"] in got} for m in cfg()["milestones"]]
    return {"species": out, "found": len(rows), "total": len(species()), "milestones": ms}


async def records(db: AsyncSession, user: User | None = None) -> dict:
    """Spec 11.3: the biggest fish of every species on the whole server."""
    top = cfg()["records_top"]
    rows = (await db.execute(
        select(FishCatch.fish_id, FishCatch.best_size_cm, FishCatch.user_id, FishCatch.first_caught_at,
               Character.display_name)
        .join(Character, Character.user_id == FishCatch.user_id)
        .order_by(FishCatch.fish_id, FishCatch.best_size_cm.desc(), FishCatch.first_caught_at))).all()
    by: dict[str, list] = {}
    for fid, size, uid, _, name in rows:
        if fid in species() and len(by.setdefault(fid, [])) < top:
            by[fid].append({"name": name, "size_cm": size, "me": user is not None and uid == user.id})
    order = {r: i for i, r in enumerate(RARITIES)}
    out = []
    for fid in sorted(by, key=lambda k: (order[species()[k]["rarity"]], k)):
        f = species()[fid]
        out.append({"id": fid, "name_vi": f["name_vi"], "hanzi": f["hanzi"], "rarity": f["rarity"], "top": by[fid]})
    return {"records": out}
