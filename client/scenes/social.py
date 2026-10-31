"""Friends list, friend requests, blocks, and the small menu shown when clicking another
player (spec 15.3)."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from .base import Scene


class FriendsScene(Scene):
    def __init__(self, game, tab: str = "friends"):
        super().__init__(game)
        self.tab = tab
        self.data: dict | None = None
        self.blocked: list = []
        self.busy = False
        self.scroll = 0
        self.refresh()

    def refresh(self) -> None:
        def ok(d):
            self.data = d
            self.game.state.friends = d.get("friends", [])
        self.api.get("/friends", ok, self.game.api_error)
        self.api.get("/blocks", lambda d: setattr(self, "blocked", d.get("blocked", [])), lambda e: None)

    def _post(self, path: str, body: dict, done_msg: str | None = None) -> None:
        self.busy = True

        def ok(r):
            self.busy = False
            if done_msg:
                self.game.toast(done_msg)
            self.refresh()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post(path, body, ok, err)

    def add_friend(self) -> None:
        name = self.game.ui.value("fr_add").strip()
        if not name:
            return
        self.game.ui.set_value("fr_add", "")

        def ok(r):
            self.busy = False
            msg = T.FRIEND_NOW if r.get("status") == "accepted" else T.FRIEND_SENT
            self.game.toast(msg.format(name=r.get("user", {}).get("display_name", name)))
            self.refresh()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.busy = True
        self.api.post("/friends/request", {"display_name": name}, ok, err)

    def draw_ui(self, ui):
        ui.dim(140)
        x, y, w, h = 70, 26, 340, 222
        ui.panel(x, y, w, h, T.FRIENDS_TITLE)
        d = self.data or {}
        friends, incoming = d.get("friends", []), d.get("incoming", [])
        tabs = [("friends", T.FRIENDS_TAB.format(n=len(friends))),
                ("requests", T.REQUESTS_TAB.format(n=len(incoming))), ("blocked", T.BLOCKED_TAB)]
        tx = x + 12
        for key, label in tabs:
            tw = ui.text_size(label, 8)[0] + 12
            if ui.button(f"fr_tab_{key}", tx, y + 12, tw, 13, label, selected=self.tab == key):
                self.tab, self.scroll = key, 0
            tx += tw + 4
        if self.data is not None:
            ui.text(T.HELPS_LEFT.format(n=d.get("helps_left", 0)), x + w - 12, y + 15, 7, "#6A994E", anchor="topright")
        ui.input_box("fr_add", x + 12, y + 30, w - 92, 14, T.FRIEND_ADD_PH, max_len=20)
        if ui.button("fr_add_btn", x + w - 76, y + 30, 64, 14, T.FRIEND_ADD, style="primary",
                     enabled=not self.busy) or ui.submitted("fr_add"):
            self.add_friend()
        rows_y = y + 50
        area_h = h - 64
        if self.tab == "friends":
            self._rows(ui, friends, rows_y, area_h, x, w, T.NO_FRIENDS, self._friend_row)
        elif self.tab == "requests":
            self._rows(ui, incoming, rows_y, area_h, x, w, T.NO_REQUESTS, self._request_row)
        else:
            self._rows(ui, self.blocked, rows_y, area_h, x, w, T.NO_BLOCKED, self._blocked_row)
        if ui.button("fr_close", x + w / 2 - 35, y + h - 18, 70, 13, T.CLOSE) or \
                (ui.focus != "fr_add" and ui.key(pygame.K_ESCAPE)):
            if ui.focus == "fr_add":
                ui.set_focus(None)
            self.close()

    def _rows(self, ui, items, y0, area_h, x, w, empty, draw_row) -> None:
        if self.data is None and self.tab != "blocked":
            ui.text("...", x + w / 2, y0 + 20, 9, anchor="center")
            return
        if not items:
            ui.text(empty, x + 16, y0 + 8, 8, "#5A5A5A", max_w=w - 32)
            return
        per = int(area_h // 22)
        if ui.hover(x, y0, w, area_h) and ui.inp.wheel:
            self.scroll = max(0, min(len(items) - per, self.scroll - ui.inp.wheel))
        for i, it in enumerate(items[self.scroll:self.scroll + per]):
            ry = y0 + i * 22
            ui.fill(x + 10, ry, w - 20, 20, "#EFE4CF" if i % 2 else "#F8F1E3")
            draw_row(ui, it, x + 10, ry, w - 20)

    def _friend_row(self, ui, f, x, y, w) -> None:
        uid = f["user_id"]
        dot = "#6A994E" if f.get("online") else "#9A9A9A"
        ui.fill(x + 5, y + 7, 6, 6, dot)
        ui.text(f["display_name"], x + 16, y + 2, 8)
        status = T.ONLINE_IN.format(zone=f.get("zone_name", "")) if f.get("online") else T.OFFLINE_LABEL
        ui.text(f"{T.REALMS.get(f.get('realm'), '')} · {status}", x + 16, y + 11, 7, "#5A5A5A")
        bx = x + w - 4
        for wid, label, style, fn in [
                (f"fr_rm_{uid}", T.REMOVE, "normal", lambda: self.game.message(
                    T.REMOVE_CONFIRM.format(name=f["display_name"]), cancel=T.CANCEL,
                    on_ok=lambda: self._post("/friends/remove", {"user_id": uid}))),
                (f"fr_visit_{uid}", T.VISIT, "green", lambda: self.visit(f)),
                (f"fr_gift_{uid}", T.GIFT_BUTTON, "gold", lambda: self.game.push(GiftScene(self.game, f))),
                (f"fr_msg_{uid}", T.MSG, "normal", lambda: self.message(f))]:
            bw = ui.text_size(label, 7)[0] + 10
            bx -= bw + 3
            if ui.button(wid, bx, y + 3, bw, 14, label, size=7, style=style, enabled=not self.busy):
                fn()

    def _request_row(self, ui, f, x, y, w) -> None:
        uid = f["user_id"]
        ui.text(f["display_name"], x + 8, y + 2, 8)
        ui.text(T.REALMS.get(f.get("realm"), ""), x + 8, y + 11, 7, "#5A5A5A")
        if ui.button(f"fr_acc_{uid}", x + w - 120, y + 3, 56, 14, T.ACCEPT, size=7, style="green",
                     enabled=not self.busy):
            self._post("/friends/accept", {"user_id": uid}, T.FRIEND_NOW.format(name=f["display_name"]))
        if ui.button(f"fr_dec_{uid}", x + w - 60, y + 3, 56, 14, T.DECLINE, size=7, enabled=not self.busy):
            self._post("/friends/decline", {"user_id": uid})

    def _blocked_row(self, ui, b, x, y, w) -> None:
        ui.text(b["display_name"], x + 8, y + 6, 8)
        if ui.button(f"fr_unb_{b['user_id']}", x + w - 60, y + 3, 56, 14, T.UNBLOCK, size=7, enabled=not self.busy):
            self._post("/blocks/remove", {"user_id": b["user_id"]})

    def message(self, f: dict) -> None:
        self.close()
        self.game.chatbox.open(whisper_to=f["display_name"])

    def visit(self, f: dict) -> None:
        from .visit import VisitScene
        self.close()
        self.game.push(VisitScene(self.game, f["user_id"], f["display_name"]))


class PlayerMenu(Scene):
    """Shown when clicking another player in the world or their name in the chat."""

    def __init__(self, game, uid: int, name: str, realm: str | None = None):
        super().__init__(game)
        self.uid, self.name, self.realm = uid, name, realm

    def draw_ui(self, ui):
        ui.dim(90)
        x, y, w, h = 170, 62, 140, 130
        ui.panel(x, y, w, h)
        ui.text(self.name, x + w / 2, y + 10, 10, anchor="midtop")
        if self.realm:
            ui.text(T.PLAYER_REALM.format(realm=T.REALMS.get(self.realm, self.realm)), x + w / 2, y + 24, 7,
                    "#6A994E", anchor="midtop")
        g = self.game
        is_friend = any(f["user_id"] == self.uid for f in g.state.friends)
        by = y + 36
        if not is_friend:
            if ui.button("pm_add", x + 14, by, w - 28, 14, T.FRIEND_ADD, style="primary"):
                self.close()
                g.api.post("/friends/request", {"display_name": self.name},
                           lambda r: g.toast((T.FRIEND_NOW if r.get("status") == "accepted" else T.FRIEND_SENT)
                                             .format(name=self.name)), g.api_error)
                return
        else:
            if ui.button("pm_msg", x + 14, by, w - 28, 14, T.MSG):
                self.close()
                g.chatbox.open(whisper_to=self.name)
                return
        by += 18
        if ui.button("pm_party", x + 14, by, w - 28, 14, T.PARTY_INVITE, style="gold"):   # stage 9
            self.close()
            if g.net is not None:
                g.net.send({"t": "party", "op": "invite", "name": self.name})
            return
        by += 18
        if ui.button("pm_block", x + 14, by, w - 28, 14, T.BLOCK):
            self.close()
            g.message(T.BLOCK_CONFIRM.format(name=self.name), cancel=T.CANCEL, on_ok=self.block)
            return
        by += 18
        if ui.button("pm_report", x + 14, by, w - 28, 14, T.REPORT):
            self.close()
            g.message(T.REPORT_CONFIRM.format(name=self.name), cancel=T.CANCEL, on_ok=self.report)
            return
        if ui.button("pm_close", x + 14, y + h - 18, w - 28, 13, T.CLOSE, key=pygame.K_ESCAPE) or \
                (ui.inp.clicked and not ui.hover(x, y, w, h)):
            self.close()

    def block(self) -> None:
        g = self.game
        g.api.post("/blocks", {"user_id": self.uid}, lambda r: (g.toast(T.BLOCK + ": " + self.name),
                                                                 g.refresh_friends()), g.api_error)

    def report(self) -> None:
        g = self.game
        last = g.chat.last_from.get(self.uid, "")
        g.api.post("/reports", {"user_id": self.uid, "message": last, "reason": "chat"},
                   lambda r: g.toast(T.REPORT_DONE), g.api_error)


class GiftScene(Scene):
    """A small present for a friend (spec 12.4, stage 8): unbound items only, a few at a time."""

    GIFT_KINDS = ("food", "material", "herb", "bait", "pill", "fish", "egg")

    def __init__(self, game, friend: dict):
        super().__init__(game)
        self.friend = friend
        self.busy = False
        self.scroll = 0
        self.qty: dict[str, int] = {}
        game.refresh_inv()

    def give(self, it: dict, n: int):
        self.busy = True

        def ok(r):
            self.busy = False
            self.game.toast(T.GIFT_SENT.format(name=r["name_vi"], n=r["qty"]), "#6A994E")
            self.game.audio.play("coin")
            self.game.refresh_inv()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/friends/gift", {"friend_id": self.friend["user_id"], "item_id": it["item_id"], "qty": n},
                      ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 90, 30, 300, 210
        ui.panel(x, y, w, h, T.GIFT_TITLE.format(name=self.friend["display_name"]))
        ui.text(T.GIFT_HINT, x + w / 2, y + 12, 7, "#5A5A5A", anchor="center")
        items = [i for i in (self.game.state.inv or {}).get("items", []) if i.get("kind") in self.GIFT_KINDS]
        if not items:
            ui.text(T.GIFT_NONE, x + 14, y + 30, 8, "#8E877A")
        per = 7
        if ui.inp.wheel:
            self.scroll = max(0, min(max(0, len(items) - per), self.scroll - ui.inp.wheel))
        for row, it in enumerate(items[self.scroll:self.scroll + per]):
            ry = y + 26 + row * 22
            ui.fill(x + 10, ry, w - 20, 20, "#FFFDF7" if row % 2 else "#F8F1E3")
            ui.text(f"{it['name_vi']} ×{it['qty']}", x + 16, ry + 6, 8)
            n = min(self.qty.get(it["item_id"], 1), it["qty"], 5)
            if ui.button(f"gift_less_{it['item_id']}", x + w - 128, ry + 3, 14, 14, "-", size=7):
                self.qty[it["item_id"]] = max(1, n - 1)
            ui.text(str(n), x + w - 106, ry + 10, 8, anchor="center")
            if ui.button(f"gift_more_{it['item_id']}", x + w - 98, ry + 3, 14, 14, "+", size=7):
                self.qty[it["item_id"]] = min(5, it["qty"], n + 1)
            if ui.button(f"gift_give_{it['item_id']}", x + w - 78, ry + 3, 64, 14, T.GIFT_GIVE.format(n=n), size=7,
                         style="gold", enabled=not self.busy):
                self.give(it, n)
        if ui.button("gift_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
