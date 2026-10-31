"""Question card for every question type Q1-Q11 (spec 8.2). The client never knows the
answer: it sends the choice and shows what the server reveals afterwards."""
from __future__ import annotations

import random
import re

import pygame

from .. import strings_vi as T
from ..art.palette import UI as UICOL
from .base import Scene

CJK = re.compile(r"[⺀-鿿]")
TONE_MARKED = re.compile(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]")
KEYS = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4]


# option text: Vietnamese meanings use the pixel font, hanzi/pinyin use Noto
OPTION_KIND = {"Q1": "ui", "Q10": "ui", "Q11": "ui"}


def _kind(text: str, qtype: str = "") -> str:
    if qtype in OPTION_KIND:
        return OPTION_KIND[qtype]
    return "han" if CJK.search(text) or TONE_MARKED.search(text) else "ui"


class QuizScene(Scene):
    compact = False          # True: a shorter card in the lower part of the screen (combat)

    def panel_rect(self) -> tuple[float, float, float, float]:
        return (40, 94, 400, 172) if self.compact else (40, 50, 400, 214)

    def _k(self, v: float) -> float:
        """Prompt sizes/offsets shrink in the compact card."""
        return v * 0.74 if self.compact else v

    def __init__(self, game, question: dict, on_result=None, show_timer: bool | None = None):
        super().__init__(game)
        self.q = question
        self.on_result = on_result
        self.result: dict | None = None
        self.chosen: str | None = None
        self.order: list[str] = []          # Q9 picked token ids
        self.sent = False
        self.t = 0.0
        self.show_timer = (question.get("context") != "garden") if show_timer is None else show_timer
        self.limit = float(question.get("time_limit") or 10)
        self.result_t = 0.0
        self.quip = ""
        game.ui.set_value("quiz_text", "")
        if question.get("input") == "text":
            game.ui.set_focus("quiz_text")
        if question.get("prompt", {}).get("audio"):
            self.play_audio()

    # ------------------------------------------------------------ actions
    def play_audio(self):
        self.api.get(f"/quiz/{self.q['session_id']}/audio", lambda data: self.game.audio.play_bytes(data),
                     lambda e: None, raw=True)

    def submit(self, answer: dict):
        if self.sent:
            return
        self.sent = True
        self.chosen = answer.get("option")

        def ok(res):
            self.result = res
            self.result_t = 0.0
            self.game.on_xp(res.get("xp"))
            good = res.get("correct")
            self.game.audio.play("correct" if good else "wrong")
            self.quip = random.choice(T.QUIP_CORRECT if good else T.QUIP_WRONG)
            if res.get("mishap"):
                self.quip = res["mishap"]["line_vi"]

        def err(e):
            self.sent = False
            self.game.api_error(e)
            if e.status in (404, 409):
                self.close()
        self.api.post("/quiz/answer", {"session_id": self.q["session_id"], "answer": answer}, ok, err)

    auto_close_after: float | None = None   # seconds after the result (combat: 2 s reveal, spec 8.1)

    def draw_result_extra(self, ui, bx, by, bw, bh) -> None:
        pass

    def finish(self):
        self.close()
        if self.on_result and self.result:
            self.on_result(self.result)

    def update(self, dt, top):
        self.t += dt
        if self.result:
            self.result_t += dt
        elif self.show_timer and not self.sent and self.t > self.limit:
            self.submit({})  # time is up: the server records it as wrong

    # ------------------------------------------------------------ drawing
    def draw_ui(self, ui):
        ui.dim(40 if self.compact else 150)
        q = self.q
        x, y, w, h = self.panel_rect()
        ui.panel(x, y, w, h)
        ui.text(q.get("instruction_vi", ""), x + w / 2, y + 10, 9, "#5A5A5A", anchor="center")
        if q.get("number") and q.get("total"):      # Thiên Kiếp: "Câu 4/20"
            ui.text(T.QUIZ_NUMBER.format(n=q["number"], t=q["total"]), x + 12, y + 10, 8, "#BC4749",
                    anchor="midleft")
        if self.show_timer and not self.result:
            frac = max(0.0, 1 - self.t / self.limit)
            ui.progress(x + 12, y + 20, w - 24, 4, frac, "#BC4749" if frac < 0.3 else "#6A994E")
        if not self.result:
            self.draw_prompt(ui, x, y + 26, w)
        inp = q.get("input")
        c = self.compact
        if inp in ("choice", "tone"):
            self.draw_choices(ui, x, y + (86 if c else 112), w)
        elif inp == "text":
            self.draw_text_input(ui, x, y + (96 if c else 120), w)
        elif inp == "order":
            self.draw_order(ui, x, y + (72 if c else 108), w)
        if self.result:
            self.draw_result(ui, x, y, w, h)

    def draw_prompt(self, ui, x, y, w):
        p = self.q.get("prompt", {})
        cx = x + w / 2
        qt = self.q.get("qtype")
        if qt == "Q6":
            ui.text(" ".join(p.get("phrase", [])).replace("__", "＿"), cx, y + self._k(30), self._k(26), kind="han",
                    anchor="center")
            ui.text(p.get("noun_meaning_vi", ""), cx, y + self._k(58), 8, "#5A5A5A", anchor="center")
            return
        if qt == "Q7":
            line = " ".join("＿＿" if t == "__" else t for t in p.get("tokens", []))
            ui.text(line, cx, y + self._k(26), self._k(20), kind="han", anchor="center")
            ui.text(p.get("vi", ""), cx, y + self._k(54), 9, "#5A5A5A", anchor="center")
            return
        if qt == "Q9":
            ui.text(p.get("vi", ""), cx, y + 4, 10, "#5A5A5A", anchor="midtop", max_w=w - 30)
            return
        if qt == "Q10":
            ui.text(p.get("text", ""), cx, y + self._k(34), self._k(22), kind="han", anchor="center", max_w=w - 30)
            return
        if "hanzi" in p:
            n = len(p["hanzi"])
            size = 46 if n == 1 else 36 if n == 2 else 26 if n <= 4 else 20
            ui.text(p["hanzi"], cx, y + self._k(34), self._k(size), kind="han", anchor="center")
            if qt == "Q11" and p.get("pinyin_toneless"):
                ui.text(p["pinyin_toneless"], cx, y + self._k(70), 12, "#5A5A5A", anchor="center")
            if p.get("meaning_vi"):
                ui.text(p["meaning_vi"], cx, y + self._k(72), 8, "#5A5A5A", anchor="center")
            return
        if qt == "Q2":
            ui.text(p.get("meaning_vi", ""), cx, y + self._k(36), self._k(22), anchor="center", max_w=w - 40)
            return
        if qt == "Q4":
            if p.get("audio"):
                if ui.button("quiz_listen", cx - 40, y + self._k(20), 80, 22, "♪ " + T.QUIZ_LISTEN
                             if ui.f._ui_has("♪") else T.QUIZ_LISTEN, style="gold"):
                    self.play_audio()
            else:
                ui.text(p.get("pinyin", ""), cx, y + self._k(34), self._k(26), "#BC4749", kind="han", anchor="center")

    def draw_choices(self, ui, x, y, w):
        opts = self.q.get("options") or []
        tone = self.q.get("input") == "tone"
        bw, bh = (w - 36) / 2, 30
        correct = self.result.get("correct_option") if self.result else None
        for i, o in enumerate(opts):
            bx = x + 12 + (i % 2) * (bw + 12)
            by = y + (i // 2) * (bh + 8)
            label = T.QUIZ_TONES.get(o["text"], o["text"]) if tone else o["text"]
            style = "normal"
            if self.result:
                if o["id"] == correct:
                    style = "green"
                elif o["id"] == self.chosen:
                    style = "primary"
            kind = _kind(label, self.q.get("qtype", ""))
            size = 16 if kind == "han" and len(label) <= 4 else 10 if kind == "han" else 9
            if tone:
                kind, size = "ui", 10
            clicked = ui.button(f"opt_{o['id']}", bx, by, bw, bh, "", style=style,
                                key=KEYS[i] if not self.sent else None, enabled=not self.sent or bool(self.result))
            ui.text(str(i + 1), bx + 6, by + 4, 7, "#8E877A")
            ui.text(label, bx + bw / 2, by + bh / 2, size, "#FFFFFF" if style in ("green", "primary") else "#2B2B2B",
                    kind=kind, anchor="center", max_w=bw - 16)
            if tone:
                self._contour(ui, bx + bw - 30, by + 6, int(o["text"]))
            if clicked and not self.sent:
                self.submit({"option": o["id"]})

    def _contour(self, ui, x, y, tone):
        """Little pitch curve: ¯ ´ ˇ ` drawn as lines (spec 8.2 Q11)."""
        pts = {1: [(0, 4), (18, 4)], 2: [(0, 16), (18, 2)], 3: [(0, 8), (8, 18), (18, 2)],
               4: [(0, 2), (18, 18)]}[tone]
        win_pts = [ui.d.to_window(x + px, y + py * 0.9) for px, py in pts]
        pygame.draw.lines(ui.win, pygame.Color("#BC4749"), False, win_pts, max(2, ui.s))

    def draw_text_input(self, ui, x, y, w):
        ui.text(T.QUIZ_TYPE_HINT, x + w / 2, y - 12, 7, "#8E877A", anchor="center")
        val = ui.input_box("quiz_text", x + 80, y, w - 200, 20, placeholder="ma1", max_len=40)
        go = ui.button("quiz_submit", x + w - 112, y, 72, 20, T.QUIZ_SUBMIT, style="primary",
                       enabled=bool(val.strip()) and not self.sent)
        if (go or ui.submitted("quiz_text")) and val.strip() and not self.sent:
            self.submit({"text": val.strip()})

    def draw_order(self, ui, x, y, w):
        opts = {o["id"]: o["text"] for o in (self.q.get("options") or [])}
        end = self.q.get("prompt", {}).get("end_punct", "")
        # answer line
        ui.fill(x + 20, y, w - 40, 26, "#FFFDF7")
        ui.border(x + 20, y, w - 40, 26)
        cx = x + 26
        for i, tid in enumerate(list(self.order)):
            tw = ui.text_size(opts[tid], 14, "han")[0] + 10
            if ui.button(f"ord_{tid}", cx, y + 4, tw, 18, opts[tid], kind="han", size=14, enabled=not self.sent):
                self.order.remove(tid)
            cx += tw + 4
        ui.text(end, cx, y + 13, 14, kind="han", anchor="midleft")
        # pool
        px = x + 20
        py = y + 34
        for tid, txt in opts.items():
            if tid in self.order:
                continue
            tw = ui.text_size(txt, 14, "han")[0] + 12
            if px + tw > x + w - 20:
                px, py = x + 20, py + 24
            if ui.button(f"tok_{tid}", px, py, tw, 20, txt, kind="han", size=14, enabled=not self.sent):
                self.order.append(tid)
            px += tw + 5
        full = len(self.order) == len(opts)
        if ui.button("ord_clear", x + 20, y + 80, 60, 16, T.QUIZ_CLEAR, enabled=bool(self.order) and not self.sent):
            self.order = []
        if ui.button("ord_submit", x + w - 100, y + 80, 80, 16, T.QUIZ_SUBMIT, style="primary",
                     enabled=full and not self.sent, key=pygame.K_RETURN if full else None):
            self.submit({"order": list(self.order)})

    def draw_result(self, ui, x, y, w, h):
        res = self.result
        good = res.get("correct")
        title = T.QUIZ_CORRECT if good else (T.QUIZ_TIMEOUT if res.get("timed_out") else T.QUIZ_WRONG)
        bx, by, bw, bh = x + 16, y + (20 if self.compact else 26), w - 32, (62 if self.compact else 78)
        ui.fill(bx + 2, by + 2, bw, bh, (0, 0, 0, 90))
        ui.fill(bx, by, bw, bh, "#E8F2DC" if good else "#F6E0DE")
        ui.border(bx, by, bw, bh, UICOL["green"] if good else UICOL["accent"], 2)
        ui.text(title, bx + 10, by + 6, 12, UICOL["green"] if good else UICOL["accent"])
        rv = res.get("reveal") or {}
        if rv:
            ui.text(rv.get("hanzi", ""), bx + 40, by + 44, 26 if len(rv.get("hanzi", "")) <= 2 else 14,
                    kind="han", anchor="center")
            ui.text(f"{rv.get('pinyin', '')}", bx + 80, by + 26, 11, "#BC4749", kind="han")
            ui.text(rv.get("meaning_vi", ""), bx + 80, by + 40, 9, max_w=bw - 90)
            if not good and rv.get("answer_text") and not (self.compact and self.q.get("input") in ("choice", "tone")):
                # (the compact card has no room for this line; the right option is already shown green)
                ui.text(T.QUIZ_ANSWER_WAS.format(a=rv["answer_text"]), bx + 80, by + (50 if self.compact else 52),
                        7 if self.compact else 8, "#BC4749", max_w=bw - 170 if self.compact else bw - 90)
        if res.get("correct_order") and not good:
            ui.text(T.QUIZ_ANSWER_WAS.format(a="".join(res["correct_order"])), bx + 80, by + 52, 8, "#BC4749")
        if not self.compact:
            ui.text(f"{T.MASTER}: {self.quip}", bx + 10, by + 66, 8, "#5A5A5A", max_w=bw - 20)
        self.draw_result_extra(ui, bx, by, bw, bh)
        reward = (res.get("reward") or {}).get("spirit_stones")
        if reward:
            ui.text(T.REWARD.format(n=reward), bx + bw - 10, by + 6, 10, "#C99A3A", anchor="topright")
        if self.auto_close_after is not None and self.result_t >= self.auto_close_after:
            self.finish()
            return
        cx_, cy_ = (bx + bw - 76, by + bh - 20) if self.compact else (x + w / 2 - 45, y + h - 22)
        if ui.button("quiz_continue", cx_, cy_, 70 if self.compact else 90, 16, T.CONTINUE, style="primary") or \
                ui.key(pygame.K_RETURN) or ui.key(pygame.K_SPACE) or ui.key(pygame.K_ESCAPE):
            self.finish()
