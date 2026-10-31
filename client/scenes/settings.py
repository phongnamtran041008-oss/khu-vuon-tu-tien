from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..config import normalize_url
from .base import Scene


class SettingsScene(Scene):
    def __init__(self, game, in_game: bool = False):
        super().__init__(game)
        self.in_game = in_game
        cfg = game.cfg
        self.scale = cfg.window_scale
        self.fullscreen = cfg.fullscreen
        self.sfx = cfg.sfx_volume
        self.voice = cfg.voice_volume
        game.ui.set_value("set_server", game.api.base_url)

    def _slider(self, ui, wid, x, y, w, value) -> float:
        ui.progress(x, y, w, 8, value, "#6A994E")
        ui.widgets[wid] = ui.rect(x, y, w, 8)
        if ui.inp.mouse_down and ui.hover(x, y - 3, w, 14):
            value = max(0.0, min(1.0, (ui.inp.mouse[0] - x) / w))
        return value

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 110, 30, 260, 210
        ui.panel(x, y, w, h, T.SETTINGS_TITLE)
        ui.text(T.SCALE, x + 14, y + 18, 8)
        for i, sc in enumerate([0, 1, 2, 3, 4]):
            label = T.SCALE_AUTO if sc == 0 else f"x{sc}"
            if ui.button(f"scale_{sc}", x + 14 + i * 47, y + 29, 44, 14, label, selected=self.scale == sc):
                self.scale = sc
        if ui.button("fullscreen", x + 14, y + 49, 120, 14, T.FULLSCREEN + (": Bật" if self.fullscreen else ": Tắt"),
                     selected=self.fullscreen):
            self.fullscreen = not self.fullscreen
        ui.text(T.SFX_VOLUME, x + 14, y + 70, 8)
        self.sfx = self._slider(ui, "sfx", x + 120, y + 72, 120, self.sfx)
        ui.text(T.VOICE_VOLUME, x + 14, y + 86, 8)
        self.voice = self._slider(ui, "voice", x + 120, y + 88, 120, self.voice)
        if self.game.lan_mode:   # LAN worlds: no fixed server; show how friends reach this world
            host = self.game.host
            if host is not None and host.alive():
                ui.text(T.WORLD_LAN_ADDR, x + 14, y + 104, 8)
                ui.text(", ".join(host.lan_urls()) or f"127.0.0.1:{host.port}", x + 14, y + 116, 8, "#4F7A3A",
                        max_w=w - 28)
            else:
                ui.text(T.WORLD_PLAYING_ON.format(url=self.game.api.base_url), x + 14, y + 108, 7, "#5A5A5A",
                        max_w=w - 28)
        else:
            ui.text(T.SERVER, x + 14, y + 104, 8)
            ui.input_box("set_server", x + 14, y + 114, w - 28, 15, max_len=120)
        if self.in_game and ui.button("logout", x + 14, y + 140, 110, 15,
                                      T.WORLD_LEAVE if self.game.lan_mode else T.LOGOUT):
            self.logout()
            return
        if ui.button("set_cancel", x + w - 160, y + h - 24, 70, 15, T.CANCEL, key=pygame.K_ESCAPE):
            self.close()
            return
        if ui.button("set_save", x + w - 84, y + h - 24, 70, 15, T.SAVE, style="primary"):
            self.save()

    def save(self) -> None:
        g = self.game
        cfg = g.cfg
        cfg.window_scale, cfg.fullscreen = self.scale, self.fullscreen
        cfg.sfx_volume, cfg.voice_volume = round(self.sfx, 2), round(self.voice, 2)
        g.audio.sfx_volume, g.audio.voice_volume = cfg.sfx_volume, cfg.voice_volume
        url = "" if g.lan_mode else normalize_url(g.ui.value("set_server"))
        if g.lan_mode:
            pass
        elif not url and cfg.server_list_url:
            # an empty box hands the choice back to server_list_url (stage 10)
            g.session.save(server_manual=False)
            g._fetch_server_list()
        elif url and url != g.api.base_url:
            cfg.server_url = url
            g.api.set_base_url(url)
            g.session.save(server_url=url, server_manual=True)
            if not self.in_game:
                g.set_token(None)
            g.check_version()
        cfg.save()
        g.display.set_mode(cfg.window_scale, cfg.fullscreen)
        self.close()

    def logout(self) -> None:
        from .menu import MenuScene
        self.game.leave_abode()
        self.game.disconnect_world()
        self.game.set_token(None)
        if self.game.lan_mode:   # leaving a world: like Minecraft, closing your own world stops it
            from .play import PlayScene
            self.game.stop_host()
            self.game.replace_all(PlayScene(self.game))
            return
        self.game.replace_all(MenuScene(self.game))


class CreditsScene(Scene):
    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 80, 40, 320, 190
        ui.panel(x, y, w, h, T.CREDITS_TITLE)
        ui.text(T.CREDITS_TEXT, x + 16, y + 18, 8, max_w=w - 32)
        if ui.button("cr_close", 240 - 35, y + h - 24, 70, 15, T.CLOSE, key=pygame.K_ESCAPE, style="primary"):
            self.close()
