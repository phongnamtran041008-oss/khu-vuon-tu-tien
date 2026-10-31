"""Yêu Quái Phổ (spec 9.3): monsters met, how many beaten, what they ask and drop."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..models import CodexEntry, User
from . import catalog


async def meet_monster(db: AsyncSession, user_id: int, kind: str) -> bool:
    """Returns True the first time this player meets this kind of monster."""
    if await db.get(CodexEntry, (user_id, "monster", kind)) is not None:
        return False
    db.add(CodexEntry(user_id=user_id, codex="monster", entry_id=kind, discovered_at=clock.now(),
                      progress={"kills": 0}))
    await db.flush()
    return True


async def monster_killed(db: AsyncSession, user_id: int, kind: str) -> int:
    e = await db.get(CodexEntry, (user_id, "monster", kind))
    if e is None:
        await meet_monster(db, user_id, kind)
        e = await db.get(CodexEntry, (user_id, "monster", kind))
    kills = int((e.progress or {}).get("kills", 0)) + 1
    e.progress = {**(e.progress or {}), "kills": kills}
    return kills


async def monster_book(db: AsyncSession, user: User) -> dict:
    rows = {e.entry_id: e for e in (await db.execute(select(CodexEntry).where(
        CodexEntry.user_id == user.id, CodexEntry.codex == "monster"))).scalars().all()}
    qnames = {k: v["name_vi"] for k, v in balance.quiz()["types"].items()}
    out = []
    for kind, m in catalog.monsters().items():
        e = rows.get(kind)
        entry = {"id": kind, "found": e is not None, "sprite": m.get("sprite", kind), "rank": m.get("rank", "normal")}
        if e is not None:
            drops = []
            for d in m.get("drops", []):
                if "item" in d:
                    drops.append(catalog.item_name(d["item"]))
                else:
                    drops.append("Trang bị: " + ", ".join(catalog.item_name(i) for i in d["equipment"]))
            entry.update({"name_vi": m["name_vi"], "kills": int((e.progress or {}).get("kills", 0)),
                          "qtypes_vi": [qnames.get(q, q) for q in m.get("qtypes", [])],
                          "weakness_vi": m.get("weakness_vi", ""), "drops_vi": drops, "hp": m.get("hp"),
                          "rank_vi": {"normal": "Thường", "elite": "Tinh anh", "boss": "Thủ lĩnh"}.get(m.get("rank"), "")})
        out.append(entry)
    from . import td   # Mặc Quái of the Thủ Vườn levels (stage 7) are in the same book
    for kind, m in td.cfg()["monsters"].items():
        e = rows.get("td_" + kind)
        entry = {"id": "td_" + kind, "found": e is not None, "sprite": "td_" + kind, "td": True,
                 "rank": "boss" if m.get("boss") else "normal"}
        if e is not None:
            entry.update({"name_vi": m["name_vi"], "kills": int((e.progress or {}).get("kills", 0)),
                          "qtypes_vi": [], "weakness_vi": m["weakness_vi"], "drops_vi": [], "hp": m["hp"],
                          "rank_vi": "Thủ lĩnh · Thủ Vườn" if m.get("boss") else "Thủ Vườn"})
        out.append(entry)
    found = sum(1 for x in out if x["found"])
    return {"entries": out, "found": found, "total": len(out)}
