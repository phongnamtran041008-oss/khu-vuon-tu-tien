"""Overlays for one garden plot: actions, seed picker, the word introduction card."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..art.palette import RARITY_COLORS
from ..ui.kit import rarity_name
from .abode import fmt_secs
from .base import Scene


class PlotPanel(Scene):
    def __init__(self, game, abode, plot_id: int):
        super().__init__(game)
        self.abode, self.plot_id = abode, plot_id
        self.busy = False

    @property
    def plot(self):
        return self.abode.plot_by_id(self.plot_id)

    def draw_ui(self, ui):
        p = self.plot
        if p is None:
            self.close()
            return
        ui.dim(90)
        x, y, w, h = 140, 150, 200, 92
        ui.panel(x, y, w, h)
        word = p.get("word")
        if ui.key(pygame.K_ESCAPE) or (ui.inp.clicked and not ui.hover(x, y, w, h)):
            self.close()
            return
        if not p["unlocked"]:
            ui.text(T.PLOT_LOCKED, x + w / 2, y + 14, 10, anchor="center")
            if p.get("can_unlock"):
                cost = p.get("unlock_cost")
                ui.text("Dọn cỏ, nhặt đá để có thêm một ô trồng.", x + w / 2, y + 32, 8, "#5A5A5A", anchor="center")
                if ui.button("pp_unlock", x + 30, y + h - 26, w - 60, 16, T.PLOT_UNLOCK.format(cost=cost),
                             style="gold", key=pygame.K_RETURN, enabled=not self.busy):
                    self.unlock()
            else:
                ui.text(T.PLOT_UNLOCK_FAR, x + w / 2, y + 40, 8, "#5A5A5A", anchor="center")
            return
        if not word:
            ui.text(T.PLOT_EMPTY, x + w / 2, y + 16, 10, anchor="center")
            if ui.button("pp_plant", x + 50, y + h - 30, w - 100, 18, T.PLANT, style="primary", key=pygame.K_RETURN):
                self.close()
                self.game.push(SeedPicker(self.game, self.abode, self.plot_id))
            return
        ui.text(word["hanzi"], x + 30, y + 30, 22, kind="han", anchor="center")
        ui.text(word.get("pinyin") or "?", x + 30, y + 52, 9, kind="han", anchor="center")
        ui.text(T.STAGES[p.get("stage", 0)], x + 62, y + 12, 10)
        stage = p.get("stage", 0)
        ui.progress(x + 62, y + 26, 120, 6, stage / 5, "#6A994E")
        info = ""
        if p.get("ripe"):
            info = "Chín rồi!"
        elif stage > 0:
            info = T.DUE_NOW if self.abode.is_due(p) else T.DUE_IN.format(
                t=fmt_secs(self.abode.seconds_left(p) or 0))
        ui.text(info, x + 62, y + 36, 8, "#BC4749" if self.abode.is_due(p) else "#5A5A5A")
        if (p.get("wither") or 0) >= 1:
            ui.text(T.WITHER.format(p=int(p["wither"])), x + 62, y + 47, 8, "#5A5A5A")
        bx, by, bw = x + 62, y + h - 26, w - 74
        if stage == 0:
            if ui.button("pp_card", bx, by, bw, 16, T.VIEW_CARD, style="primary", key=pygame.K_RETURN):
                self.close()
                self.game.push(IntroCard(self.game, self.abode, self.plot_id))
        elif p.get("ripe"):
            if ui.button("pp_harvest", bx, by, bw, 16, T.HARVEST, style="gold", key=pygame.K_RETURN,
                         enabled=not self.busy):
                self.harvest()
        else:
            due = self.abode.is_due(p)
            if ui.button("pp_review", bx, by, bw, 16, T.REVIEW, style="primary", enabled=due and not self.busy,
                         key=pygame.K_RETURN):
                self.review()

    def unlock(self):
        self.busy = True

        def ok(r):
            self.busy = False
            self.game.state.me["spirit_stones"] = r["spirit_stones"]
            self.game.audio.play("coin")
            self.abode.refresh_garden()
            self.close()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/garden/expand", {"plot_id": self.plot_id}, ok, err)

    def harvest(self):
        self.busy = True

        def ok(r):
            self.busy = False
            p = self.plot
            cx, cy = self.abode.plot_center(p)
            self.abode.fx.burst(cx, cy, "o", 24, 45)
            self.abode.fx.float_text(f"+{r['fruits_gained']} quả {p['word']['hanzi']}", cx, cy - 10, "#BC4749")
            if r.get("spirit_fruit"):     # spec 10.2: a pollinated plant may give a Linh Quả
                self.abode.fx.float_text(T.SPIRIT_FRUIT, cx, cy - 20, "#C99A3A")
                self.game.toast(T.SPIRIT_FRUIT, "#C99A3A")
            self.game.audio.play("coin")
            self.abode.update_plot(r["plot"])
            self.game.on_xp(r.get("xp"))
            self.close()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/garden/harvest", {"plot_id": self.plot_id}, ok, err)

    def review(self):
        self.busy = True
        from .quiz import QuizScene

        def ok(q):
            self.busy = False
            plot = self.plot
            self.close()
            self.game.push(QuizScene(self.game, q, on_result=lambda res: self.abode.on_answer(plot, res)))

        def err(e):
            self.busy = False
            self.game.api_error(e)
            self.abode.refresh_garden()
        self.api.post("/garden/review", {"plot_id": self.plot_id}, ok, err)


class SeedPicker(Scene):
    def __init__(self, game, abode, plot_id: int):
        super().__init__(game)
        self.abode, self.plot_id = abode, plot_id
        self.seeds: list | None = None
        self.scroll = 0
        self.api.get("/seeds", self._got, game.api_error)

    def _got(self, r):
        self.seeds = r["seeds"]

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 120, 40, 240, 190
        ui.panel(x, y, w, h, T.PICK_SEED)
        if self.seeds is None:
            ui.text("...", 240, y + 40, 10, anchor="center")
        elif not self.seeds:
            ui.text(T.NO_SEEDS, x + 14, y + 20, 8, max_w=w - 28)
        else:
            per_row, cell = 6, 36
            visible = self.seeds[self.scroll * per_row:(self.scroll + 4) * per_row]
            for i, s in enumerate(visible):
                cx, cy = x + 12 + (i % per_row) * cell, y + 16 + (i // per_row) * 36
                ui.fill(cx, cy, 32, 32, "#FFFDF7")
                ui.border(cx, cy, 32, 32, RARITY_COLORS[s["rarity"]], 2)
                ui.text(s["hanzi"] if len(s["hanzi"]) <= 2 else s["hanzi"][:2] + "…", cx + 16, cy + 14,
                        13 if len(s["hanzi"]) == 1 else 8, kind="han", anchor="center")
                if s["duplicate"]:
                    ui.text(T.DUPLICATE, cx + 16, cy + 27, 6, "#8E877A", anchor="center")
                ui.widgets[f"seed_{s['seed_id']}"] = ui.rect(cx, cy, 32, 32)
                if ui.hover(cx, cy, 32, 32):
                    ui.set_tooltip(f"{s['hanzi']} · {rarity_name(s['rarity'])}")
                if ui.click_in(cx, cy, 32, 32):
                    self.plant(s)
                    return
            rows = (len(self.seeds) + per_row - 1) // per_row
            if ui.inp.wheel and ui.enabled:
                self.scroll = max(0, min(rows - 4, self.scroll - ui.inp.wheel))
        if ui.button("sp_close", 240 - 35, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def plant(self, seed):
        def ok(view):
            self.game.audio.play("plant")
            self.abode.update_plot(view)
            cx, cy = self.abode.plot_center(view)
            self.abode.fx.burst(cx, cy + 6, "d", 10, 20)
            self.close()
            self.abode.tutorial_event("plant")
        self.api.post("/garden/plant", {"plot_id": self.plot_id, "seed_id": seed["seed_id"]}, ok,
                      self.game.api_error)


class IntroCard(Scene):
    """Stage 0 card: big character, pinyin, meaning, example, listen, 'Đã nhớ' (spec 6.2)."""

    def __init__(self, game, abode, plot_id: int):
        super().__init__(game)
        self.abode, self.plot_id = abode, plot_id
        self.card = None
        self.busy = False
        self.api.get(f"/garden/intro/{plot_id}", self._got, game.api_error)

    def _got(self, c):
        self.card = c
        self.game.audio.play_word(c["id"])

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 70, 22, 340, 228
        ui.panel(x, y, w, h, T.INTRO_TITLE)
        c = self.card
        if c is None:
            ui.text("...", 240, 120, 12, anchor="center")
            if ui.key(pygame.K_ESCAPE):
                self.close()
            return
        ui.fill(x + 14, y + 16, 96, 96, "#FFFDF7")
        ui.border(x + 14, y + 16, 96, 96, RARITY_COLORS.get(c["rarity"], "#9A9A9A"), 2)
        big = 44 if len(c["hanzi"]) == 1 else (26 if len(c["hanzi"]) == 2 else 15)
        ui.text(c["hanzi"], x + 62, y + 64, big, kind="han", anchor="center")
        ui.text(c["pinyin"], x + 62, y + 124, 14, "#BC4749", kind="han", anchor="center")
        ui.text(rarity_name(c["rarity"]), x + 62, y + 140, 7, RARITY_COLORS.get(c["rarity"]), anchor="center")
        rx, rw = x + 122, w - 136
        ui.text(c["meaning_vi"], rx, y + 18, 12, max_w=rw)
        yy = y + 40
        if not c.get("meaning_vi_reviewed"):
            ui.text(T.UNREVIEWED, rx, yy, 7, "#8E877A")
            yy += 10
        if c.get("example"):
            ex = c["example"]
            ui.text(T.EXAMPLE, rx, yy, 8, "#6A994E")
            ui.text(ex["text"], rx, yy + 11, 11, kind="han", max_w=rw)
            ui.text(ex["pinyin"], rx, yy + 27, 7, "#5A5A5A", kind="han", max_w=rw)
            ui.text(ex["vi"], rx, yy + 38, 8, max_w=rw)
            yy += 54
        if c.get("components"):
            ui.text(f"{T.COMPONENTS}: {' + '.join(c['components'])}"
                    + (f" — {c['etymology_hint']}" if c.get("etymology_hint") else ""), rx, yy, 8, "#5A5A5A",
                    max_w=rw)
            yy += 22
        if c.get("measure_words"):
            ui.text(f"{T.MEASURE}: {'、'.join(c['measure_words'])}", rx, yy, 8, "#5A5A5A")
            yy += 12
        if c.get("story_vi"):
            ui.text(T.STORY + ": " + c["story_vi"], x + 14, y + 152, 7, "#5A5A5A", max_w=w - 28)
        if c.get("has_audio") and self.game.audio.has_word(c["id"]):
            if ui.button("ic_listen", x + 34, y + 150 if not c.get("story_vi") else y + 112 - 14, 56, 14,
                         T.INTRO_LISTEN):
                self.game.audio.play_word(c["id"])
        if ui.button("ic_close", x + 14, y + h - 24, 60, 15, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
            return
        if ui.button("ic_remember", x + w - 114, y + h - 26, 100, 18, T.INTRO_REMEMBER, style="primary",
                     key=pygame.K_RETURN, enabled=not self.busy):
            self.remember()

    def remember(self):
        self.busy = True

        def ok(view):
            self.busy = False
            self.game.audio.play("correct")
            found = view.pop("discoveries", [])
            self.abode.update_plot(view)
            cx, cy = self.abode.plot_center(view)
            self.abode.fx.burst(cx, cy, "l", 14, 30)
            self.close()
            if found:
                self.abode.show_discoveries(found)
            self.abode.tutorial_event("learn")

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/garden/learn", {"plot_id": self.plot_id}, ok, err)
