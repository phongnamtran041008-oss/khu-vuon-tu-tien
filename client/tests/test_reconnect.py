"""Spec 15.1/15.5: the server restarts while a player stands in Trúc Lâm Thôn. The game
shows the offline banner, reconnects by itself and puts the character back in place."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pygame

from client.tests.driver import Driver, ServerProcess
from client.tests.test_flow import advance_dialogs
from client.tests.test_world_flow import make_account


def test_reconnect_after_server_restart():
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        server = ServerProcess(workdir)
        try:
            token, _ = make_account(server.url, "detu_r", "Về Lại")
            (workdir / "session.json").write_text(json.dumps({"token": token, "username": "detu_r",
                                                              "server_url": server.url}))
            drv = Driver(server.url, workdir)
            drv.click("menu_start")
            drv.wait(lambda: "AbodeScene" in drv.scene_names(), 10, "abode")
            drv.wait_api()
            advance_dialogs(drv)
            drv.wait(lambda: drv.game.net is not None and drv.game.net.online, 10, "online")
            drv.hold([pygame.K_s], 0.9)
            drv.press(pygame.K_e)
            drv.wait(lambda: drv.game.world_scene() is not None and drv.game.world_scene().joined, 10, "village")
            ws = drv.game.world_scene()
            drv.hold([pygame.K_w], 0.5)
            drv.step(20)
            pos = (ws.player.x, ws.player.y)
            port = server.port
            server.stop()          # saves positions on shutdown
            drv.wait(lambda: not drv.game.net.online, 10, "offline")
            assert drv.game.net.connected_once  # -> the offline banner is shown
            server = ServerProcess(workdir, port=port)
            drv.wait(lambda: drv.game.net.online and drv.game.world_scene() is not None
                     and drv.game.world_scene().joined, 40, "reconnected and back in the village")
            ws = drv.game.world_scene()
            assert ws.zone_id == "truc_lam_thon"
            assert abs(ws.player.x - pos[0]) < 1 and abs(ws.player.y - pos[1]) < 1
            drv.close()
        finally:
            server.stop()
