"""Scene stack. The bottom scene usually draws the pixel world; scenes pushed on top are
overlays drawn at window resolution. Only the top scene receives input."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .. import strings_vi as T

if TYPE_CHECKING:
    from ..main import Game
    from ..ui.kit import UI


class Scene:
    modal = True          # dims what is below
    draws_world = False
    opaque = False        # True: scenes below are not drawn at all (still updated)
    toast_y = 4           # toasts sit above the panels; world scenes move them under their HUD card

    def __init__(self, game: "Game"):
        self.game = game

    @property
    def api(self):
        return self.game.api

    def on_enter(self) -> None: ...
    def on_exit(self) -> None: ...
    def on_resume(self) -> None: ...
    def update(self, dt: float, top: bool) -> None: ...
    def draw_world(self, surf: pygame.Surface) -> None: ...
    def draw_ui(self, ui: "UI") -> None: ...

    def close(self) -> None:
        self.game.pop(self)


class MessageBox(Scene):
    """Simple modal message with one or two buttons."""

    def __init__(self, game, text: str, title: str | None = None, ok: str = T.OK,
                 cancel: str | None = None, on_ok=None, on_cancel=None, width: float = 260):
        super().__init__(game)
        self.text, self.title, self.ok, self.cancel = text, title, ok, cancel
        self.on_ok, self.on_cancel, self.width = on_ok, on_cancel, width

    def draw_ui(self, ui):
        ui.dim()
        lines = ui.f.wrap(self.text, 8, int((self.width - 24) * ui.s), ui.s)
        lh = ui.text_size("Ag", 8)[1] * (1.15 if len(lines) > 1 else 1)    # the line gap ui.text uses
        h = 42 + len(lines) * lh
        x, y = (480 - self.width) / 2, (270 - h) / 2
        ui.panel(x, y, self.width, h, self.title)
        ui.text(self.text, x + 12, y + 12, 8, max_w=self.width - 24)
        bw = 70
        if self.cancel:
            if ui.button("msg_cancel", x + self.width / 2 - bw - 6, y + h - 22, bw, 15, self.cancel,
                         key=pygame.K_ESCAPE):
                self.close()
                if self.on_cancel:
                    self.on_cancel()
                return
            ox = x + self.width / 2 + 6
        else:
            ox = x + (self.width - bw) / 2
        if ui.button("msg_ok", ox, y + h - 22, bw, 15, self.ok, key=pygame.K_RETURN, style="primary") or \
                (not self.cancel and ui.key(pygame.K_ESCAPE)):
            self.close()
            if self.on_ok:
                self.on_ok()
