"""Admin commands from the server console (stage 10), against whatever DATABASE_URL points at.

    cd server
    python -m app.admin_cli grant <username>      # make an account admin (then use /admin in chat)
    python -m app.admin_cli revoke <username>
    python -m app.admin_cli admins                # list admins
    python -m app.admin_cli ban <tên> 7d [lý do]  # any /admin command works here too:
    python -m app.admin_cli flagged               #   who, unban, unmute, flagged, reports, log ...

In Docker: `docker compose exec server python -m app.admin_cli grant <username>`.
A running server only sees a ban or mute from here when the player next connects; from
chat (`/admin ban ...`) it also kicks them at once.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from . import admin
from . import db as dbm
from .models import User


async def _grant(username: str, value: bool) -> int:
    async with dbm.SessionLocal() as db:
        try:
            user, _ = await admin.find_user(db, "@" + username.lstrip("@"))
        except admin.AdminError as e:
            print(e)
            return 1
        user.is_admin = value
        await admin.log_action(db, "cli", "grant" if value else "revoke", user)
        await db.commit()
        print(f"@{user.username}: is_admin = {value}")
        return 0


async def _admins() -> int:
    async with dbm.SessionLocal() as db:
        rows = (await db.execute(select(User.username).where(User.is_admin.is_(True)))).scalars().all()
    print("\n".join("@" + u for u in rows) if rows else "Chưa có quản trị viên nào.")
    return 0


async def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("\n".join(admin.HELP))
        return 0
    try:
        if argv[0] in ("grant", "revoke"):
            if len(argv) != 2:
                print(f"Cách dùng: python -m app.admin_cli {argv[0]} <username>")
                return 2
            return await _grant(argv[1], argv[0] == "grant")
        if argv[0] == "admins":
            return await _admins()
        async with dbm.SessionLocal() as db:
            ok, lines = await admin.run(db, None, "cli", " ".join(argv), world=None)
        print("\n".join(lines))
        return 0 if ok else 1
    finally:
        await dbm.engine.dispose()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Vietnamese text on a Windows console
    sys.exit(asyncio.run(main(sys.argv[1:])))
