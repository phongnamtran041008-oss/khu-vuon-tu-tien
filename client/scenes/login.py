from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..net.rest import NETWORK_ERROR, SLEEPING
from .base import Scene
from .menu import TitleBackground


class LoginScene(Scene):
    draws_world = True

    def __init__(self, game, notice: str = ""):
        super().__init__(game)
        self.bg = TitleBackground()
        self.tab = "login"
        self.status = notice
        self.status_err = bool(notice)
        self.busy = False
        self.dt = 0.0
        self.retry_at: float | None = None
        self._last_job = None
        user = game.session.data.get("username", "")
        game.ui.set_value("lg_user", user)
        game.ui.set_focus("lg_pass" if user else "lg_user")

    def update(self, dt, top):
        self.dt = dt
        if self.retry_at is not None and self.game.now >= self.retry_at and self._last_job:
            self.retry_at = None
            self._last_job()

    def draw_world(self, surf):
        self.bg.draw(surf, self.dt)

    # ------------------------------------------------------------ actions
    def _fail(self, err, again=None):
        self.busy = False
        self.status, self.status_err = err.message_vi, True
        if err.code in (NETWORK_ERROR, SLEEPING) and again:
            if err.code == SLEEPING:
                self.status = T.SERVER_STARTING
            else:
                self.status = T.CANNOT_CONNECT.format(url=self.api.base_url)
            self.retry_at = self.game.now + 6
            self._last_job = again

    def do_login(self):
        u, p = self.game.ui.value("lg_user").strip(), self.game.ui.value("lg_pass")
        if not u or not p:
            return
        self.busy, self.status, self.status_err = True, T.CONNECTING, False

        def ok(r):
            self.busy = False
            self.game.set_token(r["token"], u)
            self.game.enter_game()
        self.api.post("/auth/login", {"username": u, "password": p}, ok,
                      lambda e: self._fail(e, self.do_login), timeout=60)

    def do_register(self):
        ui = self.game.ui
        u, p, p2 = ui.value("rg_user").strip(), ui.value("rg_pass"), ui.value("rg_pass2")
        if p != p2:
            self.status, self.status_err = T.PASSWORDS_DIFFER, True
            return
        self.busy, self.status, self.status_err = True, T.CONNECTING, False

        def ok(r):
            self.busy = False
            self.game.set_token(r["token"], u)
            self.game.push(RecoveryCodeScene(self.game, r["recovery_code"], then=self.game.enter_game))
        self.api.post("/auth/register", {"username": u, "password": p}, ok,
                      lambda e: self._fail(e, self.do_register), timeout=60)

    def do_recover(self):
        ui = self.game.ui
        u, code, p = ui.value("rc_user").strip(), ui.value("rc_code"), ui.value("rc_pass")
        self.busy, self.status, self.status_err = True, T.CONNECTING, False

        def ok(r):
            self.busy = False
            self.game.set_token(r["token"], u)
            self.game.push(RecoveryCodeScene(self.game, r["recovery_code"], then=self.game.enter_game,
                                             title="Mã khôi phục mới"))
        self.api.post("/auth/reset_password", {"username": u, "recovery_code": code, "new_password": p},
                      ok, lambda e: self._fail(e, self.do_recover), timeout=60)

    # ------------------------------------------------------------ ui
    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (20, 18, 15, 120))
        x, y, w, h = 120, 28, 240, 214
        ui.panel(x, y, w, h)
        ui.text(T.TITLE, 240, y + 14, 12, anchor="center")
        tabs = [("login", T.LOGIN), ("register", T.REGISTER), ("recover", T.RECOVER)]
        for i, (k, label) in enumerate(tabs):
            if ui.button(f"tab_{k}", x + 12 + i * 73, y + 28, 70, 14, label, selected=self.tab == k):
                self.tab = k
                self.status = ""
                ui.set_focus({"login": "lg_user", "register": "rg_user", "recover": "rc_user"}[k])
        fy = y + 52
        if self.tab == "login":
            ui.text(T.USERNAME, x + 16, fy, 8)
            ui.input_box("lg_user", x + 16, fy + 10, w - 32, 16, max_len=20)
            ui.text(T.PASSWORD, x + 16, fy + 32, 8)
            ui.input_box("lg_pass", x + 16, fy + 42, w - 32, 16, password=True, max_len=128)
            ui.handle_tab()
            go = ui.button("btn_login", x + 60, fy + 70, w - 120, 18, T.LOGIN, style="primary",
                           enabled=not self.busy)
            if go or ui.submitted("lg_pass") or ui.submitted("lg_user"):
                self.do_login()
        elif self.tab == "register":
            ui.text(T.USERNAME + " (3–20 ký tự, không dấu)", x + 16, fy, 8)
            ui.input_box("rg_user", x + 16, fy + 10, w - 32, 15, max_len=20)
            ui.text(T.PASSWORD + " (ít nhất 6 ký tự)", x + 16, fy + 29, 8)
            ui.input_box("rg_pass", x + 16, fy + 39, w - 32, 15, password=True, max_len=128)
            ui.text(T.PASSWORD_AGAIN, x + 16, fy + 58, 8)
            ui.input_box("rg_pass2", x + 16, fy + 68, w - 32, 15, password=True, max_len=128)
            ui.handle_tab()
            go = ui.button("btn_register", x + 60, fy + 92, w - 120, 18, T.REGISTER, style="primary",
                           enabled=not self.busy)
            if go or ui.submitted("rg_pass2"):
                self.do_register()
        else:
            ui.text(T.USERNAME, x + 16, fy, 8)
            ui.input_box("rc_user", x + 16, fy + 10, w - 32, 15, max_len=20)
            ui.text(T.RECOVERY_CODE + " (XXXX-XXXX-XXXX)", x + 16, fy + 29, 8)
            ui.input_box("rc_code", x + 16, fy + 39, w - 32, 15, max_len=20)
            ui.text(T.NEW_PASSWORD, x + 16, fy + 58, 8)
            ui.input_box("rc_pass", x + 16, fy + 68, w - 32, 15, password=True, max_len=128)
            ui.handle_tab()
            go = ui.button("btn_recover", x + 60, fy + 92, w - 120, 18, T.RECOVER, style="primary",
                           enabled=not self.busy)
            if go or ui.submitted("rc_pass"):
                self.do_recover()
        if self.status:
            ui.text(self.status, 240, y + h - 30, 8, "#BC4749" if self.status_err else "#5A5A5A",
                    anchor="midtop", max_w=w - 24)
        ui.text(f"{T.SERVER}: {self.api.base_url}", 240, y + h - 10, 7, "#8E877A", anchor="center")
        maint = self.game.server_info.get("maintenance_message")
        if maint:   # stage 10: set by an admin, shown before anyone tries to log in
            ui.fill(x, 8, w, 16, (244, 235, 217, 235))
            ui.text(T.MAINTENANCE.format(text=maint), 240, 16, 7, "#BC4749", anchor="center", max_w=w - 8)
        if ui.button("lg_back", 8, 248, 60, 14, T.BACK, key=pygame.K_ESCAPE):
            from .menu import MenuScene
            self.game.replace_all(MenuScene(self.game))


class RecoveryCodeScene(Scene):
    def __init__(self, game, code: str, then=None, title: str = T.RECOVERY_TITLE):
        super().__init__(game)
        self.code, self.then, self.title = code, then, title

    def draw_ui(self, ui):
        ui.dim(170)
        x, y, w, h = 100, 50, 280, 170
        ui.panel(x, y, w, h, self.title)
        ui.fill(x + 40, y + 24, w - 80, 34, "#FFFDF7")
        ui.border(x + 40, y + 24, w - 80, 34, "#BC4749", 2)
        ui.text(self.code, 240, y + 41, 16, "#2B2B2B", anchor="center")
        ui.text(T.RECOVERY_HINT, x + 16, y + 68, 8, max_w=w - 32)
        if ui.button("btn_copy", x + 30, y + h - 26, 100, 16, "Sao chép mã"):
            try:
                pygame.scrap.put_text(self.code)
                self.game.toast("Đã sao chép")
            except (pygame.error, AttributeError):
                self.game.toast("Không sao chép được, hãy chép tay nhé", "#BC4749")
        if ui.button("btn_saved", x + w - 140, y + h - 26, 110, 16, T.RECOVERY_SAVED, style="primary"):
            self.close()
            if self.then:
                self.then()
