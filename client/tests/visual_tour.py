"""Screenshots of screens the main flow does not reach (10-pull, sentence board,
discovery popup, every question type). For visual review:

    python -m client.tests.visual_tour OUT_DIR
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import httpx
import pygame

from client.tests.driver import Driver, ServerProcess, answer_current_quiz


def tour(workdir: Path, out: Path) -> None:
    server = ServerProcess(workdir)
    try:
        r = httpx.post(server.url + "/auth/register", json={"username": "tour", "password": "matkhau1"}).json()
        token = r["token"]
        h = {"Authorization": f"Bearer {token}"}
        httpx.post(server.url + "/character/create", headers=h,
                   json={"display_name": "Khách Tham Quan", "appearance": {"hair_color": "#6B3FA0",
                                                                         "hair_style": "dai", "body": "nu"}})
        httpx.post(server.url + "/tutorial", headers=h, json={"step": 5})
        httpx.get(server.url + "/garden", headers=h)
        server.sql("update users set spirit_stones=5000")
        # learned words + fruits for one sentence (我 喜欢 吃 苹果)
        ids = {row[1]: row[0] for row in server.sql("select id, hanzi from words")}
        for hz in ("我", "喜欢", "吃", "苹果", "好", "女", "子", "只", "猫", "妈"):
            server.sql("insert or ignore into collection(user_id, word_id, introduced, mastery, times_correct,"
                       " times_wrong, needs_review, first_seen_at) values (1, ?, 1, 40, 0, 0, 0, datetime('now'))",
                       (ids[hz],))
        for hz in ("我", "喜欢", "吃", "苹果", "水"):
            server.sql("insert into fruits(user_id, word_id, count) values (1, ?, 2)", (ids[hz],))
        # 女 next to 子 at stage 1 -> discovery on next garden load
        server.sql("update plots set word_id=?, stage=1, next_review_at=datetime('now','+1 day'), wither=0 "
                   "where x=1 and y=1", (ids["女"],))
        server.sql("update plots set word_id=?, stage=2, next_review_at=datetime('now','+1 day'), wither=0 "
                   "where x=2 and y=1", (ids["子"],))
        (workdir / "session.json").write_text(f'{{"token": "{token}", "username": "tour", '
                                              f'"server_url": "{server.url}"}}')
        drv = Driver(server.url, workdir, out)
        drv.n_shots = 40
        drv.click("menu_start")
        drv.wait(lambda: "AbodeScene" in drv.scene_names(), 10, "abode")
        drv.wait_scene("DiscoveryPopup")
        drv.step(40)
        drv.shot("discovery_popup")
        drv.click("disc_ok")
        drv.press(pygame.K_g)
        drv.wait_scene("GachaScene")
        drv.wait_api()
        drv.click("g_roll10")
        drv.wait(lambda: drv.game.top.results is not None, 5, "10-pull")
        drv.wait(lambda: drv.game.top.anim_t > 3.5, 10, "revealed")
        drv.shot("gacha_10")
        drv.click("g_done")
        drv.press(pygame.K_ESCAPE)
        drv.press(pygame.K_c)
        drv.wait_scene("CraftScene")
        drv.wait_api()
        drv.shot("craft_list")
        drv.click("sent_s001")
        for hz in ("喜欢", "我", "吃", "苹果"):
            drv.click(f"fruit_{ids[hz]}")
        drv.click("cr_go")
        drv.wait_api()
        drv.shot("craft_wrong")
        drv.click("cr_clear")
        for hz in ("我", "喜欢", "吃", "苹果"):
            drv.click(f"fruit_{ids[hz]}")
        drv.click("cr_go")
        drv.wait_api()
        drv.shot("craft_done")
        drv.press(pygame.K_ESCAPE)
        drv.press(pygame.K_b)
        drv.wait_scene("BookScene")
        drv.wait_api()
        drv.shot("book_one_found")
        drv.press(pygame.K_ESCAPE)
        # every question type through the practice endpoint
        from client.scenes.quiz import QuizScene
        for qt, hz in [("Q2", "妈"), ("Q6", "猫"), ("Q7", "喜欢"), ("Q8", "好"), ("Q9", "苹果"),
                       ("Q10", "猫"), ("Q11", "吃"), ("Q4", "妈")]:
            q = httpx.post(server.url + "/quiz/practice", headers=h, json={"qtype": qt, "word_id": ids[hz]}).json()
            if "session_id" not in q:
                print("skip", qt, q)
                continue
            drv.game.push(QuizScene(drv.game, q))
            drv.step(5)
            drv.shot(f"practice_{qt}")
            answer_current_quiz(drv, server, correct=(qt != "Q9"))
            drv.shot(f"practice_{qt}_result")
            drv.click("quiz_continue")
        drv.close()
    finally:
        server.stop()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "screenshots"
    with tempfile.TemporaryDirectory() as tmp:
        tour(Path(tmp), out)
    print("screenshots in", out)
