"""Stage 6 through the real client UI: fish in the Động Phủ pond (F, wait for the float, strike,
answer the question a rare fish asks, reel it in with the button), read the Ngư Phổ; then at
Hồ Nghiên Mực talk to Ngư Ông, buy worms in his shop and fish from the end of the dock.
The server runs with BALANCE_PROFILE=dev (fast bites, rare fish more often)."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import httpx
import pygame

from client.tests.driver import Driver, ServerProcess, answer_current_quiz
from client.tests.test_linh_phong_flow import abode, give, learn
from client.tests.test_world_flow import make_account


def fishing_scene(drv: Driver):
    from client.scenes.fishing import FishingScene
    return next((s for s in drv.game.scenes if isinstance(s, FishingScene)), None)


def one_cast(drv: Driver, server: ServerProcess) -> dict:
    """Press F at the water and play one fish to the end like a careful player.
    Returns {"result": ..., "quiz": bool}."""
    drv.press(pygame.K_f)
    drv.wait(lambda: fishing_scene(drv) is not None, 5, "fishing scene")
    fsc = fishing_scene(drv)
    drv.wait(lambda: fsc.phase in ("bite", "over") or fsc not in drv.game.scenes, 15, "a bite")
    assert fsc.phase == "bite", (fsc.phase, drv.toast_log[-3:])
    drv.press(pygame.K_f)                       # strike
    quiz = False
    drv.wait(lambda: fsc.phase in ("reel", "quiz", "over"), 10, "the fish")
    while fsc.phase == "quiz":
        drv.wait(lambda: drv.top_is("FishQuizScene") or fsc.phase != "quiz", 10, "fish question")
        if drv.top_is("FishQuizScene"):
            quiz = True
            answer_current_quiz(drv, server, correct=True)
            drv.wait(lambda: not drv.top_is("FishQuizScene") or fsc.phase != "quiz", 10, "question closes")
            drv.step(3)
    end = time.time() + 70
    while fsc.phase == "reel" and not fsc.sent and time.time() < end:
        r = fsc.reel
        drv.keys.held = {pygame.K_SPACE} if r.hook + r.vel * 0.25 < r.fish else set()
        drv.step(1)
    drv.keys.held = set()
    drv.wait(lambda: fsc.result is not None or fsc.phase == "over", 10, "reel result")
    result = (fsc.result or {}).get("result", "lost")
    if result == "caught":
        drv.wait_scene("CatchScene", 5)
    return {"result": result, "quiz": quiz, "fish": (fsc.result or {}).get("fish")}


def close_catch(drv: Driver) -> None:
    if drv.top_is("CatchScene"):
        drv.press(pygame.K_RETURN)
    drv.wait(lambda: fishing_scene(drv) is None and not drv.top_is("CatchScene"), 5, "back at the water")


def run_fishing_flow(workdir: Path, shots: Path | None = None) -> None:
    server = ServerProcess(workdir, time_scale=1, env={"BALANCE_PROFILE": "dev"})
    try:
        url = server.url
        token, uid = make_account(url, "ngu_phu", "Ngư Phủ")
        h = {"Authorization": f"Bearer {token}"}
        httpx.get(url + "/garden", headers=h).raise_for_status()
        httpx.get(url + "/quests", headers=h).raise_for_status()
        for hz in ("水", "火", "木", "人", "大", "小"):
            learn(server, uid, hz)
        give(server, uid, "can_long_cot", 1)
        server.sql("update users set flags=? where id=?",
                   (json.dumps({"tutorial": 5, "fishing": {"rod": "can_long_cot", "bait": None, "levels": {}}}), uid))
        # beside the Động Phủ pond, facing it
        server.sql("update characters set zone_id='abode', x=?, y=?, facing='left' where user_id=?", (10 * 16 + 7, 17 * 16 + 8, uid))
        (workdir / "session.json").write_text(json.dumps({"token": token, "username": "ngu_phu", "server_url": url}))
        drv = Driver(url, workdir, shots)
        drv.click("menu_start")
        drv.wait(lambda: abode(drv) is not None, 15, "abode")
        drv.wait_api()
        ab = abode(drv)
        ab.player.facing = "left"
        drv.step(3)
        drv.shot("pond")
        caught, quizzes = [], 0
        for _ in range(8):
            out = one_cast(drv, server)
            quizzes += out["quiz"]
            if out["result"] == "caught":
                caught.append(out["fish"]["id"])
                if len(caught) == 1:
                    drv.shot("catch")
            close_catch(drv)
            if caught and quizzes:
                break
        assert caught, "no fish landed in 8 casts"
        assert quizzes, "no rare fish asked a question in 8 casts"
        rows = server.sql("select fish_id, count from fish_catches where user_id=?", (uid,))
        assert {r[0] for r in rows} == set(caught)
        items = {r[0]: r[1] for r in server.sql("select item_id, quantity from inventory_items where user_id=?", (uid,))}
        assert any(k.startswith("fish_") or k == "ca_nho" for k in items)
        # Ngư Phổ, through the Sổ Phát Hiện
        drv.press(pygame.K_b)
        drv.wait_scene("BookScene")
        drv.click("book_to_fish")
        drv.wait_scene("FishBookScene")
        drv.wait(lambda: drv.game.top.data is not None, 5, "Ngư Phổ")
        assert drv.game.top.data["found"] == len(set(caught))
        drv.shot("ngu_pho")
        drv.click("fishbook_records")
        drv.wait(lambda: drv.game.top.records is not None, 5, "records")
        assert {r["id"] for r in drv.game.top.records} == set(caught)
        drv.press(pygame.K_ESCAPE)
        drv.close()

        # ---- Hồ Nghiên Mực: Ngư Ông, his shop, the dock
        server.sql("update characters set zone_id='ho_nghien_muc', x=408, y=472, facing='up' where user_id=?", (uid,))
        drv = Driver(url, workdir, shots)
        drv.click("menu_start")
        from client.tests.test_combat_flow import world
        drv.wait(lambda: world(drv) is not None and world(drv).joined, 20, "the lake")
        assert world(drv).zone_id == "ho_nghien_muc"
        drv.wait_api()
        drv.wait(lambda: world(drv).target is not None, 5, "Ngư Ông in front")
        drv.press(pygame.K_e)
        drv.wait_scene("DialogScene")
        drv.shot("ngu_ong")
        for _ in range(12):
            if not drv.top_is("DialogScene"):
                break
            drv.press(pygame.K_RETURN)
            drv.step(20)
        drv.wait_scene("FishShopScene")
        drv.wait(lambda: drv.game.top.data is not None, 5, "shop")
        drv.click("bait_buy_giun_dat")
        drv.wait_api()
        drv.wait(lambda: any(b["id"] == "giun_dat" and b["qty"] == 10 for b in drv.game.top.data["baits"]), 5, "worms")
        drv.click("bait_use_giun_dat")
        drv.wait_api()
        drv.shot("ngu_ong_shop")
        drv.press(pygame.K_ESCAPE)
        quests = {q[0]: q[1] for q in server.sql("select quest_id, state from quests where user_id=?", (uid,))}
        assert quests.get("no1_ben_ho") == "done"
        # walk onto the dock and cast into the lake
        drv.hold([pygame.K_d], 0.45)
        drv.hold([pygame.K_w], 1.2)
        ws = world(drv)
        assert 432 <= ws.player.x <= 464 and ws.player.y < 420, (ws.player.x, ws.player.y)
        drv.step(10)
        out = one_cast(drv, server)
        assert out["result"] in ("caught", "escaped", "snapped")
        drv.shot("lake_cast")
        close_catch(drv)
        left = server.sql("select sum(quantity) from inventory_items where user_id=? and item_id='giun_dat'", (uid,))[0][0]
        assert left == 9
        drv.close()
    finally:
        server.stop()


def test_fishing_flow():
    with tempfile.TemporaryDirectory() as tmp:
        run_fishing_flow(Path(tmp))


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "screenshots" / "fishing"
    with tempfile.TemporaryDirectory() as tmp:
        run_fishing_flow(Path(tmp), out)
    print("screenshots in", out)
