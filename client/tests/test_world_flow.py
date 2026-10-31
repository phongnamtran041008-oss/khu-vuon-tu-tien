"""Stage 3 acceptance test (spec 20): two players in the shared world.

Player A is the real game client driven through its UI; player B is a second WebSocket
client on another thread (the same network code the game uses). They see each other
walk, chat, become friends, A visits B's abode and "tưới giúp", walks to Rừng Mực Loang,
quits, and comes back where they left off."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import httpx
import pygame

from client.config import PROTOCOL_VERSION
from client.net.ws_client import WsClient
from client.tests.driver import Driver, ServerProcess, answer_current_quiz
from client.tests.test_flow import advance_dialogs

LOOK = {"hair_color": "#A0522D", "hair_style": "buoi", "body": "nu"}


def make_account(url: str, username: str, display: str, look=None) -> tuple[str, int]:
    r = httpx.post(url + "/auth/register", json={"username": username, "password": "matkhau1"}).json()
    token = r["token"]
    httpx.post(url + "/character/create", json={"display_name": display, "appearance": look or LOOK},
               headers={"Authorization": f"Bearer {token}"}).raise_for_status()
    return token, r["user_id"]


class Bot:
    """Player B: a bare WebSocket client."""

    def __init__(self, url: str, token: str):
        self.ws = WsClient(url, token, PROTOCOL_VERSION)
        self.msgs: list[dict] = []
        self.seq = 0

    def pump(self) -> list[dict]:
        new = self.ws.poll()
        self.msgs += new
        return new

    def find(self, t: str, pred=lambda m: True):
        return [m for m in self.msgs if m.get("t") == t and pred(m)]

    def walk(self, dx: int, dy: int, drv: Driver, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            self.ws.send({"t": "in", "s": self.seq, "k": [[dx, dy, 50]]})
            self.seq += 1
            t0 = time.time()
            while time.time() - t0 < 0.05:
                drv.step(1)
            self.pump()


def world(drv: Driver):
    return drv.game.world_scene()


def run_world_flow(workdir: Path, shots: Path | None = None) -> None:
    server = ServerProcess(workdir)
    bot = None
    try:
        url = server.url
        ta, a_id = make_account(url, "detu_a", "Tiểu Trúc")
        tb, b_id = make_account(url, "detu_b", "Lão Mai", {"hair_color": "#8E8E8E", "hair_style": "ngan",
                                                           "body": "nam"})
        hb = {"Authorization": f"Bearer {tb}"}
        (workdir / "session.json").write_text(json.dumps({"token": ta, "username": "detu_a", "server_url": url}))
        drv = Driver(url, workdir, shots)
        drv.click("menu_start")
        drv.wait(lambda: "AbodeScene" in drv.scene_names(), 10, "abode")
        drv.wait_api()
        advance_dialogs(drv)
        drv.wait(lambda: drv.game.net is not None and drv.game.net.online, 10, "world connection")

        # A walks out through the bamboo gate into Trúc Lâm Thôn
        drv.hold([pygame.K_s], 0.9)
        abode = drv.game.scenes[0]
        assert abode.target and abode.target[1].props.get("action") == "exit", abode.target
        drv.shot("abode_gate")
        drv.press(pygame.K_e)
        drv.wait(lambda: world(drv) is not None and world(drv).joined, 10, "village")
        assert world(drv).zone_id == "truc_lam_thon"

        # B arrives too
        bot = Bot(url, tb)
        drv.wait(lambda: bot.pump() is not None and bot.find("welcome"), 10, "bot welcome")
        bot.ws.send({"t": "join", "zone": "truc_lam_thon", "via": "abode"})
        drv.wait(lambda: bot.pump() is not None and bot.find("zone"), 10, "bot zone")
        ws = world(drv)
        drv.wait(lambda: any(e.name == "Lão Mai" for e in ws.entities.values()), 10, "A sees B")
        ent = next(e for e in ws.entities.values() if e.name == "Lão Mai")
        drv.step(20)
        y_before = ent.pos[1]
        bot.walk(0, -1, drv, 1.0)
        drv.step(20)
        assert ent.pos[1] < y_before - 40, (y_before, ent.pos)   # B moved and A saw it glide
        assert ws.corrections == 0
        # A walks; B sees it
        a_eid = f"p{a_id}"
        bot.msgs.clear()
        drv.hold([pygame.K_d], 0.6)
        drv.wait(lambda: bot.pump() is not None and any(
            e[0] == a_eid for m in bot.find("snap") for e in m.get("e", [])), 5, "B sees A move")
        assert ws.corrections == 0, "prediction should match the server exactly"
        drv.shot("village_two_players")

        # chat both ways
        drv.press(pygame.K_RETURN)
        assert drv.game.chatbox.typing
        drv.type("Chào Lão Mai!")
        drv.press(pygame.K_RETURN)
        drv.wait(lambda: bot.pump() is not None and bot.find("chat", lambda m: m["text"] == "Chào Lão Mai!"),
                 5, "B gets chat")
        assert not drv.game.chatbox.typing
        bot.ws.send({"t": "chat", "ch": "zone", "text": "Chào Tiểu Trúc, đi Rừng Mực Loang không?"})
        drv.wait(lambda: any("Rừng Mực Loang" in e["text"] for e in drv.game.chat.items), 5, "A gets chat")
        assert ent.id in ws.bubbles
        drv.shot("chat_bubble")

        # friends: B asks, A accepts in the friends window
        httpx.post(url + "/friends/request", json={"display_name": "Tiểu Trúc"}, headers=hb).raise_for_status()
        drv.wait(lambda: any("muốn kết bạn" in t for t in drv.toast_log), 5, "request toast")
        drv.press(pygame.K_p)
        drv.wait_scene("FriendsScene")
        drv.click("fr_tab_requests")
        drv.click(f"fr_acc_{b_id}")
        drv.wait_api()
        drv.click("fr_tab_friends")
        drv.wait(lambda: drv.game.top.data and drv.game.top.data["friends"], 5, "friend listed")
        f = drv.game.top.data["friends"][0]
        assert f["display_name"] == "Lão Mai" and f["online"] and f["zone_id"] == "truc_lam_thon"
        drv.shot("friends")

        # B has a 水 seedling; A has learned 水, so A can water it
        httpx.get(url + "/garden", headers=hb)
        w_id = server.sql("select id from words where hanzi='水'")[0][0]
        server.sql("update plots set word_id=?, stage=2, next_review_at=datetime('now','+3 days'), "
                   "wither_checked_at=datetime('now') where user_id=? and x=1 and y=1", (w_id, b_id))
        server.sql("update collection set introduced=1 where user_id=? and word_id=?", (a_id, w_id))
        stones = lambda uid: server.sql("select spirit_stones from users where id=?", (uid,))[0][0]  # noqa: E731
        a0, b0 = stones(a_id), stones(b_id)
        drv.click(f"fr_visit_{b_id}")
        drv.wait_scene("VisitScene")
        drv.wait(lambda: drv.game.top.data.get("plots"), 5, "visit garden")
        visit = drv.game.top
        plot = next(p for p in visit.plots() if p.get("word"))
        assert plot["helpable"]
        drv.step(10)
        drv.shot("visit_friend")
        r = visit.plot_rect(plot)
        drv.click_at(drv.game.display.to_window(r.centerx - visit.cam[0], r.centery - visit.cam[1]))
        drv.wait_scene("HelpPanel")
        drv.click("help_go")
        drv.wait_scene("QuizScene")
        res = answer_current_quiz(drv, server, correct=True)
        assert res["correct"] and res["reward"] == {"spirit_stones": 10}
        drv.shot("help_result")
        drv.click("quiz_continue")
        drv.wait_api()
        assert (stones(a_id), stones(b_id)) == (a0 + 10, b0 + 10)
        drv.wait(lambda: bot.pump() is not None and bot.find("friend", lambda m: m["event"] == "helped"), 5,
                 "B told about the help")
        drv.click("visit_back")
        drv.wait_scene("WorldScene")

        # channels
        drv.click("w_channel")
        drv.wait_scene("ChannelPicker")
        drv.shot("channels")
        drv.press(pygame.K_ESCAPE)

        # walk to the forest: back to the middle of the road, north to the square, east to the gate
        ws = world(drv)
        road_x = 28 * 16
        drv.hold([pygame.K_a], max(0.05, (ws.player.x - road_x) / 74.0))
        drv.hold([pygame.K_w], (ws.player.y - 18 * 16) / 74.0 + 0.6)   # ...and bump into the well
        assert 280 <= ws.player.y < 290, ws.player.y
        drv.step(20)
        assert ws.corrections == 0, "walking into a wall must be predicted exactly too"
        drv.hold([pygame.K_d], 7.0)
        drv.wait(lambda: world(drv) is not None and world(drv).zone_id == "rung_muc_loang" and world(drv).joined,
                 10, "forest")
        drv.wait(lambda: any(e.kind == "m" for e in world(drv).entities.values()), 5, "monsters")
        drv.step(30)
        drv.shot("forest")
        drv.wait(lambda: bot.pump() is not None and any(a_eid in m.get("rm", []) for m in bot.find("snap")), 5,
                 "B sees A leave")
        pos = (world(drv).player.x, world(drv).player.y)
        drv.close()

        # come back: the game reconnects in the forest, same place
        drv2 = Driver(url, workdir, shots)
        drv2.n_shots = drv.n_shots
        drv2.click("menu_start")
        drv2.wait(lambda: world(drv2) is not None and world(drv2).joined, 15, "resume in the world")
        w2 = world(drv2)
        assert w2.zone_id == "rung_muc_loang"
        assert abs(w2.player.x - pos[0]) < 1 and abs(w2.player.y - pos[1]) < 1
        drv2.shot("back_in_forest")
        drv2.close()
    finally:
        if bot is not None:
            bot.ws.close()
        server.stop()


def test_two_players_world_flow():
    with tempfile.TemporaryDirectory() as tmp:
        run_world_flow(Path(tmp))
