"""Admin commands (spec 17, stage 10). Accounts with `is_admin` type them in chat as
`/admin <lệnh> ...`; the text never reaches any chat channel. The same functions back
`python -m app.admin_cli` for the server console.

Every command that changes something is written to `admin_actions`. Nothing here bans
anyone automatically: flagged accounts (fast-answer streaks, chat reports) only show up
in `/admin flagged` and `/admin reports` for a person to judge.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import clock, server_state
from . import db as dbm
from .config import settings
from .models import AdminAction, Character, ChatReport, User

if TYPE_CHECKING:
    from .realtime.world import Session, World

PERMANENT = dt.timedelta(days=365 * 100)
_DURATION = re.compile(r"^(\d+)\s*(m|p|ph|phut|h|g|gio|d|n|ngay|w|t|tuan)?$")
_UNIT = {"m": 60, "p": 60, "ph": 60, "phut": 60, "h": 3600, "g": 3600, "gio": 3600,
         "d": 86400, "n": 86400, "ngay": 86400, "w": 604800, "t": 604800, "tuan": 604800}

# Vietnamese aliases, so `/admin camchat` and `/admin mute` are the same command
ALIASES = {"camchat": "mute", "mochat": "unmute", "khoa": "ban", "mokhoa": "unban", "da": "kick",
           "thongbao": "announce", "baotri": "maintenance", "danhdau": "flagged", "bocodanhdau": "unflag",
           "baocao": "reports", "xem": "who", "tocdo": "timescale", "trogiup": "help", "nhatky": "log"}

HELP = [
    "Lệnh quản trị (/admin ...):",
    "  mute <tên> <thời hạn> [lý do] — cấm chat (30m, 2h, 7d, 1w, vinhvien)",
    "  unmute <tên> — bỏ cấm chat",
    "  ban <tên> <thời hạn> [lý do] — khóa tài khoản có thời hạn, đá khỏi game",
    "  unban <tên> — mở khóa",
    "  kick <tên> — ngắt kết nối (vào lại được ngay)",
    "  announce <nội dung> — thông báo toàn máy chủ (announce off: gỡ)",
    "  maintenance <nội dung> — thông báo bảo trì ở màn đăng nhập (maintenance off: gỡ)",
    "  online — ai đang online",
    "  who <tên> — xem tài khoản",
    "  flagged / unflag <tên> — tài khoản bị nghi dùng bot",
    "  reports — báo cáo chat gần nhất",
    "  log — 10 lệnh quản trị gần nhất",
    "  timescale <số> — tua thời gian (chỉ máy chủ dev)",
    "<tên> là đạo hiệu hoặc @tên_đăng_nhập.",
]


class AdminError(Exception):
    pass


def parse_duration(token: str) -> dt.timedelta | None:
    t = token.strip().lower().replace("đ", "d")
    if t in ("vinhvien", "vĩnhviễn", "perm", "forever"):
        return PERMANENT
    m = _DURATION.match(t)
    if not m or int(m.group(1)) <= 0:
        return None
    return dt.timedelta(seconds=int(m.group(1)) * _UNIT[m.group(2) or "m"])


def fmt_vn(t: dt.datetime) -> str:
    """Naive UTC -> 'dd/mm/yyyy HH:MM (giờ VN)'."""
    if t - clock.now() > dt.timedelta(days=365 * 50):
        return "vĩnh viễn"
    return f"{t + clock.VN_OFFSET:%d/%m/%Y %H:%M} (giờ VN)"


async def find_user(db: AsyncSession, name: str) -> tuple[User, Character | None]:
    """By display name (đạo hiệu, case-insensitive) or `@username`."""
    name = name.strip()
    if not name:
        raise AdminError("Thiếu tên người chơi.")
    if name.startswith("@"):
        user = (await db.execute(select(User).where(func.lower(User.username) == name[1:].lower()))).scalar_one_or_none()
        if user is None:
            raise AdminError(f"Không có tài khoản @{name[1:]}.")
        return user, await db.get(Character, user.id)
    ch = (await db.execute(select(Character).where(func.lower(Character.display_name) == name.lower())
                           )).scalar_one_or_none()
    if ch is None:
        # SQLite's lower() only folds ASCII, so names with Vietnamese capitals are compared here
        for row in (await db.execute(select(Character))).scalars():
            if row.display_name.casefold() == name.casefold():
                ch = row
                break
    if ch is None:
        user = (await db.execute(select(User).where(func.lower(User.username) == name.lower()))).scalar_one_or_none()
        if user is None:
            raise AdminError(f"Không tìm thấy người chơi '{name}'.")
        return user, await db.get(Character, user.id)
    return await db.get(User, ch.user_id), ch


def _label(user: User, ch: Character | None) -> str:
    return f"{ch.display_name} (@{user.username})" if ch else f"@{user.username}"


def _split_name_duration(args: list[str]) -> tuple[str, dt.timedelta, str]:
    """'Tiểu Trúc 2h nói tục' -> ('Tiểu Trúc', 2h, 'nói tục'): names may contain spaces,
    so the first token that reads as a duration ends the name."""
    for i, tok in enumerate(args):
        d = parse_duration(tok)
        if d is not None and i > 0:
            return " ".join(args[:i]), d, " ".join(args[i + 1:])
    raise AdminError("Cần thời hạn, ví dụ: 30m, 2h, 7d, 1w hoặc vinhvien.")


async def log_action(db: AsyncSession, admin_name: str, action: str, target: User | None = None,
                     detail: str = "") -> None:
    db.add(AdminAction(admin_name=admin_name[:40], action=action, target_id=target.id if target else None,
                       target_name=target.username if target else None, detail=detail[:300],
                       created_at=clock.now()))


def _guard_target(admin: User | None, target: User) -> None:
    """In-game admins cannot act on themselves or each other; the console (admin=None) can."""
    if admin is None:
        return
    if target.id == admin.id:
        raise AdminError("Không dùng lệnh này với chính mình.")
    if target.is_admin:
        raise AdminError("Không dùng lệnh này với quản trị viên khác.")


# ---------------------------------------------------------------- commands
async def mute(db, admin: User | None, admin_name: str, args: list[str], world: "World | None") -> list[str]:
    name, dur, reason = _split_name_duration(args)
    target, ch = await find_user(db, name)
    _guard_target(admin, target)
    target.chat_banned_until = clock.now() + dur
    await log_action(db, admin_name, "mute", target, f"{dur} {reason}".strip())
    await db.commit()
    if world is not None:
        s = world.sessions.get(target.id)
        if s is not None:
            s.chat_banned_until = target.chat_banned_until
            s.send({"t": "notice", "text": f"Bạn bị cấm chat đến {fmt_vn(target.chat_banned_until)}."
                                           + (f" Lý do: {reason}" if reason else "")})
    return [f"Đã cấm chat {_label(target, ch)} đến {fmt_vn(target.chat_banned_until)}."]


async def unmute(db, admin, admin_name, args, world) -> list[str]:
    target, ch = await find_user(db, " ".join(args))
    target.chat_banned_until = None
    await log_action(db, admin_name, "unmute", target)
    await db.commit()
    if world is not None and (s := world.sessions.get(target.id)) is not None:
        s.chat_banned_until = None
        s.send({"t": "notice", "text": "Bạn đã được chat trở lại."})
    return [f"Đã bỏ cấm chat {_label(target, ch)}."]


async def ban(db, admin, admin_name, args, world) -> list[str]:
    name, dur, reason = _split_name_duration(args)
    target, ch = await find_user(db, name)
    _guard_target(admin, target)
    target.banned_until = clock.now() + dur
    await log_action(db, admin_name, "ban", target, f"{dur} {reason}".strip())
    await db.commit()
    until = fmt_vn(target.banned_until)
    if world is not None and (s := world.sessions.get(target.id)) is not None:
        s.close(4010, {"t": "kicked", "reason": "banned",
                       "message_vi": f"Tài khoản bị khóa đến {until}." + (f" Lý do: {reason}" if reason else "")})
    return [f"Đã khóa {_label(target, ch)} đến {until}."]


async def unban(db, admin, admin_name, args, world) -> list[str]:
    target, ch = await find_user(db, " ".join(args))
    target.banned_until = None
    await log_action(db, admin_name, "unban", target)
    await db.commit()
    return [f"Đã mở khóa {_label(target, ch)}."]


async def kick(db, admin, admin_name, args, world) -> list[str]:
    target, ch = await find_user(db, " ".join(args))
    _guard_target(admin, target)
    if world is None:
        return ["Lệnh này chỉ dùng trong game."]
    s = world.sessions.get(target.id)
    if s is None:
        return [f"{_label(target, ch)} không online."]
    s.close(4011, {"t": "kicked", "reason": "admin", "message_vi": "Bạn đã bị quản trị viên ngắt kết nối."})
    await log_action(db, admin_name, "kick", target)
    await db.commit()
    return [f"Đã ngắt kết nối {_label(target, ch)}."]


async def announce(db, admin, admin_name, args, world) -> list[str]:
    text = " ".join(args).strip()
    if not text:
        raise AdminError("Thiếu nội dung thông báo.")
    if text.lower() in ("off", "tat", "tắt"):
        server_state.announcement = ""
        await log_action(db, admin_name, "announce", detail="off")
        await db.commit()
        return ["Đã gỡ thông báo."]
    server_state.announcement = text[:200]
    await log_action(db, admin_name, "announce", detail=text)
    await db.commit()
    n = 0
    if world is not None:
        for s in list(world.sessions.values()):
            s.send({"t": "notice", "text": server_state.announcement, "kind": "announce"})
            n += 1
    return [f"Đã gửi thông báo tới {n} người đang online."]


async def maintenance(db, admin, admin_name, args, world) -> list[str]:
    text = " ".join(args).strip()
    if not text:
        cur = server_state.maintenance_message
        return [f"Thông báo bảo trì hiện tại: {cur}" if cur else "Chưa có thông báo bảo trì."]
    off = text.lower() in ("off", "tat", "tắt")
    server_state.maintenance_message = "" if off else text[:200]
    await log_action(db, admin_name, "maintenance", detail="off" if off else text)
    await db.commit()
    if off:
        return ["Đã gỡ thông báo bảo trì."]
    if world is not None:
        for s in list(world.sessions.values()):
            s.send({"t": "notice", "text": server_state.maintenance_message, "kind": "maintenance"})
    return ["Đã đặt thông báo bảo trì (hiện ở màn đăng nhập và /server/info)."]


async def online(db, admin, admin_name, args, world) -> list[str]:
    if world is None:
        return ["Lệnh này chỉ dùng trong game."]
    names = sorted(s.name for s in world.sessions.values())
    head = f"{len(names)} người online"
    return [head + (": " + ", ".join(names[:30]) + (" ..." if len(names) > 30 else "") if names else ".")]


async def who(db, admin, admin_name, args, world) -> list[str]:
    from .systems.cultivation import realm_name
    target, ch = await find_user(db, " ".join(args))
    now = clock.now()
    lines = [f"{_label(target, ch)} — id {target.id}" + (" — QUẢN TRỊ" if target.is_admin else "")]
    if ch:
        lines.append(f"  Cảnh giới: {realm_name(ch.realm)} tầng {ch.realm_stage}, đang ở {ch.zone_id}")
    lines.append(f"  Tạo lúc {fmt_vn(target.created_at)}"
                 + (f", đăng nhập gần nhất {fmt_vn(target.last_login_at)}" if target.last_login_at else ""))
    lines.append(f"  Linh Thạch {target.spirit_stones}, Tiên Ngọc {target.immortal_jade}")
    if target.banned_until and target.banned_until > now:
        lines.append(f"  Bị khóa đến {fmt_vn(target.banned_until)}")
    if target.chat_banned_until and target.chat_banned_until > now:
        lines.append(f"  Bị cấm chat đến {fmt_vn(target.chat_banned_until)}")
    if target.suspicious_flag:
        lines.append(f"  Nghi dùng bot: {target.suspicious_flag}")
    reports = (await db.execute(select(func.count()).select_from(ChatReport).where(
        ChatReport.reported_id == target.id))).scalar_one()
    if reports:
        lines.append(f"  Bị báo cáo {reports} lần")
    if world is not None:
        lines.append("  Đang online" if target.id in world.sessions else "  Ngoại tuyến")
    return lines


async def flagged(db, admin, admin_name, args, world) -> list[str]:
    rows = (await db.execute(select(User).where(User.suspicious_flag.is_not(None))
                             .order_by(User.id.desc()).limit(15))).scalars().all()
    if not rows:
        return ["Không có tài khoản nào bị đánh dấu."]
    out = [f"{len(rows)} tài khoản bị đánh dấu (mới nhất trước):"]
    for u in rows:
        ch = await db.get(Character, u.id)
        out.append(f"  {_label(u, ch)}: {u.suspicious_flag}")
    return out


async def unflag(db, admin, admin_name, args, world) -> list[str]:
    target, ch = await find_user(db, " ".join(args))
    target.suspicious_flag = None
    target.flags = {**(target.flags or {}), "fast_streak": 0}
    await log_action(db, admin_name, "unflag", target)
    await db.commit()
    return [f"Đã bỏ đánh dấu {_label(target, ch)}."]


async def reports(db, admin, admin_name, args, world) -> list[str]:
    rows = (await db.execute(select(ChatReport).order_by(ChatReport.id.desc()).limit(10))).scalars().all()
    if not rows:
        return ["Chưa có báo cáo nào."]
    out = ["10 báo cáo gần nhất:"]
    for r in rows:
        a = await db.get(Character, r.reporter_id)
        b = await db.get(Character, r.reported_id)
        who_a = a.display_name if a else f"#{r.reporter_id}"
        who_b = b.display_name if b else f"#{r.reported_id}"
        out.append(f"  {fmt_vn(r.created_at)} {who_a} → {who_b}: \"{r.message[:60]}\""
                   + (f" ({r.reason})" if r.reason else ""))
    return out


async def action_log(db, admin, admin_name, args, world) -> list[str]:
    rows = (await db.execute(select(AdminAction).order_by(AdminAction.id.desc()).limit(10))).scalars().all()
    if not rows:
        return ["Chưa có lệnh quản trị nào."]
    return ["10 lệnh quản trị gần nhất:"] + [
        f"  {fmt_vn(r.created_at)} {r.admin_name}: {r.action}"
        + (f" @{r.target_name}" if r.target_name else "") + (f" — {r.detail[:60]}" if r.detail else "")
        for r in rows]


async def timescale(db, admin, admin_name, args, world) -> list[str]:
    if settings.env != "dev":
        raise AdminError("TIME_SCALE chỉ đổi được trên máy chủ dev (ENV=dev).")
    if not args:
        return [f"TIME_SCALE hiện tại: {settings.time_scale:g}"]
    try:
        value = float(args[0].replace(",", "."))
    except ValueError:
        raise AdminError("TIME_SCALE phải là một số, ví dụ 1440.") from None
    if not 0 < value <= 100000:
        raise AdminError("TIME_SCALE phải lớn hơn 0 và không quá 100000.")
    settings.time_scale = value
    await log_action(db, admin_name, "timescale", detail=f"{value:g}")
    await db.commit()
    return [f"Đã đặt TIME_SCALE = {value:g} (mất khi khởi động lại máy chủ)."]


async def show_help(db, admin, admin_name, args, world) -> list[str]:
    return list(HELP)


COMMANDS = {"mute": mute, "unmute": unmute, "ban": ban, "unban": unban, "kick": kick,
            "announce": announce, "maintenance": maintenance, "online": online, "who": who,
            "flagged": flagged, "unflag": unflag, "reports": reports, "log": action_log,
            "timescale": timescale, "help": show_help}


async def run(db: AsyncSession, admin: User | None, admin_name: str, text: str,
              world: "World | None" = None) -> tuple[bool, list[str]]:
    """`text` is everything after '/admin'. Returns (ok, reply lines)."""
    parts = text.split()
    if not parts:
        return True, list(HELP)
    cmd = parts[0].lower().replace("đ", "d")
    cmd = ALIASES.get(cmd, cmd)
    fn = COMMANDS.get(cmd)
    if fn is None:
        return False, [f"Không có lệnh '{parts[0]}'. Gõ /admin help để xem danh sách."]
    try:
        return True, await fn(db, admin, admin_name, parts[1:], world)
    except AdminError as e:
        await db.rollback()
        return False, [str(e)]


def is_admin_command(text: str) -> bool:
    t = text.lstrip().lower()
    return t == "/admin" or t.startswith("/admin ")


async def handle_chat(world: "World", s: "Session", text: str) -> None:
    """A `/admin ...` line typed in chat. The admin flag is read from the database, not the
    session, so a revoked admin cannot keep using an old connection."""
    rest = text.lstrip()[len("/admin"):]
    async with dbm.SessionLocal() as db:
        user = await db.get(User, s.user_id)
        if user is None or not user.is_admin:
            s.send({"t": "admin", "ok": False, "lines": ["Bạn không có quyền dùng lệnh quản trị."]})
            return
        ok, lines = await run(db, user, user.username, rest, world)
    s.send({"t": "admin", "ok": ok, "lines": lines})


async def sync_admin_usernames() -> int:
    """ADMIN_USERNAMES: give those existing accounts is_admin (never takes it away)."""
    if not settings.admin_usernames:
        return 0
    n = 0
    async with dbm.SessionLocal() as db:
        rows = (await db.execute(select(User).where(func.lower(User.username).in_(settings.admin_usernames)
                                                    ))).scalars().all()
        for u in rows:
            if not u.is_admin:
                u.is_admin = True
                await log_action(db, "ADMIN_USERNAMES", "grant", u)
                n += 1
        await db.commit()
    return n
