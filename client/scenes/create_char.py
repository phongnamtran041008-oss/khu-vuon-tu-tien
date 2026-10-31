from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..engine import sprites
from .base import Scene
from .menu import TitleBackground


class CreateCharScene(Scene):
    draws_world = True

    def __init__(self, game):
        super().__init__(game)
        self.bg = TitleBackground()
        self.opts = {"hair_colors": ["#2B2B2B", "#5C3A21", "#A0522D", "#D9C27A", "#8E8E8E", "#6B3FA0"],
                     "hair_styles": ["ngan", "buoi", "dai"], "bodies": ["nam", "nu"]}
        self.app = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}
        self.t = 0.0
        self.dt = 0.0
        self.busy = False
        self.error = ""
        game.ui.set_focus("cc_name")
        self.api.get("/character/options", self._got_opts, lambda e: None)

    def _got_opts(self, o):
        self.opts.update({k: o[k] for k in ("hair_colors", "hair_styles", "bodies") if k in o})

    def update(self, dt, top):
        self.t += dt
        self.dt = dt

    def draw_world(self, surf):
        self.bg.draw(surf, self.dt)

    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (20, 18, 15, 130))
        x, y, w, h = 60, 22, 360, 226
        ui.panel(x, y, w, h, T.CREATE_TITLE)
        # preview: turns around slowly and walks in place
        frames = sprites.character(self.app)
        d = ("down", "left", "up", "right")[int(self.t / 1.5) % 4]
        f = (0, 1, 0, 2)[int(self.t * 6) % 4]
        ui.fill(x + 20, y + 22, 90, 110, "#E3D5BA")
        ui.border(x + 20, y + 22, 90, 110)
        ui.image(frames[(d, f)], x + 65, y + 125, zoom=4, anchor="midbottom")
        ui.text("Áo Vải Phàm Nhân", x + 65, y + 140, 7, "#5A5A5A", anchor="center")
        rx = x + 125
        ui.text(T.CHAR_NAME, rx, y + 20, 8)
        ui.input_box("cc_name", rx, y + 31, 210, 16, max_len=16)
        ui.text(T.HAIR_COLOR, rx, y + 54, 8)
        for i, c in enumerate(self.opts["hair_colors"]):
            bx = rx + i * 22
            ui.fill(bx, y + 65, 18, 14, c)
            ui.border(bx, y + 65, 18, 14, "#BC4749" if self.app["hair_color"] == c else "#2B2B2B",
                      2 if self.app["hair_color"] == c else 1)
            ui.widgets[f"hc_{i}"] = ui.rect(bx, y + 65, 18, 14)
            if ui.click_in(bx, y + 65, 18, 14):
                self.app["hair_color"] = c
        ui.text(T.HAIR_STYLE, rx, y + 86, 8)
        for i, st in enumerate(self.opts["hair_styles"]):
            if ui.button(f"hs_{st}", rx + i * 70, y + 97, 66, 14, T.HAIR_STYLES.get(st, st),
                         selected=self.app["hair_style"] == st):
                self.app["hair_style"] = st
        ui.text(T.BODY, rx, y + 118, 8)
        for i, b in enumerate(self.opts["bodies"]):
            if ui.button(f"bd_{b}", rx + i * 70, y + 129, 66, 14, T.BODIES.get(b, b), selected=self.app["body"] == b):
                self.app["body"] = b
        ui.text(T.CREATE_NOTE, x + 20, y + 158, 8, "#5A5A5A", max_w=w - 40)
        if self.error:
            ui.text(self.error, 240, y + 184, 8, "#BC4749", anchor="center")
        name = ui.value("cc_name").strip()
        go = ui.button("cc_go", 240 - 60, y + h - 26, 120, 18, T.CREATE_GO, style="primary",
                       enabled=bool(name) and not self.busy)
        if (go or (ui.submitted("cc_name") and name)) and not self.busy:
            self.create(name)
        if ui.button("cc_back", x + 10, y + h - 24, 60, 14, T.BACK, key=pygame.K_ESCAPE):
            self.game.set_token(None)
            from .menu import MenuScene
            self.game.replace_all(MenuScene(self.game))

    def create(self, name: str) -> None:
        self.busy, self.error = True, ""

        def ok(ch):
            self.busy = False
            self.game.state.character = ch
            self.game.enter_game()

        def err(e):
            self.busy = False
            self.error = e.message_vi
        self.api.post("/character/create", {"display_name": name, "appearance": dict(self.app)}, ok, err)
