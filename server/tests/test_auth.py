from sqlalchemy import select

from app.models import User
from tests.helpers import register


async def test_register_login_and_validation(client):
    h, data = await register(client, "Tu_Si_01", "matkhau1")
    assert data["recovery_code"].count("-") == 2
    r = await client.post("/auth/register", json={"username": "tu_si_01", "password": "matkhau1"})
    assert r.status_code == 409  # usernames are case-insensitive
    for bad in [("ab", "matkhau1"), ("ten co dau", "matkhau1"), ("x" * 21, "matkhau1"), ("okname", "12345")]:
        r = await client.post("/auth/register", json={"username": bad[0], "password": bad[1]})
        assert r.status_code == 400, bad
        assert r.json()["error"]["message_vi"]
    r = await client.post("/auth/login", json={"username": "tu_si_01", "password": "wrong!!"})
    assert r.status_code == 401
    r = await client.post("/auth/login", json={"username": "tu_si_01", "password": "matkhau1"})
    assert r.status_code == 200
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Authorization": "Bearer junk"})).status_code == 401


async def test_password_hashed_and_recovery_code_not_stored(client, db):
    _, data = await register(client, "hasher", "matkhau1")
    u = (await db.execute(select(User))).scalar_one()
    assert "matkhau1" not in u.password_hash
    assert data["recovery_code"].replace("-", "") not in u.recovery_code_hash


async def test_reset_password_with_recovery_code(client):
    h, data = await register(client, "quenpass", "matkhau1")
    r = await client.post("/auth/reset_password", json={"username": "quenpass", "recovery_code": "AAAA-BBBB-CCCC",
                                                         "new_password": "moi12345"})
    assert r.status_code == 401
    r = await client.post("/auth/reset_password", json={"username": "quenpass",
                                                         "recovery_code": data["recovery_code"].lower(),
                                                         "new_password": "moi12345"})
    assert r.status_code == 200 and r.json()["recovery_code"] != data["recovery_code"]
    assert (await client.get("/me", headers=h)).status_code == 401  # old sessions logged out
    r = await client.post("/auth/login", json={"username": "quenpass", "password": "moi12345"})
    assert r.status_code == 200
    # the used code no longer works
    r = await client.post("/auth/reset_password", json={"username": "quenpass", "recovery_code": data["recovery_code"],
                                                         "new_password": "khac12345"})
    assert r.status_code == 401


async def test_logout_all_and_change_password(client):
    h, _ = await register(client, "doipass", "matkhau1")
    r = await client.post("/auth/change_password", json={"old_password": "sai", "new_password": "moi12345"}, headers=h)
    assert r.status_code == 401
    r = await client.post("/auth/change_password", json={"old_password": "matkhau1", "new_password": "moi12345"},
                          headers=h)
    h2 = {"Authorization": f"Bearer {r.json()['token']}"}
    assert (await client.get("/me", headers=h)).status_code == 401
    assert (await client.post("/auth/logout_all", headers=h2)).status_code == 200
    assert (await client.get("/me", headers=h2)).status_code == 401


async def test_ip_limit(client):
    for i in range(5):
        await register(client, f"clone{i}")
    r = await client.post("/auth/register", json={"username": "clone5", "password": "matkhau1"})
    assert r.status_code == 429


async def test_token_expires_after_30_days(client, frozen):
    h, _ = await register(client, "lauqua", "matkhau1")
    frozen.advance(days=29)
    assert (await client.get("/me", headers=h)).status_code == 200
    frozen.advance(days=2)
    assert (await client.get("/me", headers=h)).status_code == 401


async def test_write_rate_limit(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    h, _ = await register(client, "spammer", "matkhau1")
    codes = [(await client.post("/gacha/roll", json={"banner": "pets"}, headers=h)).status_code for _ in range(65)]
    assert 429 in codes and codes[0] == 400


async def test_server_info(client):
    info = (await client.get("/server/info")).json()
    assert info["protocol_version"] == 5 and info["name"] == "Khu Vườn Tu Tiên"
