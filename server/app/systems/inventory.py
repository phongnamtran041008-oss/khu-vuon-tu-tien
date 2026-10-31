"""The ONLY place that changes currencies and items (spec 4): atomic, never negative,
always audited. Callers own the transaction (commit/rollback)."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..models import AuditLog, Fruit, InventoryItem, User

CURRENCIES = {"spirit_stones": User.spirit_stones, "immortal_jade": User.immortal_jade}
CURRENCY_NAMES_VI = {"spirit_stones": "Linh Thạch", "immortal_jade": "Tiên Ngọc"}


class InsufficientFunds(Exception):
    def __init__(self, what: str, need: int, have: int):
        super().__init__(f"not enough {what}: need {need}, have {have}")
        self.what, self.need, self.have = what, need, have

    @property
    def message_vi(self) -> str:
        name = CURRENCY_NAMES_VI.get(self.what, self.what)
        return f"Không đủ {name} (cần {self.need}, đang có {self.have})."


async def _audit(db: AsyncSession, user_id: int, what: str, delta: int, after: int | None,
                 reason: str, ref: str | None) -> None:
    db.add(AuditLog(user_id=user_id, currency_or_item=what, delta=delta, balance_after=after,
                    reason=reason, ref_id=ref, created_at=clock.now()))


async def change_currency(db: AsyncSession, user_id: int, currency: str, delta: int,
                          reason: str, ref: str | None = None) -> int:
    """Adds delta (may be negative). Uses one conditional UPDATE so two concurrent
    spends can never take the balance below zero. Returns the new balance."""
    if currency not in CURRENCIES:
        raise ValueError(currency)
    if delta == 0:
        return (await db.execute(select(CURRENCIES[currency]).where(User.id == user_id))).scalar_one()
    col = CURRENCIES[currency]
    res = await db.execute(
        update(User).where(User.id == user_id, col + delta >= 0)
        .values({col.key: col + delta}).returning(col))
    row = res.first()
    if row is None:
        have = (await db.execute(select(col).where(User.id == user_id))).scalar_one()
        raise InsufficientFunds(currency, -delta, have)
    new_balance = row[0]
    await _audit(db, user_id, currency, delta, new_balance, reason, ref)
    return new_balance


async def charge(db: AsyncSession, user_id: int, price: dict[str, int], reason: str,
                 ref: str | None = None) -> None:
    for cur, amount in price.items():
        if amount:
            await change_currency(db, user_id, cur, -int(amount), reason, ref)


async def change_item(db: AsyncSession, user_id: int, item_id: str, delta: int, reason: str,
                      ref: str | None = None, bound: bool = False) -> int:
    row = (await db.execute(select(InventoryItem).where(
        InventoryItem.user_id == user_id, InventoryItem.item_id == item_id,
        InventoryItem.bound == bound))).scalar_one_or_none()
    if row is None:
        if delta < 0:
            raise InsufficientFunds(item_id, -delta, 0)
        row = InventoryItem(user_id=user_id, item_id=item_id, quantity=0, bound=bound)
        db.add(row)
        await db.flush()
    res = await db.execute(
        update(InventoryItem).where(InventoryItem.id == row.id, InventoryItem.quantity + delta >= 0)
        .values(quantity=InventoryItem.quantity + delta).returning(InventoryItem.quantity))
    got = res.first()
    if got is None:
        raise InsufficientFunds(item_id, -delta, row.quantity)
    await _audit(db, user_id, f"item:{item_id}", delta, got[0], reason, ref)
    return got[0]


async def change_fruit(db: AsyncSession, user_id: int, word_id: str, delta: int, reason: str,
                       ref: str | None = None) -> int:
    row = (await db.execute(select(Fruit).where(Fruit.user_id == user_id, Fruit.word_id == word_id))
           ).scalar_one_or_none()
    if row is None:
        if delta < 0:
            raise InsufficientFunds(f"fruit:{word_id}", -delta, 0)
        row = Fruit(user_id=user_id, word_id=word_id, count=0)
        db.add(row)
        await db.flush()
    res = await db.execute(
        update(Fruit).where(Fruit.user_id == user_id, Fruit.word_id == word_id, Fruit.count + delta >= 0)
        .values(count=Fruit.count + delta).returning(Fruit.count))
    got = res.first()
    if got is None:
        raise InsufficientFunds(f"fruit:{word_id}", -delta, row.count)
    await _audit(db, user_id, f"fruit:{word_id}", delta, got[0], reason, ref)
    return got[0]


async def consume_item(db: AsyncSession, user_id: int, item_id: str, qty: int, reason: str,
                       ref: str | None = None) -> int:
    """Spends qty of an item whether it is bound or not (bound copies first, they cannot be
    traded anyway). All or nothing. Returns what is left in total."""
    rows = (await db.execute(select(InventoryItem).where(
        InventoryItem.user_id == user_id, InventoryItem.item_id == item_id,
        InventoryItem.quantity > 0))).scalars().all()
    have = sum(r.quantity for r in rows)
    if have < qty:
        raise InsufficientFunds(item_id, qty, have)
    need = qty
    for r in sorted(rows, key=lambda r: not r.bound):
        take = min(need, r.quantity)
        if take:
            await change_item(db, user_id, item_id, -take, reason, ref, bound=r.bound)
            need -= take
        if not need:
            break
    return have - qty

