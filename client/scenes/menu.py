from __future__ import annotations

import math
import random

import pygame

from .. import strings_vi as T
from ..config import GAME_VERSION
from ..engine import sprites
from ..engine.tilemap import load_map
from .base import Scene


class TitleBackground:
    """The abode seen from above, drifting slowly, behind menus — with a warm sunrise
    wash, drifting motes of linh khí, and a soft vignette so the scene reads with depth."""

    MOTE_COUNT = 24

    def __init__(self):
        self.map = load_map("abode")
        self.t = 0.0
        rng = random.Random(0xA60E)   # a fixed seed so the atmosphere feels designed, not random
        self.motes = [{"x": rng.uniform(0, 480), "y": rng.uniform(0, 270),
                       "speed": rng.uniform(4, 10), "amp": rng.uniform(4, 10),
                       "phase": rng.uniform(0, math.tau), "size": rng.choice((1, 1, 1, 2)),
                       "hue": rng.choice(((255, 228, 140), (255, 205, 150), (210, 235, 255)))}
                      for _ in range(self.MOTE_COUNT)]
        self._wash: pygame.Surface | None = None
        self._vignette: pygame.Surface | None = None

    def _warm_wash(self, w: int, h: int) -> pygame.Surface:
        """Sunrise-to-dusk wash: warm orange at the top, cool indigo at the bottom, so the
        garden reads like late afternoon instead of flat noon."""
        if self._wash is None or self._wash.get_size() != (w, h):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for y in range(h):
                t = y / max(h - 1, 1)
                if t < 0.5:   # upper half: warm sun wash
                    a = int(110 * (1.0 - t * 2) ** 1.5)
                    if a > 0:
                        pygame.draw.line(surf, (255, 180, 90, a), (0, y), (w, y))
                else:         # lower half: cool shadow wash for depth
                    a = int(85 * ((t - 0.5) * 2) ** 1.5)
                    if a > 0:
                        pygame.draw.line(surf, (50, 55, 110, a), (0, y), (w, y))
            self._wash = surf
        return self._wash

    def _vignette_surf(self, w: int, h: int) -> pygame.Surface:
        if self._vignette is None or self._vignette.get_size() != (w, h):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            cx, cy = w / 2, h / 2
            max_r = math.hypot(cx, cy)
            for y in range(h):
                for x in range(w):
                    d = math.hypot(x - cx, y - cy) / max_r
                    a = int(240 * max(0.0, d - 0.45) ** 1.8)
                    if a > 0:
                        surf.set_at((x, y), (10, 6, 4, min(a, 210)))
            self._vignette = surf
        return self._vignette

    def draw(self, surf: pygame.Surface, dt: float) -> None:
        self.t += dt
        w, h = surf.get_width(), surf.get_height()
        cx = int(80 + 60 * pygame.math.Vector2(1, 0).rotate(self.t * 4).x)
        cy = 40
        self.map.draw_ground(surf, (cx, cy), self.t)
        for o in sorted(self.map.objects, key=lambda o: o.foot_y):
            name = o.props.get("sprite")
            if name:
                img = sprites.prop(name, int(o.props.get("variant", 0) or 0), int(self.t * 2) % 4)
                surf.blit(img, (int(o.x) - cx, int(o.y) - cy))
        tl = sprites.truc_lao()[0]
        for o in self.map.find("npc"):
            surf.blit(tl, (int(o.x) - cx, int(o.y) - cy))
        surf.blit(self._warm_wash(w, h), (0, 0))
        for m in self.motes:
            mx = (m["x"] + m["speed"] * self.t * 0.6) % (w + 20) - 10
            my = m["y"] + math.sin(self.t * 0.7 + m["phase"]) * m["amp"]
            if 0 <= my < h:
                twinkle = 0.55 + 0.45 * math.sin(self.t * 2.2 + m["phase"])
                alpha = int(150 * twinkle)
                if alpha > 0:
                    size = m["size"]
                    glow = pygame.Surface((size * 6, size * 6), pygame.SRCALPHA)
                    pygame.draw.circle(glow, (*m["hue"], alpha // 3), glow.get_rect().center, size * 3)
                    pygame.draw.circle(glow, (*m["hue"], alpha), glow.get_rect().center, size)
                    surf.blit(glow, (int(mx) - glow.get_width() // 2, int(my) - glow.get_height() // 2))
        surf.blit(self._vignette_surf(w, h), (0, 0))


class MenuScene(Scene):
    draws_world = True

    def __init__(self, game):
        super().__init__(game)
        self.bg = TitleBackground()
        self.dt = 0.0

    def on_enter(self):
        if not self.game.lan_mode:      # LAN worlds check the version of the world they join instead
            self.game.check_version()   # spec 15.5 (also fills the notices drawn below)

    def update(self, dt, top):
        self.dt = dt

    def draw_world(self, surf):
        self.bg.draw(surf, self.dt)

    def draw_notices(self, ui, y: int) -> None:
        """Maintenance / announcement / newer exe from /server/info (stage 10)."""
        info = self.game.server_info
        if self.game.update:        # a newer release on GitHub
            if ui.button("menu_update", 140, y - 7, 200, 14, T.UPDATE_MENU.format(v=self.game.update["version"]),
                         style="gold", size=7):
                self.game.offer_update()
        elif info.get("maintenance_message"):
            ui.text(T.MAINTENANCE.format(text=info["maintenance_message"]), 240, y, 7, "#BC4749",
                    anchor="center", max_w=210)
        elif info.get("announcement"):
            ui.text(T.ANNOUNCEMENT.format(text=info["announcement"]), 240, y, 7, "#8E5AC8",
                    anchor="center", max_w=210)
        elif self.game.newer_client():
            ui.text(T.NEW_VERSION.format(version=self.game.newer_client()), 240, y, 7, "#4A7CC8",
                    anchor="center", max_w=210)

    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (20, 18, 15, 120))
        ui.panel(130, 30, 220, 205)
        ui.text(T.SUBTITLE, 240, 52, 16, "#BC4749", kind="han", anchor="center")
        ui.text(T.TITLE, 240, 80, 18, "#2B2B2B", anchor="center")
        ui.text(T.TAGLINE, 240, 98, 8, "#5A5A5A", anchor="center")
        y = 114
        if ui.button("menu_start", 180, y, 120, 18, T.MENU_START, key=pygame.K_RETURN, style="primary"):
            self.start()
        if ui.button("menu_settings", 180, y + 24, 120, 16, T.MENU_SETTINGS):
            from .settings import SettingsScene
            self.game.push(SettingsScene(self.game))
        if ui.button("menu_credits", 180, y + 46, 120, 16, T.MENU_CREDITS):
            from .settings import CreditsScene
            self.game.push(CreditsScene(self.game))
        if ui.button("menu_quit", 180, y + 68, 120, 16, T.MENU_QUIT):
            self.game.running = False
        self.draw_notices(ui, 210)
        where = (self.game.firebase.email or T.FB_NOT_SIGNED_IN) if self.game.lan_mode else self.api.base_url
        ui.text(f"v{GAME_VERSION} · {where}", 240, 226, 7, "#8E877A", anchor="center")

    def start(self) -> None:
        from .login import LoginScene
        if self.game.lan_mode:
            from .account import AccountScene
            from .play import PlayScene
            g = self.game
            g.push(PlayScene(g) if g.firebase.signed_in else AccountScene(g))
            return
        if not self.game.version_ok:
            self.game.message(self.game.update_text())
            return
        if self.game.session.token:
            self.game.enter_game()
        else:
            self.game.push(LoginScene(self.game))
