"""Stage 4 through the real client UI: fight a Mực Con (attack, Vấn Đạo card, Hộ Thể,
shield break, kill, loot), take a Mặc Kích from a wrong answer, look at the cultivation,
bag, quest and Yêu Quái Phổ screens, then pass Thiên Kiếp from Luyện Khí 9 to Trúc Cơ."""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pygame

from client.tests.driver import Driver, ServerProcess, answer_current_quiz
from client.tests.test_world_flow import make_account


def world(drv):
    return drv.game.world_scene()


def walk_to(drv: Driver, tx: float, ty: float, near: float = 26, timeout: float = 8.0) -> None:
    """Hold the arrow keys toward a point (good enough in the open forest)."""
    import time
    end = time.time() + timeout
    while time.time() < end:
        ws = world(drv)
        dx, dy = tx - ws.player.x, ty - ws.player.y
        if math.hypot(dx, dy) < near:
            break
        keys = []
        if abs(dx) > 4:
            keys.append(pygame.K_d if dx > 0 else pygame.K_a)
        if abs(dy) > 4:
            keys.append(pygame.K_s if dy > 0 else pygame.K_w)
        drv.hold(keys, 0.15)
    drv.keys.held = set()


def nearest(ws, kind: str):
    alive = [e for e in ws.entities.values() if e.kind == "m" and e.mtype == kind and e.alive]
    return min(alive, key=lambda e: math.hypot(e.pos[0] - ws.player.x, e.pos[1] - ws.player.y)) if alive else None


def engage(drv: Driver, server: ServerProcess, kind: str = "ink_slime"):
    ws = world(drv)
    drv.wait(lambda: nearest(ws, kind) is not None, 10, f"a {kind}")
    for _ in range(6):
        m = nearest(ws, kind)
        walk_to(drv, m.pos[0], m.pos[1])
        drv.step(5)
        m = nearest(ws, kind)
        if m and math.hypot(m.pos[0] - ws.player.x, m.pos[1] - ws.player.y) < 34:
            break
    m = nearest(ws, kind)
    cx, cy = ws.cam
    drv.click_at(drv.game.display.to_window(m.pos[0] - cx, m.pos[1] - cy - 8))   # left click = attack
    drv.wait_scene("CombatQuizScene", 6)
    return m


def beat(drv: Driver, ws, m) -> None:
    """Swing (Space) at a monster whose shield is down until it falls."""
    for _ in range(60):
        if not m.alive or m.id not in ws.entities:
            return
        if drv.top_is("CombatQuizScene"):          # its shield came back (elites) - not expected here
            raise AssertionError("unexpected question")
        drv.press(pygame.K_SPACE)
        drv.step(20)
    raise AssertionError("monster did not fall")


def run_combat_flow(workdir: Path, shots: Path | None = None) -> None:
    server = ServerProcess(workdir)
    try:
        url = server.url
        token, uid = make_account(url, "detu_c", "Chiến Sĩ")
        for hz in "水火木山人日口大":
            server.sql("insert or replace into collection(user_id, word_id, introduced, mastery, times_correct, "
                       "times_wrong, needs_review, first_seen_at) select ?, id, 1, 60, 0, 0, 0, datetime('now') "
                       "from words where hanzi=?", (uid, hz))
        # stand at the edge of the Mực Con area in Rừng Mực Loang, with the quest-1 brush
        server.sql("update characters set zone_id='rung_muc_loang', x=?, y=? where user_id=?", (16 * 18, 16 * 20, uid))
        h = {"Authorization": f"Bearer {token}"}
        import httpx
        inst = server.sql("select count(*) from equipment_instances")[0][0]
        server.sql("insert into equipment_instances(user_id, item_id, rarity, enhance_level, inscriptions, "
                   "equipped_slot) values (?, 'but_long_go', 'pham', 0, '[]', 'weapon')", (uid,))
        server.sql("insert into equipment_instances(user_id, item_id, rarity, enhance_level, inscriptions, "
                   "equipped_slot) values (?, 'non_la', 'linh', 2, '[]', NULL)", (uid,))
        assert inst == 0
        server.sql("insert into inventory_items(user_id, item_id, quantity, bound) values (?, 'hoi_huyet_dan', 3, 0)",
                   (uid,))
        server.sql("insert into inventory_items(user_id, item_id, quantity, bound) values (?, 'muc_tinh', 6, 0)",
                   (uid,))
        httpx.get(url + "/quests", headers=h)
        (workdir / "session.json").write_text(json.dumps({"token": token, "username": "detu_c", "server_url": url}))
        drv = Driver(url, workdir, shots)
        drv.click("menu_start")
        drv.wait(lambda: world(drv) is not None and world(drv).joined, 15, "forest")
        drv.wait_api()
        ws = world(drv)
        assert ws.zone_id == "rung_muc_loang"

        # fight: the first hit brings the Vấn Đạo card, the character is protected meanwhile
        m = engage(drv, server)
        drv.shot("combat_question")
        assert drv.game.top.compact and drv.game.top.q["context"] == "combat"
        res = answer_current_quiz(drv, server, correct=True)
        assert res["combat"]["shield_broken"]
        drv.step(8)
        drv.shot("shield_broken")
        drv.wait(lambda: not drv.top_is("CombatQuizScene"), 5, "card closes by itself")
        beat(drv, ws, m)
        drv.wait(lambda: any("Linh Thạch" in t or "Nhận" in t for t in drv.toast_log) or
                 any(f.text.startswith("+") for f in ws.fx.texts), 6, "loot")
        drv.shot("loot")

        # a wrong answer: Mặc Kích (10% of max HP, minus Kháng Mực), red flash
        hp0 = drv.game.state.character.get("hp")
        m2 = engage(drv, server)
        res = answer_current_quiz(drv, server, correct=False)
        assert res["combat"]["mac_kich"] > 0
        drv.step(6)
        drv.shot("mac_kich")
        drv.wait(lambda: not drv.top_is("CombatQuizScene"), 5, "wrong card closes")
        drv.wait(lambda: drv.game.state.character.get("hp", 0) < hp0, 5, "hp drops")
        drv.press(pygame.K_q)              # Hồi Huyết Đan
        drv.wait_api()
        # the next question comes after a short pause; answer it and finish the fight
        drv.wait_scene("CombatQuizScene", 8)
        answer_current_quiz(drv, server, correct=True)
        drv.wait(lambda: not drv.top_is("CombatQuizScene"), 5, "card closes")
        beat(drv, ws, m2)

        # the screens
        drv.press(pygame.K_k)
        drv.wait_scene("CharacterScene")
        drv.wait(lambda: drv.game.top.inv is not None and drv.game.state.cult, 5, "character data")
        drv.shot("cultivation")
        drv.press(pygame.K_ESCAPE)
        drv.press(pygame.K_TAB)
        drv.wait_scene("BagScene")
        drv.click("bag_tab_gear")
        drv.wait(lambda: drv.game.top.inv is not None, 5, "inventory")
        drv.shot("bag_gear")
        drv.click("bag_tab_items")
        drv.shot("bag_items")
        drv.press(pygame.K_ESCAPE)
        drv.press(pygame.K_j)
        drv.wait_scene("QuestScene")
        drv.wait(lambda: drv.game.state.quests, 5, "quests")
        drv.shot("quests")
        drv.press(pygame.K_ESCAPE)
        drv.press(pygame.K_b)
        drv.wait_scene("BookScene")
        drv.click("book_to_monsters")
        drv.wait(lambda: drv.top_is("MonsterBookScene") and drv.game.top.data, 5, "monster book")
        drv.shot("monster_book")
        drv.press(pygame.K_ESCAPE)
        from client.scenes.rpg import ForgeScene
        drv.game.push(ForgeScene(drv.game))
        drv.wait(lambda: drv.game.top.inv is not None, 5, "forge")
        drv.shot("forge")
        nonla = next(e for e in drv.game.top.inv["equipment"] if e["item_id"] == "non_la")
        drv.click(f"forge_{nonla['id']}")
        drv.wait_api()
        drv.press(pygame.K_ESCAPE)

        # Thiên Kiếp from Luyện Khí 9 with full Tu Vi and a Trúc Cơ Đan
        server.sql("update characters set realm='luyen_khi', realm_stage=9, cultivation_xp=500 where user_id=?", (uid,))
        server.sql("insert into inventory_items(user_id, item_id, quantity, bound) values (?, 'truc_co_dan', 1, 1)",
                   (uid,))
        drv.press(pygame.K_k)
        drv.wait_scene("CharacterScene")
        drv.wait(lambda: drv.game.state.cult.get("can_tribulation"), 5, "can break through")
        drv.click("ch_trib")
        drv.wait_scene("TribulationScene")
        drv.shot("tribulation_intro")
        drv.click("trib_go")
        for i in range(20):
            drv.wait_scene("QuizScene", 8)
            if i == 3:
                drv.shot("tribulation_question")
            answer_current_quiz(drv, server, correct=(i != 5))       # 19/20
            drv.click("quiz_continue")
        drv.wait(lambda: drv.top_is("TribulationScene") and drv.game.top.state == "done", 8, "result")
        drv.step(10)
        drv.shot("tribulation_passed")
        assert drv.game.top.result["passed"]
        assert server.sql("select realm, realm_stage from characters where user_id=?", (uid,))[0] == ("truc_co", 1)
        drv.close()
    finally:
        server.stop()


def test_combat_and_tribulation_ui():
    with tempfile.TemporaryDirectory() as tmp:
        run_combat_flow(Path(tmp))
