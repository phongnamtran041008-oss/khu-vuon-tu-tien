"""LAN worlds (Minecraft style): worlds saved on this PC, Firebase accounts, finding and
joining worlds on the LAN. Firebase is replaced by a tiny stand-in of its Auth Emulator."""
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from client import worlds as W
from client.config import Config, Session
from client.net import lan
from client.net.firebase import FirebaseAuth, message_vi
from client.net.rest import ApiError

HOST_UID = "UIDhost000000000000000000001"
TOKENS = {"tok-host": {"localId": HOST_UID, "email": "chu.vuon@gmail.com"}}


@pytest.fixture
def world_home(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "data_dir", lambda: tmp_path)
    return tmp_path


def test_worlds_create_list_and_names(world_home):
    a = W.create("Vườn Nhà Phong")
    b = W.create("Vườn nhà phong")
    assert (a.slug, b.slug) == ("vuon-nha-phong", "vuon-nha-phong-2")
    assert (world_home / "worlds" / a.slug / "world.json").exists() and len(a.secret) == 64
    time.sleep(0.01)
    a.touch()
    assert [w.slug for w in W.list_worlds()] == [a.slug, b.slug]   # last played first
    (world_home / "worlds" / "hong").mkdir()                         # a broken folder is skipped
    assert len(W.list_worlds()) == 2
    assert W.create("   ").name == "Khu Vườn"


class FakeApi:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def post(self, url, body, ok, err, **kw):
        self.calls.append((url.split("?")[0].rsplit("/", 1)[-1], body))
        a = self.answers.pop(0)
        (err if isinstance(a, ApiError) else ok)(a)


def test_firebase_sign_in_refresh_and_expiry(tmp_path):
    session = Session(tmp_path / "s.json")
    api = FakeApi([{"localId": "U1", "email": "a@b.vn", "idToken": "id1", "refreshToken": "r1", "expiresIn": "3600"}])
    fb = FirebaseAuth(api, session, "KEY")
    got = []
    fb.sign_in("a@b.vn", "matkhau1", got.append, got.append)
    assert fb.signed_in and fb.uid == "U1" and fb.email == "a@b.vn"
    assert json.loads((tmp_path / "s.json").read_text("utf-8"))["firebase"]["refresh_token"] == "r1"
    fb.id_token(got.append, got.append)
    assert got[-1] == "id1" and len(api.calls) == 1                 # still fresh: no network
    session.data["firebase"]["expires_at"] = time.time() + 60        # about to expire: refresh
    api.answers.append({"id_token": "id2", "refresh_token": "r2", "expires_in": "3600", "user_id": "U1"})
    fb.id_token(got.append, got.append)
    assert got[-1] == "id2" and api.calls[-1][0] == "token" and fb.data["refresh_token"] == "r2"
    session.data["firebase"]["expires_at"] = 0
    api.answers.append(ApiError(400, "TOKEN_EXPIRED", ""))
    fb.id_token(got.append, got.append)
    assert "hết hạn" in got[-1] and not fb.signed_in                  # must sign in again


def test_firebase_messages_in_vietnamese():
    assert "đã có tài khoản" in message_vi(ApiError(400, "EMAIL_EXISTS", ""))
    assert "Authentication" in message_vi(ApiError(400, "CONFIGURATION_NOT_FOUND", ""))
    assert "Internet" in message_vi(ApiError(0, "network", "x"))
    assert "API key" in message_vi(ApiError(400, "API", ""))
    assert message_vi(ApiError(400, "LA_LAM", "Lỗi riêng")) == "Lỗi riêng"


def test_lan_scanner_hears_announcements():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    sc = lan.LanScanner(port)
    try:
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packet = json.dumps({"g": lan.MAGIC, "v": 5, "name": "Vườn A", "host": "phong", "port": 8001,
                             "online": 2}).encode()
        for _ in range(20):
            tx.sendto(packet, ("127.0.0.1", port))
            tx.sendto(b"rac", ("127.0.0.1", port))
            if sc.servers():
                break
            time.sleep(0.1)
        tx.close()
        (found,) = sc.servers()
        assert (found["name"], found["host"], found["port"], found["online"], found["ip"]) == \
            ("Vườn A", "phong", 8001, 2, "127.0.0.1")
    finally:
        sc.close()


# ---------------------------------------------------------------- end to end
class Emulator(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        user = TOKENS.get(body.get("idToken"))
        if self.path.split("?")[0].endswith("accounts:lookup") and user:
            code, out = 200, {"users": [user]}
        else:
            code, out = 400, {"error": {"code": 400, "message": "INVALID_ID_TOKEN"}}
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_open_world_find_it_on_lan_and_join(world_home, tmp_path, monkeypatch):
    from client.host import free_port
    from client.main import Game
    from client.scenes.play import PlayScene

    emu = ThreadingHTTPServer(("127.0.0.1", 0), Emulator)
    threading.Thread(target=emu.serve_forever, daemon=True).start()
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", f"127.0.0.1:{emu.server_address[1]}")
    session = Session(tmp_path / "session.json")
    session.save(firebase={"uid": HOST_UID, "email": "chu.vuon@gmail.com", "id_token": "tok-host",
                           "refresh_token": "r", "expires_at": time.time() + 3600})
    game = Game(Config(firebase_api_key="test-key", host_port=free_port(18600)), session)
    scanner = lan.LanScanner()
    try:
        world = W.create("Vườn Thử LAN")
        scene = game.push(PlayScene(game))
        scene.selected = world.slug
        scene.open_world()
        end = time.time() + 150
        while time.time() < end and type(game.top).__name__ != "CreateCharScene":
            game.step(0.05, events=[])
            time.sleep(0.02)
            if not scene.busy and scene.status_err:
                pytest.fail(scene.status + "\n" + game.host.log_tail(20))
        assert type(game.top).__name__ == "CreateCharScene", (scene.status, game.host.log_tail(20))
        assert game.api.base_url == game.host.url and game.state.me["is_admin"]   # the owner is admin
        assert world.db_path.exists()
        heard = []
        for _ in range(40):
            heard = [s for s in scanner.servers() if s["port"] == game.host.port]
            if heard:
                break
            time.sleep(0.1)
        assert heard and heard[0]["name"] == "Vườn Thử LAN" and heard[0]["host"] == "chu.vuon"
        proc = game.host.proc
        game.stop_host()
        assert proc.returncode == 0                                   # stopped cleanly (world saved)
        assert "world" in (world.path / "server.log").read_text("utf-8")
    finally:
        scanner.close()
        game.stop_host()
        game.api.close()
        emu.shutdown()


def test_menu_routes_lan_mode_and_screens_draw(world_home, tmp_path):
    from client.main import Game
    from client.scenes.menu import MenuScene
    W.create("Vườn Một")
    game = Game(Config(firebase_api_key="test-key"), Session(tmp_path / "s.json"))
    try:
        menu = game.push(MenuScene(game))
        menu.start()
        assert type(game.top).__name__ == "AccountScene"               # not signed in yet
        acc = game.top
        for tab in ("login", "register", "reset"):
            acc.tab = tab
            game.step(0.05, events=[])
        acc.tab = "login"
        acc.submit()
        assert acc.status_err and "email" in acc.status                 # nothing typed
        game.session.save(firebase={"uid": "U", "email": "a@b.vn", "id_token": "t", "refresh_token": "r",
                                    "expires_at": time.time() + 3600})
        game.replace_all(MenuScene(game))
        game.top.start()
        play = game.top
        assert type(play).__name__ == "PlayScene" and play.worlds[0].name == "Vườn Một"
        for tab in ("mine", "lan", "mine"):
            play.tab = tab
            game.step(0.05, events=[])
        play.sign_out()
        assert not game.firebase.signed_in and type(game.top).__name__ == "AccountScene"
    finally:
        game.api.close()


def test_lan_scanner_lists_a_two_card_pc_once():
    sc = lan.LanScanner.__new__(lan.LanScanner)
    sc._lock = threading.Lock()
    now = time.monotonic()
    base = {"v": 5, "name": "Vườn A", "host": "phong", "port": 8000, "online": 1}
    sc._found = {(ip, 8000): {**base, "ip": ip, "seen": now - age}
                 for ip, age in (("192.168.1.6", 0.1), ("192.168.1.5", 0.5), ("127.0.0.1", 0))}
    sc._found[("192.168.1.9", 8000)] = {**base, "host": "lan", "ip": "192.168.1.9", "seen": now}
    rows = sc.servers()
    assert [(r["host"], r["ip"]) for r in rows] == [("phong", "192.168.1.5"), ("lan", "192.168.1.9")]
