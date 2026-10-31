"""Sạp Tạp Hóa of Bà Chủ Sạp (spec 12.4): daily goods with a per-day limit, Phàm/Linh gear,
and selling things back. Prices and limits come from the server."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from .base import Scene


class ShopScene(Scene):
    def __init__(self, game, tab: str = "buy"):
        super().__init__(game)
        self.tab = tab
        self.data: dict | None = None
        self.busy = False
        self.scroll = 0
        self.reload()

    def reload(self):
        self.api.get("/shop", lambda r: setattr(self, "data", r), self.game.api_error)

    def _done(self, message):
        """message: the toast text, or a function of the server's answer that makes it."""
        def ok(r):
            self.busy = False
            if "spirit_stones" in r:
                self.game.state.me["spirit_stones"] = r["spirit_stones"]
            self.game.toast(message(r) if callable(message) else message, "#6A994E")
            self.game.audio.play("coin")
            self.game.refresh_inv()
            self.reload()
        return ok

    def _err(self, e):
        self.busy = False
        self.game.api_error(e)

    def buy(self, item_id: str, name: str, qty: int, rarity: str | None = None):
        self.busy = True
        body = {"item_id": item_id, "qty": qty}
        if rarity:
            body["rarity"] = rarity
        self.api.post("/shop/buy", body, self._done(T.SHOP_BOUGHT.format(name=name, n=qty)), self._err)

    def sell_item(self, it: dict, qty: int):
        self.busy = True
        self.api.post("/inventory/sell", {"item_id": it["item_id"], "qty": qty},
                      self._done(lambda r: T.SHOP_SOLD.format(n=r["earned"])), self._err)

    def sell_gear(self, e: dict):
        self.busy = True
        self.api.post("/shop/sell_equipment", {"instance_id": e["id"]},
                      self._done(lambda r: T.SHOP_SOLD.format(n=r["earned"])), self._err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 20, 400, 232
        ui.panel(x, y, w, h, T.SHOP_TITLE)
        for i, (k, label) in enumerate((("buy", T.SHOP_TAB_BUY), ("gear", T.SHOP_TAB_GEAR), ("sell", T.SHOP_TAB_SELL))):
            if ui.button(f"shop_tab_{k}", x + 10 + i * 66, y + 8, 62, 13, label, size=7, selected=self.tab == k):
                self.tab, self.scroll = k, 0
        me = self.game.state.me
        ui.text(f"{me.get('spirit_stones', 0):,} Linh Thạch".replace(",", "."), x + w - 12, y + 10, 8, "#2B2B2B",
                anchor="topright")
        d = self.data
        if d is None:
            ui.text("...", 240, 130, 10, anchor="center")
        else:
            if not d["at_shop"] and self.tab != "sell":
                ui.text(T.SHOP_FAR, x + 12, y + 26, 7, "#BC4749", max_w=w - 24)
            getattr(self, f"draw_{self.tab}")(ui, x, y + 36, w, d)
        if ui.button("shop_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def _rows(self, ui, n: int, per: int = 8):
        if ui.inp.wheel:
            self.scroll = max(0, min(max(0, n - per), self.scroll - ui.inp.wheel))
        return range(self.scroll, min(n, self.scroll + per))

    def draw_buy(self, ui, x, y, w, d):
        stock = d["stock"]
        for row, i in enumerate(self._rows(ui, len(stock))):
            s = stock[i]
            ry = y + row * 22
            ui.fill(x + 10, ry, w - 20, 20, "#FFFDF7" if row % 2 else "#F8F1E3")
            ui.text(s["name_vi"], x + 16, ry + 2, 8)
            ui.text(T.SHOP_LEFT.format(n=s["left"], d=s["daily"]), x + 16, ry + 12, 6, "#8E877A")
            if ui.hover(x + 10, ry, 200, 20):
                ui.set_tooltip(s["desc_vi"])
            ok = d["at_shop"] and not self.busy and s["left"] > 0
            stones = self.game.state.me.get("spirit_stones", 0)
            if ui.button(f"shop_buy_{s['item_id']}", x + w - 128, ry + 3, 70, 14, T.SHOP_BUY.format(p=s["price"]),
                         size=7, style="primary", enabled=ok and stones >= s["price"]):
                self.buy(s["item_id"], s["name_vi"], 1)
            if ui.button(f"shop_buy5_{s['item_id']}", x + w - 54, ry + 3, 40, 14, T.SHOP_BUY5, size=7,
                         enabled=ok and s["left"] >= 5 and stones >= 5 * s["price"]):
                self.buy(s["item_id"], s["name_vi"], 5)

    def draw_gear(self, ui, x, y, w, d):
        gear = d["equipment"]
        stones = self.game.state.me.get("spirit_stones", 0)
        for row, i in enumerate(self._rows(ui, len(gear))):
            g = gear[i]
            ry = y + row * 22
            ui.fill(x + 10, ry, w - 20, 20, "#FFFDF7" if row % 2 else "#F8F1E3")
            ui.fill(x + 10, ry, 3, 20, g["color"])
            ui.text(f"{g['name_vi']} · {g['rarity_vi']}", x + 16, ry + 2, 8, g["color"])
            stats = " ".join(f"{T.STATS_VI.get(k, k)} {v}" for k, v in g["stats"].items())
            ui.text(f"{g['slot_vi']} · {stats}", x + 16, ry + 12, 6, "#5A5A5A")
            if ui.button(f"shop_gear_{g['item_id']}_{g['rarity']}", x + w - 96, ry + 3, 82, 14,
                         T.SHOP_GEAR_BUY.format(p=g["price"]), size=7, style="primary",
                         enabled=d["at_shop"] and not self.busy and stones >= g["price"]):
                self.buy(g["item_id"], f"{g['name_vi']} ({g['rarity_vi']})", 1, g["rarity"])

    def draw_sell(self, ui, x, y, w, d):
        rows = [("item", it) for it in d["sell_items"]] + [("gear", e) for e in d["sell_equipment"]]
        if not rows:
            ui.text(T.SHOP_NOTHING, x + 16, y + 6, 8, "#8E877A")
            return
        for row, i in enumerate(self._rows(ui, len(rows))):
            kind, it = rows[i]
            ry = y + row * 22
            ui.fill(x + 10, ry, w - 20, 20, "#FFFDF7" if row % 2 else "#F8F1E3")
            if kind == "item":
                ui.text(f"{it['name_vi']} ×{it['qty']}", x + 16, ry + 5, 8)
                if ui.button(f"shop_sell_{it['item_id']}", x + w - 128, ry + 3, 70, 14,
                             T.SHOP_SELL.format(p=it["sell_price"]), size=7, enabled=not self.busy):
                    self.sell_item(it, 1)
                if ui.button(f"shop_sellall_{it['item_id']}", x + w - 54, ry + 3, 40, 14, f"×{it['qty']}", size=7,
                             enabled=not self.busy):
                    self.sell_item(it, it["qty"])
            else:
                lvl = f" +{it['enhance']}" if it["enhance"] else ""
                ui.fill(x + 10, ry, 3, 20, it["color"])
                ui.text(f"{it['name_vi']}{lvl} · {it['rarity_vi']}", x + 16, ry + 5, 8, it["color"])
                if ui.button(f"shop_sellgear_{it['id']}", x + w - 96, ry + 3, 82, 14,
                             T.SHOP_SELL.format(p=it["sell_price"]), size=7,
                             enabled=d["at_shop"] and not self.busy):
                    self.sell_gear(it)
