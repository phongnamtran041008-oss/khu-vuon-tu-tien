"""Khắc Văn (spec 12.2) at the Lò Rèn: pick a learned word (mastery >= 70), answer three
questions about it in a row, and it is carved on the piece with the stat of that word."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from .base import Scene
from .quiz import QuizScene


class InscribeScene(Scene):
    def __init__(self, game, instance_id: int, on_close=None):
        super().__init__(game)
        self.instance_id = instance_id
        self.on_close = on_close
        self.data: dict | None = None
        self.busy = False
        self.scroll = 0
        self.step = None            # (n, total) while a try is running
        self.reload()

    def reload(self):
        self.api.get(f"/forge/inscribe/{self.instance_id}", lambda r: setattr(self, "data", r), self.game.api_error)

    def close(self):
        super().close()
        if self.on_close:
            self.on_close()

    def start(self, word: dict):
        self.busy = True

        def ok(r):
            self.busy = False
            self.game.refresh_me()
            self.game.refresh_inv()
            self.ask(r["question"])

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/forge/inscribe/start", {"instance_id": self.instance_id, "word_id": word["word_id"]}, ok, err)

    def ask(self, q: dict):
        self.step = (q.get("number", 1), q.get("total", 3))
        q = {**q, "instruction_vi": f"{T.INSCRIBE_STEP.format(n=self.step[0], t=self.step[1])} · "
                                    f"{q.get('instruction_vi', '')}"}
        self.game.push(QuizScene(self.game, q, on_result=self.on_result, show_timer=True))

    def on_result(self, res: dict):
        ins = res.get("inscribe") or {}
        if res.get("next"):
            self.ask(res["next"])
            return
        self.step = None
        if ins.get("success"):
            c = ins["carved"]
            self.game.toast(T.INSCRIBE_DONE.format(c=c["hanzi"], name=ins["item"]["name_vi"], v=c["value"],
                                                   s=c["stat_vi"]), "#C99A3A")
            self.game.audio.play("discover")
            self.game.refresh_cult()
        else:
            self.game.toast(T.INSCRIBE_FAIL, "#BC4749")
        self.reload()

    def erase(self, index: int, hanzi: str):
        self.busy = True

        def ok(r):
            self.busy = False
            self.game.toast(T.INSCRIBE_ERASED.format(c=hanzi), "#5A5A5A")
            self.game.refresh_me()
            self.game.refresh_cult()
            self.reload()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/forge/inscribe/erase", {"instance_id": self.instance_id, "index": index}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 20, 400, 232
        d = self.data
        ui.panel(x, y, w, h, T.INSCRIBE_TITLE.format(name=d["item"]["name_vi"] if d else ""))
        if d is None:
            ui.text("...", 240, 130, 10, anchor="center")
            if ui.key(pygame.K_ESCAPE):
                self.close()
            return
        ui.text(T.INSCRIBE_HINT.format(m=d["mastery_min"], q=d["questions"]), x + 12, y + 10, 7, "#5A5A5A",
                max_w=w - 24)
        ui.text(T.INSCRIBE_SLOTS.format(u=d["used"], s=d["slots"]) + " · " + T.INSCRIBE_FEE.format(f=d["fee_vi"]),
                x + 12, y + 32, 7, "#2B2B2B")
        # what is carved already
        for i, ins in enumerate(d["inscriptions"]):
            bx = x + 12 + i * 92
            ui.fill(bx, y + 44, 88, 22, "#F4E6C2")
            ui.border(bx, y + 44, 88, 22, "#C99A3A")
            ui.text(ins["hanzi"], bx + 12, y + 55, 12, "#2B2B2B", kind="han", anchor="center")
            ui.text(f"+{ins['value']} {T.STATS_VI.get(ins['stat'], ins['stat'])}", bx + 24, y + 50, 6, "#6A994E")
            if ui.button(f"ins_erase_{i}", bx + 24, y + 57, 60, 8, T.INSCRIBE_ERASE.format(p=d["erase_fee"]), size=5,
                         enabled=not self.busy):
                self.erase(i, ins["hanzi"])
                return
        words = [wd for wd in d["words"] if not wd["carved"]]
        full = d["used"] >= d["slots"]
        if not any(wd["ok"] for wd in words):
            ui.text(T.INSCRIBE_NONE.format(m=d["mastery_min"]), x + 12, y + 76, 8, "#8E877A", max_w=w - 24)
        per = 7
        if ui.inp.wheel:
            self.scroll = max(0, min(max(0, len(words) - per), self.scroll - ui.inp.wheel))
        for row, wd in enumerate(words[self.scroll:self.scroll + per]):
            ry = y + 72 + row * 19
            ui.fill(x + 10, ry, w - 20, 17, "#FFFDF7" if row % 2 else "#F8F1E3")
            ui.text(wd["hanzi"], x + 16, ry + 8, 10, "#2B2B2B" if wd["ok"] else "#8E877A", kind="han", anchor="midleft")
            ui.text(f"{wd['pinyin']} · {wd['meaning_vi']}", x + 60, ry + 8, 7, "#5A5A5A", kind="han", anchor="midleft")
            ui.text(f"+{wd['value']} {wd['stat_vi']}", x + w - 150, ry + 8, 7, "#6A994E", anchor="midright")
            if wd["ok"]:
                if ui.button(f"ins_go_{wd['word_id']}", x + w - 84, ry + 1, 70, 15, T.INSCRIBE_GO, size=7, style="gold",
                             enabled=not self.busy and not full):
                    self.start(wd)
                    return
            else:
                ui.text(T.INSCRIBE_LOW.format(m=wd["mastery"]), x + w - 20, ry + 8, 7, "#BC4749", anchor="midright")
        if ui.button("ins_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
