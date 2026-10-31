"""Sổ Phát Hiện (spec 6.5): recipes are never listed in advance; found ones explain the
character's structure. Also the 'Phát hiện mới!' popup."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from .base import Scene


class DiscoveryPopup(Scene):
    def __init__(self, game, d: dict):
        super().__init__(game)
        self.d = d
        self.t = 0.0

    def update(self, dt, top):
        if top:
            self.t += dt

    def draw_ui(self, ui):
        ui.dim(170)
        d = self.d
        x, y, w, h = 90, 30, 300, 208
        ui.panel(x, y, w, h, T.DISCOVERY_TITLE)
        k = min(1.0, self.t / 0.6)
        ui.text(" + ".join(d["components"]) + "  =", x + 24, y + 42, 22, kind="han", anchor="midleft")
        size = 22 + 14 * k
        ui.text(d["result"], x + w - 60, y + 40, size, "#BC4749", kind="han", anchor="center")
        ui.text(d["pinyin"], x + w - 60, y + 70, 11, "#BC4749", kind="han", anchor="center")
        ui.text(d["meaning_vi"], x + w - 60, y + 84, 8, anchor="center", max_w=110)
        yy = ui.text(d["text_vi"], x + 16, y + 100, 9, max_w=w - 32).bottom + 4
        if not d.get("etymology_verified"):
            yy = ui.text(T.FUN_COMBO_NOTE, x + 16, yy, 7, "#8E877A", max_w=w - 32).bottom + 4
        extras = []
        if d.get("seed_id"):
            extras.append(f"Nhận hạt {d['result']}")
        if (d.get("reward") or {}).get("spirit_stones"):
            extras.append(T.REWARD.format(n=d["reward"]["spirit_stones"]))
        if (d.get("reward") or {}).get("decoration"):
            extras.append("Trang trí: Rừng nhỏ")
        if extras:
            yy = ui.text(" · ".join(extras), x + w / 2, yy + 2, 9, "#C99A3A", anchor="midtop").bottom + 4
        ui.text(f"{T.MASTER}: {T.DISCOVERY_LINE}", x + 16, yy, 7, "#5A5A5A", max_w=w - 32)
        if ui.button("disc_ok", x + w / 2 - 35, y + h - 22, 70, 15, T.OK, style="primary", key=pygame.K_RETURN) or \
                ui.key(pygame.K_ESCAPE):
            self.close()


class BookScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data = None
        self.api.get("/discoveries", lambda r: setattr(self, "data", r), game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 60, 24, 360, 224
        ui.panel(x, y, w, h, T.BOOK_TITLE)
        ui.text(T.BOOK_HINT, x + w / 2 + 30, y + 14, 7, "#5A5A5A", anchor="center")
        if ui.button("book_to_monsters", x + 12, y + 8, 70, 13, T.MONSTER_BOOK, size=7):
            from .rpg import MonsterBookScene
            self.close()
            self.game.push(MonsterBookScene(self.game))
            return
        if ui.button("book_to_bees", x + 12, y + 23, 70, 13, T.BEE_BOOK, size=7):
            self.close()
            self.game.open_bee_book()
            return
        if ui.button("book_to_library", x + 12, y + h - 20, 70, 14, T.BOOK_TO_LIBRARY, size=7, style="gold"):
            self.close()
            self.game.open_library()
            return
        if ui.button("book_to_fish", x + w - 82, y + 23, 70, 13, T.FISH_BOOK, size=7):
            from .fishing import FishBookScene
            self.close()
            self.game.push(FishBookScene(self.game))
            return
        if self.data:
            found = self.data["found"]
            total = self.data["total"]
            ui.text(f"{len(found)}/{total}", x + w - 14, y + 14, 8, "#BC4749", anchor="topright")
            for i in range(total):
                cx = x + 14 + (i % 2) * 168
                cy = y + 30 + (i // 2) * 58
                ui.fill(cx, cy, 162, 52, "#FFFDF7")
                ui.border(cx, cy, 162, 52)
                if i < len(found):
                    d = found[i]
                    ui.text(" + ".join(d["components"]) + " = ", cx + 6, cy + 12, 12, kind="han", anchor="midleft")
                    ui.text(d["result"], cx + 140, cy + 14, 20, "#BC4749", kind="han", anchor="center")
                    ui.text(f"{d['pinyin']} · {d['meaning_vi']}", cx + 6, cy + 26, 7, "#5A5A5A", max_w=120)
                    ui.text(T.BOOK_TRUE if d.get("etymology_verified") else T.BOOK_FUN, cx + 6, cy + 39, 7,
                            "#6A994E" if d.get("etymology_verified") else "#8E877A")
                    ui.widgets[f"book_{i}"] = ui.rect(cx, cy, 162, 52)
                    if ui.hover(cx, cy, 162, 52):
                        ui.set_tooltip(d["text_vi"])
                else:
                    ui.text("？＋？＝？", cx + 81, cy + 26, 14, "#B8AE9C", kind="han", anchor="center")
        if ui.button("book_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
