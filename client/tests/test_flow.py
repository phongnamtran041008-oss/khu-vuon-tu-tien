"""Stage 2 acceptance test (spec 20): a new player registers, creates a character, walks
in the abode, gets a seed, plants it, reviews it to ripeness (TIME_SCALE), harvests,
sells, rolls the gacha, quits and comes back to the same state."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pygame

from client.tests.driver import Driver, ServerProcess, answer_current_quiz


def plot_window_pos(drv: Driver, plot: dict) -> tuple[int, int]:
    abode = drv.game.scenes[0]
    r = abode.plot_rect(plot)
    return drv.game.display.to_window(r.centerx - abode.cam[0], r.centery - abode.cam[1])


def first_open_plot(drv: Driver) -> dict:
    abode = drv.game.scenes[0]
    return next(p for p in abode.plots() if p["unlocked"])


def advance_dialogs(drv: Driver) -> None:
    while drv.top_is("DialogScene"):
        drv.press(pygame.K_RETURN)
        drv.step(3)


def run_flow(workdir: Path, shots: Path | None = None) -> None:
    server = ServerProcess(workdir)
    try:
        drv = Driver(server.url, workdir, shots)
        drv.step(10)
        drv.shot("menu")
        drv.click("menu_start")
        drv.wait_scene("LoginScene")
        drv.click("tab_register")
        drv.click("rg_user")
        drv.type("detu_01")
        drv.click("rg_pass")
        drv.type("matkhau1")
        drv.click("rg_pass2")
        drv.type("matkhau1")
        drv.shot("register")
        drv.click("btn_register")
        drv.wait_scene("RecoveryCodeScene")
        code = drv.game.top.code
        assert len(code) == 14
        drv.shot("recovery_code")
        drv.click("btn_saved")
        drv.wait_scene("CreateCharScene")
        drv.click("cc_name")
        drv.type("Tiểu Trúc")
        drv.click("hc_2")
        drv.click("hs_buoi")
        drv.click("bd_nu")
        drv.step(30)
        drv.shot("create_character")
        drv.click("cc_go")
        drv.wait(lambda: "AbodeScene" in drv.scene_names(), 10, "abode")
        drv.wait_scene("DialogScene")
        drv.wait_api()
        drv.shot("tutorial_welcome")
        advance_dialogs(drv)
        abode = drv.game.scenes[0]
        assert abode.tutorial_step == 1

        # walk around the abode
        x0, y0 = abode.player.x, abode.player.y
        drv.hold([pygame.K_w], 0.8)
        drv.hold([pygame.K_a], 0.4)
        assert abode.player.y < y0 - 20 and abode.player.x < x0 - 10, "player should have moved"
        drv.shot("walking")

        # plant the tutorial seed
        plot = first_open_plot(drv)
        drv.click_at(plot_window_pos(drv, plot))
        drv.wait_scene("PlotPanel")
        drv.click("pp_plant")
        drv.wait_scene("SeedPicker")
        drv.wait(lambda: drv.game.top.seeds is not None, 5, "seeds")
        seed = drv.game.top.seeds[0]
        drv.shot("seed_picker")
        drv.click(f"seed_{seed['seed_id']}")
        drv.wait_scene("DialogScene")
        advance_dialogs(drv)
        # introduction card
        drv.click_at(plot_window_pos(drv, plot))
        drv.wait_scene("PlotPanel")
        drv.click("pp_card")
        drv.wait_scene("IntroCard")
        drv.wait(lambda: drv.game.top.card is not None, 5, "card")
        drv.shot("intro_card")
        drv.click("ic_remember")
        drv.wait_scene("DialogScene")
        advance_dialogs(drv)

        # review until ripe: stage 1..4 (TIME_SCALE=86400: 1 day = 1 second)
        qtypes = []
        for stage_wait in (0.2, 1.2, 3.2, 7.3):
            drv.wait(lambda: abode.is_due(abode.plot_by_id(plot["id"])), stage_wait + 5, "plot due")
            if not qtypes:
                drv.shot("garden_due")
            drv.click_at(plot_window_pos(drv, plot))
            drv.wait_scene("PlotPanel")
            drv.click("pp_review")
            drv.wait_scene("QuizScene")
            qtypes.append(drv.game.top.q["qtype"])
            drv.shot(f"quiz_{qtypes[-1]}")
            res = answer_current_quiz(drv, server, correct=True)
            assert res["correct"], res
            drv.shot(f"quiz_{qtypes[-1]}_result")
            drv.click("quiz_continue")
            advance_dialogs(drv)
            drv.wait_api()
        assert qtypes[:3] == ["Q1", "Q3", "Q4"] and qtypes[3] in ("Q5", "Q7"), qtypes
        p = abode.plot_by_id(plot["id"])
        assert p.get("ripe"), p
        drv.step(30)
        drv.shot("ripe")

        # harvest and sell
        drv.click_at(plot_window_pos(drv, plot))
        drv.wait_scene("PlotPanel")
        drv.click("pp_harvest")
        drv.wait_api()
        stones_before = drv.game.state.me["spirit_stones"]
        drv.press(pygame.K_TAB)
        drv.wait_scene("BagScene")
        drv.click("bag_tab_fruits")
        drv.wait(lambda: drv.game.top.fruits, 5, "fruits")
        drv.shot("bag_fruits")
        wid = drv.game.top.fruits[0]["word_id"]
        drv.click(f"sellall_{wid}")
        drv.wait_api()
        assert drv.game.state.me["spirit_stones"] > stones_before
        drv.press(pygame.K_ESCAPE)

        # gacha: free roll then a paid roll
        drv.press(pygame.K_g)
        drv.wait_scene("GachaScene")
        drv.wait_api()
        drv.shot("gacha")
        drv.click("g_free")
        drv.wait(lambda: drv.game.top.results is not None, 5, "gacha results")
        drv.wait(lambda: drv.game.top.anim_t > 0.5, 5, "shaking")
        drv.shot("gacha_opening")
        drv.wait(lambda: drv.game.top.anim_t > 2.4, 8, "revealed")
        drv.shot("gacha_revealed")
        drv.click("g_done")
        drv.click("g_roll1")
        drv.wait(lambda: drv.game.top.results is not None, 5, "gacha results 2")
        drv.wait(lambda: drv.game.top.anim_t > 2.4, 8, "revealed 2")
        drv.click("g_done")
        drv.press(pygame.K_ESCAPE)
        seeds = server.sql("select count(*) from seeds")[0][0]
        assert seeds == 2, seeds

        # discovery book and sentence table open
        drv.press(pygame.K_b)
        drv.wait_scene("BookScene")
        drv.wait_api()
        drv.shot("discovery_book")
        drv.press(pygame.K_ESCAPE)
        drv.press(pygame.K_c)
        drv.wait_scene("CraftScene")
        drv.wait_api()
        drv.shot("craft_table")
        drv.press(pygame.K_ESCAPE)

        # make a withered plant to look at the ink fog
        seed_row = server.sql("select id, word_id from seeds order by id limit 1")[0]
        p2 = [p for p in abode.plots() if p["unlocked"] and not p.get("word")][0]
        server.sql("update plots set word_id=?, stage=3, wither=80, next_review_at=datetime('now','-1 hours'),"
                   " wither_checked_at=datetime('now') where id=?", (seed_row[1], p2["id"]))
        server.sql("insert or ignore into collection(user_id, word_id, introduced, mastery, times_correct, "
                   "times_wrong, needs_review, first_seen_at) values (1, ?, 1, 0, 0, 0, 1, datetime('now'))",
                   (seed_row[1],))
        abode.refresh_garden()
        drv.wait_api()
        pygame.mouse.set_pos(plot_window_pos(drv, p2))
        drv.step(20)
        drv.shot("withered_tooltip")

        pos = (round(abode.player.x, 1), round(abode.player.y, 1), abode.player.facing)
        stones = drv.game.state.me["spirit_stones"]
        drv.close()

        # come back: auto-login from session.json, same place, same garden
        drv2 = Driver(server.url, workdir, shots)
        drv2.n_shots = drv.n_shots
        drv2.click("menu_start")
        drv2.wait(lambda: "AbodeScene" in drv2.scene_names(), 10, "abode again")
        drv2.wait_api()
        ab2 = drv2.game.scenes[0]
        assert (round(ab2.player.x, 1), round(ab2.player.y, 1), ab2.player.facing) == pos
        assert drv2.game.state.me["spirit_stones"] == stones
        assert any(p.get("word") for p in ab2.plots())
        assert not drv2.top_is("DialogScene")  # the tutorial does not start again
        drv2.shot("back_again")
        drv2.close()
        saved = json.loads((workdir / "session.json").read_text())
        assert saved["username"] == "detu_01"
    finally:
        server.stop()


def test_new_player_flow():
    with tempfile.TemporaryDirectory() as tmp:
        run_flow(Path(tmp))


def test_tests_leave_no_settings_in_game_folder():
    """Regression: a test run once saved its random server port into client/config.json,
    which then shipped and pointed players at a server that did not exist."""
    root = Path(__file__).resolve().parents[1]

    def snapshot():   # the player's own files may exist: they must just stay exactly as they were
        return {n: (root / n).read_bytes() if (root / n).exists() else None for n in ("config.json", "session.json")}
    before = snapshot()
    with tempfile.TemporaryDirectory() as tmp:
        run_flow(Path(tmp))
    assert snapshot() == before
