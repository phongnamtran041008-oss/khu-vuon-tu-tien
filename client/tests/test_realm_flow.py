"""Stage 9 through the real client: at the Cổng Bí Cảnh in Trúc Lâm Thôn the player opens the
gate, makes a party with two bots from the Tổ đội panel (typing their names), leads them into
Mặc Ảnh Động, looks around the first room, and walks out (keeping the entry's loot so far);
the two bots carry on over their own WebSockets and clear the realm. Then the game replays
everything one bot saw, room by room until the result screen, so every puzzle card is drawn
from real server messages.

    python -m client.tests.test_realm_flow OUT_DIR      # with screenshots
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
from pathlib import Path

import pygame

from client.tests.driver import ROOT, Driver, ServerProcess, answer_current_quiz
from client.tests.test_world_flow import make_account

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))


class BotTeam(threading.Thread):
    """Two realm_bots on their own asyncio loop, so the game loop here stays the real one."""

    def __init__(self, url: str, db: Path):
        super().__init__(daemon=True)
        self.url, self.db = url, db
        self.ready = threading.Event()
        self.done = threading.Event()
        self.bots = []
        self.error: BaseException | None = None
        self.quit = False

    def run(self) -> None:
        asyncio.run(self.main())

    async def main(self) -> None:
        import realm_bots
        try:
            self.bots = await realm_bots.make_bots(self.url, self.db, "cb", 2, record=0)
            self.ready.set()
            await realm_bots.play(self.bots, timeout=900, stop=lambda: self.quit)
            await asyncio.sleep(1.5)
            for b in self.bots:
                b.read()
        except BaseException as e:   # noqa: BLE001  (reported by the test)
            self.error = e
            self.ready.set()
        finally:
            self.done.set()
            for b in self.bots:
                await b.close()


def world(drv: Driver):
    return drv.game.world_scene()


def run_realm_flow(workdir: Path, shots: Path | None = None) -> None:
    server = ServerProcess(workdir, time_scale=1, env={"BALANCE_PROFILE": "dev"})
    team = None
    try:
        url = server.url
        token, uid = make_account(url, "khach_bc", "Khách Bí Cảnh")
        from app.realtime import maps
        gx, gy = maps.load("truc_lam_thon").interacts["realm"]
        server.sql("update characters set realm='truc_co', realm_stage=1, zone_id='truc_lam_thon', x=?, y=?, "
                   "facing='up' where user_id=?", (gx, gy + 14, uid))
        server.sql("update users set flags=? where id=?", (json.dumps({"tutorial": 5}), uid))
        server.sql("insert or ignore into collection(user_id, word_id, introduced, mastery, times_correct, times_wrong,"
                   " needs_review, first_seen_at) select ?, id, 1, 60, 0, 0, 0, datetime('now') from words where tier=1",
                   (uid,))
        team = BotTeam(url, server.db)
        team.start()
        assert team.ready.wait(60) and team.error is None, team.error
        names = [b.name for b in team.bots]
        (workdir / "session.json").write_text(json.dumps({"token": token, "username": "khach_bc", "server_url": url}))
        drv = Driver(url, workdir, shots)
        drv.click("menu_start")
        drv.wait(lambda: world(drv) is not None and world(drv).zone_id == "truc_lam_thon" and world(drv).joined,
                 20, "Trúc Lâm Thôn")
        drv.wait_api()
        # ---- the gate
        drv.wait(lambda: world(drv).target is not None and world(drv).action_of(world(drv).target) == "realm", 5,
                 "standing at the Cổng Bí Cảnh")
        drv.shot("village_gate")
        drv.press(pygame.K_e)
        drv.wait(lambda: drv.top_is("RealmGateScene") and drv.game.top.data is not None, 10, "the gate")
        gate = drv.game.top
        ids = [r["id"] for r in gate.data["realms"]]
        assert ids == ["khe_nut_muc", "mac_anh_dong"] and gate.data["realms"][1]["open"]
        drv.shot("realm_gate")
        drv.click("rg_tab_puzzles")
        drv.shot("realm_gate_puzzles")
        drv.click("rg_tab_forge")
        drv.shot("realm_gate_forge")
        drv.click("rg_tab_realms")
        # ---- a party, made in the Tổ đội panel
        drv.click("rg_party")
        drv.wait_scene("PartyScene")
        for i, name in enumerate(names):
            drv.click_at(drv.game.ui.widgets["pt_name"].center)
            drv.type(name)
            drv.press(pygame.K_RETURN)
            drv.wait(lambda: len((drv.game.state.party or {}).get("members", [])) == i + 2, 10, f"{name} joins")
        drv.shot("party")
        drv.click("pt_close")
        drv.wait_scene("RealmGateScene")
        drv.step(5)
        # ---- in we go
        drv.click("rg_enter_mac_anh_dong")
        drv.wait(lambda: world(drv) is not None and world(drv).zone_id == "bi_canh" and world(drv).realm.room
                 is not None, 20, "the first room")
        ws = world(drv)
        assert ws.realm.run["name_vi"] == "Mặc Ảnh Động" and len(ws.realm.run["members"]) == 3
        drv.step(30)
        drv.shot("realm_first_room")
        if drv.top_is("CombatQuizScene"):
            answer_current_quiz(drv, server)
        # ---- out again (the bots go on without us)
        drv.wait(lambda: drv.has("realm_leave") and drv.top_is("WorldScene"), 10, "the leave button")
        drv.click("realm_leave")
        drv.wait_scene("MessageBox")
        drv.click("msg_ok")
        drv.wait(lambda: world(drv) is not None and world(drv).zone_id == "truc_lam_thon", 15, "back in the village")
        drv.shot("back_in_village")
        if not team.done.wait(600):
            info = [(b.name, b.room and b.room["kind"], b.puzzle, b.mine, round(b.me.x), round(b.me.y), b.me.hp,
                     b.q_open, len(b.route)) for b in team.bots]
            raise AssertionError(f"the bots did not finish: {info}")
        assert team.error is None, team.error
        assert all(b.ended and b.ended["result"] == "won" for b in team.bots), [b.ended for b in team.bots]
        rows = server.sql("select result from realm_members where user_id=?", (uid,))
        assert rows and rows[0][0] == "left", rows                    # walked out: the entry still counts
        # ---- the same run, as one bot saw it
        rec = team.bots[0].record
        start = next(i for i, (_, m) in enumerate(rec) if m.get("t") == "zone" and m.get("zone") == "bi_canh")
        drv.game.disconnect_world()
        last_t = rec[start][0]
        shot_at: list[tuple[float, str]] = []
        rooms = 0
        for t, m in rec[start:]:
            if m.get("t") in ("q", "q_end", "welcome", "pong", "party"):
                continue
            while t - last_t > 0.05:
                step = min(0.1, t - last_t)
                drv.game.step(step, [])
                last_t += step
                while shot_at and shot_at[0][0] <= last_t:
                    drv.shot(shot_at.pop(0)[1])
            drv.game._on_net(m)
            if m.get("t") == "realm" and m.get("event") == "room":
                rooms += 1
                shot_at.append((t + 2.5, f"replay_room{m['i'] + 1}_{m['kind']}"))
                shot_at.append((t + 9.0, f"replay_room{m['i'] + 1}_{m['kind']}_later"))
            if m.get("t") == "realm" and m.get("event") == "end":
                for _ in range(20):
                    drv.game.step(0.05, [])
                drv.shot("replay_result")
                ws = world(drv)
                assert ws.realm.ended["result"] == "won" and ws.realm.loot
                break
        assert rooms == team.bots[0].ended["puzzles"] + 1
        drv.close()
    finally:
        if team is not None:
            team.quit = True
            team.done.wait(10)
        server.stop()


def test_realm_flow(tmp_path):
    run_realm_flow(tmp_path)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("screenshots_realm")
    run_realm_flow(Path(tempfile.mkdtemp(prefix="kvtt_realm_")), out)
    print("screenshots in", out)
