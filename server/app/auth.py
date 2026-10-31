"""Accounts (spec 15.4): username + password, one-time recovery code, JWT (30 days)."""
from __future__ import annotations

import asyncio
import datetime as dt
import re
import secrets
import time
from collections import defaultdict, deque

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import balance, clock
from .config import settings
from .db import get_db
from .models import User

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 to avoid misreading


def api_error(status: int, code: str, message_vi: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message_vi": message_vi})


def hash_secret(s: str) -> str:
    return bcrypt.hashpw(s.encode("utf-8")[:72], bcrypt.gensalt(rounds=10)).decode()


def check_secret(s: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(s.encode("utf-8")[:72], h.encode())
    except ValueError:
        return False


async def ahash(s: str) -> str:
    """bcrypt is slow on purpose (~0.1 s): run it on a thread so the world tick never waits."""
    return await asyncio.to_thread(hash_secret, s)


async def acheck(s: str, h: str) -> bool:
    return await asyncio.to_thread(check_secret, s, h)


def new_recovery_code() -> tuple[str, str]:
    """Returns (display 'ABCD-EFGH-JKLM', normalized 'ABCDEFGHJKLM')."""
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}", raw


def normalize_recovery(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()


def validate_credentials(username: str, password: str) -> None:
    eco = balance.economy()
    if not (eco["username_min"] <= len(username or "") <= eco["username_max"]) or not USERNAME_RE.match(username or ""):
        raise api_error(400, "bad_username",
                        f"Tên đăng nhập dài {eco['username_min']}–{eco['username_max']} ký tự, chỉ gồm chữ không dấu, số và gạch dưới.")
    if len(password or "") < eco["password_min"]:
        raise api_error(400, "bad_password", f"Mật khẩu cần ít nhất {eco['password_min']} ký tự.")
    if len(password) > 128:
        raise api_error(400, "bad_password", "Mật khẩu quá dài.")


def make_token(user: User) -> str:
    now = clock.now()
    payload = {"sub": str(user.id), "tv": user.token_version,
               "iat": int(now.replace(tzinfo=dt.timezone.utc).timestamp()),
               "exp": int((now + dt.timedelta(days=balance.economy()["token_days"]))
                          .replace(tzinfo=dt.timezone.utc).timestamp())}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def user_from_token(db: AsyncSession, token: str) -> User:
    try:
        # exp is checked against the server clock so tests with a frozen clock behave
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                          options={"verify_exp": False})
    except jwt.PyJWTError:
        raise api_error(401, "bad_token", "Phiên đăng nhập không hợp lệ, hãy đăng nhập lại.")
    if data.get("exp", 0) < clock.now().replace(tzinfo=dt.timezone.utc).timestamp():
        raise api_error(401, "token_expired", "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.")
    user = await db.get(User, int(data["sub"]))
    if user is None or user.token_version != data.get("tv"):
        raise api_error(401, "bad_token", "Phiên đăng nhập không hợp lệ, hãy đăng nhập lại.")
    if user.banned_until and user.banned_until > clock.now():
        raise api_error(403, "banned", f"Tài khoản bị khóa đến {user.banned_until:%d/%m/%Y %H:%M} (UTC).")
    return user


async def current_user(authorization: str | None = Header(default=None),
                       db: AsyncSession = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise api_error(401, "no_token", "Bạn cần đăng nhập.")
    return await user_from_token(db, authorization.split(" ", 1)[1].strip())


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def accounts_created_today_from_ip(db: AsyncSession, ip: str) -> int:
    now = clock.now()
    start_local = dt.datetime.fromisoformat(clock.local_date(now)) - clock.VN_OFFSET
    q = select(func.count()).select_from(User).where(User.register_ip == ip, User.created_at >= start_local)
    return (await db.execute(q)).scalar_one()


# ------------------------------------------------------------ rate limiting (spec 17)
class RateLimiter:
    """Sliding one-minute window per key, in memory (single server process)."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def reset(self):
        self.hits.clear()


limiter = RateLimiter()


async def write_user(request: Request, user: User = Depends(current_user)) -> User:
    """Dependency for state-changing endpoints: auth + per-user write rate limit."""
    if settings.rate_limit_enabled and not limiter.check(
            f"w:{user.id}", balance.economy()["write_requests_per_minute"]):
        raise api_error(429, "rate_limited", "Bạn thao tác quá nhanh, chờ một chút nhé.")
    return user


def anon_limit(request: Request, bucket: str, limit: int) -> None:
    if settings.rate_limit_enabled and not limiter.check(f"{bucket}:{client_ip(request)}", limit):
        raise api_error(429, "rate_limited", "Thử lại quá nhiều lần, chờ một chút nhé.")
