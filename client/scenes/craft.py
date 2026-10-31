"""Bàn Ghép Câu (spec 6.4): put fruits in order to form the sentence whose meaning is shown."""
from __future__ import annotations

import random

import pygame

from .. import strings_vi as T
from ..art.palette import RARITY_COLORS
from .base import Scene


class CraftScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.sentences = None
        self.fruits = None
        self.current = None
        self.slots: list[str | None] = []
        self.wrong_slot: int | None = None
        self.line = ""
        self.done = None
        self.busy = False
        self.reload()

    def reload(self):
        self.api.get("/sentences", lambda r: setattr(self, "sentences", r["sentences"]), self.game.api_error)
        self.api.get("/fruits", lambda r: setattr(self, "fruits", r["fruits"]), self.game.api_error)

    def pick(self, s):
        self.current, self.slots = s, [None] * s["slots"]
        self.wrong_slot, self.line, self.done = None, T.CRAFT_HINT, None

    def available(self) -> dict:
        have = {f["word_id"]: f["count"] for f in (self.fruits or [])}
        for wid in self.slots:
            if wid:
                have[wid] -= 1
        return have

    def submit(self):
        self.busy = True

        def ok(r):
            self.busy = False
            if r["correct"]:
                self.done = r
                self.game.audio.play("reveal")
                self.game.state.me["spirit_stones"] = r["spirit_stones"]
                self.reload()
            else:
                self.game.audio.play("wrong")
                self.wrong_slot = r["first_wrong_slot"]
                self.line = random.choice(T.CRAFT_WRONG)
                if r.get("right_words_wrong_order"):
                    self.line += " (Đủ đúng các từ rồi, chỉ sai thứ tự.)"

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/sentences/craft", {"sentence_id": self.current["sentence_id"], "word_ids": self.slots}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 20, 400, 232
        ui.panel(x, y, w, h, T.CRAFT_TITLE)
        if self.current is None:
            self.draw_list(ui, x, y, w, h)
        else:
            self.draw_board(ui, x, y, w, h)
        if ui.button("cr_close", x + w - 76, y + h - 22, 64, 14, T.CLOSE, key=pygame.K_ESCAPE):
            if self.current and not self.done:
                self.current = None
            else:
                self.close()

    def draw_list(self, ui, x, y, w, h):
        ui.text(T.CRAFT_PICK, x + 14, y + 14, 9)
        if self.sentences is None:
            return
        ready = [s for s in self.sentences if s["ready"]]
        if not ready:
            ui.text(T.CRAFT_NONE, x + 14, y + 32, 8, "#5A5A5A", max_w=w - 28)
        for i, s in enumerate(ready[:9]):
            by = y + 30 + i * 19
            label = f"{s['vi']}  ({s['slots']} quả)"
            if ui.button(f"sent_{s['sentence_id']}", x + 14, by, w - 28, 16, label):
                self.pick(s)
            ui.text(T.CRAFT_REWARD.format(n=s["reward"]), x + w - 20, by + 8, 7, "#C99A3A", anchor="midright")

    def draw_board(self, ui, x, y, w, h):
        s = self.current
        ui.text(s["vi"], x + w / 2, y + 16, 11, anchor="center", max_w=w - 30)
        n = len(self.slots)
        sw = min(44, (w - 40) / max(1, n) - 4)
        sx = x + w / 2 - (n * (sw + 4)) / 2
        for i, wid in enumerate(self.slots):
            bx = sx + i * (sw + 4)
            border = "#BC4749" if self.wrong_slot == i else "#2B2B2B"
            ui.fill(bx, y + 34, sw, 34, "#FFFDF7")
            ui.border(bx, y + 34, sw, 34, border, 2 if self.wrong_slot == i else 1)
            ui.widgets[f"slot_{i}"] = ui.rect(bx, y + 34, sw, 34)
            if wid:
                hz = next((f["hanzi"] for f in self.fruits or [] if f["word_id"] == wid), "?")
                ui.text(hz, bx + sw / 2, y + 51, 15 if len(hz) <= 2 else 10, kind="han", anchor="center")
                if not self.done and ui.click_in(bx, y + 34, sw, 34):
                    self.slots[i] = None
                    self.wrong_slot = None
        ui.text(s.get("end_punct", ""), sx + n * (sw + 4) + 2, y + 51, 15, kind="han", anchor="midleft")
        if self.done:
            ui.text(T.CRAFT_DONE, x + w / 2, y + 84, 12, "#6A994E", anchor="center")
            ui.text(self.done["text"], x + w / 2, y + 106, 18, kind="han", anchor="center")
            ui.text(self.done["pinyin"], x + w / 2, y + 126, 9, "#5A5A5A", kind="han", anchor="center")
            ui.text(T.REWARD.format(n=self.done["reward"]), x + w / 2, y + 144, 11, "#C99A3A", anchor="center")
            if ui.button("cr_more", x + w / 2 - 50, y + 168, 100, 16, "Ghép câu khác", style="primary",
                         key=pygame.K_RETURN):
                self.current = None
            return
        ui.text(f"{T.MASTER}: {self.line}", x + 14, y + 74, 8, "#5A5A5A", max_w=w - 28)
        have = self.available()
        fx, fy = x + 14, y + 112
        for f in self.fruits or []:
            left = have.get(f["word_id"], 0)
            if left <= 0:
                continue
            fw = max(30, ui.text_size(f["hanzi"], 13, "han")[0] + 14)
            if fx + fw > x + w - 14:
                fx, fy = x + 14, fy + 30
            if fy > y + h - 50:
                break
            if ui.button(f"fruit_{f['word_id']}", fx, fy, fw, 24, f["hanzi"], kind="han", size=13):
                if None in self.slots:
                    self.slots[self.slots.index(None)] = f["word_id"]
                    self.wrong_slot = None
            ui.fill(fx + fw - 9, fy - 3, 11, 8, RARITY_COLORS.get(f["rarity"]))
            ui.text(str(left), fx + fw - 3.5, fy + 1, 6, "#FFFFFF", anchor="center")
            fx += fw + 6
        full = None not in self.slots
        if ui.button("cr_clear", x + 14, y + h - 22, 60, 14, T.QUIZ_CLEAR, enabled=any(self.slots)):
            self.slots = [None] * len(self.slots)
            self.wrong_slot = None
        if ui.button("cr_go", x + w / 2 - 40, y + h - 24, 80, 18, T.CRAFT_GO, style="primary",
                     enabled=full and not self.busy, key=pygame.K_RETURN if full else None):
            self.submit()
