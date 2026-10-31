"""Pixel-perfect display (spec 18): the world is drawn on a 480x270 surface and scaled
by a whole number (x2, x3, x4) with black bars if the window does not divide evenly.
Interface text and the big question cards are drawn afterwards at the real window
resolution so Chinese characters stay sharp. UI code uses base coordinates (480x270)
and this class converts them."""
from __future__ import annotations

import pygame

BASE_W, BASE_H = 480, 270


class Display:
    def __init__(self, scale_pref: int = 0, fullscreen: bool = False, size: tuple[int, int] | None = None):
        self.scale_pref = scale_pref
        self.fullscreen = fullscreen
        self.world = pygame.Surface((BASE_W, BASE_H))
        info = pygame.display.Info()
        if size is None:
            avail_w = info.current_w if info.current_w > 0 else 1440
            avail_h = info.current_h if info.current_h > 0 else 900
            s = scale_pref or max(1, min((avail_w - 80) // BASE_W, (avail_h - 120) // BASE_H, 4))
            size = (BASE_W * s, BASE_H * s)
        flags = pygame.RESIZABLE | (pygame.FULLSCREEN if fullscreen else 0)
        self.window = pygame.display.set_mode((0, 0) if fullscreen else size, flags)
        pygame.display.set_caption("Khu Vườn Tu Tiên · 字园仙途")
        self._recompute()

    def _recompute(self) -> None:
        w, h = self.window.get_size()
        fit = max(1, min(w // BASE_W, h // BASE_H))
        self.scale = min(self.scale_pref, fit) if self.scale_pref else fit
        self.ox = (w - BASE_W * self.scale) // 2
        self.oy = (h - BASE_H * self.scale) // 2

    def on_resize(self) -> None:
        self.window = pygame.display.get_surface()
        self._recompute()

    def set_mode(self, scale_pref: int, fullscreen: bool) -> None:
        self.scale_pref = scale_pref
        if fullscreen != self.fullscreen:
            self.fullscreen = fullscreen
            if fullscreen:
                self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.RESIZABLE)
            else:
                s = scale_pref or 2
                self.window = pygame.display.set_mode((BASE_W * s, BASE_H * s), pygame.RESIZABLE)
        elif scale_pref and not fullscreen:
            self.window = pygame.display.set_mode((BASE_W * scale_pref, BASE_H * scale_pref), pygame.RESIZABLE)
        self._recompute()

    # ------------------------------------------------------------ frame
    def present_world(self) -> None:
        self.window.fill((0, 0, 0))
        scaled = pygame.transform.scale(self.world, (BASE_W * self.scale, BASE_H * self.scale))
        self.window.blit(scaled, (self.ox, self.oy))

    # ------------------------------------------------------------ coords
    def to_base(self, pos: tuple[int, int]) -> tuple[float, float]:
        return ((pos[0] - self.ox) / self.scale, (pos[1] - self.oy) / self.scale)

    def to_window(self, x: float, y: float) -> tuple[int, int]:
        return (int(self.ox + x * self.scale), int(self.oy + y * self.scale))

    def rect(self, x: float, y: float, w: float, h: float) -> pygame.Rect:
        return pygame.Rect(int(self.ox + x * self.scale), int(self.oy + y * self.scale),
                           int(w * self.scale), int(h * self.scale))
