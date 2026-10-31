"""Firebase account screen (LAN worlds): sign in, register, or get a password-reset e-mail.
Signed in once, the game remembers it (session.json) and goes straight to the world list."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from .base import Scene
from .menu import TitleBackground


class AccountScene(Scene):
    draws_world = True

    def __init__(self, game, notice: str = ""):
        super().__init__(game)
        self.bg = TitleBackground()
        self.tab = "login"
        self.status, self.status_err = notice, bool(notice)
        self.busy = False
        self.dt = 0.0
        game.ui.set_value("fb_email", game.session.data.get("last_email", ""))
        game.ui.set_focus("fb_pass" if game.ui.value("fb_email") else "fb_email")

    def update(self, dt, top):
        self.dt = dt

    def draw_world(self, surf):
        self.bg.draw(surf, self.dt)

    # ------------------------------------------------------------ actions
    def _fail(self, msg: str) -> None:
        self.busy, self.status, self.status_err = False, msg, True

    def _signed_in(self, _r) -> None:
        from .play import PlayScene
        self.busy = False
        self.game.session.save(last_email=self.game.firebase.email)
        self.game.replace_all(PlayScene(self.game))

    def submit(self) -> None:
        ui, fb = self.game.ui, self.game.firebase
        email, pw = ui.value("fb_email").strip(), ui.value("fb_pass")
        if not email:
            self._fail(T.FB_NEED_EMAIL)
            return
        if self.tab == "reset":
            self.busy, self.status, self.status_err = True, T.CONNECTING, False

            def sent():
                self.busy, self.status, self.status_err = False, T.FB_RESET_SENT.format(email=email), False
            fb.send_reset(email, sent, self._fail)
            return
        if not pw:
            self._fail(T.FB_NEED_PASSWORD)
            return
        if self.tab == "register" and pw != ui.value("fb_pass2"):
            self._fail(T.PASSWORDS_DIFFER)
            return
        self.busy, self.status, self.status_err = True, T.CONNECTING, False
        (fb.sign_up if self.tab == "register" else fb.sign_in)(email, pw, self._signed_in, self._fail)

    # ------------------------------------------------------------ ui
    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (20, 18, 15, 120))
        x, y, w, h = 120, 28, 240, 214
        ui.panel(x, y, w, h)
        ui.text(T.FB_TITLE, 240, y + 14, 12, anchor="center")
        tabs = [("login", T.LOGIN), ("register", T.REGISTER), ("reset", T.RECOVER)]
        for i, (k, label) in enumerate(tabs):
            if ui.button(f"fbtab_{k}", x + 12 + i * 73, y + 28, 70, 14, label, selected=self.tab == k):
                self.tab, self.status = k, ""
                ui.set_focus("fb_email")
        fy = y + 52
        ui.text(T.FB_EMAIL, x + 16, fy, 8)
        ui.input_box("fb_email", x + 16, fy + 10, w - 32, 15, max_len=120)
        last = "fb_email"
        if self.tab != "reset":
            ui.text(T.PASSWORD + (" (ít nhất 6 ký tự)" if self.tab == "register" else ""), x + 16, fy + 29, 8)
            ui.input_box("fb_pass", x + 16, fy + 39, w - 32, 15, password=True, max_len=128)
            last = "fb_pass"
        if self.tab == "register":
            ui.text(T.PASSWORD_AGAIN, x + 16, fy + 58, 8)
            ui.input_box("fb_pass2", x + 16, fy + 68, w - 32, 15, password=True, max_len=128)
            last = "fb_pass2"
        if self.tab == "reset":
            ui.text(T.FB_RESET_HINT, x + 16, fy + 32, 7, "#5A5A5A", max_w=w - 32)
        ui.handle_tab()
        label = {"login": T.LOGIN, "register": T.REGISTER, "reset": T.FB_SEND_RESET}[self.tab]
        go = ui.button("fb_go", x + 60, fy + 92, w - 120, 18, label, style="primary", enabled=not self.busy)
        if (go or ui.submitted(last)) and not self.busy:
            self.submit()
        if self.status:
            ui.text(self.status, 240, y + h - 34, 8, "#BC4749" if self.status_err else "#5A5A5A",
                    anchor="midtop", max_w=w - 24)
        ui.text(T.FB_NOTE, 240, y + h - 10, 7, "#8E877A", anchor="center")
        if ui.button("fb_back", 8, 248, 60, 14, T.BACK, key=pygame.K_ESCAPE):
            from .menu import MenuScene
            self.game.replace_all(MenuScene(self.game))
