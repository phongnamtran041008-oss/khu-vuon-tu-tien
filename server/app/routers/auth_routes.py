from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..auth import (accounts_created_today_from_ip, acheck, ahash, anon_limit, api_error, client_ip,
                    current_user, make_token, new_recovery_code, normalize_recovery, validate_credentials)
from ..config import settings
from ..db import get_db
from ..learning.wordbank import bank
from .. import firebase_auth
from ..models import Collection, Seed, User
from ..schemas import ChangePasswordIn, FirebaseIn, LoginIn, RegisterIn, ResetPasswordIn

router = APIRouter(prefix="/auth", tags=["auth"])
STARTER_SEED = "水"  # tutorial: Trúc Lão hands over the first seed (spec 6.9)


def _local_accounts_on() -> None:
    if not settings.local_accounts:
        raise api_error(403, "local_off", "Thế giới này chỉ dùng tài khoản Firebase: hãy đăng nhập bằng email.")


async def _create_user(db: AsyncSession, username: str, password_hash: str, recovery_hash: str, ip: str,
                       **extra) -> User:
    """A new account with the starter seed (spec 6.9: Trúc Lão hands over 水)."""
    now = clock.now()
    eco = balance.economy()
    user = User(username=username, password_hash=password_hash, recovery_code_hash=recovery_hash,
                spirit_stones=eco["starting_spirit_stones"], immortal_jade=eco["starting_immortal_jade"], pity={},
                created_at=now, last_login_at=now, register_ip=ip, **extra)
    db.add(user)
    await db.flush()
    starter = bank().by_hanzi[STARTER_SEED]
    db.add(Seed(user_id=user.id, word_id=starter.id, duplicate=False, source="tutorial", obtained_at=now))
    db.add(Collection(user_id=user.id, word_id=starter.id, first_seen_at=now))
    return user


@router.post("/register")
async def register(body: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)):
    _local_accounts_on()
    anon_limit(request, "register", 10)
    validate_credentials(body.username, body.password)
    ip = client_ip(request)
    ip_limit = settings.accounts_per_ip or balance.economy()["max_accounts_per_ip_per_day"]
    if await accounts_created_today_from_ip(db, ip) >= ip_limit:
        raise api_error(429, "ip_limit", "Hôm nay mạng của bạn đã tạo đủ số tài khoản cho phép.")
    exists = (await db.execute(select(User.id).where(User.username.ilike(body.username)))).first()
    if exists:
        raise api_error(409, "username_taken", "Tên đăng nhập đã có người dùng.")
    display, raw = new_recovery_code()
    user = await _create_user(db, body.username, await ahash(body.password), await ahash(raw), ip,
                              is_admin=body.username.casefold() in settings.admin_usernames)
    await db.commit()
    return {"token": make_token(user), "user_id": user.id, "recovery_code": display,
            "recovery_note_vi": "Hãy chép lại mã khôi phục này. Đây là lần duy nhất mã được hiển thị; "
                                "bạn cần nó để đặt lại mật khẩu khi quên."}


@router.post("/login")
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    _local_accounts_on()
    anon_limit(request, "login", 20)
    user = (await db.execute(select(User).where(User.username.ilike(body.username)))).scalar_one_or_none()
    if user is None or not await acheck(body.password, user.password_hash):
        raise api_error(401, "bad_login", "Sai tên đăng nhập hoặc mật khẩu.")
    if user.banned_until and user.banned_until > clock.now():
        raise api_error(403, "banned", f"Tài khoản bị khóa đến {user.banned_until:%d/%m/%Y %H:%M} (UTC).")
    user.last_login_at = clock.now()
    await db.commit()
    return {"token": make_token(user), "user_id": user.id}


FIREBASE_ERRORS = {
    "network": (503, "Máy chủ không liên lạc được với Firebase (cần Internet để đăng nhập)."),
    "USER_DISABLED": (403, "Tài khoản Firebase này đã bị khóa."),
    "CONFIGURATION_NOT_FOUND": (503, "Dự án Firebase chưa bật Authentication (Email/Password)."),
}


def _username_base(email: str, uid: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", (email.split("@")[0] if email else "").lower().replace(".", "_"))
    base = base[:16]
    return base if len(base) >= 3 else "dh_" + re.sub(r"[^a-z0-9]", "", uid.lower())[:8]


@router.post("/firebase")
async def firebase_login(body: FirebaseIn, request: Request, db: AsyncSession = Depends(get_db)):
    """LAN worlds: trade a Firebase ID token for this world's own session token. The first
    visit creates the local account (with the starter seed); later visits find it again."""
    if not settings.firebase_api_key:
        raise api_error(404, "firebase_off", "Máy chủ này không dùng tài khoản Firebase.")
    anon_limit(request, "firebase", 30)
    try:
        who = await firebase_auth.verify(body.id_token)
    except firebase_auth.FirebaseError as e:
        status, msg = FIREBASE_ERRORS.get(e.code, (401, "Phiên đăng nhập Firebase không hợp lệ, hãy đăng nhập lại."))
        raise api_error(status, "firebase_" + e.code.lower(), msg)
    host = bool(settings.host_firebase_uid) and who["uid"] == settings.host_firebase_uid
    owner = bool(who["email"]) and who["email"].casefold() in settings.admin_emails   # the game's author
    user = (await db.execute(select(User).where(User.firebase_uid == who["uid"]))).scalar_one_or_none()
    created = user is None
    if user is None:
        base = _username_base(who["email"], who["uid"])
        name, n = base, 1
        while (await db.execute(select(User.id).where(func.lower(User.username) == name))).first():
            n += 1
            name = f"{base[:20 - len(str(n))]}{n}"
        unusable = "!firebase"   # no password can ever match this: the account signs in only through Firebase
        user = await _create_user(db, name, unusable, unusable, client_ip(request),
                                  firebase_uid=who["uid"], email=who["email"][:200] or None)
    if user.banned_until and user.banned_until > clock.now():
        raise api_error(403, "banned", f"Tài khoản bị khóa đến {user.banned_until:%d/%m/%Y %H:%M} (UTC).")
    if (host or owner) and not user.is_admin:
        user.is_admin = True
    if who["email"] and user.email != who["email"]:
        user.email = who["email"][:200]
    user.last_login_at = clock.now()
    await db.commit()
    return {"token": make_token(user), "user_id": user.id, "username": user.username, "created": created,
            "is_admin": user.is_admin}


@router.post("/reset_password")
async def reset_password(body: ResetPasswordIn, request: Request, db: AsyncSession = Depends(get_db)):
    anon_limit(request, "reset", 5)
    user = (await db.execute(select(User).where(User.username.ilike(body.username)))).scalar_one_or_none()
    if user is None or not await acheck(normalize_recovery(body.recovery_code), user.recovery_code_hash):
        raise api_error(401, "bad_recovery", "Sai tên đăng nhập hoặc mã khôi phục.")
    validate_credentials(user.username, body.new_password)
    display, raw = new_recovery_code()  # a used code is replaced, so it cannot be reused
    user.password_hash = await ahash(body.new_password)
    user.recovery_code_hash = await ahash(raw)
    user.token_version += 1  # log out every device
    await db.commit()
    return {"token": make_token(user), "recovery_code": display,
            "recovery_note_vi": "Mã khôi phục cũ đã hết hiệu lực. Hãy chép lại mã mới này."}


@router.post("/change_password")
async def change_password(body: ChangePasswordIn, user: User = Depends(current_user),
                          db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    if not await acheck(body.old_password, user.password_hash):
        raise api_error(401, "bad_password", "Mật khẩu cũ không đúng.")
    validate_credentials(user.username, body.new_password)
    user.password_hash = await ahash(body.new_password)
    user.token_version += 1
    await db.commit()
    return {"token": make_token(user)}


@router.post("/logout_all")
async def logout_all(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user = await db.merge(user)
    user.token_version += 1
    await db.commit()
    return {"ok": True}
