"""LAN worlds: Firebase accounts and the LAN announcement (no real Firebase: `lookup` is faked)."""
import socket

import pytest
from sqlalchemy import select

from app import firebase_auth, lan
from app.config import settings
from app.models import Seed, User

ACCOUNTS = {
    "tok-host": {"uid": "UIDhost000000000000000000001", "email": "chu.vuon@gmail.com", "name": ""},
    "tok-ban": {"uid": "UIDban0000000000000000000002", "email": "ban.be@gmail.com", "name": ""},
    "tok-ban2": {"uid": "UIDban0000000000000000000003", "email": "ban.be@yahoo.com", "name": ""},
    "tok-x": {"uid": "UIDxx000000000000000000000004", "email": "", "name": ""},
}


@pytest.fixture
def firebase(monkeypatch):
    async def fake_lookup(token):
        if token == "tok-down":
            raise firebase_auth.FirebaseError("network")
        if token not in ACCOUNTS:
            raise firebase_auth.FirebaseError("INVALID_ID_TOKEN")
        return ACCOUNTS[token]
    monkeypatch.setattr(firebase_auth, "lookup", fake_lookup)
    monkeypatch.setattr(settings, "firebase_api_key", "AIza-test")
    monkeypatch.setattr(settings, "host_firebase_uid", ACCOUNTS["tok-host"]["uid"])


async def fb_login(client, token):
    return await client.post("/auth/firebase", json={"id_token": token})


async def test_first_visit_creates_account_then_finds_it(client, db, firebase):
    r = await fb_login(client, "tok-ban")
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["created"] and first["username"] == "ban_be" and not first["is_admin"]
    me = (await client.get("/me", headers={"Authorization": f"Bearer {first['token']}"})).json()
    assert me["username"] == "ban_be" and me["has_character"] is False
    again = (await fb_login(client, "tok-ban")).json()
    assert not again["created"] and again["user_id"] == first["user_id"]
    user = await db.get(User, first["user_id"])
    assert user.firebase_uid == ACCOUNTS["tok-ban"]["uid"] and user.email == "ban.be@gmail.com"
    seeds = (await db.execute(select(Seed).where(Seed.user_id == user.id))).scalars().all()
    assert len(seeds) == 1                                   # the starter 水, once
    # same e-mail name on another provider: a different account, a free username
    other = (await fb_login(client, "tok-ban2")).json()
    assert other["username"] == "ban_be2" and other["user_id"] != first["user_id"]
    assert (await fb_login(client, "tok-x")).json()["username"].startswith("dh_")


async def test_world_owner_is_admin(client, db, firebase):
    r = (await fb_login(client, "tok-host")).json()
    assert r["is_admin"] and r["username"] == "chu_vuon"


async def test_game_author_is_admin_in_every_world(client, firebase, monkeypatch):
    from app.config import OWNER_EMAILS
    ACCOUNTS_OWNER = {"uid": "UIDowner00000000000000000005", "email": OWNER_EMAILS[0].upper(), "name": ""}
    monkeypatch.setitem(ACCOUNTS, "tok-owner", ACCOUNTS_OWNER)
    assert (await fb_login(client, "tok-owner")).json()["is_admin"]          # not the host, still admin
    assert not (await fb_login(client, "tok-ban")).json()["is_admin"]
    monkeypatch.setattr(settings, "admin_emails", [*settings.admin_emails, "ban.be@yahoo.com"])
    assert (await fb_login(client, "tok-ban2")).json()["is_admin"]           # ADMIN_EMAILS


async def test_firebase_accounts_cannot_use_a_password(client, firebase):
    r = (await fb_login(client, "tok-ban")).json()
    for pw in ("!firebase", "", "matkhau1"):
        res = await client.post("/auth/login", json={"username": r["username"], "password": pw or "x"})
        assert res.status_code in (401, 422)


async def test_bad_tokens_and_firebase_down(client, firebase):
    r = await fb_login(client, "gia-mao")
    assert r.status_code == 401 and r.json()["error"]["code"] == "firebase_invalid_id_token"
    r = await fb_login(client, "tok-down")
    assert r.status_code == 503 and "Internet" in r.json()["error"]["message_vi"]


async def test_off_without_key_and_local_accounts_switch(client, monkeypatch):
    monkeypatch.setattr(settings, "firebase_api_key", "")
    assert (await fb_login(client, "tok-ban")).json()["error"]["code"] == "firebase_off"
    monkeypatch.setattr(settings, "local_accounts", False)
    r = await client.post("/auth/register", json={"username": "cuc_bo", "password": "matkhau1"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "local_off"
    assert (await client.post("/auth/login", json={"username": "cuc_bo", "password": "matkhau1"})).status_code == 403
    info = (await client.get("/server/info")).json()
    assert info["auth"] == "local" and info["local_accounts"] is False


async def test_banned_firebase_account(client, db, firebase):
    import datetime as dt
    from app import clock
    r = (await fb_login(client, "tok-ban")).json()
    u = await db.get(User, r["user_id"])
    u.banned_until = clock.now() + dt.timedelta(days=1)
    await db.commit()
    assert (await fb_login(client, "tok-ban")).status_code == 403


def test_beacon_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "lan_world_name", "Vườn Nhà Phong")
    monkeypatch.setattr(settings, "lan_host_name", "Phong")
    monkeypatch.setattr(settings, "lan_port", 8001)
    m = lan.parse(lan.beacon(3))
    assert m == {"v": 5, "name": "Vườn Nhà Phong", "host": "Phong", "port": 8001, "online": 3}
    for junk in (b"", b"xin chao", b'{"g": "khac", "port": 1}', b'[1,2]', b"\xff\xfe"):
        assert lan.parse(junk) is None


async def test_beacon_reaches_a_listener(monkeypatch):
    import asyncio
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        rx.bind(("", lan.PORT))
    except OSError:
        pytest.skip("LAN port busy")
    rx.settimeout(5)
    monkeypatch.setattr(lan, "INTERVAL", 0.2)
    task = asyncio.create_task(lan.run())
    try:
        data = await asyncio.to_thread(rx.recv, 2048)
    finally:
        task.cancel()
        rx.close()
    assert lan.parse(data)["port"] == settings.lan_port


async def test_beacon_leaves_through_every_network_card(monkeypatch):
    """Windows sends an unbound 255.255.255.255 broadcast out of the lowest-metric card only
    (often WSL/Hyper-V), so the beacon binds one socket per address of this PC."""
    import asyncio
    sent = []

    class FakeSock:
        def __init__(self, bound):
            self.bound = bound

        def sendto(self, data, addr):
            sent.append((self.bound, addr[0]))

        def close(self):
            pass

    monkeypatch.setattr(lan, "local_ipv4", lambda: ["192.168.1.5", "192.168.1.6", "172.31.48.1"])
    monkeypatch.setattr(lan, "_udp", lambda bind_ip=None: FakeSock(bind_ip))
    task = asyncio.create_task(lan.run())
    await asyncio.sleep(0.05)
    task.cancel()
    assert {b for b, a in sent if a == "255.255.255.255"} == {"192.168.1.5", "192.168.1.6", "172.31.48.1"}
    assert (None, "127.0.0.1") in sent


def test_local_ipv4_skips_loopback_and_link_local(monkeypatch):
    monkeypatch.setattr(lan.socket, "gethostbyname_ex",
                        lambda h: (h, [], ["127.0.0.1", "169.254.1.2", "192.168.1.5", "192.168.1.5"]))
    ips = lan.local_ipv4()
    assert "192.168.1.5" in ips and ips.count("192.168.1.5") == 1
    assert not any(ip.startswith(("127.", "169.254.")) for ip in ips)
