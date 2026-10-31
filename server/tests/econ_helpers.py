"""Shared helpers of the stage 8 tests (luyện đan, khắc văn, Linh Thú, cửa hàng, kinh tế)."""
from sqlalchemy import select, update

from app import clock
from app import db as dbm
from app.learning.wordbank import bank
from app.models import Collection, Fruit, InventoryItem, User
from app.systems import inventory
from tests.helpers import register

LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}


async def player(client, name="dan_su", learn: list[str] | None = None, mastery: int = 40, stones: int | None = None):
    h, data = await register(client, name)
    r = await client.post("/character/create", json={"display_name": name.replace("_", " ").title(), "appearance": LOOK},
                          headers=h)
    assert r.status_code == 200, r.text
    uid = data["user_id"]
    if learn:
        await learn_words(uid, learn, mastery)
    if stones is not None:
        await set_stones(uid, stones)
    return h, uid


async def learn_words(uid: int, words, mastery: int = 40) -> None:
    async with dbm.SessionLocal() as db:
        for hz in words:
            wid = bank().by_hanzi[hz].id
            col = await db.get(Collection, (uid, wid))
            if col is None:
                db.add(Collection(user_id=uid, word_id=wid, introduced=True, mastery=mastery, first_seen_at=clock.now()))
            else:
                col.introduced, col.mastery = True, mastery
        await db.commit()


async def set_stones(uid: int, n: int, jade: int | None = None) -> None:
    async with dbm.SessionLocal() as db:
        vals = {"spirit_stones": n}
        if jade is not None:
            vals["immortal_jade"] = jade
        await db.execute(update(User).where(User.id == uid).values(**vals))
        await db.commit()


async def stones(uid: int) -> int:
    async with dbm.SessionLocal() as db:
        return (await db.execute(select(User.spirit_stones).where(User.id == uid))).scalar_one()


async def give(uid: int, item_id: str, n: int, bound: bool = False) -> None:
    async with dbm.SessionLocal() as db:
        await inventory.change_item(db, uid, item_id, n, "test", bound=bound)
        await db.commit()


async def give_fruit(uid: int, hanzi: str, n: int) -> None:
    async with dbm.SessionLocal() as db:
        await inventory.change_fruit(db, uid, bank().by_hanzi[hanzi].id, n, "test")
        await db.commit()


async def qty(uid: int, item_id: str) -> int:
    async with dbm.SessionLocal() as db:
        rows = (await db.execute(select(InventoryItem).where(InventoryItem.user_id == uid,
                                                             InventoryItem.item_id == item_id))).scalars().all()
        return sum(r.quantity for r in rows)


async def fruits(uid: int) -> int:
    async with dbm.SessionLocal() as db:
        return sum((await db.execute(select(Fruit.count).where(Fruit.user_id == uid))).scalars().all())


def common_word(exclude: str = "") -> str:
    """Some common word (for fruits)."""
    return next(w.hanzi for w in bank().words.values() if w.rarity == "common" and not w.hidden and w.hanzi != exclude)


def rare_word() -> str:
    return next(w.hanzi for w in bank().words.values() if w.rarity == "rare" and not w.hidden)
