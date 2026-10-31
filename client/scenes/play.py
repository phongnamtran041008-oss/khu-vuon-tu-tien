"""Choose where to play (LAN worlds, Minecraft style):

- "Thế giới của tôi": worlds saved on this PC. Opening one starts its server here, opens it
  to the LAN and joins it; everything players do in it is saved in that world's folder.
- "Tham gia mạng LAN": worlds other players on the same network have opened (found by
  their LAN announcement), or an address typed by hand.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pygame

from .. import strings_vi as T
from .. import worlds as W
from .base import Scene
from .menu import TitleBackground

ROWS = 7


class PlayScene(Scene):
    draws_world = True

    def __init__(self, game, notice: str = ""):
        super().__init__(game)
        self.bg = TitleBackground()
        self.dt = 0.0
        self.tab = "mine"
        self.status, self.status_err = notice, bool(notice)
        self.busy = False
        self.worlds = W.list_worlds()
        self.selected = self.worlds[0].slug if self.worlds else None
        self.picked_lan: tuple[str, int] | None = None
        self.scanner = None
        self.wait_until = 0.0
        self.next_ping = 0.0
        game.ui.set_value("pl_new", "")
        game.ui.set_value("pl_addr", game.session.data.get("last_lan_addr", ""))

    # ------------------------------------------------------------ lifecycle
    def on_exit(self):
        self._stop_scan()

    def _start_scan(self):
        if self.scanner is None:
            from ..net.lan import LanScanner
            self.scanner = LanScanner()

    def _stop_scan(self):
        if self.scanner is not None:
            self.scanner.close()
            self.scanner = None

    def update(self, dt, top):
        self.dt = dt
        host = self.game.host
        if not (self.busy and self.wait_until and host):
            return
        now = self.game.now
        if not host.alive():
            self.wait_until = 0.0
            self._fail(T.WORLD_HOST_DIED.format(log=host.log_tail(3)))
        elif now > self.wait_until:
            self.wait_until = 0.0
            self._fail(T.WORLD_HOST_SLOW)
        elif now >= self.next_ping:
            self.next_ping = now + 0.5

            def ready(_):
                if self.wait_until:
                    self.wait_until = 0.0
                    self._join(host.url)
            self.api.get(host.url + "/healthz", ready, lambda e: None, retries=0, timeout=1)

    def draw_world(self, surf):
        self.bg.draw(surf, self.dt)

    # ------------------------------------------------------------ actions
    def _fail(self, msg: str) -> None:
        self.busy, self.status, self.status_err = False, msg, True

    def _say(self, msg: str) -> None:
        self.status, self.status_err = msg, False

    def _join(self, url: str) -> None:
        self._say(T.WORLD_JOINING)
        self.game.join_world(url, self._fail)

    def open_world(self) -> None:
        world = next((w for w in self.worlds if w.slug == self.selected), None)
        if world is None:
            return
        self.busy = True
        try:
            self.game.open_world(world)
        except (OSError, RuntimeError) as e:
            self._fail(T.WORLD_HOST_FAILED.format(err=e))
            return
        self._say(T.WORLD_OPENING.format(name=world.name))
        self.wait_until = self.game.now + 120     # first start migrates the new database
        self.next_ping = self.game.now + 0.8

    def create_world(self) -> None:
        name = self.game.ui.value("pl_new").strip()
        if not name:
            self._fail(T.WORLD_NEED_NAME)
            return
        w = W.create(name)
        self.worlds = W.list_worlds()
        self.selected = w.slug
        self.game.ui.set_value("pl_new", "")
        self._say(T.WORLD_CREATED.format(name=w.name))

    def join_lan(self, ip: str, port: int) -> None:
        self.game.stop_host()
        self.busy = True
        self._join(f"http://{ip}:{port}")

    def join_typed(self) -> None:
        addr = self.game.ui.value("pl_addr").strip()
        if not addr:
            return
        if "://" not in addr and ":" not in addr:   # a bare LAN IP; https://...trycloudflare.com stays as is
            addr += ":8000"
        self.game.session.save(last_lan_addr=addr)
        self.game.stop_host()
        self.busy = True
        self._join(addr)

    def open_folder(self) -> None:
        world = next((w for w in self.worlds if w.slug == self.selected), None)
        path = str(world.path if world else W.worlds_dir())
        try:
            if sys.platform == "win32":
                os.startfile(path)   # noqa: S606 - the player's own folder
            else:
                import subprocess
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
        except OSError:
            self._say(path)

    def sign_out(self) -> None:
        from .account import AccountScene
        self.game.stop_host()
        self.game.firebase.sign_out()
        self.game.replace_all(AccountScene(self.game))

    # ------------------------------------------------------------ ui
    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (20, 18, 15, 120))
        x, y, w, h = 40, 16, 400, 228
        ui.panel(x, y, w, h)
        for i, (k, label) in enumerate((("mine", T.WORLD_TAB_MINE), ("lan", T.WORLD_TAB_LAN))):
            if ui.button(f"pltab_{k}", x + 12 + i * 126, y + 8, 122, 15, label, selected=self.tab == k,
                         enabled=not self.busy):
                self.tab, self.status = k, ""
        if self.tab == "lan":
            self._start_scan()
            self._draw_lan(ui, x, y, w)
        else:
            self._stop_scan()
            self._draw_mine(ui, x, y, w)
        if self.status:
            ui.text(self.status, 240, y + h - 40, 7, "#BC4749" if self.status_err else "#4F7A3A",
                    anchor="midtop", max_w=w - 24)
        fb = self.game.firebase
        ui.text(T.WORLD_SIGNED_IN.format(email=fb.email), x + 12, y + h - 12, 7, "#5A5A5A", anchor="midleft")
        if ui.button("pl_signout", x + w - 92, y + h - 19, 80, 13, T.FB_SIGN_OUT, size=7, enabled=not self.busy):
            self.sign_out()
            return
        if ui.button("pl_back", 8, 250, 60, 14, T.BACK, key=pygame.K_ESCAPE, enabled=not self.busy):
            from .menu import MenuScene
            self.game.replace_all(MenuScene(self.game))

    def _draw_mine(self, ui, x, y, w):
        ly = y + 30
        if not self.worlds:
            ui.text(T.WORLD_NONE, 240, ly + 40, 8, "#5A5A5A", anchor="center", max_w=w - 40)
        for i, world in enumerate(self.worlds[:ROWS]):
            ry = ly + i * 17
            sel = world.slug == self.selected
            if ui.button(f"plw_{world.slug}", x + 12, ry, w - 24, 15, "", selected=sel, enabled=not self.busy):
                self.selected = world.slug
            color = "#FFFFFF" if sel else "#2B2B2B"
            ui.text(world.name, x + 18, ry + 7.5, 8, color, anchor="midleft")
            when = dt.datetime.fromtimestamp(world.last_played).strftime("%d/%m/%Y %H:%M")
            ui.text(T.WORLD_ROW.format(when=when, kb=world.size_kb), x + w - 18, ry + 7.5, 7,
                    "#E3D5BA" if sel else "#8E877A", anchor="midright")
        by = ly + ROWS * 17 + 4
        ui.input_box("pl_new", x + 12, by, 170, 15, placeholder=T.WORLD_NEW_PLACEHOLDER, max_len=32)
        if ui.button("pl_create", x + 186, by, 60, 15, T.WORLD_CREATE, enabled=not self.busy) or ui.submitted("pl_new"):
            self.create_world()
        if ui.button("pl_folder", x + 250, by, 60, 15, T.WORLD_FOLDER, size=7, enabled=not self.busy):
            self.open_folder()
        if ui.button("pl_open", x + w - 86, by, 74, 15, T.WORLD_OPEN, style="primary",
                     enabled=bool(self.selected) and not self.busy, key=pygame.K_RETURN):
            self.open_world()

    def _draw_lan(self, ui, x, y, w):
        ly = y + 30
        servers = self.scanner.servers() if self.scanner else []
        if self.scanner and self.scanner.error:
            ui.text(T.LAN_LISTEN_FAILED.format(err=self.scanner.error), x + 14, ly, 7, "#BC4749", max_w=w - 28)
        elif not servers:
            dots = "." * (1 + int(self.game.now * 2) % 3)
            ui.text(T.LAN_SEARCHING + dots, 240, ly + 30, 8, "#5A5A5A", anchor="center")
            ui.text(T.LAN_HINT, 240, ly + 46, 7, "#8E877A", anchor="midtop", max_w=w - 60)
        for i, s in enumerate(servers[:ROWS - 1]):
            ry = ly + i * 17
            key = (s["ip"], s["port"])
            sel = key == self.picked_lan
            if ui.button(f"pll_{s['ip']}_{s['port']}", x + 12, ry, w - 24, 15, "", selected=sel, enabled=not self.busy):
                self.picked_lan = key
            color = "#FFFFFF" if sel else "#2B2B2B"
            label = s["name"] + (f" — {s['host']}" if s["host"] else "")
            ui.text(label, x + 18, ry + 7.5, 8, color, anchor="midleft")
            ui.text(T.LAN_ROW.format(n=s["online"], addr=f"{s['ip']}:{s['port']}"), x + w - 18, ry + 7.5, 7,
                    "#E3D5BA" if sel else "#8E877A", anchor="midright")
        if self.picked_lan and self.picked_lan not in {(s["ip"], s["port"]) for s in servers}:
            self.picked_lan = None
        by = ly + ROWS * 17 + 4
        ui.input_box("pl_addr", x + 12, by, 170, 15, placeholder=T.LAN_ADDR_PLACEHOLDER, max_len=80)
        if ui.button("pl_connect", x + 186, by, 70, 15, T.LAN_CONNECT, enabled=not self.busy) or ui.submitted("pl_addr"):
            self.join_typed()
        if ui.button("pl_join", x + w - 86, by, 74, 15, T.LAN_JOIN, style="primary",
                     enabled=bool(self.picked_lan) and not self.busy):
            self.join_lan(*self.picked_lan)
