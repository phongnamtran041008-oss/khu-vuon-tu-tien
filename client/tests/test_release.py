"""Stage 10: server_list_url, version check, admin replies and the packaged-exe paths (no server)."""
import json
import sys

import pytest

from client import config as C
from client.config import GAME_VERSION, Config, Session, normalize_url, version_tuple


@pytest.fixture
def game(tmp_path):
    from client.main import Game
    g = Game(Config(server_url="http://127.0.0.1:9"), Session(tmp_path / "session.json"))
    yield g
    g.api.close()


def answer_get(game, monkeypatch, routes: dict):
    """Make Api.get answer at once from `routes` instead of going to the network."""
    calls = []

    def fake_get(path, on_ok=None, on_err=None, **kw):
        calls.append(path)
        if path in routes and on_ok:
            on_ok(routes[path])
    monkeypatch.setattr(game.api, "get", fake_get)
    return calls


def test_normalize_url():
    assert normalize_url("abc.trycloudflare.com") == "http://abc.trycloudflare.com"
    assert normalize_url(" https://vuon.duckdns.org/server/info ") == "https://vuon.duckdns.org"
    assert normalize_url("http://192.168.1.5:8000/") == "http://192.168.1.5:8000"
    assert normalize_url("https://x.onrender.com/docs") == "https://x.onrender.com"
    assert normalize_url("") == ""


def test_version_tuple():
    assert version_tuple("1.0.0") < version_tuple("1.0.1") < version_tuple("v1.2") < version_tuple("10.0")
    assert version_tuple("1.0.0-beta") == (1, 0, 0)


def test_server_list_replaces_a_stale_address(game, monkeypatch):
    game.cfg.server_list_url = "https://raw.example/server_list.json"
    game.api.set_base_url("https://old-tunnel.trycloudflare.com")
    calls = answer_get(game, monkeypatch, {
        "https://raw.example/server_list.json": {"servers": [{"name": "Chính", "url": "https://new.trycloudflare.com/"},
                                                             {"name": "Dự phòng", "url": "http://1.2.3.4:8000"}]},
        "/server/info": {"protocol_version": C.PROTOCOL_VERSION}})
    game._fetch_server_list()
    assert game.api.base_url == "https://new.trycloudflare.com"
    assert game.session.data["server_url"] == "https://new.trycloudflare.com"
    assert calls[-1] == "/server/info"                # the new server's version is checked


def test_server_list_keeps_a_listed_or_typed_address(game, monkeypatch):
    game.cfg.server_list_url = "https://raw.example/list.json"
    answer_get(game, monkeypatch, {"https://raw.example/list.json": ["http://a:8000", "http://b:8000"]})
    game.api.set_base_url("http://b:8000")
    game._fetch_server_list()
    assert game.api.base_url == "http://b:8000"       # still on the list: keep it
    game.api.set_base_url("http://my-own:8000")
    game.session.save(server_manual=True)             # typed in Cài đặt
    game._fetch_server_list()
    assert game.api.base_url == "http://my-own:8000"
    game.session.save(server_manual=False)
    game._fetch_server_list()
    assert game.api.base_url == "http://a:8000"


def test_version_check_notices_and_update_link(game, monkeypatch):
    answer_get(game, monkeypatch, {"/server/info": {
        "protocol_version": C.PROTOCOL_VERSION, "latest_client_version": "99.0.0",
        "client_download_url": "https://github.com/x/y/releases/latest", "maintenance_message": "Bảo trì 23:00"}})
    game.check_version()
    assert game.version_ok and game.newer_client() == "99.0.0"
    assert game.server_info["maintenance_message"] == "Bảo trì 23:00"
    answer_get(game, monkeypatch, {"/server/info": {"protocol_version": C.PROTOCOL_VERSION + 1,
                                                    "latest_client_version": GAME_VERSION,
                                                    "client_download_url": "https://dl.example/VuonChu.zip"}})
    game.check_version()
    assert not game.version_ok and game.newer_client() is None
    box = game.scenes[-1]
    assert "https://dl.example/VuonChu.zip" in box.text


def test_admin_replies_and_announcements_reach_the_chat(game):
    game._on_net({"t": "admin", "ok": True, "lines": ["Đã khóa Bình (@binh) đến 01/11/2026 08:00 (giờ VN).", "x"]})
    texts = [e["text"] for e in game.chat.items if e["ch"] == "system"]
    assert texts[-2:] == ["Đã khóa Bình (@binh) đến 01/11/2026 08:00 (giờ VN).", "x"]
    game._on_net({"t": "notice", "text": "Tối nay mở bí cảnh", "kind": "announce"})
    assert game.server_info["announcement"] == "Tối nay mở bí cảnh"
    assert game.toasts[-1].life > 5


def test_config_paths_when_packaged(tmp_path, monkeypatch):
    exe_dir = tmp_path / "VuonChu"
    exe_dir.mkdir()
    (exe_dir / "config.json").write_text(json.dumps({"server_url": "https://vuon.duckdns.org",
                                                     "server_list_url": "https://raw.example/l.json"}), "utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "VuonChu.exe"))
    assert C.data_dir() == exe_dir                       # writable: everything stays next to the exe
    cfg = Config.load()
    assert cfg.server_url == "https://vuon.duckdns.org" and cfg.path == exe_dir / "config.json"
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setattr(C, "_writable", lambda d: d != exe_dir)   # e.g. unpacked into Program Files
    assert C.data_dir() == appdata / "KhuVuonTuTien"
    cfg = Config.load()                                  # still reads the shipped config ...
    assert cfg.server_list_url == "https://raw.example/l.json"
    cfg.window_scale = 3
    cfg.save()                                           # ... but saves where it can write
    assert json.loads((appdata / "KhuVuonTuTien" / "config.json").read_text("utf-8"))["window_scale"] == 3
    assert Config.load().window_scale == 3
    assert Session().path == appdata / "KhuVuonTuTien" / "session.json"
