"""Stage 10: admin commands (spec 17), /server/info, /healthz and the bot watch."""
import asyncio
import datetime as dt

import pytest
from sqlalchemy import select

from app import admin, admin_cli, clock, server_state
from app.config import GAME_VERSION, PROTOCOL_VERSION, settings
from app.learning import quiz
from app.models import AdminAction, ChatReport, User
from app.realtime import protocol
from app.realtime.world import Session, World
from tests.helpers import answer_key, correct_answer, register
from tests.test_social import player


@pytest.fixture(autouse=True)
def fresh_state():
    server_state.reset()
    yield
    server_state.reset()


def live(w: World, uid: int, name: str) -> Session:
    s = Session(uid, f"user{uid}", name, "pham_nhan", {})
    s.sent = []
    w.sessions[uid] = s
    return s


async def make_admin(db, uid: int) -> None:
    u = await db.get(User, uid)
    u.is_admin = True
    await db.commit()


async def say(w: World, s: Session, text: str) -> dict:
    """Type a line in chat and wait for the admin reply."""
    w.chat.handle(s, protocol.Chat(t="chat", ch="world", text=text))
    await asyncio.gather(*list(w._bg))
    replies = [m for m in s.sent if m.get("t") == "admin"]
    return replies[-1]


def test_parse_duration():
    assert admin.parse_duration("30m") == dt.timedelta(minutes=30)
    assert admin.parse_duration("45") == dt.timedelta(minutes=45)
    assert admin.parse_duration("2h") == admin.parse_duration("2gio") == dt.timedelta(hours=2)
    assert admin.parse_duration("7d") == admin.parse_duration("7ngay") == dt.timedelta(days=7)
    assert admin.parse_duration("1w") == dt.timedelta(weeks=1)
    assert admin.parse_duration("vinhvien") == admin.PERMANENT
    for bad in ("", "abc", "0h", "-3d", "2x", "Trúc"):
        assert admin.parse_duration(bad) is None


async def test_non_admin_cannot_use_and_nothing_is_broadcast(client, db):
    _, a = await player(client, db, "an_01", "An")
    _, b = await player(client, db, "binh_01", "Bình")
    w = World()
    sa, sb = live(w, a, "An"), live(w, b, "Bình")
    reply = await say(w, sa, "/admin ban Bình 1d")
    assert reply["ok"] is False and "quyền" in reply["lines"][0]
    assert not [m for m in sb.sent if m.get("t") == "chat"]          # the line went nowhere
    assert (await db.get(User, b)).banned_until is None


async def test_mute_name_with_spaces_and_chat_is_blocked(client, db):
    _, a = await player(client, db, "quan_tri", "Vân Sơn")
    _, b = await player(client, db, "tieu_truc", "Tiểu Trúc")
    await make_admin(db, a)
    w = World()
    sa, sb = live(w, a, "Vân Sơn"), live(w, b, "Tiểu Trúc")
    reply = await say(w, sa, "/admin camchat tiểu trúc 2h nói tục")
    assert reply["ok"], reply
    await db.refresh(u := await db.get(User, b))
    assert u.chat_banned_until == clock.now() + dt.timedelta(hours=2)
    assert sb.chat_banned_until == u.chat_banned_until
    assert any(m.get("t") == "notice" and "nói tục" in m["text"] for m in sb.sent)
    w.chat.handle(sb, protocol.Chat(t="chat", ch="world", text="xin chào"))
    assert sb.sent[-1]["code"] == "chat_banned"
    reply = await say(w, sa, "/admin unmute @tieu_truc")
    assert reply["ok"] and sb.chat_banned_until is None
    log = (await db.execute(select(AdminAction.action).order_by(AdminAction.id))).scalars().all()
    assert log == ["mute", "unmute"]


async def test_ban_kicks_blocks_login_then_unban(client, db):
    _, a = await player(client, db, "quan_tri", "Vân Sơn")
    _, b = await player(client, db, "binh_01", "Bình")
    await make_admin(db, a)
    w = World()
    sa, sb = live(w, a, "Vân Sơn"), live(w, b, "Bình")
    reply = await say(w, sa, "/admin ban Bình 3d spam")
    assert reply["ok"] and "Bình" in reply["lines"][0]
    assert sb.closed and sb.close_code == 4010
    assert sb.sent[-1]["t"] == "kicked" and sb.sent[-1]["reason"] == "banned"
    r = await client.post("/auth/login", json={"username": "binh_01", "password": "secret123"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "banned"
    clock_now = clock.now()
    assert (await db.get(User, b)).banned_until == clock_now + dt.timedelta(days=3)
    reply = await say(w, sa, "/admin unban Bình")
    assert reply["ok"]
    r = await client.post("/auth/login", json={"username": "binh_01", "password": "secret123"})
    assert r.status_code == 200


async def test_guards_and_errors(client, db):
    _, a = await player(client, db, "quan_tri", "Vân Sơn")
    _, b = await player(client, db, "pho_tri", "Thanh Hà")
    await make_admin(db, a)
    await make_admin(db, b)
    w = World()
    sa = live(w, a, "Vân Sơn")
    assert "chính mình" in (await say(w, sa, "/admin ban Vân Sơn 1d"))["lines"][0]
    assert "quản trị viên khác" in (await say(w, sa, "/admin mute Thanh Hà 1h"))["lines"][0]
    assert "thời hạn" in (await say(w, sa, "/admin ban Thanh Hà"))["lines"][0]
    assert "Không tìm thấy" in (await say(w, sa, "/admin unban Không Ai"))["lines"][0]
    assert (await say(w, sa, "/admin lamgido"))["ok"] is False
    assert (await say(w, sa, "/admin"))["lines"][0].startswith("Lệnh quản trị")
    assert (await db.get(User, b)).chat_banned_until is None


async def test_announce_and_maintenance_show_in_server_info(client, db):
    _, a = await player(client, db, "quan_tri", "Vân Sơn")
    _, b = await player(client, db, "binh_01", "Bình")
    await make_admin(db, a)
    w = World()
    sa, sb = live(w, a, "Vân Sơn"), live(w, b, "Bình")
    reply = await say(w, sa, "/admin thongbao Tối nay 21:00 mở Mặc Ảnh Động!")
    assert "2 người" in reply["lines"][0]
    assert sb.sent[-1] == {"t": "notice", "text": "Tối nay 21:00 mở Mặc Ảnh Động!", "kind": "announce"}
    await say(w, sa, "/admin baotri Bảo trì lúc 23:00, khoảng 10 phút")
    info = (await client.get("/server/info")).json()
    assert info["announcement"] == "Tối nay 21:00 mở Mặc Ảnh Động!"
    assert info["maintenance_message"] == "Bảo trì lúc 23:00, khoảng 10 phút"
    await say(w, sa, "/admin announce off")
    await say(w, sa, "/admin maintenance off")
    info = (await client.get("/server/info")).json()
    assert info["announcement"] is None and info["maintenance_message"] is None


async def test_who_flagged_reports_log_online(client, db):
    _, a = await player(client, db, "quan_tri", "Vân Sơn")
    hb, b = await player(client, db, "binh_01", "Bình")
    await make_admin(db, a)
    u = await db.get(User, b)
    u.suspicious_flag = "200 câu đúng liền"
    db.add(ChatReport(reporter_id=a, reported_id=b, message="lời khó nghe", reason="tục", created_at=clock.now()))
    await db.commit()
    w = World()
    sa = live(w, a, "Vân Sơn")
    lines = (await say(w, sa, "/admin who Bình"))["lines"]
    assert "@binh_01" in lines[0] and any("Nghi dùng bot" in x for x in lines)
    assert any("báo cáo 1 lần" in x for x in lines) and lines[-1].strip() == "Ngoại tuyến"
    assert "Bình (@binh_01)" in "\n".join((await say(w, sa, "/admin flagged"))["lines"])
    assert "lời khó nghe" in "\n".join((await say(w, sa, "/admin reports"))["lines"])
    assert (await say(w, sa, "/admin online"))["lines"][0].startswith("1 người online")
    await say(w, sa, "/admin unflag Bình")
    await db.refresh(u)
    assert u.suspicious_flag is None
    assert "unflag @binh_01" in "\n".join((await say(w, sa, "/admin log"))["lines"])


async def test_timescale_only_on_dev(client, db, monkeypatch):
    _, a = await player(client, db, "quan_tri", "Vân Sơn")
    await make_admin(db, a)
    w = World()
    sa = live(w, a, "Vân Sơn")
    monkeypatch.setattr(settings, "time_scale", 1.0)
    assert (await say(w, sa, "/admin tocdo 1440"))["ok"]
    assert settings.time_scale == 1440
    assert (await client.get("/server/info")).json()["time_scale"] == 1440
    assert not (await say(w, sa, "/admin timescale 0"))["ok"]
    monkeypatch.setattr(settings, "env", "prod")
    reply = await say(w, sa, "/admin timescale 60")
    assert not reply["ok"] and "dev" in reply["lines"][0] and settings.time_scale == 1440


async def test_admin_usernames_and_cli(client, db, monkeypatch):
    monkeypatch.setattr(settings, "admin_usernames", ["chu_vuon"])
    await register(client, "chu_vuon")
    await register(client, "khach_01")
    users = {u.username: u for u in (await db.execute(select(User))).scalars()}
    assert users["chu_vuon"].is_admin and not users["khach_01"].is_admin
    assert await admin_cli.main(["grant", "khach_01"]) == 0
    assert await admin_cli.main(["grant", "khong_co"]) == 1
    await db.refresh(users["khach_01"])
    assert users["khach_01"].is_admin
    assert await admin_cli.main(["revoke", "khach_01"]) == 0
    assert await admin_cli.main(["ban", "@chu_vuon", "1d"]) == 0   # the console is nobody: no self/admin guard
    await db.refresh(users["chu_vuon"])
    assert users["chu_vuon"].banned_until is not None
    actions = (await db.execute(select(AdminAction.action, AdminAction.admin_name).order_by(AdminAction.id))).all()
    assert [tuple(x) for x in actions] == [("grant", "cli"), ("revoke", "cli"), ("ban", "cli")]


async def test_server_info_json_html_and_health(client):
    info = (await client.get("/server/info")).json()
    assert info["version"] == GAME_VERSION and info["protocol_version"] == PROTOCOL_VERSION
    assert {"online", "uptime_seconds", "latest_client_version", "client_download_url"} <= set(info)
    r = await client.get("/server/info", headers={"Accept": "text/html,application/xhtml+xml"})
    assert r.headers["content-type"].startswith("text/html") and "Máy chủ đang chạy" in r.text
    assert (await client.get("/server/info?format=json", headers={"Accept": "text/html"})).json()["version"]
    server_state.announcement = "<script>x</script>"
    assert "<script>x" not in (await client.get("/server/info?format=html")).text
    assert (await client.get("/healthz")).json() == {"ok": True}
    r = await client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/server/info"


def test_bot_watch_streak():
    w = quiz.balance.quiz()["bot_watch"]
    u = User(flags={}, suspicious_flag=None)
    for _ in range(w["streak"] - 1):
        quiz._watch_for_bots(u, True, 120)
    assert u.flags["fast_streak"] == w["streak"] - 1 and u.suspicious_flag is None
    quiz._watch_for_bots(u, True, w["fast_ms"] + 300)    # one human-speed answer resets it
    assert u.flags["fast_streak"] == 0
    for _ in range(w["streak"]):
        quiz._watch_for_bots(u, True, 80)
    assert u.suspicious_flag and str(w["streak"]) in u.suspicious_flag
    quiz._watch_for_bots(u, False, 80)
    assert u.flags["fast_streak"] == 0 and u.suspicious_flag     # the flag stays for the admin


async def test_bot_watch_through_the_api(client, db):
    from tests.test_practice import _learned
    h, data = await register(client)
    pid = await _learned(client, h)
    await client.post("/garden/learn", json={"plot_id": pid}, headers=h)
    for _ in range(3):   # the frozen test clock makes every answer take 0 ms
        q = (await client.post("/quiz/practice", json={"qtype": "Q2"}, headers=h)).json()
        key = await answer_key(q["session_id"])
        await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                "answer": correct_answer("Q2", key)}, headers=h)
    u = await db.get(User, data["user_id"])
    await db.refresh(u)
    assert u.flags["fast_streak"] == 3 and u.suspicious_flag is None
