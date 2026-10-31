"""Túi đồ: seeds, word fruits (sell), and the word list (mastery, Giâm cành)."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..art.palette import RARITY_COLORS
from ..ui.kit import rarity_name
from .base import Scene


class BagScene(Scene):
    def __init__(self, game, abode=None):
        super().__init__(game)
        self.abode = abode
        self.tab = "seeds"
        self.seeds = self.fruits = self.words = None
        self.inv = None
        self.scroll = 0
        self.reload()

    def reload(self):
        def inv(r):
            self.inv = r
            self.game.state.inv = r
        self.api.get("/inventory", inv, self.game.api_error)
        self.api.get("/seeds", lambda r: setattr(self, "seeds", r["seeds"]), self.game.api_error)
        self.api.get("/fruits", lambda r: setattr(self, "fruits", r["fruits"]), self.game.api_error)
        self.api.get("/collection", lambda r: setattr(self, "words", [c for c in r["collection"] if c["introduced"]]),
                     self.game.api_error)

    def _money(self, r):
        if "spirit_stones" in r:
            self.game.state.me["spirit_stones"] = r["spirit_stones"]
            self.game.audio.play("coin")
        self.reload()

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 50, 24, 380, 226
        ui.panel(x, y, w, h, T.BAG_TITLE)
        tabs = [("seeds", T.BAG_SEEDS), ("fruits", T.BAG_FRUITS), ("words", T.BAG_WORDS), ("items", T.BAG_ITEMS),
                ("gear", T.BAG_GEAR)]
        for i, (k, label) in enumerate(tabs):
            if ui.button(f"bag_tab_{k}", x + 12 + i * 71, y + 12, 68, 14, label, selected=self.tab == k):
                self.tab, self.scroll = k, 0
        lx, ly, lw = x + 12, y + 32, w - 24
        inv = self.inv or {}
        rows = {"seeds": self.seeds, "fruits": self.fruits, "words": self.words,
                "items": inv.get("items") if self.inv else None,
                "gear": inv.get("equipment") if self.inv else None}[self.tab]
        if rows is None:
            ui.text("...", 240, ly + 30, 10, anchor="center")
        elif not rows:
            ui.text(T.EMPTY_LIST if self.tab != "seeds" else T.NO_SEEDS, lx, ly + 6, 8, max_w=lw)
        else:
            per = 9
            if ui.inp.wheel and ui.enabled:
                self.scroll = max(0, min(max(0, len(rows) - per), self.scroll - ui.inp.wheel))
            for i, r in enumerate(rows[self.scroll:self.scroll + per]):
                ry = ly + i * 18
                ui.fill(lx, ry, lw, 16, "#FFFDF7" if i % 2 else "#F8F1E3")
                if self.tab in ("items", "gear"):
                    getattr(self, f"row_{self.tab}")(ui, r, lx, ry, lw)
                    continue
                ui.fill(lx, ry, 3, 16, RARITY_COLORS.get(r.get("rarity", "common")))
                ui.text(r["hanzi"], lx + 8, ry + 8, 11, kind="han", anchor="midleft")
                getattr(self, f"row_{self.tab}")(ui, r, lx, ry, lw)
            if len(rows) > per:
                ui.text(f"{self.scroll + 1}–{min(len(rows), self.scroll + per)}/{len(rows)} (cuộn chuột)",
                        x + w - 14, y + h - 30, 7, "#8E877A", anchor="topright")
        if ui.button("bag_close", x + w / 2 - 35, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def row_seeds(self, ui, r, lx, ry, lw):
        ui.text(rarity_name(r["rarity"]), lx + 90, ry + 8, 8, RARITY_COLORS[r["rarity"]], anchor="midleft")
        if r["duplicate"]:
            ui.text(T.DUPLICATE, lx + 160, ry + 8, 8, "#8E877A", anchor="midleft")
            if ui.button(f"sell_seed_{r['seed_id']}", lx + lw - 70, ry + 2, 66, 12, f"{T.SELL} (20)", size=7):
                self.api.post("/seeds/sell", {"seed_id": r["seed_id"]}, self._money, self.game.api_error)

    def row_fruits(self, ui, r, lx, ry, lw):
        ui.text(r.get("pinyin", ""), lx + 60, ry + 8, 8, "#5A5A5A", kind="han", anchor="midleft")
        ui.text(f"x{r['count']}", lx + 150, ry + 8, 9, anchor="midleft")
        ui.text(f"{r['sell_price']}/quả", lx + 190, ry + 8, 8, "#8E877A", anchor="midleft")
        if ui.button(f"sell1_{r['word_id']}", lx + lw - 130, ry + 2, 56, 12, T.SELL, size=7):
            self.api.post("/fruits/sell", {"word_id": r["word_id"], "count": 1}, self._money, self.game.api_error)
        if ui.button(f"sellall_{r['word_id']}", lx + lw - 70, ry + 2, 66, 12, T.SELL_ALL, size=7):
            self.api.post("/fruits/sell", {"word_id": r["word_id"], "count": r["count"]}, self._money,
                          self.game.api_error)

    def row_words(self, ui, r, lx, ry, lw):
        ui.text(r.get("pinyin", ""), lx + 60, ry + 8, 8, "#BC4749", kind="han", anchor="midleft")
        ui.text(r.get("meaning_vi", ""), lx + 120, ry + 8, 8, anchor="midleft", max_w=120)
        ui.progress(lx + 248, ry + 6, 40, 4, r["mastery"] / 100, "#6A994E")
        if ui.button(f"cut_{r['word_id']}", lx + lw - 70, ry + 2, 66, 12, T.CUTTING, size=7, tooltip=T.CUTTING_TIP):
            def ok(res):
                self.game.toast(f"Đã có thêm một hạt {r['hanzi']}")
                self._money(res)
            self.api.post("/garden/cutting", {"word_id": r["word_id"]}, ok, self.game.api_error)

    # ---------------------------------------------------------------- stage 4
    def _after(self, msg: str | None = None):
        def ok(r):
            if msg:
                self.game.toast(msg, "#6A994E")
            self.game.refresh_cult()
            self.reload()
        return ok

    def row_items(self, ui, r, lx, ry, lw):
        ui.fill(lx, ry, 3, 16, "#4A7CC8" if r.get("kind") == "manual" else "#BC4749" if r.get("kind") == "pill"
                else "#C99A3A" if r.get("kind") in ("egg", "food") else "#8E877A")
        ui.text(r["name_vi"], lx + 8, ry + 8, 8, anchor="midleft")
        ui.text(f"x{r['qty']}", lx + 170, ry + 8, 8, anchor="midleft")
        if ui.hover(lx, ry, lw - 70, 16):
            ui.set_tooltip(r.get("desc_vi", ""))
        if r.get("usable") and ui.button(f"use_{r['item_id']}", lx + lw - 70, ry + 2, 66, 12, T.USE, size=7):
            self.api.post("/inventory/use", {"item_id": r["item_id"]},
                          self._after(r["name_vi"] if r.get("kind") == "manual" else None), self.game.api_error)
        elif r.get("kind") == "egg":
            ui.text(T.EGG_HINT, lx + lw - 6, ry + 8, 7, "#6A994E", anchor="midright")
        elif r.get("sell_price") and ui.button(f"sell_item_{r['item_id']}", lx + lw - 70, ry + 2, 66, 12,
                                               T.SELL_ITEM.format(p=r["sell_price"]), size=7,
                                               tooltip=f"{r['sell_price']} Linh Thạch mỗi cái"):
            self.api.post("/inventory/sell", {"item_id": r["item_id"], "qty": 1}, self._money, self.game.api_error)

    def row_gear(self, ui, r, lx, ry, lw):
        ui.fill(lx, ry, 3, 16, r["color"])
        lvl = f" +{r['enhance']}" if r["enhance"] else ""
        ui.text(r["name_vi"] + lvl, lx + 8, ry + 8, 8, r["color"], anchor="midleft")
        stats = " ".join(f"{T.STATS_VI.get(k, k)} {v}" for k, v in r["stats"].items())
        ui.text(f"{r['slot_vi']} · {stats}", lx + 130, ry + 8, 7, "#5A5A5A", anchor="midleft")
        if ui.hover(lx, ry, lw - 70, 16):
            ui.set_tooltip(f"{r['name_vi']} · {r['rarity_vi']}\n{r.get('desc_vi', '')}")
        if r.get("equipped"):
            if ui.button(f"uneq_{r['id']}", lx + lw - 70, ry + 2, 66, 12, T.UNEQUIP, size=7, selected=True):
                self.api.post("/equipment/unequip", {"slot": r["equipped"]}, self._after(), self.game.api_error)
        elif ui.button(f"eq_{r['id']}", lx + lw - 70, ry + 2, 66, 12, T.EQUIP, size=7, style="green"):
            self.api.post("/equipment/equip", {"instance_id": r["id"]}, self._after(), self.game.api_error)
