"""Telling players about a newer release on GitHub (client/net/updates.py), with a fake GitHub API."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pygame
import pytest

from client.config import GAME_VERSION, Config, Session
from client.net import updates

REPO = "chu-vuon/khu-vuon-tu-tien"
RELEASE = {"tag_name": "v9.0.0", "html_url": f"https://github.com/{REPO}/releases/tag/v9.0.0",
           "draft": False, "prerelease": False, "body": "Sửa lỗi LAN.\n\nThêm cá mới.",
           "assets": [{"name": "VuonChu-9.0.0-windows.zip",
                       "browser_download_url": f"https://github.com/{REPO}/releases/download/v9.0.0/VuonChu.zip"}]}


def test_parse_release_newer_only():
    u = updates.parse_release(RELEASE, REPO, "1.1.1")
    assert u == {"version": "9.0.0", "url": RELEASE["assets"][0]["browser_download_url"],
                 "page": RELEASE["html_url"], "notes": "Sửa lỗi LAN. Thêm cá mới."}
    assert updates.parse_release({**RELEASE, "tag_name": "v1.1.1"}, REPO, "1.1.1") is None   # same version
    assert updates.parse_release({**RELEASE, "tag_name": "v1.0.9"}, REPO, "1.1.1") is None   # older
    assert updates.parse_release({**RELEASE, "tag_name": "1.10.0"}, REPO, "1.9.0")          # not string order
    assert updates.parse_release({**RELEASE, "draft": True}, REPO, "1.1.1") is None
    assert updates.parse_release({**RELEASE, "prerelease": True}, REPO, "1.1.1") is None
    assert updates.parse_release({"message": "Not Found"}, REPO, "1.1.1") is None
    no_zip = updates.parse_release({**RELEASE, "assets": []}, REPO, "1.1.1")
    assert no_zip["url"] == RELEASE["html_url"]                          # the release page instead
    assert len(updates.parse_release({**RELEASE, "body": "x " * 400}, REPO, "1.1.1")["notes"]) <= 163


class FakeGitHub(BaseHTTPRequestHandler):
    release = RELEASE
    seen: list = []

    def do_GET(self):
        FakeGitHub.seen.append((self.path, self.headers.get("User-Agent")))
        ok = self.path == f"/repos/{REPO}/releases/latest" and self.release
        data = json.dumps(self.release if ok else {"message": "Not Found"}).encode()
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def github(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(updates, "API", f"http://127.0.0.1:{srv.server_address[1]}/repos/{{repo}}/releases/latest")
    FakeGitHub.release, FakeGitHub.seen = RELEASE, []
    yield srv
    srv.shutdown()


def wait_done(chk):
    end = time.time() + 10
    while not chk.done and time.time() < end:
        time.sleep(0.02)
    assert chk.done


def test_checker_asks_github(github):
    chk = updates.UpdateChecker(REPO, "1.1.1", updates.API)
    wait_done(chk)
    assert chk.result["version"] == "9.0.0"
    assert FakeGitHub.seen[0][1].startswith("VuonChu/")      # GitHub refuses requests with no User-Agent


def test_checker_quiet_without_release_or_internet(github):
    FakeGitHub.release = None                                 # repo has no release yet: 404
    chk = updates.UpdateChecker(REPO, "1.1.1", updates.API)
    wait_done(chk)
    assert chk.result is None
    chk = updates.UpdateChecker(REPO, "1.1.1", "http://127.0.0.1:9/{repo}")   # nothing listens there
    wait_done(chk)
    assert chk.result is None


def _click(game, wid):
    pos = game.ui.widgets[wid].center
    pygame.mouse.set_pos(pos)
    for ev in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.step(0.02, [pygame.event.Event(ev, button=1, pos=pos)])
    game.step(0.02, [])


def test_title_screen_offers_the_update(github, tmp_path, monkeypatch):
    from client.main import Game
    from client.scenes.base import MessageBox
    from client.scenes.menu import MenuScene
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    game = Game(Config(firebase_api_key="k", update_repo=REPO), Session(tmp_path / "s.json"))
    game.push(MenuScene(game))
    end = time.time() + 10
    while not isinstance(game.top, MessageBox) and time.time() < end:
        game.step(0.02, [])
        time.sleep(0.01)
    box = game.top
    assert isinstance(box, MessageBox) and "v9.0.0" in box.text and GAME_VERSION in box.text
    assert "Replace" in box.text                                    # how to install it
    _click(game, "msg_ok")
    assert opened == [RELEASE["assets"][0]["browser_download_url"]]
    assert isinstance(game.top, MenuScene)
    assert "menu_update" in game.ui.widgets                         # still offered on the title screen
    _click(game, "menu_update")
    assert isinstance(game.top, MessageBox)


def test_no_repo_no_check(tmp_path, monkeypatch):
    from client.main import Game
    monkeypatch.setattr(updates, "UpdateChecker", lambda *a, **k: pytest.fail("must not ask GitHub"))
    game = Game(Config(firebase_api_key="k"), Session(tmp_path / "s.json"))
    game.step(0.02, [])
    assert game.update is None
