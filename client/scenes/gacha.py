"""Thiên Cơ Các — seed, bee-egg and Linh Thú gacha (spec 6.1, 13). Rates are shown openly; all
randomness and charging happen on the server, the client only plays the opening animation."""
from __future__ import annotations

import math

import pygame

from .. import strings_vi as T
from ..art.palette import RARITY_COLORS
from ..engine import sprites
from ..ui.kit import rarity_name
from .base import Scene

ORDER = ["common", "rare", "epic", "legendary"]
BEE_ORDER = ["pham", "linh", "huyen", "dia", "thien"]
BEE_COLORS = {"pham": "#7D7468", "linh": "#6A994E", "huyen": "#4A7CC8", "dia": "#8E5AC8", "thien": "#C99A3A"}
BEE_NAMES = {"pham": "Phàm", "linh": "Linh", "huyen": "Huyền", "dia": "Địa", "thien": "Thiên"}


class GachaScene(Scene):
    def __init__(self, game, on_close=None, tab: str = "seeds"):
        super().__init__(game)
        self.on_close = on_close
        self.tab = tab
        self.banners: dict = {}
        self.banner: dict | None = None
        self.results: list | None = None
        self.anim_t = 0.0
        self.busy = False
        self.opened = False
        self.refresh()

    def refresh(self):
        def ok(r):
            self.banners = {b["id"]: b for b in r["banners"]}
            self.banner = self.banners.get(self.tab)
        self.api.get("/gacha/banners", ok, self.game.api_error)
        self.api.get("/me", lambda me: self.game.state.me.update(me), lambda e: None)

    def roll(self, count: int, free: bool = False, currency: str = "spirit_stones"):
        self.busy = True
        banner = self.tab

        def ok(r):
            self.busy = False
            self.results = r["results"]
            self.anim_t = 0.0
            self.opened = False
            self.game.state.me["spirit_stones"] = r["spirit_stones"]
            self.game.state.me["immortal_jade"] = r.get("immortal_jade", self.game.state.me.get("immortal_jade", 0))
            self.game.state.me["daily_rolls_left"] = r["daily_rolls_left"]
            if banner == "bees":
                self.game.refresh_inv()
            if banner == "pets":
                self.game.refresh_pets()
            if free:
                self.game.state.me["free_rolls_left"] = 0
            if self.banner is not None:
                self.banner["pity_counters"] = r["pity"]

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/gacha/roll", {"banner": banner, "count": count, "free": free, "currency": currency}, ok, err)

    def update(self, dt, top):
        if self.results is not None:
            prev = self.anim_t
            self.anim_t += dt
            if prev < 0.9 <= self.anim_t:
                self.game.audio.play("crack")
            if prev < 1.3 <= self.anim_t:
                rank = (lambda r: BEE_ORDER.index(r)) if self.results[0]["rarity"] in BEE_ORDER else ORDER.index
                best = max(rank(s["rarity"]) for s in self.results)
                self.game.audio.play("reveal" if best >= 2 else "coin")
                self.opened = True

    def close(self):
        super().close()
        if self.on_close:
            self.on_close()

    def draw_ui(self, ui):
        ui.dim(170)
        if self.results is not None:
            self.draw_opening(ui)
            return
        x, y, w, h = 70, 26, 340, 220
        title = {"bees": T.GACHA_BEES_TITLE, "pets": T.GACHA_PET_TITLE}.get(self.tab, T.GACHA_TITLE)
        ui.panel(x, y, w, h, title)
        for i, (k, label) in enumerate((("seeds", T.GACHA_TAB_SEEDS), ("bees", T.GACHA_TAB_BEES),
                                        ("pets", T.GACHA_TAB_PETS))):
            if ui.button(f"g_tab_{k}", x + 8 + i * 54, y + 10, 52, 13, label, size=7, selected=self.tab == k,
                         enabled=not self.busy):
                self.tab = k
                self.banner = self.banners.get(k)
        if self.tab == "bees":
            self.draw_bees(ui, x, y, w, h)
            return
        if self.tab == "pets":
            self.draw_pets(ui, x, y, w, h)
            return
        me = self.game.state.me
        # altar art
        img = sprites.prop("shrine", 0, int(ui.time * 3) % 4)
        ui.image(img, x + 60, y + 100, zoom=2.5, anchor="center")
        rx, rw = x + 120, w - 132
        yy = ui.text(T.GACHA_RATES, rx, y + 16, 8, max_w=rw).bottom + 3
        yy = ui.text(T.GACHA_PITY, rx, yy, 7, "#5A5A5A", max_w=rw).bottom + 3
        if self.banner:
            pc = self.banner.get("pity_counters", {})
            yy = ui.text(T.GACHA_PITY_NOW.format(e=pc.get("epic", 0), l=pc.get("legendary", 0)), rx, yy, 7,
                         "#8E877A", max_w=rw).bottom + 2
            eff = self.banner.get("effective_rates_with_pity", {})
            yy = ui.text(T.GACHA_EFFECTIVE.format(l=round(eff.get("legendary", 0) * 100, 1),
                                                  e=round(eff.get("epic", 0) * 100, 1)), rx, yy, 7, "#8E877A",
                         max_w=rw).bottom + 2
        left = me.get("daily_rolls_left", 15)
        ui.text(T.GACHA_LEFT.format(n=left), rx, y + 118, 9, "#BC4749" if left <= 0 else "#2B2B2B")
        stones = me.get("spirit_stones", 0)
        ui.image(sprites.icon("stone"), rx, y + 131, zoom=1)
        ui.text(f"{stones:,}".replace(",", "."), rx + 11, y + 135, 9, anchor="midleft")
        by = y + 146
        free = me.get("free_rolls_left", 0) > 0
        if ui.button("g_free", rx, by, 200, 16, T.GACHA_FREE, style="gold", enabled=free and left > 0 and not self.busy):
            self.roll(1, free=True)
        if ui.button("g_roll1", rx, by + 22, 96, 18, T.GACHA_ROLL1.format(p=100), style="primary",
                     enabled=left >= 1 and stones >= 100 and not self.busy):
            self.roll(1)
        if ui.button("g_roll10", rx + 104, by + 22, 96, 18, T.GACHA_ROLL10.format(p=900), style="primary",
                     enabled=left >= 10 and stones >= 900 and not self.busy,
                     tooltip="10 lượt chắc chắn có ít nhất 1 hạt Hiếm trở lên"):
            self.roll(10)
        if ui.button("g_close", x + w / 2 - 35, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def draw_bees(self, ui, x, y, w, h):
        """Trứng Ong (spec 13): 300 Linh Thạch or 5 Tiên Ngọc; eggs hatch in the hive."""
        me = self.game.state.me
        t = ui.time
        for i, r in enumerate(BEE_ORDER):     # five eggs on the altar, gently bobbing
            ex = x + 20 + i * 20
            ui.image(sprites.egg(BEE_COLORS[r])[0], ex, y + 60 + math.sin(t * 2 + i) * 2, zoom=1.5, anchor="center")
        ui.image(sprites.prop("hive", 0, int(t * 3) % 4), x + 60, y + 140, zoom=2, anchor="center")
        rx, rw = x + 120, w - 132
        yy = ui.text(T.GACHA_BEE_RATES, rx, y + 16, 8, max_w=rw).bottom + 3
        yy = ui.text(T.GACHA_BEE_PITY, rx, yy, 7, "#5A5A5A", max_w=rw).bottom + 3
        if self.banner:
            pc = self.banner.get("pity_counters", {})
            yy = ui.text(T.GACHA_BEE_PITY_NOW.format(h=pc.get("huyen", 0), t=pc.get("thien", 0)), rx, yy, 7,
                         "#8E877A", max_w=rw).bottom + 2
            eff = self.banner.get("effective_rates_with_pity", {})
            ui.text(T.GACHA_BEE_EFFECTIVE.format(t=round(eff.get("thien", 0) * 100, 1),
                                                 h=round(eff.get("huyen", 0) * 100, 1)), rx, yy, 7, "#8E877A",
                    max_w=rw)
        stones, jade = me.get("spirit_stones", 0), me.get("immortal_jade", 0)
        ui.image(sprites.icon("stone"), rx, y + 128, zoom=1)
        ui.text(f"{stones:,}".replace(",", ".") + f"  ·  {jade} {T.JADE}", rx + 11, y + 132, 8, anchor="midleft")
        by = y + 142
        b = self.banner or {}
        p1 = (b.get("price") or {}).get("spirit_stones", 300)
        p10 = (b.get("price_10") or {}).get("spirit_stones", p1 * 10)
        j1 = (b.get("alt_price") or {}).get("immortal_jade", 5)
        j10 = (b.get("alt_price_10") or {}).get("immortal_jade", j1 * 10)
        if ui.button("g_bee1", rx, by, 96, 17, T.GACHA_ROLL1.format(p=p1), style="primary",
                     enabled=stones >= p1 and not self.busy):
            self.roll(1)
        if ui.button("g_bee10", rx + 104, by, 96, 17, T.GACHA_ROLL10.format(p=p10), style="primary",
                     enabled=stones >= p10 and not self.busy, tooltip="10 lượt chắc chắn có ít nhất 1 trứng Linh"):
            self.roll(10)
        if ui.button("g_bee1_jade", rx, by + 22, 96, 15, f"Quay 1 ({j1} {T.JADE})", size=7, style="gold",
                     enabled=jade >= j1 and not self.busy):
            self.roll(1, currency="immortal_jade")
        if ui.button("g_bee10_jade", rx + 104, by + 22, 96, 15, f"Quay 10 ({j10} {T.JADE})", size=7, style="gold",
                     enabled=jade >= j10 and not self.busy):
            self.roll(10, currency="immortal_jade")
        if ui.button("g_close", x + w / 2 - 35, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def draw_pets(self, ui, x, y, w, h):
        """Linh Thú (spec 13): 500 Linh Thạch or 10 Tiên Ngọc, the 12 con giáp walking round the altar."""
        me = self.game.state.me
        t = ui.time
        kinds = list(((self.game.state.pets or {}).get("looks") or {}).keys())
        for i, kind in enumerate(kinds):
            ang = t * 0.4 + i * 6.283 / max(1, len(kinds))
            ui.image(sprites.pet(kind, int(t * 4 + i) % 2, math.sin(ang) < 0), x + 60 + math.cos(ang) * 44,
                     y + 104 + math.sin(ang) * 30, zoom=1.2, anchor="center")
        ui.image(sprites.prop("shrine", 0, int(t * 3) % 4), x + 60, y + 100, zoom=1.6, anchor="center")
        rx, rw = x + 120, w - 132
        yy = ui.text(T.GACHA_PET_RATES, rx, y + 16, 8, max_w=rw).bottom + 3
        yy = ui.text(T.GACHA_PET_PITY, rx, yy, 7, "#5A5A5A", max_w=rw).bottom + 3
        if self.banner:
            pc = self.banner.get("pity_counters", {})
            ui.text(T.GACHA_PET_PITY_NOW.format(e=pc.get("epic", 0), l=pc.get("legendary", 0)), rx, yy, 7, "#8E877A",
                    max_w=rw)
        stones, jade = me.get("spirit_stones", 0), me.get("immortal_jade", 0)
        ui.image(sprites.icon("stone"), rx, y + 128, zoom=1)
        ui.text(f"{stones:,}".replace(",", ".") + f"  ·  {jade} {T.JADE}", rx + 11, y + 132, 8, anchor="midleft")
        by = y + 142
        b = self.banner or {}
        p1 = (b.get("price") or {}).get("spirit_stones", 500)
        p10 = (b.get("price_10") or {}).get("spirit_stones", p1 * 10)
        j1 = (b.get("alt_price") or {}).get("immortal_jade", 10)
        j10 = (b.get("alt_price_10") or {}).get("immortal_jade", j1 * 10)
        if ui.button("g_pet1", rx, by, 96, 17, T.GACHA_ROLL1.format(p=p1), style="primary",
                     enabled=stones >= p1 and not self.busy):
            self.roll(1)
        if ui.button("g_pet10", rx + 104, by, 96, 17, T.GACHA_ROLL10.format(p=p10), style="primary",
                     enabled=stones >= p10 and not self.busy):
            self.roll(10)
        if ui.button("g_pet1_jade", rx, by + 22, 96, 15, f"Quay 1 ({j1} {T.JADE})", size=7, style="gold",
                     enabled=jade >= j1 and not self.busy):
            self.roll(1, currency="immortal_jade")
        if ui.button("g_pet10_jade", rx + 104, by + 22, 96, 15, f"Quay 10 ({j10} {T.JADE})", size=7, style="gold",
                     enabled=jade >= j10 and not self.busy):
            self.roll(10, currency="immortal_jade")
        if ui.button("g_close", x + w / 2 - 35, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def draw_pets_open(self, ui, res):
        from .pets import RARITY_COLORS
        n = len(res)
        cols = 5 if n > 1 else 1
        cell = 72 if n > 1 else 120
        rows = (n + cols - 1) // cols
        ox = 240 - cols * cell / 2
        oy = 135 - rows * (cell + 16) / 2
        t = self.anim_t
        zoom = 3 if n > 1 else 5
        for i, p in enumerate(res):
            cx = ox + (i % cols) * cell + cell / 2
            cy = oy + (i // cols) * (cell + 16) + cell / 2
            col = RARITY_COLORS.get(p["rarity"], "#7D7468")
            if t < 1.3:     # a ball of light gathering
                self._glow(ui, cx, cy, col, min(1.0, t / 1.3) * 0.7, n)
                continue
            k = min(1.0, (t - 1.3 - i * 0.08) / 0.4)
            self._glow(ui, cx, cy, col, 0.6 + 0.4 * max(0.0, k), n)
            if k <= 0:
                continue
            ui.image(sprites.pet(p["pet_type"], int(t * 4) % 2), cx, cy - 4, zoom=zoom * k, anchor="center")
            if k >= 1:
                ui.text(f"{p['name_vi']} {p['hanzi']}", cx, cy + cell / 2 - 10, 7 if n > 1 else 10, col, kind="han",
                        anchor="center")
                tag = T.GACHA_PET_NEW if p.get("new") else T.GACHA_PET_STONES.format(n=p["stones"])                     if p.get("stones") else T.GACHA_PET_LEVEL.format(l=p.get("level", 1))
                ui.text(tag, cx, cy - cell / 2 + 6, 7, "#BC4749" if p.get("new") else "#F4EBD9", anchor="center")
        if self.opened and t > 1.3 + n * 0.08 + 0.3:
            ui.text(T.GACHA_PET_DONE, 240, 236, 8, "#F4EBD9", anchor="center")
            if ui.button("g_done", 240 - 40, 246, 80, 16, T.OK, style="primary", key=pygame.K_RETURN) or                     ui.key(pygame.K_ESCAPE):
                self.results = None
                self.refresh()
        elif ui.consume_click():
            self.anim_t = max(self.anim_t, 1.3 + n * 0.08 + 0.31)
            self.opened = True

    def draw_opening(self, ui):
        res = self.results
        if res and res[0].get("pet_type"):
            self.draw_pets_open(ui, res)
            return
        if res and res[0]["rarity"] in BEE_ORDER:
            self.draw_eggs(ui, res)
            return
        n = len(res)
        cols = 5 if n > 1 else 1
        cell = 72 if n > 1 else 120
        rows = (n + cols - 1) // cols
        ox = 240 - cols * cell / 2
        oy = 135 - rows * (cell + 16) / 2
        t = self.anim_t
        for i, s in enumerate(res):
            cx = ox + (i % cols) * cell + cell / 2
            cy = oy + (i // cols) * (cell + 16) + cell / 2
            frames = sprites.seeds(s["rarity"])
            col = RARITY_COLORS[s["rarity"]]
            if t < 0.9:  # shaking
                dx = math.sin(t * 40 + i) * (1 + t * 2)
                ui.image(frames[0], cx + dx, cy, zoom=3 if n > 1 else 5, anchor="center")
            elif t < 1.3:  # cracking with light leaking out
                self._glow(ui, cx, cy, col, (t - 0.9) / 0.4 * 0.6, n)
                ui.image(frames[1 if t < 1.1 else 2], cx, cy, zoom=3 if n > 1 else 5, anchor="center")
            else:
                k = min(1.0, (t - 1.3 - i * 0.08) / 0.4)
                if k <= 0:
                    ui.image(frames[2], cx, cy, zoom=3 if n > 1 else 5, anchor="center")
                    continue
                self._glow(ui, cx, cy, col, 0.6 + 0.4 * k, n)
                cw, chh = (cell - 14) * k, (cell - 4) * k
                ui.fill(cx - cw / 2, cy - chh / 2, cw, chh, "#F4EBD9")
                ui.border(cx - cw / 2, cy - chh / 2, cw, chh, col, 2)
                if k < 1:
                    continue
                hz = s["word"]["hanzi"]
                size = (24 if len(hz) == 1 else 14 if len(hz) == 2 else 9) * (1 if n > 1 else 1.8)
                ui.text(hz, cx, cy - 2, size, "#2B2B2B", kind="han", anchor="center")
                ui.text(rarity_name(s["rarity"]), cx, cy + chh / 2 - 7, 7, col, anchor="center")
                ui.text(T.DUPLICATE if s["duplicate"] else T.GACHA_NEW, cx, cy - chh / 2 + 6, 7,
                        "#8E877A" if s["duplicate"] else "#BC4749", anchor="center")
        if self.opened and t > 1.3 + n * 0.08 + 0.3:
            ui.text("Hạt đã vào túi. Gieo trong vườn để học chữ mới!", 240, 236, 8, "#F4EBD9", anchor="center")
            if ui.button("g_done", 240 - 40, 246, 80, 16, T.OK, style="primary", key=pygame.K_RETURN) or \
                    ui.key(pygame.K_ESCAPE):
                self.results = None
                self.refresh()
        elif ui.consume_click():
            self.anim_t = max(self.anim_t, 1.3 + n * 0.08 + 0.31)
            if not self.opened:
                self.opened = True

    def _glow(self, ui, cx, cy, color, strength, n):
        r = (30 if n > 1 else 52) * strength
        surf = pygame.Surface((int(r * 2 * ui.s), int(r * 2 * ui.s)), pygame.SRCALPHA)
        c = pygame.Color(color)
        for k in range(6, 0, -1):
            pygame.draw.circle(surf, (c.r, c.g, c.b, int(30 * strength)), surf.get_rect().center,
                               int(r * ui.s * k / 6))
        wx, wy = ui.d.to_window(cx, cy)
        ui.win.blit(surf, (wx - surf.get_width() // 2, wy - surf.get_height() // 2))

    def draw_eggs(self, ui, res):
        n = len(res)
        cols = 5 if n > 1 else 1
        cell = 72 if n > 1 else 120
        rows = (n + cols - 1) // cols
        ox = 240 - cols * cell / 2
        oy = 135 - rows * (cell + 16) / 2
        t = self.anim_t
        zoom = 3 if n > 1 else 5
        for i, e in enumerate(res):
            cx = ox + (i % cols) * cell + cell / 2
            cy = oy + (i // cols) * (cell + 16) + cell / 2
            col = BEE_COLORS[e["rarity"]]
            frames = sprites.egg(col)
            if t < 0.9:
                ui.image(frames[0], cx + math.sin(t * 40 + i) * (1 + t * 2), cy, zoom=zoom, anchor="center")
            elif t < 1.3:
                self._glow(ui, cx, cy, col, (t - 0.9) / 0.4 * 0.6, n)
                ui.image(frames[1], cx, cy, zoom=zoom, anchor="center")
            else:
                k = min(1.0, (t - 1.3 - i * 0.08) / 0.4)
                self._glow(ui, cx, cy, col, 0.6 + 0.4 * max(0.0, k), n)
                ui.image(frames[1], cx, cy, zoom=zoom, anchor="center")
                if k >= 1:
                    ui.text(e["name_vi"], cx, cy + cell / 2 - 4, 7 if n > 1 else 10, col, anchor="center")
        if self.opened and t > 1.3 + n * 0.08 + 0.3:
            ui.text(T.GACHA_BEE_DONE, 240, 236, 8, "#F4EBD9", anchor="center")
            if ui.button("g_done", 240 - 40, 246, 80, 16, T.OK, style="primary", key=pygame.K_RETURN) or \
                    ui.key(pygame.K_ESCAPE):
                self.results = None
                self.refresh()
        elif ui.consume_click():
            self.anim_t = max(self.anim_t, 1.3 + n * 0.08 + 0.31)
            self.opened = True
