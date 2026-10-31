"""Checking a Firebase ID token (LAN worlds). The game signs in to Firebase Authentication
itself and hands the ID token to whichever world it joins; the world asks Firebase who it
belongs to (Identity Toolkit `accounts:lookup`). That needs only the public Web API key,
no service account, so any player's computer can host a world.

Tests replace `lookup` with a fake.
"""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

import httpx

from .config import settings

LOOKUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"


def lookup_url() -> str:
    """FIREBASE_AUTH_EMULATOR_HOST (Firebase's own convention) points at the local Auth Emulator."""
    emu = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
    return f"http://{emu}/identitytoolkit.googleapis.com/v1/accounts:lookup" if emu else LOOKUP_URL


class FirebaseError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def _lookup(id_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(lookup_url(), params={"key": settings.firebase_api_key}, json={"idToken": id_token})
    except httpx.HTTPError:
        raise FirebaseError("network") from None
    data = r.json() if r.content else {}
    if r.status_code != 200:
        msg = str((data.get("error") or {}).get("message", "error"))
        raise FirebaseError(msg.split(" ")[0])
    users = data.get("users") or []
    if not users:
        raise FirebaseError("INVALID_ID_TOKEN")
    u = users[0]
    if u.get("disabled"):
        raise FirebaseError("USER_DISABLED")
    return {"uid": u["localId"], "email": u.get("email") or "", "name": u.get("displayName") or ""}


lookup: Callable[[str], Awaitable[dict]] = _lookup


async def verify(id_token: str) -> dict:
    """-> {uid, email, name}; raises FirebaseError."""
    if not id_token or len(id_token) > 4096:
        raise FirebaseError("INVALID_ID_TOKEN")
    return await lookup(id_token)
