"""Tàng Thư Các (spec 9.3, 8.3): every "phổ" in one place, its % complete and milestone
rewards, the Bách Thảo Phổ (one page per plant = per word), a search over all books by
hanzi, pinyin with or without tones, or Vietnamese meaning, and the Sổ Lỗi (words most
often answered wrong, practised through /quiz/practice).

The other books keep their own data and screens (Yêu Quái Phổ, Ong Phổ, Ngư Phổ, Sổ Phát
Hiện); the library counts them and links to them.
"""
from __future__ import annotations

import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance
from ..garden import combos
from ..learning import pinyin as py
from ..learning import quiz
from ..learning.wordbank import bank
from ..models import AuditLog, CodexEntry, Collection, EquipmentInstance, FishCatch, InventoryItem, Skill, User
from . import catalog, inventory, td

BOOKS = ["plant", "monster", "bee", "fish", "discovery", "treasure", "pet"]
BOOK_VI = {"plant": "Bách Thảo Phổ", "monster": "Yêu Quái Phổ", "bee": "Ong Phổ", "fish": "Ngư Phổ",
           "discovery": "Sổ Phát Hiện", "treasure": "Bảo Vật Phổ", "pet": "Linh Thú Phổ"}


class LibraryError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("library")


# ------------------------------------------------------------------ counting every book
async def _count(db: AsyncSession, user_id: int, codex: str) -> int:
    return (await db.execute(select(func.count()).select_from(CodexEntry).where(
        CodexEntry.user_id == user_id, CodexEntry.codex == codex))).scalar_one()


async def counts(db: AsyncSession, user: User) -> dict[str, tuple[int, int]]:
    """book -> (found, total)."""
    owned = (await db.execute(select(func.count()).select_from(Collection).where(
        Collection.user_id == user.id))).scalar_one()
    fish = (await db.execute(select(func.count()).select_from(FishCatch).where(
        FishCatch.user_id == user.id))).scalar_one()
    unlocks = sum(1 for c in combos.combos() if c["kind"] == "unlock")
    monsters_total = len(catalog.monsters()) + len(td.cfg()["monsters"])
    return {"plant": (owned, len(bank().words)),
            "monster": (await _count(db, user.id, "monster"), monsters_total),
            "bee": (await _count(db, user.id, "bee"), len(catalog.bees())),
            "fish": (fish, len(catalog.fish())),
            "discovery": (await _count(db, user.id, "discovery"), unlocks),
            "treasure": (len(await treasures_owned(db, user.id)), len(treasure_catalog())),
            "pet": (await _count(db, user.id, "pet"), len(catalog.pets()["species"]))}


def _claimed(user: User) -> dict[str, list[int]]:
    return {k: list(v) for k, v in ((user.flags or {}).get("library_claims") or {}).items()}


def reward_vi(r: dict) -> str:
    parts = []
    if r.get("spirit_stones"):
        parts.append(f"{r['spirit_stones']} Linh Thạch")
    if r.get("immortal_jade"):
        parts.append(f"{r['immortal_jade']} Tiên Ngọc")
    if r.get("title"):
        parts.append(f"danh hiệu «{r['title']}»")
    if r.get("frame"):
        parts.append(cfg()["frames_vi"].get(r["frame"], r["frame"]))
    if r.get("hive_cell"):
        parts.append("thêm 1 ô tổ ong")
    return ", ".join(parts)


async def overview(db: AsyncSession, user: User) -> dict:
    c = cfg()
    claimed = _claimed(user)
    books = []
    for book, (found, total) in (await counts(db, user)).items():
        pct = int(found * 100 // total) if total else 0
        ms = []
        for m in c["milestones"]:
            r = c["rewards"][book][str(m)]
            ms.append({"pct": m, "reward": r, "reward_vi": reward_vi(r), "ready": pct >= m,
                       "claimed": m in claimed.get(book, [])})
        books.append({"id": book, "name_vi": BOOK_VI[book], "found": found, "total": total, "pct": pct,
                      "milestones": ms})
    flags = user.flags or {}
    return {"books": books, "titles": flags.get("titles", []),
            "frames": [{"id": f, "name_vi": c["frames_vi"].get(f, f)} for f in flags.get("frames", [])],
            "title": flags.get("title"), "frame": flags.get("frame"),
            "shop": await shop_view(db, user), "at_desk": at_desk(user.id)}


# ------------------------------------------------------------------ titles and avatar frames
async def wear(db: AsyncSession, user: User, title: str | None, frame: str | None) -> dict:
    """Choose the title shown under the name and the frame around the portrait ("" = none)."""
    flags = dict(user.flags or {})
    if title is not None:
        if title and title not in flags.get("titles", []):
            raise LibraryError(400, "no_title", "Con chưa có danh hiệu này.")
        flags["title"] = title or None
    if frame is not None:
        if frame and frame not in flags.get("frames", []):
            raise LibraryError(400, "no_frame", "Con chưa có khung này.")
        flags["frame"] = frame or None
    user.flags = flags
    await db.flush()
    return await overview(db, user)


# ------------------------------------------------------------------ the librarian's shelf
def at_desk(user_id: int) -> bool:
    """Bí kíp are sold by the Thủ Thư herself (spec 8.4): stand next to her in Trúc Lâm Thôn."""
    from ..realtime.world import world
    return world.near_npc(user_id, "librarian", cfg()["shop_reach"])


async def shop_view(db: AsyncSession, user: User) -> list[dict]:
    learned = set((await db.execute(select(Skill.skill_id).where(Skill.user_id == user.id))).scalars())
    held = dict((await db.execute(select(InventoryItem.item_id, func.sum(InventoryItem.quantity)).where(
        InventoryItem.user_id == user.id).group_by(InventoryItem.item_id))).all())
    out = []
    for iid, price in cfg()["shop"].items():
        m = catalog.materials().get(iid)
        if m is None:
            continue
        have = int(held.get(iid) or 0)
        # a bí kíp is "learned" once its Pháp Chữ is known; an đan phương as soon as it is in the bag
        out.append({"item_id": iid, "name_vi": m["name_vi"], "desc_vi": m.get("desc_vi", ""), "price": price,
                    "kind": m.get("kind"), "have": have,
                    "learned": (have > 0) if m.get("kind") == "recipe" else m.get("skill") in learned})
    return out


async def buy(db: AsyncSession, user: User, item_id: str) -> dict:
    price = cfg()["shop"].get(item_id)
    if price is None:
        raise LibraryError(400, "not_sold", "Tàng Thư Các không bán thứ này.")
    if not at_desk(user.id):
        raise LibraryError(400, "too_far", "Muốn mua bí kíp thì tới gặp Thủ Thư ở Tàng Thư Các.")
    if catalog.materials().get(item_id, {}).get("kind") == "recipe" and \
            (await inventory_count(db, user.id, item_id)) > 0:
        raise LibraryError(400, "already_have", "Con đã có đan phương này rồi, giữ trong túi là luyện được mãi.")
    try:
        await inventory.charge(db, user.id, {"spirit_stones": price}, "library_shop", item_id)
    except inventory.InsufficientFunds:
        raise LibraryError(400, "not_enough", "Chưa đủ Linh Thạch.")
    await inventory.change_item(db, user.id, item_id, 1, "library_shop")
    return {"bought": item_id, "name_vi": catalog.item_name(item_id), **(await overview(db, user))}


async def inventory_count(db: AsyncSession, user_id: int, item_id: str) -> int:
    return int((await db.execute(select(func.coalesce(func.sum(InventoryItem.quantity), 0)).where(
        InventoryItem.user_id == user_id, InventoryItem.item_id == item_id))).scalar_one())


async def claim(db: AsyncSession, user: User, book: str, pct: int) -> dict:
    c = cfg()
    if book not in BOOKS or pct not in c["milestones"]:
        raise LibraryError(400, "bad_milestone", "Không có mốc thưởng này.")
    found, total = (await counts(db, user))[book]
    if not total or found * 100 // total < pct:
        raise LibraryError(400, "not_yet", f"{BOOK_VI[book]} chưa đạt {pct}%.")
    claimed = _claimed(user)
    if pct in claimed.get(book, []):
        raise LibraryError(409, "claimed", "Con đã nhận mốc này rồi.")
    r = c["rewards"][book][str(pct)]
    flags = dict(user.flags or {})
    ref = f"{book}:{pct}"
    for cur in ("spirit_stones", "immortal_jade"):
        if r.get(cur):
            await inventory.change_currency(db, user.id, cur, r[cur], "library_milestone", ref)
    if r.get("title"):
        flags["titles"] = sorted(set(flags.get("titles", [])) | {r["title"]})
    if r.get("frame"):
        flags["frames"] = sorted(set(flags.get("frames", [])) | {r["frame"]})
    if r.get("hive_cell"):
        from . import bees
        hive = await bees.ensure_hive(db, user)
        if hive.cells < bees.cfg()["hive"]["cells_max"]:
            hive.cells += r["hive_cell"]
    claimed[book] = sorted(set(claimed.get(book, [])) | {pct})
    flags["library_claims"] = claimed
    user.flags = flags
    await db.flush()
    return {"claimed": {"book": book, "pct": pct, "reward_vi": reward_vi(r)}, **(await overview(db, user))}


# ------------------------------------------------------------------ Bảo Vật Phổ
def treasure_catalog() -> dict[str, dict]:
    """Spec 9.3: equipment, pills (and fishing rods, gear too) a player has ever had."""
    out: dict[str, dict] = {}
    eq = catalog.equipment()
    for iid, it in eq["items"].items():
        out[iid] = {"id": iid, "kind": "equip", "kind_vi": eq["slots"].get(it["slot"], it["slot"]),
                    "name_vi": it["name_vi"], "desc_vi": it.get("desc_vi", ""), "stats": it.get("stats", {})}
    for iid, it in catalog.pills().items():
        out[iid] = {"id": iid, "kind": "pill", "kind_vi": "Đan dược", "name_vi": it["name_vi"],
                    "desc_vi": it.get("desc_vi", "")}
    for iid, it in catalog.rods().items():
        out[iid] = {"id": iid, "kind": "rod", "kind_vi": "Cần câu", "name_vi": it["name_vi"],
                    "desc_vi": it.get("desc_vi", ""), "rarity": it.get("rarity")}
    return out


async def treasures_owned(db: AsyncSession, user_id: int) -> dict[str, object]:
    """Every treasure ever received (from the audit log of every item change, plus what is
    held now), with the first time it came."""
    known = treasure_catalog()
    got: dict[str, object] = {}
    rows = (await db.execute(select(AuditLog.currency_or_item, func.min(AuditLog.created_at)).where(
        AuditLog.user_id == user_id, AuditLog.delta > 0,
        (AuditLog.currency_or_item.like("item:%")) | (AuditLog.currency_or_item.like("equip:%")))
        .group_by(AuditLog.currency_or_item))).all()
    for key, first in rows:
        iid = key.split(":")[1]
        if iid in known and (iid not in got or first < got[iid]):
            got[iid] = first
    held = list((await db.execute(select(InventoryItem.item_id).where(
        InventoryItem.user_id == user_id, InventoryItem.quantity > 0))).scalars())
    held += list((await db.execute(select(EquipmentInstance.item_id).where(
        EquipmentInstance.user_id == user_id))).scalars())
    for iid in held:
        if iid in known:
            got.setdefault(iid, None)
    return got


async def treasure_book(db: AsyncSession, user: User) -> dict:
    owned = await treasures_owned(db, user.id)
    out = []
    for iid, t in treasure_catalog().items():
        if iid in owned:
            first = owned[iid]
            out.append({**t, "found": True, "first_at": first.isoformat() + "Z" if first else None})
        else:
            out.append({"id": iid, "kind": t["kind"], "kind_vi": t["kind_vi"], "found": False})
    return {"entries": out, "found": len(owned), "total": len(out)}


# ------------------------------------------------------------------ Bách Thảo Phổ
QUIPS = [(90, "Chữ này con thuộc làu rồi, cây mọc ra cũng thẳng lưng hơn."),
         (60, "Khá lắm. Ôn thêm vài lần nữa là cây này thành cổ thụ."),
         (30, "Mới quen thôi, đừng để sương mực phủ lên nó nhé."),
         (0, "Hạt còn non. Ra vườn ôn đúng lịch là cây khỏe ngay.")]
ROLE_QUIPS = {"hoa": "Trồng cạnh đường quanh co, lửa nổ trúng cả bầy.",
              "thuy": "Đặt trước cây Hỏa: quái chậm lại thì lửa đốt được lâu hơn.",
              "moc": "Trồng ngay trên đường để chặn quái; ba cây 木 liền nhau thành 森.",
              "son": "Đặt chỗ quái đông, rung một cái cả bọn đứng hình.",
              "kim": "Kim châm nhắm con khỏe nhất, để dành cho Mực Đặc với Thạch Mặc.",
              "quang": "Không có ánh sáng thì Mực Ẩn cứ thế mà đi qua. 日 cạnh 月 sáng gấp đôi.",
              "sinh_khi": "Trồng sớm, Linh Khí sinh ra càng nhiều.",
              "ho_tro": "Đặt giữa mấy cây đánh, cả nhóm bắn nhanh hẳn.",
              "thanh_ngu": "Thành ngữ không trồng được, nhưng dùng đúng lúc thì xoay chuyển cả trận."}


def quip_vi(role: str, mastery: int) -> str:
    q = next(t for m, t in QUIPS if mastery >= m)
    return f"{q} {ROLE_QUIPS.get(role, '')}".strip()


def plant_page(w, col: Collection | None, entry: dict | None) -> dict:
    role = td.role_of(w.id)
    rd = td.roles_data()["roles"][role]
    page = {"word_id": w.id, "found": True, "hanzi": w.hanzi, "pinyin": w.pinyin, "meaning_vi": w.meaning_vi,
            "rarity": w.rarity, "topic": w.topic, "hidden": w.hidden, "role": role, "role_vi": rd["name_vi"],
            "role_desc_vi": rd["desc_vi"], "role_stats": td.cfg()["roles"][role],
            "example": w.example, "chars": w.chars, "story_vi": w.story_vi, "measure_words": w.measure_words,
            "has_audio": quiz.has_audio(w.id), "introduced": bool(col and col.introduced),
            "mastery": col.mastery if col else 0, "times_correct": col.times_correct if col else 0,
            "times_wrong": col.times_wrong if col else 0}
    if entry:
        page["power"] = entry["power"]
        page["wither"] = entry["wither"]
        if entry.get("skill"):
            page["skill"] = entry["skill"]
    elif role == "thanh_ngu":
        page["skill"] = td.cfg()["idiom_skills"].get(w.hanzi)
    page["quip_vi"] = quip_vi(role, page["mastery"])
    return page


async def herb_book(db: AsyncSession, user: User) -> dict:
    """Spec 9.3: plants the player has get a full page; others are a dark silhouette with '?';
    hidden plants (明 林 森 好 休 吗...) are an empty frame until discovered."""
    cols = {c.word_id: c for c in (await db.execute(select(Collection).where(
        Collection.user_id == user.id))).scalars()}
    entries = await td.plant_entries(db, user)
    out = []
    order = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}
    for w in sorted(bank().words.values(), key=lambda w: (w.tier, w.hidden, order.get(w.rarity, 9), w.id)):
        col = cols.get(w.id)
        if col is not None:
            out.append(plant_page(w, col, entries.get(w.id)))
        elif w.hidden:
            out.append({"word_id": w.id, "found": False, "hidden": True, "tier": w.tier})
        else:
            out.append({"word_id": w.id, "found": False, "hidden": False, "rarity": w.rarity, "tier": w.tier,
                        "role": td.role_of(w.id)})
    found = sum(1 for e in out if e["found"])
    return {"plants": out, "found": found, "total": len(out)}


# ------------------------------------------------------------------ search
def fold(s: str) -> str:
    """Lower case without Vietnamese accents or pinyin tone marks (đ -> d), no spaces."""
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace(" ", "").replace("'", "")


def _pinyin_keys(numeric: str, marked: str) -> list[str]:
    plain = py.strip_tones(numeric).replace(" ", "").replace("ü", "v")
    return [fold(marked), plain, plain.replace("v", "u"), py.canonical(numeric).replace(" ", "")]


def matches(q: str, *, hanzi: str = "", pinyin_numeric: str = "", pinyin: str = "", texts: list[str] = ()) -> bool:
    q = q.strip()
    if not q:
        return False
    if hanzi and q in hanzi:
        return True
    fq = fold(q)
    if pinyin_numeric and any(fq and fq in k for k in _pinyin_keys(pinyin_numeric, pinyin)):
        return True
    for t in texts:
        if q.lower() in t.lower() or (fq and fq in fold(t)):
            return True
    return False


async def search(db: AsyncSession, user: User, q: str) -> dict:
    """Only what the player has already found is listed (searching never reveals a secret)."""
    q = q.strip()
    out: list[dict] = []
    if not q:
        return {"q": q, "results": out}
    limit = cfg()["search_limit"]
    owned = set((await db.execute(select(Collection.word_id).where(Collection.user_id == user.id))).scalars())
    for w in bank().words.values():
        if w.id in owned and matches(q, hanzi=w.hanzi, pinyin_numeric=w.pinyin_numeric, pinyin=w.pinyin,
                                     texts=[w.meaning_vi]):
            out.append({"book": "plant", "id": w.id, "title": w.hanzi, "sub": f"{w.pinyin} · {w.meaning_vi}"})
    caught = set((await db.execute(select(FishCatch.fish_id).where(FishCatch.user_id == user.id))).scalars())
    for fid, f in catalog.fish().items():
        if fid in caught and matches(q, hanzi=f["hanzi"], pinyin=f["pinyin"], texts=[f["name_vi"], fold(f["pinyin"])]):
            out.append({"book": "fish", "id": fid, "title": f["name_vi"], "sub": f"{f['hanzi']} {f['pinyin']}"})
    met = {e.entry_id for e in (await db.execute(select(CodexEntry).where(
        CodexEntry.user_id == user.id, CodexEntry.codex.in_(["bee", "monster"])))).scalars()}
    for bid, b in catalog.bees().items():
        if bid in met and matches(q, hanzi=b.get("hanzi", ""), pinyin=b.get("pinyin", ""),
                                  texts=[b["name_vi"], fold(b.get("pinyin", ""))]):
            out.append({"book": "bee", "id": bid, "title": b["name_vi"], "sub": f"{b.get('hanzi', '')} {b.get('pinyin', '')}"})
    owned_t = await treasures_owned(db, user.id)
    for iid, t in treasure_catalog().items():
        if iid in owned_t and matches(q, texts=[t["name_vi"]]):
            out.append({"book": "treasure", "id": iid, "title": t["name_vi"], "sub": f"Bảo Vật Phổ · {t['kind_vi']}"})
    pets_met = {e.entry_id for e in (await db.execute(select(CodexEntry).where(
        CodexEntry.user_id == user.id, CodexEntry.codex == "pet"))).scalars()}
    for pid, p in catalog.pets()["species"].items():
        if pid in pets_met and matches(q, hanzi=p["hanzi"], pinyin=p["pinyin"],
                                       texts=[p["name_vi"], fold(p["pinyin"])]):
            out.append({"book": "pet", "id": pid, "title": p["name_vi"], "sub": f"{p['hanzi']} {p['pinyin']}"})
    for mid, m in catalog.monsters().items():
        if mid in met and matches(q, texts=[m["name_vi"]]):
            out.append({"book": "monster", "id": mid, "title": m["name_vi"], "sub": "Yêu Quái Phổ"})
    for mid, m in td.cfg()["monsters"].items():
        if "td_" + mid in met and matches(q, texts=[m["name_vi"]]):
            out.append({"book": "monster", "id": "td_" + mid, "title": m["name_vi"], "sub": "Yêu Quái Phổ · Thủ Vườn"})
    return {"q": q, "results": out[:limit], "more": max(0, len(out) - limit)}


# ------------------------------------------------------------------ Sổ Lỗi
async def mistakes(db: AsyncSession, user: User) -> dict:
    """Spec 8.3: the words answered wrong most often, with a button to practise each."""
    rows = (await db.execute(select(Collection).where(
        Collection.user_id == user.id, Collection.times_wrong > 0, Collection.introduced.is_(True))
        .order_by(Collection.times_wrong.desc(), Collection.mastery).limit(cfg()["mistakes_top"]))).scalars().all()
    out = []
    for c in rows:
        if c.word_id not in bank().words:
            continue
        w = bank().get(c.word_id)
        total = c.times_correct + c.times_wrong
        out.append({"word_id": w.id, "hanzi": w.hanzi, "pinyin": w.pinyin, "meaning_vi": w.meaning_vi,
                    "times_wrong": c.times_wrong, "times_correct": c.times_correct,
                    "accuracy": round(c.times_correct / total, 2) if total else 0.0,
                    "mastery": c.mastery, "needs_review": c.needs_review})
    return {"words": out}
