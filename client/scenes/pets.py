"""Linh Thú (spec 13): the pets owned, wearing one, and the Linh Thú Phổ of the 12 con giáp."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..engine import sprites
from .base import Scene

RARITY_COLORS = {"common": "#7D7468", "rare": "#4A7CC8", "epic": "#8E5AC8", "legendary": "#C99A3A"}


class PetScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.busy = False
        self.sel = 0
        game.refresh_pets()

    def equip(self, pet_id):
        self.busy = True

        def ok(r):
            self.busy = False
            from ..engine import sprites as sp
            sp.set_pet_looks(r.get("looks", {}))
            self.game.state.pets = r
            w = next((p for p in r["pets"] if p["equipped"]), None)
            if w:
                self.game.toast(T.PETS_EQUIPPED.format(name=w["name_vi"]), "#6A994E")
                self.game.audio.play("coin")
            self.game.refresh_cult()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/pets/equip", {"pet_id": pet_id}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 22, 400, 228
        ui.panel(x, y, w, h, T.PETS_TITLE)
        ui.text(T.PETS_HINT, x + w / 2, y + 12, 7, "#5A5A5A", anchor="center", max_w=w - 20)
        d = self.game.state.pets or {}
        pets = d.get("pets")
        if ui.button("pets_book", x + w - 82, y + h - 20, 70, 14, T.PETS_BOOK, size=7, style="gold"):
            self.game.push(PetBookScene(self.game))
            return
        if pets is None:
            ui.text("...", 240, 130, 10, anchor="center")
        elif not pets:
            ui.text(T.PETS_NONE, x + 16, y + 40, 8, max_w=w - 32)
        else:
            self.sel = min(self.sel, len(pets) - 1)
            for i, p in enumerate(pets):      # up to 12, a 4 x 3 grid of cards
                cx, cy = x + 12 + (i % 4) * 46, y + 30 + (i // 4) * 54
                col = RARITY_COLORS.get(p["rarity"], "#7D7468")
                ui.fill(cx, cy, 42, 50, "#FFFDF7" if i != self.sel else "#F4E6C2")
                ui.border(cx, cy, 42, 50, col, 2 if p["equipped"] else 1)
                ui.image(sprites.pet(p["pet_type"], int(ui.time * 3) % 2 if p["equipped"] else 0),
                         cx + 21, cy + 20, zoom=2, anchor="center")
                ui.text(p["name_vi"], cx + 21, cy + 38, 7, col, anchor="center")
                ui.text(T.PETS_LEVEL.format(l=p["level"], m=p["max_level"]), cx + 21, cy + 45, 6, "#8E877A",
                        anchor="center")
                if ui.click_in(cx, cy, 42, 50):
                    self.sel = i
            p = pets[self.sel]
            px = x + 202
            col = RARITY_COLORS.get(p["rarity"], "#7D7468")
            ui.fill(px, y + 30, w - 214, 160, "#FFFDF7")
            ui.border(px, y + 30, w - 214, 160, col)
            ui.image(sprites.pet(p["pet_type"], int(ui.time * 4) % 2), px + 30, y + 62, zoom=3.5, anchor="center")
            ui.text(p["hanzi"], px + 88, y + 52, 22, "#2B2B2B", kind="han", anchor="center")
            ui.text(p["pinyin"], px + 88, y + 72, 9, "#5A5A5A", kind="han", anchor="center")
            ui.text(f"{p['name_vi']} · {p['zodiac_vi']}", px + 120, y + 44, 9, col)
            ui.text(p["rarity_vi"], px + 120, y + 56, 7, col)
            ui.text(T.PETS_LEVEL.format(l=p["level"], m=p["max_level"]), px + 120, y + 66, 7, "#8E877A")
            ui.text(p["skill_vi"], px + 10, y + 96, 7, "#2B2B2B", max_w=w - 234)
            stats = "  ".join(f"{T.STATS_VI.get(k, k)} +{v}" for k, v in p["stats"].items())
            ui.text(stats, px + 10, y + 140, 7, "#6A994E", max_w=w - 234)
            if p["equipped"]:
                ui.text(T.PETS_WORN, px + 10, y + 166, 8, "#C99A3A")
                if ui.button("pets_off", px + w - 290, y + 162, 60, 16, T.PETS_TAKE_OFF, size=7,
                             enabled=not self.busy):
                    self.equip(None)
            elif ui.button(f"pets_wear_{p['id']}", px + w - 290, y + 162, 60, 16, T.PETS_WEAR, style="primary",
                           enabled=not self.busy):
                self.equip(p["id"])
        if ui.button("pets_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


class PetBookScene(Scene):
    """Linh Thú Phổ (Tàng Thư Các): the 12 con giáp, the ones never met as a dark shape."""

    def __init__(self, game):
        super().__init__(game)
        game.refresh_pets()

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 22, 400, 228
        ui.panel(x, y, w, h, T.PETS_BOOK_TITLE)
        d = self.game.state.pets or {}
        book = d.get("book") or []
        ui.text(T.PETS_FOUND.format(f=d.get("found", 0), t=d.get("total", 12)), x + w / 2, y + 12, 8, "#5A5A5A",
                anchor="center")
        for i, b in enumerate(book):
            cx, cy = x + 10 + (i % 6) * 64, y + 26 + (i // 6) * 92
            col = RARITY_COLORS.get(b["rarity"], "#7D7468")
            ui.fill(cx, cy, 60, 88, "#FFFDF7" if b["found"] else "#E3D5BA")
            ui.border(cx, cy, 60, 88, col)
            img = sprites.pet(b["id"], 0)
            if not b["found"]:
                img = img.copy()
                img.fill((40, 34, 28, 255), special_flags=pygame.BLEND_RGBA_MIN)
            ui.image(img, cx + 30, cy + 22, zoom=2.5, anchor="center")
            ui.text(b["zodiac_vi"], cx + 30, cy + 44, 7, "#8E877A", anchor="center")
            if b["found"]:
                ui.text(f"{b['hanzi']} {b['pinyin']}", cx + 30, cy + 56, 9, "#2B2B2B", kind="han", anchor="center")
                ui.text(b["name_vi"], cx + 30, cy + 70, 8, col, anchor="center")
                if ui.hover(cx, cy, 60, 88):
                    ui.set_tooltip(b["skill_vi"])
            else:
                ui.text(T.PETS_UNKNOWN, cx + 30, cy + 64, 7, "#8E877A", anchor="center")
        if ui.button("petbook_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
