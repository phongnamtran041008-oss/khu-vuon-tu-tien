"""Trúc Lão's dialogue box (spec 6.9): portrait in the corner, typewriter text."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..engine import sprites
from ..scenes.base import Scene


class DialogScene(Scene):
    modal = False

    def __init__(self, game, lines: list[str], speaker: str = T.MASTER, on_done=None, chars_per_sec: float = 55,
                 portrait: pygame.Surface | None = None):
        super().__init__(game)
        self.lines, self.speaker, self.on_done = list(lines), speaker, on_done
        self.portrait = portrait  # a 16x24 character; None = Trúc Lão
        self.i = 0
        self.t = 0.0
        self.cps = chars_per_sec

    def update(self, dt, top):
        if top:
            self.t += dt

    def _shown(self) -> int:
        return int(self.t * self.cps)

    def advance(self) -> None:
        line = self.lines[self.i]
        if self._shown() < len(line):
            self.t = len(line) / self.cps + 0.01
            return
        self.i += 1
        self.t = 0.0
        if self.i >= len(self.lines):
            self.close()
            if self.on_done:
                self.on_done()

    def draw_ui(self, ui):
        if self.i >= len(self.lines):
            return
        x, y, w, h = 20, 192, 440, 70
        ui.fill(x + 2, y + 2, w, h, (0, 0, 0, 90))
        ui.fill(x, y, w, h, "#F4EBD9")
        ui.border(x, y, w, h, "#8B5A2B", 2)
        if self.portrait is not None:
            head = self.portrait.subsurface(pygame.Rect(2, 1, 12, 11))
        else:
            head = sprites.truc_lao()[0 if int(ui.time * 0.7) % 6 else 1].subsurface(pygame.Rect(0, 0, 16, 12))
        ui.fill(x + 8, y + 8, 54, 42, "#E3D5BA")
        ui.border(x + 8, y + 8, 54, 42)
        ui.image(head, x + 35, y + 29, zoom=3, anchor="center")
        ui.fill(x + 8, y + 52, 54, 12, "#BC4749")
        ui.text(self.speaker, x + 35, y + 58, 8, "#FFFFFF", anchor="center")
        line = self.lines[self.i]
        ui.text(line[:self._shown()], x + 72, y + 9, 9, max_w=w - 84)
        if self._shown() >= len(line) and int(ui.time * 3) % 2 == 0:
            ui.text("▼" if ui.f._ui_has("▼") else "...", x + w - 14, y + h - 12, 8, "#BC4749")
        ui.widgets["dialog_next"] = ui.rect(x, y, w, h)
        if ui.click_in(0, 0, 480, 270) or ui.key(pygame.K_RETURN) or ui.key(pygame.K_SPACE) or ui.key(pygame.K_e):
            self.advance()
