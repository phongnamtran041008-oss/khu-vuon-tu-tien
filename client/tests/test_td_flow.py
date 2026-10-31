"""Stage 7 through the real client UI: walk up to the Cổng Thủ Vườn in Trúc Lâm Thôn, choose 8
plants, then play all 10 levels of chapter 1 by clicking the plant cards and the board,
answering every Linh Khí question and upgrade question on the card, starting the waves and
pressing Tụ Khí. Every level is checked by the server (it replays the log) and must be won.
Then the Tàng Thư Các: the books, the Bách Thảo Phổ, a search and a milestone.

The server runs with BALANCE_PROFILE=dev, which only allows the board to run faster (×32);
the levels and numbers are the real ones."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import pygame

from client.engine import td_sim
from client.tests.driver import ROOT, Driver, ServerProcess, answer_current_quiz
from client.tests.test_combat_flow import world
from client.tests.test_linh_phong_flow import learn
from client.tests.test_world_flow import make_account

sys.path.insert(0, str(ROOT / "tools"))
import td_bot  # noqa: E402

BEGINNER = ["火", "水", "木", "山", "一", "茶", "妈妈", "月"]


def top(drv: Driver):
    return drv.game.top


def play_scene(drv: Driver):
    from client.scenes.td import TdPlayScene
    return next((s for s in drv.game.scenes if isinstance(s, TdPlayScene)), None)


def map_scene(drv: Driver):
    from client.scenes.td import TdMapScene
    return next((s for s in drv.game.scenes if isinstance(s, TdMapScene)), None)


def answer_and_close(drv: Driver, server: ServerProcess) -> bool:
    card = drv.game.top
    drv.wait(lambda: card.t >= card.GUARD_SECONDS, 3, "the card is ready for clicks")
    res = answer_current_quiz(drv, server, correct=True)
    drv.press(pygame.K_RETURN)        # no need to wait for the card to close by itself
    return bool(res.get("correct"))


def on_board(drv: Driver, sc, wid: str) -> bool:
    """Click a widget of the board, unless a question card has just come up over it (a wave
    can end between two clicks); then the caller lets the main loop answer it first."""
    if drv.game.top is not sc or sc.busy or not drv.has(wid):
        return False
    drv.click_at(drv.game.ui.widgets[wid].center)
    return True


def click_card(drv: Driver, sc, word: str | None) -> bool:
    """Make `word` the chosen card (None: no card chosen)."""
    if sc.card == word:
        return True
    if sc.card is not None and not on_board(drv, sc, f"td_card_{sc.words.index(sc.card)}"):
        return False
    return word is None or on_board(drv, sc, f"td_card_{sc.words.index(word)}")


def perform(drv: Driver, sc, act: dict) -> None:
    if act["k"] == "place":
        if click_card(drv, sc, act["w"]):
            on_board(drv, sc, f"td_cell_{act['x']}_{act['y']}")
    elif act["k"] == "up":
        if click_card(drv, sc, None) and on_board(drv, sc, f"td_cell_{act['x']}_{act['y']}"):
            if sc.picked == (act["x"], act["y"]):
                on_board(drv, sc, "td_upgrade")


def play_level(drv: Driver, server: ServerProcess, stats: dict, shot: str | None = None) -> dict:
    """Play the open board to the end like a careful beginner; returns the server's result."""
    drv.wait(lambda: play_scene(drv) is not None, 10, "the board")
    sc = play_scene(drv)
    end = time.time() + 240
    last_think = 0.0
    while time.time() < end:
        t = top(drv)
        name = type(t).__name__
        if name == "TdResultScene":
            return t.r
        if name == "TdQuizScene":
            stats["questions"] += 1
            stats["right"] += answer_and_close(drv, server)
            continue
        if t is not sc or sc.sending or sc.busy:
            drv.step(1)
            continue
        sim = sc.sim
        if sc.speed < sc.speeds[-1]:          # fast forward (the dev profile allows ×32)
            on_board(drv, sc, "td_speed")
            continue
        if sim.phase == td_sim.BUILD:
            acts = td_bot.decide(sim)
            if acts:
                perform(drv, sc, acts[0])
            elif click_card(drv, sc, None):
                on_board(drv, sc, "td_wave")
            continue
        if sim.phase == td_sim.WAVE:
            if shot and sim.wave >= 3 and len(sim.monsters) >= 4:
                drv.shot(shot)
                shot = None
            if sc.tu_khi_left() <= 0 and sim.qi < 90 and on_board(drv, sc, "td_tukhi"):
                stats["tu_khi"] += 1
                continue
            if time.time() - last_think > 0.25:
                last_think = time.time()
                acts = td_bot.decide(sim)
                if acts:
                    perform(drv, sc, acts[0])
                    continue
        drv.step(1)
    raise AssertionError(f"level did not end in time: {sc.sim.summary()}")


def run_td_flow(workdir: Path, shots: Path | None = None, levels: int = 10) -> None:
    server = ServerProcess(workdir, time_scale=1, env={"BALANCE_PROFILE": "dev"})
    try:
        url = server.url
        token, uid = make_account(url, "thu_vuon", "Thủ Vườn")
        import httpx
        h = {"Authorization": f"Bearer {token}"}
        httpx.get(url + "/garden", headers=h).raise_for_status()
        httpx.get(url + "/quests", headers=h).raise_for_status()
        for hz in BEGINNER:
            learn(server, uid, hz)
        server.sql("update users set flags=? where id=?", (json.dumps({"tutorial": 5}), uid))
        # in Trúc Lâm Thôn, just below the Cổng Thủ Vườn
        server.sql("update characters set zone_id='truc_lam_thon', x=724, y=438, facing='up' where user_id=?", (uid,))
        (workdir / "session.json").write_text(json.dumps({"token": token, "username": "thu_vuon", "server_url": url}))
        drv = Driver(url, workdir, shots)
        drv.click("menu_start")
        drv.wait(lambda: world(drv) is not None and world(drv).joined, 20, "the village")
        drv.wait_api()
        drv.wait(lambda: world(drv).target is not None and world(drv).action_of(world(drv).target) == "td", 5,
                 "the Cổng Thủ Vườn in front")
        drv.press(pygame.K_e)
        drv.wait_scene("DialogScene")
        drv.shot("td_gate_intro")
        for _ in range(10):
            if not drv.top_is("DialogScene"):
                break
            drv.press(pygame.K_RETURN)
            drv.step(20)
        drv.wait(lambda: drv.top_is("TdMapScene") and top(drv).data is not None, 10, "the level map")
        m = top(drv)
        assert m.data["levels"][0]["unlocked"] and not m.data["levels"][1]["unlocked"]
        assert {p["hanzi"] for p in m.data["plants"]} >= set(BEGINNER)

        # choose the 8 plants
        drv.click("td_loadout_edit")
        drv.wait_scene("TdLoadoutScene")
        lo = top(drv)
        for wid in list(lo.chosen):
            drv.click(f"td_pick_{wid}")
        by_hz = {p["hanzi"]: p["word_id"] for p in m.data["plants"]}
        for hz in BEGINNER:
            drv.click(f"td_pick_{by_hz[hz]}")
        drv.shot("td_loadout")
        drv.click("td_loadout_save")
        drv.wait(lambda: drv.top_is("TdMapScene") and len(m.data["loadout"]) == 8, 5, "loadout saved")
        drv.shot("td_map")

        stats = {"questions": 0, "right": 0, "tu_khi": 0}
        for i in range(1, levels + 1):
            lid = f"c1_{i:02d}"
            drv.wait(lambda: drv.top_is("TdMapScene") and m.level(lid) and m.level(lid)["unlocked"], 10,
                     f"{lid} open")
            drv.click(f"td_lv_{lid}")
            drv.click("td_start")
            res = play_level(drv, server, stats, shot=f"td_board_{lid}" if i in (2, 9) else None)
            assert res["result"] == "won", (lid, res)
            assert res["stars"] >= 1
            if i in (1, levels):
                drv.shot(f"td_result_{lid}")
            drv.click("td_result_next" if i < 10 else "td_result_map")
        rows = dict(server.sql("select level_id, stars from td_progress where user_id=?", (uid,)))
        assert all(rows.get(f"c1_{i:02d}", 0) >= 1 for i in range(1, levels + 1)), rows
        assert stats["questions"] >= 3 * levels and stats["right"] == stats["questions"], stats
        assert stats["tu_khi"] > 0
        n_td = server.sql("select count(*) from quiz_sessions where user_id=? and context='td'", (uid,))[0][0]
        assert n_td == stats["questions"], (n_td, stats)
        drv.wait(lambda: drv.top_is("TdMapScene"), 10, "back on the map")
        if levels == 10:
            assert m.data["endless"]["unlocked"]
        drv.press(pygame.K_ESCAPE)
        drv.wait(lambda: map_scene(drv) is None, 5, "map closed")

        # ---- Tàng Thư Các (the L key)
        drv.press(pygame.K_l)
        drv.wait(lambda: drv.top_is("LibraryScene") and top(drv).data is not None, 10, "Tàng Thư Các")
        lib = top(drv)
        books = {b["id"]: b for b in lib.data["books"]}
        assert books["plant"]["found"] >= len(BEGINNER)
        assert books["monster"]["found"] >= (3 if levels == 10 else 1)   # Mặc Quái met in the garden trial
        drv.shot("library")
        drv.click("lib_search")
        drv.type("huo")
        drv.wait(lambda: lib.results is not None and any(r["title"] == "火" for r in lib.results["results"]), 5,
                 "search result for huo")
        drv.shot("library_search")
        drv.click("lib_res_0")
        drv.wait(lambda: drv.top_is("HerbBookScene") and top(drv).data is not None, 5, "Bách Thảo Phổ")
        assert top(drv).sel == by_hz["火"]
        drv.shot("bach_thao_pho")
        drv.press(pygame.K_ESCAPE)
        drv.wait_scene("LibraryScene")
        drv.click("lib_search_clear")
        ready = [(b["id"], ms["pct"]) for b in lib.data["books"] for ms in b["milestones"] if ms["ready"] and not ms["claimed"]]
        if ready:
            book, pct = ready[0]
            drv.click(f"lib_claim_{book}_{pct}")
            drv.wait(lambda: any(ms["claimed"] for b in lib.data["books"] if b["id"] == book for ms in b["milestones"]),
                     5, "milestone claimed")
        drv.click("lib_open_monster")
        drv.wait(lambda: drv.top_is("MonsterBookScene") and top(drv).data is not None, 5, "Yêu Quái Phổ")
        assert any(e["id"].startswith("td_") and e["found"] for e in top(drv).data["entries"])
        drv.press(pygame.K_ESCAPE)
        drv.wait_scene("LibraryScene")
        drv.press(pygame.K_ESCAPE)
        drv.close()
    finally:
        server.stop()


def test_td_chapter_one_through_the_ui():
    with tempfile.TemporaryDirectory() as tmp:
        run_td_flow(Path(tmp))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "screenshots" / "td"
    with tempfile.TemporaryDirectory() as tmp:
        run_td_flow(Path(tmp), out)
    print("screenshots in", out)
