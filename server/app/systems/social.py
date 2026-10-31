"""Friends, blocks, reports and visiting a friend's abode (spec 15.3).

Friendship is stored as two rows once accepted (A->B and B->A, status "accepted"); a
request is a single "pending" row from the requester. "Tưới giúp": a visitor answers a
question about a word growing in the friend's garden; when right, both get Linh Thạch,
at most N attempts a day per visitor. Only words the visitor has learned are asked, so
the question is always fair (spec 1, principle 4).
"""
from __future__ import annotations

import datetime as dt
import random
from types import SimpleNamespace

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..learning import question_bank as qb
from ..learning import quiz, srs
from ..learning.wordbank import bank
from ..models import Block, Character, ChatReport, Collection, Friendship, Plot, QuizSession, User
from ..realtime.world import world
from . import inventory


class SocialError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("social")


async def _char(db: AsyncSession, user_id: int) -> Character:
    ch = await db.get(Character, user_id)
    if ch is None:
        raise SocialError(404, "no_character", "Không tìm thấy người chơi này.")
    return ch


async def _by_name(db: AsyncSession, name: str) -> Character:
    ch = (await db.execute(select(Character).where(
        func.lower(Character.display_name) == (name or "").strip().lower()))).scalar_one_or_none()
    if ch is None:
        raise SocialError(404, "no_player", "Không có đạo hữu nào tên như vậy.")
    return ch


async def _row(db: AsyncSession, a: int, b: int) -> Friendship | None:
    return await db.get(Friendship, (a, b))


async def are_friends(db: AsyncSession, a: int, b: int) -> bool:
    r = await _row(db, a, b)
    return r is not None and r.status == "accepted"


async def _blocked_either(db: AsyncSession, a: int, b: int) -> bool:
    q = select(Block).where(or_((Block.user_id == a) & (Block.blocked_id == b),
                                (Block.user_id == b) & (Block.blocked_id == a)))
    return (await db.execute(q)).first() is not None


def _person(ch: Character) -> dict:
    return {"user_id": ch.user_id, "display_name": ch.display_name, "realm": ch.realm, **world.online(ch.user_id)}


# ------------------------------------------------------------------ friends
async def list_friends(db: AsyncSession, user: User) -> dict:
    mine = (await db.execute(select(Friendship).where(Friendship.user_id == user.id))).scalars().all()
    incoming = (await db.execute(select(Friendship).where(
        Friendship.friend_id == user.id, Friendship.status == "pending"))).scalars().all()
    ids = {r.friend_id for r in mine} | {r.user_id for r in incoming}
    chars = {c.user_id: c for c in (await db.execute(select(Character).where(
        Character.user_id.in_(ids)))).scalars().all()} if ids else {}
    friends = [_person(chars[r.friend_id]) for r in mine if r.status == "accepted" and r.friend_id in chars]
    friends.sort(key=lambda f: (not f["online"], f["display_name"].lower()))
    return {"friends": friends,
            "incoming": [_person(chars[r.user_id]) for r in incoming if r.user_id in chars],
            "outgoing": [_person(chars[r.friend_id]) for r in mine if r.status == "pending" and r.friend_id in chars],
            "helps_left": await helps_left(db, user.id), "max": cfg()["friends_max"]}


async def request(db: AsyncSession, user: User, display_name: str) -> dict:
    me = await _char(db, user.id)
    other = await _by_name(db, display_name)
    if other.user_id == user.id:
        raise SocialError(400, "self", "Không thể tự kết bạn với chính mình.")
    if await _blocked_either(db, user.id, other.user_id):
        raise SocialError(403, "blocked", "Không thể gửi lời mời kết bạn cho người này.")
    if await are_friends(db, user.id, other.user_id):
        raise SocialError(409, "already_friends", "Hai bạn đã là bạn bè rồi.")
    count = (await db.execute(select(func.count()).select_from(Friendship).where(
        Friendship.user_id == user.id))).scalar_one()
    if count >= cfg()["friends_max"]:
        raise SocialError(400, "too_many", "Danh sách bạn bè đã đầy.")
    reverse = await _row(db, other.user_id, user.id)
    if reverse is not None and reverse.status == "pending":  # they asked first: accept both ways
        return await accept(db, user, other.user_id)
    if await _row(db, user.id, other.user_id) is None:
        db.add(Friendship(user_id=user.id, friend_id=other.user_id, status="pending", created_at=clock.now()))
        await db.flush()
        world.notify(other.user_id, {"t": "friend", "event": "request",
                                     "user": {"uid": user.id, "name": me.display_name}})
    return {"status": "pending", "user": _person(other)}


async def accept(db: AsyncSession, user: User, requester_id: int) -> dict:
    r = await _row(db, requester_id, user.id)
    if r is None or r.status != "pending":
        raise SocialError(404, "no_request", "Không có lời mời kết bạn này.")
    r.status = "accepted"
    mine = await _row(db, user.id, requester_id)
    if mine is None:
        db.add(Friendship(user_id=user.id, friend_id=requester_id, status="accepted", created_at=clock.now()))
    else:
        mine.status = "accepted"
    await db.flush()
    me = await _char(db, user.id)
    world.set_friends(user.id, requester_id, True)
    world.notify(requester_id, {"t": "friend", "event": "accepted", "user": {"uid": user.id, "name": me.display_name}})
    return {"status": "accepted", "user": _person(await _char(db, requester_id))}


async def decline(db: AsyncSession, user: User, requester_id: int) -> dict:
    await db.execute(delete(Friendship).where(Friendship.user_id == requester_id, Friendship.friend_id == user.id,
                                              Friendship.status == "pending"))
    return {"ok": True}


async def remove(db: AsyncSession, user: User, other_id: int) -> dict:
    await db.execute(delete(Friendship).where(or_(
        (Friendship.user_id == user.id) & (Friendship.friend_id == other_id),
        (Friendship.user_id == other_id) & (Friendship.friend_id == user.id))))
    world.set_friends(user.id, other_id, False)
    return {"ok": True}


# ------------------------------------------------------------------ blocks & reports
async def block(db: AsyncSession, user: User, other_id: int) -> dict:
    if other_id == user.id:
        raise SocialError(400, "self", "Không thể tự chặn chính mình.")
    await _char(db, other_id)
    if await db.get(Block, (user.id, other_id)) is None:
        db.add(Block(user_id=user.id, blocked_id=other_id, created_at=clock.now()))
    await remove(db, user, other_id)  # blocking also ends the friendship
    await db.flush()
    world.set_block(user.id, other_id, True)
    return {"ok": True}


async def unblock(db: AsyncSession, user: User, other_id: int) -> dict:
    await db.execute(delete(Block).where(Block.user_id == user.id, Block.blocked_id == other_id))
    world.set_block(user.id, other_id, False)
    return {"ok": True}


async def list_blocks(db: AsyncSession, user: User) -> dict:
    rows = (await db.execute(select(Character).join(Block, Block.blocked_id == Character.user_id)
                             .where(Block.user_id == user.id))).scalars().all()
    return {"blocked": [{"user_id": c.user_id, "display_name": c.display_name} for c in rows]}


async def report(db: AsyncSession, user: User, other_id: int, message: str, reason: str) -> dict:
    if other_id == user.id:
        raise SocialError(400, "self", "Không thể tự báo cáo chính mình.")
    await _char(db, other_id)
    since = clock.now() - dt.timedelta(days=1)
    n = (await db.execute(select(func.count()).select_from(ChatReport).where(
        ChatReport.reporter_id == user.id, ChatReport.created_at >= since))).scalar_one()
    if n >= cfg()["reports_per_day"]:
        raise SocialError(429, "too_many_reports", "Bạn đã gửi nhiều báo cáo hôm nay, quản trị viên sẽ xem sớm.")
    db.add(ChatReport(reporter_id=user.id, reported_id=other_id, message=(message or "")[:500],
                      reason=(reason or "")[:200], created_at=clock.now()))
    await db.flush()
    return {"ok": True}


# ------------------------------------------------------------------ visiting & helping
async def helps_left(db: AsyncSession, user_id: int) -> int:
    today = clock.local_date(clock.now())
    used = (await db.execute(select(func.coalesce(func.sum(Friendship.help_count), 0)).where(
        Friendship.user_id == user_id, Friendship.help_count_date == today))).scalar_one()
    return max(0, cfg()["help_daily_limit"] - int(used))


async def _learned(db: AsyncSession, user_id: int) -> set[str]:
    return set((await db.execute(select(Collection.word_id).where(
        Collection.user_id == user_id, Collection.introduced.is_(True)))).scalars().all())


def _helpable(p: Plot, learned: set[str]) -> bool:
    return bool(p.word_id) and 1 <= p.stage and p.word_id in learned


async def visit(db: AsyncSession, user: User, owner_id: int) -> dict:
    """Read-only view of a friend's garden, with wither brought up to date on copies."""
    if not await are_friends(db, user.id, owner_id):
        raise SocialError(403, "not_friend", "Chỉ thăm được động phủ của bạn bè.")
    owner = await _char(db, owner_id)
    owner_user = await db.get(User, owner_id)
    now = clock.now()
    plots = (await db.execute(select(Plot).where(Plot.user_id == owner_id))).scalars().all()
    learned = await _learned(db, user.id)
    from ..garden.garden import wither_rate
    rate = await wither_rate(db, owner_id)     # the owner's Hổ counts (stage 8)
    b = bank()
    views = []
    for row in sorted(plots, key=lambda q: (q.y, q.x)):
        # work on a copy: looking at a garden must never change it
        p = SimpleNamespace(**{k: getattr(row, k) for k in ("id", "x", "y", "unlocked", "word_id", "stage",
                                                             "next_review_at", "wither", "wither_checked_at")})
        if p.word_id:
            srs.refresh_wither(p, now, rate)
        v = {"id": p.id, "x": p.x, "y": p.y, "unlocked": p.unlocked, "word": None}
        if p.unlocked and p.word_id:
            w = b.get(p.word_id)
            known = p.word_id in learned
            v.update({"word": {"id": w.id, "hanzi": w.hanzi, "rarity": w.rarity,
                               "pinyin": w.pinyin if known else None,
                               "meaning_vi": w.meaning_vi if known else None},
                      "stage": p.stage, "wither": round(p.wither, 1), "ripe": p.stage >= srs.RIPE,
                      "helpable": _helpable(p, learned), "known": known,
                      "pollinated": bool(row.pollinated), "pollen": round(row.pollen or 0.0, 1)})
        views.append(v)
    owner_view = {"user_id": owner_id, "display_name": owner.display_name, "realm": owner.realm,
                  **world.online(owner_id)}
    decorations = list((owner_user.flags or {}).get("decorations", [])) if owner_user else []
    g = balance.garden()["grid"]
    from . import bees as beesys
    hive = await beesys.get_hive(db, owner_id)
    bee_rows = await beesys.bees_of(db, owner_id)
    return {"owner": owner_view, "width": g["width"], "height": g["height"], "plots": views,
            "decorations": decorations, "helps_left": await helps_left(db, user.id),
            "help_reward": cfg()["help_reward"],
            "bees": [{"id": x.id, "sp": x.bee_type, "role": x.role} for x in bee_rows],
            "hive": {"level": hive.level, "decorations": list(hive.decorations or [])} if hive else None}


async def start_help(db: AsyncSession, user: User, owner_id: int, plot_id: int,
                     rng: random.Random | None = None) -> dict:
    if not await are_friends(db, user.id, owner_id):
        raise SocialError(403, "not_friend", "Chỉ tưới giúp được vườn của bạn bè.")
    p = await db.get(Plot, plot_id)
    if p is None or p.user_id != owner_id or not p.unlocked or not p.word_id:
        raise SocialError(404, "no_plot", "Ô đất này không có cây để tưới.")
    if p.word_id not in await _learned(db, user.id):
        raise SocialError(400, "not_learned", "Bạn chưa học chữ này nên chưa tưới giúp được.")
    if p.stage < 1:
        raise SocialError(400, "too_young", "Hạt vừa gieo, chủ vườn cần xem thẻ chữ trước đã.")
    if await helps_left(db, user.id) <= 0:
        raise SocialError(400, "help_limit", "Hôm nay bạn đã tưới giúp đủ số lần rồi.")
    now = clock.now()
    today = clock.local_date(now)
    row = await _row(db, user.id, owner_id)
    if row.help_count_date != today:
        row.help_count_date, row.help_count = today, 0
    row.help_count += 1  # an attempt counts, right or wrong (no retrying until it is easy)
    w = bank().get(p.word_id)
    ctx = quiz.gen_context(rng, max_tier=w.tier)
    try:
        question = qb.generate_any(["Q1", "Q2", "Q3"], w, ctx)
    except qb.QuestionError:
        raise SocialError(400, "no_question", "Không tạo được câu hỏi cho chữ này.")
    out = await quiz.create_session(db, user, "help", question, ref=f"{owner_id}:{plot_id}")
    out["helps_left"] = await helps_left(db, user.id)
    return out


async def help_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool, now: dt.datetime) -> dict:
    """A visitor's answer: mastery ±2 for the visitor like any non-garden question (the
    owner's plant does not change), and when right both players get the reward."""
    out = await quiz.practice_handler(db, user, s, correct, now)
    owner_id = int((s.ref or "0:0").split(":")[0])
    out["helps_left"] = await helps_left(db, user.id)
    if not correct:
        return out
    reward = cfg()["help_reward"]
    out["spirit_stones"] = await inventory.change_currency(db, user.id, "spirit_stones", reward, "help_water", s.id)
    await inventory.change_currency(db, owner_id, "spirit_stones", reward, "helped_by_friend", s.id)
    out["reward"] = {"spirit_stones": reward}
    me = await db.get(Character, user.id)
    world.notify(owner_id, {"t": "friend", "event": "helped", "reward": reward,
                            "user": {"uid": user.id, "name": me.display_name if me else ""}})
    return out


quiz.register_handler("help", help_handler)


# ------------------------------------------------------------------ presents (stage 8, spec 12.4)
def gifts_left(user: User) -> int:
    g = balance.load("shop")["gift"]
    flags = user.flags or {}
    used = int(flags.get("gift_count", 0)) if flags.get("gift_day") == clock.local_date(clock.now()) else 0
    return max(0, g["per_day"] - used)


def giftable(item_id: str) -> bool:
    info = catalog_item(item_id)
    return info is not None and info.get("kind") in balance.load("shop")["gift"]["kinds"]


def catalog_item(item_id: str) -> dict | None:
    from . import catalog
    return catalog.stack_item(item_id)


async def gift(db: AsyncSession, user: User, friend_id: int, item_id: str, qty: int) -> dict:
    """A small present to a friend: an unbound stack item, at most max_qty of it, at most
    per_day presents a day. No money and no equipment change hands (no trading in v1)."""
    from . import catalog
    from ..models import InventoryItem
    g = balance.load("shop")["gift"]
    if friend_id == user.id or not await are_friends(db, user.id, friend_id):
        raise SocialError(403, "not_friend", "Chỉ tặng quà được cho bạn bè.")
    if await _blocked_either(db, user.id, friend_id):
        raise SocialError(403, "blocked", "Không tặng quà được cho người này.")
    if not giftable(item_id):
        raise SocialError(400, "not_giftable", "Thứ này không tặng được.")
    if not 1 <= qty <= g["max_qty"]:
        raise SocialError(400, "bad_count", f"Mỗi lần tặng từ 1 đến {g['max_qty']} cái thôi.")
    if gifts_left(user) <= 0:
        raise SocialError(400, "gift_limit", f"Hôm nay con đã tặng đủ {g['per_day']} lần rồi.")
    have = (await db.execute(select(func.coalesce(func.sum(InventoryItem.quantity), 0)).where(
        InventoryItem.user_id == user.id, InventoryItem.item_id == item_id,
        InventoryItem.bound.is_(False)))).scalar_one()
    if have < qty:
        raise SocialError(400, "not_enough", f"Con chỉ có {have} {catalog.item_name(item_id)} tặng được "
                                             "(đồ đã ràng buộc không tặng được).")
    ref = f"gift:{user.id}:{friend_id}"
    left = await inventory.change_item(db, user.id, item_id, -qty, "gift_out", ref, bound=False)
    await inventory.change_item(db, friend_id, item_id, qty, "gift_in", ref, bound=False)
    flags = dict(user.flags or {})
    today = clock.local_date(clock.now())
    flags["gift_count"] = (int(flags.get("gift_count", 0)) if flags.get("gift_day") == today else 0) + 1
    flags["gift_day"] = today
    user.flags = flags
    me = await db.get(Character, user.id)
    world.notify(friend_id, {"t": "friend", "event": "gift", "item": item_id, "name_vi": catalog.item_name(item_id),
                             "qty": qty, "user": {"uid": user.id, "name": me.display_name if me else ""}})
    return {"gave": item_id, "name_vi": catalog.item_name(item_id), "qty": qty, "left": left,
            "gifts_left": gifts_left(user)}
