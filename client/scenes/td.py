"""Ải Thủ Vườn on the client (spec 9): the level map with its chapters and the Vô Tận Trận,
the loadout of up to 8 plant types, the board itself and the result.

The board runs engine/td_sim.py, the same file as the server. Every action (planting,
selling, an upgrade, a Linh Khí question, starting a wave, an idiom skill) is applied to the
simulation and written to a log; at the end the log goes to /td/finish and the server plays
it again before giving any reward. Time only runs during a wave, and stops while a question
card is open (questions are for learning, not for racing the clock)."""
from __future__ import annotations

import math

import pygame

from .. import strings_vi as T
from ..art import build as B
from ..art.palette import RARITY_COLORS, rgb
from ..engine import sprites, td_sim
from .base import Scene
from .quiz import QuizScene

CELL = 24
BX, BY = 8, 24          # top-left of the board (12 x 7 cells)
BAR_Y = 202             # the plant cards
SPEEDS = [1, 2, 4, 8, 16, 32]
SPRITE_OF = {"muc_con": ("ink_slime", None, 1.0), "muc_phi": ("ink_slime", (90, 150, 210), 0.8),
             "muc_dac": ("ink_slime", (40, 30, 60), 1.3), "muc_an": ("tone_wisp", None, 1.0),
             "thach_mac": ("ink_fox", (120, 120, 120), 1.1), "mac_vuong": ("ink_fox", (110, 20, 30), 1.8)}


def role_color(role: str):
    return rgb(T.TD_ROLE_COLORS.get(role, "#7D7468"))


_MON: dict = {}


def monster_frames(kind: str) -> list[pygame.Surface]:
    """Mặc Quái of the garden trial: the world's ink monsters, tinted and resized by kind."""
    if kind in _MON:
        return _MON[kind]
    base, tint, k = SPRITE_OF.get(kind, ("ink_slime", None, 1.0))
    frames = []
    for f in sprites.monster(base):
        s = f.copy()
        if tint:
            px = pygame.PixelArray(s)
            w, h = s.get_size()
            for yy in range(h):
                for xx in range(w):
                    c = s.unmap_rgb(px[xx, yy])
                    if c.a and c.r + c.g + c.b < 240:     # tint the ink, keep eyes and highlights
                        px[xx, yy] = (min(255, c.r // 2 + tint[0] // 2), min(255, c.g // 2 + tint[1] // 2),
                                      min(255, c.b // 2 + tint[2] // 2), c.a)
            del px
        if k != 1.0:
            s = pygame.transform.scale(s, (int(s.get_width() * k), int(s.get_height() * k)))
        frames.append(s)
    _MON[kind] = frames
    return frames


_PLANT: dict = {}


def plant_sprite(word: str, rarity: str, level: int, frame: int) -> pygame.Surface:
    key = (word, rarity, level, frame)
    if key not in _PLANT:
        r = rarity if rarity in RARITY_COLORS else "common"
        _PLANT[key] = B.plant(min(5, 3 + level), r, word, frame)
    return _PLANT[key]


def draw_star(ui, cx: float, cy: float, r: float, on: bool) -> None:
    """A five-pointed star (the fonts have no ★)."""
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(ui.d.to_window(cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(ui.win, rgb("#E9C46A" if on else "#E3D5BA"), pts)
    pygame.draw.polygon(ui.win, rgb("#8B5A2B" if on else "#B8AE9C"), pts, max(1, ui.s // 2))


def draw_stars(ui, cx: float, cy: float, n: int, r: float = 3.5, gap: float = 8) -> None:
    for i in range(3):
        draw_star(ui, cx + (i - 1) * gap, cy, r, i < n)


def reward_text(r: dict) -> str:
    parts = []
    if r.get("spirit_stones"):
        parts.append(f"{r['spirit_stones']} Linh Thạch")
    if r.get("immortal_jade"):
        parts.append(f"{r['immortal_jade']} Tiên Ngọc")
    for it in r.get("items") or []:
        if isinstance(it, dict):
            parts.append(f"{it.get('qty', 1)} {it.get('name_vi', it.get('item'))}")
    if isinstance(r.get("items"), dict):
        parts.extend(f"{n} {k}" for k, n in r["items"].items())
    if r.get("seed"):
        sd = r["seed"]
        parts.append(f"hạt {sd['hanzi']}" if isinstance(sd, dict) else "1 hạt giống")
    return ", ".join(parts) or "—"


def stats_text(role: str, st: dict, power: float, level: int = 1, mult: list | None = None) -> str:
    k = power * ((mult or [1.0])[level - 1] if mult else 1.0)
    if role == "moc":
        return T.TD_STATS_MOC.format(hp=int(st["hp"] * k), t=round(st["thorns"] * k, 1))
    if role == "sinh_khi":
        return T.TD_STATS_QI.format(q=round(st["qi"] * k, 1), cd=st["cd"])
    if role == "ho_tro":
        return T.TD_STATS_SUPPORT.format(h=int(st["haste"] * k * 100), hl=round(st["heal"] * k, 1))
    if role == "thanh_ngu":
        return ""
    return T.TD_STATS_DMG.format(d=round(st["dmg"] * k, 1), r=st["range"], cd=st["cd"])


# ------------------------------------------------------------------ level map
class TdMapScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.tab = 1
        self.sel: str | None = None
        self.board: dict | None = None
        self.starting = False
        self.speed = 1          # the last speed chosen on the board, kept for the next level
        self.reload()

    def reload(self, select: str | None = None) -> None:
        def ok(d):
            self.data = d
            if select:
                self.sel = select
                lv = self.level(select)
                if lv:
                    self.tab = lv["chapter"]
            if self.sel is None:
                opened = [lv for lv in d["levels"] if lv["unlocked"]]
                pick = next((lv for lv in opened if lv["stars"] == 0), opened[-1] if opened else d["levels"][0])
                self.sel, self.tab = pick["id"], pick["chapter"]
        self.api.get("/td/levels", ok, self.game.api_error)

    def level(self, lid: str) -> dict | None:
        return next((lv for lv in (self.data or {}).get("levels", []) if lv["id"] == lid), None)

    def plant(self, wid: str) -> dict | None:
        return next((p for p in (self.data or {}).get("plants", []) if p["word_id"] == wid), None)

    def start_level(self, lid: str) -> None:
        if self.starting or not self.data:
            return
        loadout = self.data["loadout"]
        if not any((self.plant(w) or {}).get("role") not in (None, "thanh_ngu") for w in loadout):
            self.game.toast(T.TD_NEED_LOADOUT, "#BC4749")
            return
        self.starting = True

        def ok(r):
            self.starting = False
            self.game.push(TdPlayScene(self.game, r, self))

        def err(e):
            self.starting = False
            self.game.api_error(e)
        self.api.post("/td/start", {"level_id": lid, "loadout": loadout}, ok, err)

    def resume(self) -> None:
        if self.starting:
            return
        self.starting = True

        def ok(r):
            self.starting = False
            self.game.push(TdPlayScene(self.game, r, self))

        def err(e):
            self.starting = False
            self.game.api_error(e)
            self.reload()
        self.api.post("/td/resume", {}, ok, err)

    def drop_run(self) -> None:
        self.api.post("/td/cancel", {}, lambda r: self.reload(), self.game.api_error)

    def open_endless(self) -> None:
        self.tab = 4
        self.sel = "endless"
        self.api.get("/td/endless/board", lambda b: setattr(self, "board", b), lambda e: None)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 14, 14, 452, 244
        ui.panel(x, y, w, h, T.TD_TITLE)
        d = self.data
        if ui.button("td_close", x + w - 52, y + 6, 44, 13, T.CLOSE, size=7, key=pygame.K_ESCAPE):
            self.close()
            return
        if not d:
            return
        for i in range(1, 5):
            label = T.TD_CHAPTER_TAB.format(n=i) if i < 4 else T.TD_ENDLESS
            if ui.button(f"td_tab_{i}", x + 10 + (i - 1) * 74, y + 8, 70, 13, label, size=7, selected=self.tab == i):
                if i == 4:
                    self.open_endless()
                else:
                    self.tab = i
                    lvs = [lv for lv in d["levels"] if lv["chapter"] == i]
                    self.sel = next((lv["id"] for lv in lvs if lv["unlocked"] and lv["stars"] == 0),
                                    lvs[0]["id"])
        if self.tab < 4:
            self.draw_chapter(ui, x, y)
        else:
            self.draw_endless(ui, x, y)
        self.draw_loadout(ui, x, y + h - 52, w)
        run = d.get("active_run")
        if run:     # a run left unfinished (the game was closed): continue it or give it up
            bx, by, bw = x + 10, y + 142, 214
            ui.fill(bx, by, bw, 46, "#FFF3C4")
            ui.border(bx, by, bw, 46, "#C99A3A")
            ui.text(T.TD_RESUME_TEXT.format(name=run["name_vi"], n=run["waves"]), bx + 5, by + 3, 6, max_w=bw - 10)
            if ui.button("td_resume", bx + 5, by + 27, 90, 14, T.TD_RESUME, size=7, style="primary"):
                self.resume()
            if ui.button("td_drop_run", bx + 101, by + 27, 70, 14, T.TD_DROP_RUN, size=7):
                self.drop_run()

    def draw_chapter(self, ui, x, y):
        d = self.data
        ch = next((c for c in d["chapters"] if c["id"] == self.tab), None)
        if ch:
            ui.text(ch["name_vi"], x + 12, y + 28, 9, "#BC4749")
        lvs = [lv for lv in d["levels"] if lv["chapter"] == self.tab]
        for i, lv in enumerate(lvs):
            cx = x + 26 + (i % 5) * 44
            cy = y + 56 + (i // 5) * 50 + (8 if i % 2 else 0)
            if i + 1 < len(lvs):
                nx = x + 26 + ((i + 1) % 5) * 44
                ny = y + 56 + ((i + 1) // 5) * 50 + (8 if (i + 1) % 2 else 0)
                if (i + 1) % 5:
                    ui.fill(min(cx, nx) + 6, (cy + ny) / 2 + 5, abs(nx - cx) - 12, 2, "#B8AE9C")
            style = "gold" if lv["stars"] == 3 else ("green" if lv["stars"] else "normal")
            if ui.button(f"td_lv_{lv['id']}", cx - 14, cy - 2, 28, 18, str(lv["index"]), size=9, style=style,
                         enabled=lv["unlocked"], selected=self.sel == lv["id"],
                         tooltip=lv["name_vi"] if lv["unlocked"] else lv.get("locked_vi")):
                self.sel = lv["id"]
            draw_stars(ui, cx, cy + 22, lv["stars"])
        lv = self.level(self.sel or "")
        if lv is None or lv["chapter"] != self.tab:
            return
        px, py, pw = x + 232, y + 28, 206
        ui.fill(px, py, pw, 160, "#FFFDF7")
        ui.border(px, py, pw, 160)
        ui.text(f"{lv['index']}. {lv['name_vi']}", px + 6, py + 5, 9)
        ui.text(T.TD_LEVEL_WAVES.format(n=lv["waves"]) + ("" if lv["unlocked"] else f" · {lv.get('locked_vi') or ''}"),
                px + 6, py + 18, 7, "#5A5A5A", max_w=pw - 12)
        ui.text(T.TD_MONSTERS, px + 6, py + 32, 7, "#BC4749")
        yy = py + 42
        for m in lv["monsters"]:
            ui.image(monster_frames(m["id"])[0], px + 12, yy + 5, 0.6, anchor="center")
            ui.text(m["name_vi"], px + 22, yy, 7)
            r = ui.text(m["weakness_vi"], px + 22, yy + 8, 6, "#5A5A5A", max_w=pw - 28)
            yy = r.bottom + 2
        fr = lv["first_rewards"]
        ui.text(T.TD_FIRST_REWARDS.format(a=reward_text(fr[0]), b=reward_text(fr[1]), c=reward_text(fr[2])),
                px + 6, py + 160 - 26, 6, "#8B5A2B", max_w=pw - 12)
        if not self.data.get("active_run"):
            ui.text(T.TD_DAILY.format(n=self.data["daily_left"], m=self.data["daily_max"]), x + 12, y + 160, 7,
                    "#5A5A5A")
        if ui.button("td_start", px + pw - 74, py + 164, 74, 16, T.TD_START, style="primary",
                     enabled=lv["unlocked"] and not self.starting, key=pygame.K_RETURN):
            self.start_level(lv["id"])

    def draw_endless(self, ui, x, y):
        e = self.data["endless"]
        ui.text(T.TD_ENDLESS, x + 12, y + 28, 10, "#BC4749")
        r = ui.text(T.TD_ENDLESS_DESC, x + 12, y + 44, 7, "#5A5A5A", max_w=200)
        ui.text(e["locked_vi"] if not e["unlocked"] else T.TD_ENDLESS_BEST.format(n=e["best_wave"]),
                x + 12, r.bottom + 6, 8, "#8B5A2B" if e["unlocked"] else "#BC4749", max_w=200)
        px, py, pw = x + 232, y + 28, 206
        ui.fill(px, py, pw, 132, "#FFFDF7")
        ui.border(px, py, pw, 132)
        ui.text(T.TD_BOARD, px + 6, py + 5, 8, "#BC4749")
        top = (self.board or {}).get("top", [])
        if not top:
            ui.text(T.TD_BOARD_EMPTY, px + 6, py + 20, 7, "#8E877A")
        for i, row in enumerate(top[:10]):
            ui.text(T.TD_BOARD_ROW.format(rank=row["rank"], name=row["name"], n=row["waves"]), px + 8, py + 18 + i * 11,
                    7, "#BC4749" if row["me"] else "#2B2B2B")
        if ui.button("td_start", px + pw - 74, py + 164, 74, 16, T.TD_START, style="primary",
                     enabled=e["unlocked"] and not self.starting, key=pygame.K_RETURN):
            self.start_level("endless")

    def draw_loadout(self, ui, x, y, w):
        d = self.data
        ui.text(T.TD_LOADOUT, x + 12, y + 2, 8)
        for i in range(d["loadout_max"]):
            cx = x + 12 + i * 34
            ui.fill(cx, y + 14, 30, 30, "#FFFDF7")
            wid = d["loadout"][i] if i < len(d["loadout"]) else None
            p = self.plant(wid) if wid else None
            if p:
                ui.border(cx, y + 14, 30, 30, T.TD_ROLE_COLORS.get(p["role"], "#2B2B2B"), 2)
                ui.text(p["hanzi"], cx + 15, y + 26, 12 if len(p["hanzi"]) <= 2 else 7, kind="han", anchor="center")
                ui.text(f"{int(p['power'] * 100)}%", cx + 15, y + 39, 6, "#5A5A5A", anchor="center")
                if ui.hover(cx, y + 14, 30, 30):
                    ui.set_tooltip(f"{p['hanzi']} {p['pinyin']} · {p['meaning_vi']} · "
                                   f"{d['roles'][p['role']]['name_vi']}: {d['roles'][p['role']]['desc_vi']}")
            else:
                ui.border(cx, y + 14, 30, 30, "#CFC6B4")
        if ui.button("td_loadout_edit", x + w - 92, y + 20, 80, 16, T.TD_LOADOUT_EDIT):
            self.game.push(TdLoadoutScene(self.game, self))


# ------------------------------------------------------------------ choosing the plants
class TdLoadoutScene(Scene):
    def __init__(self, game, host: TdMapScene):
        super().__init__(game)
        self.host = host
        self.chosen: list[str] = list(host.data["loadout"])
        self.page = 0

    def save(self) -> None:
        def ok(r):
            self.host.data["loadout"] = r["loadout"]
            self.close()
        self.api.post("/td/loadout", {"slots": self.chosen}, ok, self.game.api_error)

    def draw_ui(self, ui):
        ui.dim(170)
        d = self.host.data
        x, y, w, h = 24, 18, 432, 236
        n = d["loadout_max"]
        ui.panel(x, y, w, h, T.TD_LOADOUT_TITLE.format(n=n))
        ui.text(T.TD_LOADOUT_HINT, x + w / 2, y + 12, 7, "#5A5A5A", anchor="center")
        plants = d["plants"]
        if not plants:
            ui.text(T.TD_LOADOUT_EMPTY, x + w / 2, y + 100, 9, anchor="center")
        per = 30
        pages = max(1, math.ceil(len(plants) / per))
        self.page = min(self.page, pages - 1)
        for i, p in enumerate(plants[self.page * per:(self.page + 1) * per]):
            cx = x + 12 + (i % 6) * 70
            cy = y + 24 + (i // 6) * 36
            on = p["word_id"] in self.chosen
            ui.fill(cx, cy, 66, 32, "#FFF3C4" if on else "#FFFDF7")
            ui.border(cx, cy, 66, 32, T.TD_ROLE_COLORS.get(p["role"], "#2B2B2B"), 2 if on else 1)
            ui.text(p["hanzi"], cx + 15, cy + 14, 13 if len(p["hanzi"]) <= 2 else 7, kind="han", anchor="center")
            ui.text(d["roles"][p["role"]]["name_vi"], cx + 32, cy + 4, 7, T.TD_ROLE_COLORS.get(p["role"], "#2B2B2B"))
            ui.text(T.TD_POWER.format(p=int(p["power"] * 100)), cx + 32, cy + 14, 6, "#5A5A5A")
            ui.text(T.TD_MASTERY_WITHER.format(m=p["mastery"], w=int(p["wither"])), cx + 4, cy + 24, 5, "#8E877A")
            ui.widgets[f"td_pick_{p['word_id']}"] = ui.rect(cx, cy, 66, 32)
            if ui.hover(cx, cy, 66, 32):
                st = d["role_stats"][p["role"]]
                ui.set_tooltip(f"{p['hanzi']} {p['pinyin']} · {p['meaning_vi']}\n{d['roles'][p['role']]['desc_vi']}\n"
                               + stats_text(p["role"], st, p["power"]))
            if ui.click_in(cx, cy, 66, 32):
                if on:
                    self.chosen.remove(p["word_id"])
                elif len(self.chosen) < n:
                    self.chosen.append(p["word_id"])
                else:
                    self.game.toast(T.TD_LOADOUT_FULL.format(n=n), "#BC4749")
        if pages > 1:
            if ui.button("td_pg_prev", x + 12, y + h - 22, 40, 14, "<", enabled=self.page > 0):
                self.page -= 1
            ui.text(T.HERB_PAGE.format(n=self.page + 1, t=pages), x + 80, y + h - 15, 7, anchor="center")
            if ui.button("td_pg_next", x + 108, y + h - 22, 40, 14, ">", enabled=self.page < pages - 1):
                self.page += 1
        ui.text(f"{len(self.chosen)}/{n}", x + w / 2, y + h - 15, 9, "#BC4749", anchor="center")
        if ui.button("td_loadout_save", x + w - 170, y + h - 22, 80, 15, T.TD_LOADOUT_SAVE, style="primary",
                     key=pygame.K_RETURN):
            self.save()
        if ui.button("td_loadout_cancel", x + w - 84, y + h - 22, 70, 15, T.BACK, key=pygame.K_ESCAPE):
            self.close()


# ------------------------------------------------------------------ the board
class TdQuizScene(QuizScene):
    """A question in the garden trial: the card sits low, the board stays visible (and still).
    A wave can end while the player is clicking on the board, so the card ignores clicks and
    number keys for a moment after it appears (no answer picked by accident)."""
    compact = True
    modal = False
    toast_y = 70
    GUARD_SECONDS = 0.3

    def __init__(self, game, question: dict, hint: str, on_result=None):
        super().__init__(game, question, on_result=on_result, show_timer=True)
        self.hint = hint
        self.auto_close_after = 1.4
        self._done = False

    def finish(self):
        self._done = True
        super().finish()

    def close(self):
        super().close()
        if not self._done and self.result is None and self.on_result:   # the answer could not be sent
            self._done = True
            self.on_result({"correct": False})

    def draw_ui(self, ui):
        if self.t < self.GUARD_SECONDS and ui.enabled:
            ui.inp.clicked = False
            ui.inp.keys = [k for k in ui.inp.keys if k not in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                                                pygame.K_RETURN, pygame.K_SPACE)]
        super().draw_ui(ui)
        x, y, w, h = self.panel_rect()
        if not self.result:
            ui.fill(x, y - 14, w, 12, (20, 18, 15, 190))
            ui.text(self.hint, x + w / 2, y - 8, 7, "#E9C46A", anchor="center")


class TdPlayScene(Scene):
    opaque = True
    draws_world = True
    toast_y = 26

    def __init__(self, game, run: dict, host: TdMapScene | None):
        super().__init__(game)
        self.run, self.host = run, host
        self.params = run["params"]
        self.answers: dict = dict(run.get("answers") or {})
        self.events: list[dict] = list(run.get("events") or [])
        if self.events:   # continuing a run left unfinished: rebuild it from the saved log
            self.sim = td_sim.replay(self.params, self.answers, self.events, finish=False)
        else:
            self.sim = td_sim.Sim(self.params, self.answers)
        self.sim.record_fx = True
        self.saved = len(self.events)       # events the server has stored (/td/event)
        self.saving = False
        self.save_now = False
        self.saved_at = 0.0
        self.words = list(self.params["plants"])
        self.max_speed = int(run.get("max_speed", 2))
        self.speeds = [s for s in SPEEDS if s <= self.max_speed]
        self.speed = host.speed if host and host.speed in self.speeds else 1
        self.acc = 0.0
        self.t = 0.0
        self.card: str | None = None        # word chosen in the bar
        self.picked: tuple[int, int] | None = None   # planted cell chosen
        self.busy = False                   # a question is being asked
        self.break_left = 0
        self.sending = False
        self.result: dict | None = None
        self.fx: list[list] = []            # [kind, data, age, life]
        self.flash = 0.0
        self.seen_combos: set[str] = set()
        self.monster_info = {m["id"]: m for m in run.get("monsters", [])}
        self.start_break()

    # ------------------------------------------------------------ actions
    def log(self, ev: dict) -> bool:
        ev = {"s": self.sim.step_n, **ev}
        try:
            self.sim.apply(ev)
        except td_sim.LogError as e:
            msg = {"no_qi": T.TD_NO_QI, "needs_path": T.TD_ON_PATH, "off_path": T.TD_OFF_PATH}.get(str(e), T.TD_CANT_PLACE)
            self.game.toast(msg, "#BC4749")
            return False
        self.events.append(ev)
        if ev["k"] in ("qi", "up", "wave", "skill"):
            self.save_now = True
        self.check_combos()
        return True

    def check_combos(self) -> None:
        for cid in self.sim.combos:
            if cid not in self.seen_combos:
                self.seen_combos.add(cid)
                cb = next(c for c in self.params["combos"] if c["id"] == cid)
                self.game.toast(T.TD_COMBO_NEW.format(name=cb["name_vi"], text=cb["text_vi"]), "#6A994E")
                self.game.audio.play("discover")

    def start_break(self) -> None:
        if self.sim.phase == td_sim.BUILD and self.sim.wave < self.sim.total:
            self.break_left = self.params["qi"]["break_questions"] - self.sim.break_q
            if self.break_left > 0:
                self.ask("break")

    def ask(self, kind: str, word: str | None = None, cell: tuple[int, int] | None = None) -> None:
        if self.busy:
            return
        self.busy = True
        body = {"run_id": self.run["run_id"], "kind": kind}
        if word:
            body["word_id"] = word
        q = self.params["qi"]

        def ok(question):
            if kind == "break":
                n = q["break_questions"] - self.break_left + 1
                hint = T.TD_BREAK_HINT.format(n=n, t=q["break_questions"], q=q["break_qi"])
            elif kind == "tu_khi":
                hint = T.TD_TU_KHI_HINT.format(q=q["tu_khi_qi"], l=q["tu_khi_wrong_loss"])
            else:
                hint = T.TD_UPGRADE_HINT.format(hz=self.params["plants"][word]["hanzi"])
            self.game.push(TdQuizScene(self.game, question, hint,
                                       on_result=lambda res: self.answered(question, kind, word, cell, res)))

        def err(e):
            self.busy = False
            if kind == "break":
                self.break_left = 0
            self.game.api_error(e)
        self.api.post("/td/question", body, ok, err)

    def answered(self, q: dict, kind: str, word: str | None, cell, res: dict) -> None:
        sid = q["session_id"]
        ok = bool(res.get("correct"))
        self.answers[sid] = {"kind": kind, "word": word or "", "ok": ok}
        self.busy = False
        if kind == "upgrade":
            self.log({"k": "up", "x": cell[0], "y": cell[1], "q": sid})
            if ok:
                self.game.audio.play("discover")
        else:
            before = self.sim.qi
            self.log({"k": "qi", "q": sid})
            gain = int(round(self.sim.qi - before))
            if gain:
                self.fx.append(["text", (BX + 144, BY + 14, f"{gain:+d} Linh Khí", "#2E6B2E" if gain > 0 else "#BC4749"),
                                0.0, 1.2])
        if kind == "break":
            self.break_left -= 1
            if self.break_left > 0 and self.sim.phase == td_sim.BUILD:
                self.ask("break")

    def place(self, x: int, y: int) -> None:
        why = self.sim.can_place(x, y, self.card)
        if why:
            msg = {"no_qi": T.TD_NO_QI, "needs_path": T.TD_ON_PATH, "off_path": T.TD_OFF_PATH}.get(why, T.TD_CANT_PLACE)
            self.game.toast(msg, "#BC4749")
            return
        if self.log({"k": "place", "x": x, "y": y, "w": self.card}):
            self.game.audio.play("step")
            if self.sim.qi < self.sim.cost_to_place(self.card):
                self.card = None

    def upgrade(self) -> None:
        pl = self.sim.plants.get(self.picked) if self.picked else None
        if pl is None:
            return
        cost = self.sim.cost_to_upgrade(pl)
        if cost is None or self.sim.qi < cost:
            self.game.toast(T.TD_NO_QI, "#BC4749")
            return
        self.ask("upgrade", pl.word, (pl.x, pl.y))

    def sell(self) -> None:
        if self.picked and self.log({"k": "sell", "x": self.picked[0], "y": self.picked[1]}):
            self.picked = None

    def skill(self, word: str) -> None:
        if self.sim.phase != td_sim.WAVE:
            self.game.toast(T.TD_SKILL_WAVE, "#BC4749")
            return
        if self.log({"k": "skill", "w": word}):
            self.flash = 0.5
            self.game.audio.play("reveal")

    def start_wave(self) -> None:
        if self.log({"k": "wave"}):
            self.break_left = 0
            self.game.audio.play("crack")

    def tu_khi_left(self) -> float:
        cd = self.sim.tu_khi_cd()
        return max(0.0, (cd - (self.sim.step_n - self.sim.last_tu_khi)) * td_sim.STEP_MS / 1000)

    def leave(self) -> None:
        def go():
            self.sending = True
            self.api.post("/td/cancel", {}, None, lambda e: None)
            self.close()
            if self.host:
                self.host.reload()
        self.game.message(T.TD_LEAVE_CONFIRM, T.TD_LEAVE, ok=T.TD_LEAVE, cancel=T.BACK, on_ok=go)

    def send_finish(self) -> None:
        self.sending = True
        s = self.sim.summary()
        claim = {k: s[k] for k in ("result", "core_hp", "wave", "steps")}

        def ok(r):
            self.result = r
            self.game.refresh_me()
            self.game.refresh_inv()
            self.game.push(TdResultScene(self.game, self, r))

        def err(e):
            self.game.api_error(e)
            self.close()
            if self.host:
                self.host.reload()
        self.api.post("/td/finish", {"run_id": self.run["run_id"], "events": self.events, "claim": claim}, ok, err)

    # ------------------------------------------------------------ time
    def update(self, dt, top):
        self.t += dt
        for f in list(self.fx):
            f[2] += dt
            if f[2] >= f[3]:
                self.fx.remove(f)
        self.flash = max(0.0, self.flash - dt)
        if self.sending:
            return
        sim = self.sim
        if sim.phase == td_sim.WAVE and not self.busy and top:
            self.acc += min(dt, 0.1) * 1000 * self.speed
            n = 0
            while self.acc >= td_sim.STEP_MS and sim.phase == td_sim.WAVE and n < 600:
                sim.step()
                self.acc -= td_sim.STEP_MS
                n += 1
            self.take_fx()
            self.check_combos()
            if sim.phase == td_sim.BUILD:
                self.acc = 0.0
                self.start_break()
        if sim.phase in (td_sim.WON, td_sim.LOST) and not self.busy:
            self.send_finish()
        elif len(self.events) > self.saved and not self.saving and (self.save_now or self.t - self.saved_at > 2.0):
            self.save_log()

    def save_log(self) -> None:
        """Keep the server's copy of the log up to date (/td/event), so a game closed in the
        middle can continue this run."""
        self.saving, self.save_now, self.saved_at = True, False, self.t
        start, part = self.saved, self.events[self.saved:]

        def ok(r):
            self.saving = False
            self.saved = max(self.saved, int(r.get("saved", start + len(part))))

        def err(e):
            self.saving = False
        self.api.post("/td/event", {"run_id": self.run["run_id"], "start": start, "events": part}, ok, err)

    def take_fx(self) -> None:
        for f in self.sim.fx[-60:]:
            kind = f[0]
            if kind == "shot":
                self.fx.append(["shot", (f[1], f[2], f[3]), 0.0, 0.14])
            elif kind == "quake":
                self.fx.append(["ring", (f[1], f[2]), 0.0, 0.35])
            elif kind == "qi":
                self.fx.append(["text", (BX + f[1][0] * CELL + 12, BY + f[1][1] * CELL, "+", "#6A994E"), 0.0, 0.8])
            elif kind == "die":
                self.fx.append(["puff", f[1], 0.0, 0.35])
            elif kind == "leak":
                self.flash = 0.35
                self.game.audio.play("wrong")
            elif kind == "skill":
                self.fx.append(["ring", (f[1], 2.0), 0.0, 0.6])
        self.sim.fx = []

    # ------------------------------------------------------------ drawing: the board in pixels
    def draw_world(self, surf):
        sim = self.sim
        surf.fill(rgb("#E9DFC8"))
        path = set(sim.path)
        for y in range(sim.rows):
            for x in range(sim.cols):
                r = pygame.Rect(BX + x * CELL, BY + y * CELL, CELL, CELL)
                if (x, y) in path:
                    pygame.draw.rect(surf, rgb("#B8996B"), r)
                    pygame.draw.rect(surf, rgb("#A3865A"), r, 1)
                else:
                    shade = "#8DB360" if (x + y) % 2 else "#86AC5A"
                    pygame.draw.rect(surf, rgb(shade), r)
                if (x, y) in sim.rocks:
                    surf.blit(B.rock(x % 2), (r.x + 4, r.y + 4))
        if sim.lit:   # light on the path
            glow = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            glow.fill((255, 236, 150, 70))
            for i in sim.lit:
                px, py = sim.path[i]
                surf.blit(glow, (BX + px * CELL, BY + py * CELL))
        gx, gy = sim.path[0]
        pygame.draw.circle(surf, rgb("#2B2B2B"), (BX + gx * CELL + 12, BY + gy * CELL + 12), 10)
        pygame.draw.circle(surf, rgb("#5A3E6E"), (BX + gx * CELL + 12, BY + gy * CELL + 12), 6 + int(self.t * 3) % 3)
        cx, cy = sim.path[-1]
        pulse = 2 * math.sin(self.t * 3)
        pygame.draw.circle(surf, rgb("#B5E3F0"), (BX + cx * CELL + 12, BY + cy * CELL + 12), int(9 + pulse))
        pygame.draw.circle(surf, rgb("#4A90C8"), (BX + cx * CELL + 12, BY + cy * CELL + 12), int(9 + pulse), 2)
        frame = int(self.t * 2) % 2
        # range preview
        hover = self.hover_cell()
        show = None
        if self.card and hover:
            show = (hover, self.sim.roles[self.params["plants"][self.card]["role"]].get("range", 0))
        elif self.picked and self.picked in sim.plants:
            pl = sim.plants[self.picked]
            show = (self.picked, sim.roles[pl.role].get("range", 0) * (pl.light if pl.role == "quang" else 1))
        if show and show[1]:
            (hx, hy), rr = show
            ring = pygame.Surface((480, 270), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 255, 255, 50), (BX + hx * CELL + 12, BY + hy * CELL + 12), int(rr * CELL))
            pygame.draw.circle(ring, (255, 255, 255, 140), (BX + hx * CELL + 12, BY + hy * CELL + 12), int(rr * CELL), 1)
            surf.blit(ring, (0, 0))
        if self.card and hover:
            ok = sim.can_place(hover[0], hover[1], self.card) is None
            pygame.draw.rect(surf, rgb("#6A994E" if ok else "#BC4749"),
                             (BX + hover[0] * CELL, BY + hover[1] * CELL, CELL, CELL), 2)
        for c in sim.order:
            pl = sim.plants[c]
            d = self.params["plants"][pl.word]
            img = plant_sprite(pl.word, d.get("rarity", "common"), pl.level, frame)
            rx, ry = BX + pl.x * CELL, BY + pl.y * CELL
            if pl.role == "moc":
                pygame.draw.rect(surf, rgb("#5C4A2E"), (rx + 3, ry + 3, CELL - 6, CELL - 6))
            surf.blit(img, (rx, ry - 2))
            pygame.draw.rect(surf, role_color(pl.role), (rx + 1, ry + CELL - 3, CELL - 2, 2))
            for i in range(pl.level):
                pygame.draw.rect(surf, rgb("#E9C46A"), (rx + 2 + i * 4, ry + 2, 3, 3))
            if pl.role == "moc" and pl.max_hp:
                k = max(0.0, pl.hp / pl.max_hp)
                pygame.draw.rect(surf, rgb("#3A342C"), (rx + 2, ry + CELL - 6, CELL - 4, 2))
                pygame.draw.rect(surf, rgb("#6A994E"), (rx + 2, ry + CELL - 6, int((CELL - 4) * k), 2))
            if self.picked == c:
                pygame.draw.rect(surf, rgb("#E9C46A"), (rx, ry, CELL, CELL), 1)
        for m in sim.monsters:
            mx, my = sim.pos(m)
            img = monster_frames(m.kind)[frame % len(monster_frames(m.kind))]
            px, py = BX + mx * CELL + 12, BY + my * CELL + 12
            if sim.kinds[m.kind].get("hidden") and not sim.visible(m):
                img = img.copy()
                img.set_alpha(80)
            surf.blit(img, (int(px - img.get_width() / 2), int(py - img.get_height() / 2 - 2)))
            k = max(0.0, m.hp / m.max_hp)
            pygame.draw.rect(surf, rgb("#3A342C"), (int(px - 7), int(py - img.get_height() / 2 - 5), 14, 2))
            pygame.draw.rect(surf, rgb("#BC4749"), (int(px - 7), int(py - img.get_height() / 2 - 5), int(14 * k), 2))
            if m.stun_until > sim.step_n:
                pygame.draw.circle(surf, rgb("#E9C46A"), (int(px), int(py - 10)), 2)
            elif m.slow_until > sim.step_n:
                pygame.draw.circle(surf, rgb("#4A90C8"), (int(px + 6), int(py + 4)), 2)
        for kind, data, age, life in self.fx:
            if kind == "shot":
                role, (sx, sy), (tx, ty) = data
                pygame.draw.line(surf, role_color(role), (BX + sx * CELL + 12, BY + sy * CELL + 8),
                                 (int(BX + tx * CELL + 12), int(BY + ty * CELL + 12)), 2 if role == "kim" else 1)
                if role == "hoa":
                    pygame.draw.circle(surf, rgb("#E07A3F"), (int(BX + tx * CELL + 12), int(BY + ty * CELL + 12)),
                                       int(4 + age * 40), 1)
            elif kind == "ring":
                (rx, ry), rr = data
                pygame.draw.circle(surf, rgb("#9C7B4E"), (int(BX + rx * CELL + 12), int(BY + ry * CELL + 12)),
                                   max(2, int(rr * CELL * age / life)), 1)
            elif kind == "puff":
                px, py = data
                pygame.draw.circle(surf, rgb("#5A5A5A"), (int(BX + px * CELL + 12), int(BY + py * CELL + 12)),
                                   int(3 + age * 20), 1)
        if self.flash:
            veil = pygame.Surface((480, 270), pygame.SRCALPHA)
            veil.fill((188, 71, 73, int(120 * self.flash)))
            surf.blit(veil, (0, 0))

    def hover_cell(self) -> tuple[int, int] | None:
        mx, my = self.game.ui.inp.mouse
        x, y = int((mx - BX) // CELL), int((my - BY) // CELL)
        if 0 <= x < self.sim.cols and 0 <= y < self.sim.rows and mx >= BX and my >= BY:
            return x, y
        return None

    # ------------------------------------------------------------ drawing: HUD and input
    def draw_ui(self, ui):
        sim = self.sim
        top = self.game.top is self
        p = self.params
        # top bar
        ui.fill(0, 0, 480, 20, (43, 43, 43, 230))
        ui.text(self.run.get("name_vi", ""), 6, 10, 8, "#F4EBD9", anchor="midleft")
        wave = T.TD_WAVE.format(n=sim.wave, t=sim.total) if p.get("waves") else T.TD_WAVE_ENDLESS.format(n=sim.wave)
        ui.text(wave, 150, 10, 8, "#E9C46A", anchor="midleft")
        ui.text(T.TD_CORE.format(n=sim.hp, m=p["core_hp"]), 214, 10, 8, "#B5E3F0", anchor="midleft")
        ui.text(T.TD_QI.format(n=int(sim.qi)), 300, 10, 9, "#B5D67A", anchor="midleft")
        # plant labels on the board (crisp, at window resolution)
        for c in sim.order:
            pl = sim.plants[c]
            hz = p["plants"][pl.word]["hanzi"]
            tx, ty = BX + pl.x * CELL + CELL - 5, BY + pl.y * CELL + CELL - 8
            ui.fill(tx - 5, ty - 5, 10, 10, "#FFFDF7")
            ui.text(hz[:2], tx, ty, 7 if len(hz) == 1 else 4, kind="han", anchor="center")
        for i in range(sim.rows):
            for j in range(sim.cols):
                ui.widgets[f"td_cell_{j}_{i}"] = ui.rect(BX + j * CELL, BY + i * CELL, CELL, CELL)
        for kind, data, age, life in self.fx:
            if kind == "text":
                x, y, txt, col = data
                ui.text(txt, x, y - age * 14, 8, col, anchor="center")
        self.draw_bar(ui, top)
        self.draw_side(ui, top)
        if self.sending and not self.result:
            ui.fill(120, 110, 240, 24, (20, 18, 15, 220))
            ui.text(T.TD_CHECKING, 240, 122, 8, "#F4EBD9", anchor="center")
        if not top or self.sending:
            return
        # monster card on hover
        mx, my = ui.inp.mouse
        for m in sim.monsters:
            px, py = sim.pos(m)
            if abs(BX + px * CELL + 12 - mx) < 9 and abs(BY + py * CELL + 12 - my) < 9:
                info = self.monster_info.get(m.kind) or {"name_vi": m.kind, "weakness_vi": ""}
                ui.set_tooltip(f"{info['name_vi']} — {T.TD_MONSTER_HP.format(hp=int(m.hp), sp=sim.kinds[m.kind]['speed'], lk=sim.kinds[m.kind]['leak'])}\n{info.get('weakness_vi', '')}")
                break
        cell = self.hover_cell()
        if ui.inp.right_clicked:
            self.card, self.picked = None, None
        if cell and ui.click_in(BX, BY, sim.cols * CELL, sim.rows * CELL):
            if self.card and not self.busy:
                self.place(*cell)
            elif cell in sim.plants:
                self.picked = cell
            else:
                self.picked = None
        if ui.key(pygame.K_SPACE) and sim.phase == td_sim.BUILD and not self.busy:
            self.start_wave()

    def draw_bar(self, ui, top):
        sim = self.sim
        ui.fill(0, BAR_Y - 4, 300, 72, (43, 43, 43, 200))
        for i, w in enumerate(self.words):
            d = self.params["plants"][w]
            cx, cy = BX + i * 36, BAR_Y
            role = d["role"]
            is_skill = bool(d.get("skill"))
            cost = 0 if is_skill else sim.cost_to_place(w)
            used = is_skill and w in sim.skills_used
            can = (not used) and (sim.phase == td_sim.WAVE if is_skill else sim.qi >= cost)
            ui.fill(cx, cy, 34, 52, "#FFF3C4" if self.card == w else ("#FFFDF7" if can else "#CFC6B4"))
            ui.border(cx, cy, 34, 52, T.TD_ROLE_COLORS.get(role, "#2B2B2B"), 2 if self.card == w else 1)
            ui.text(d["hanzi"], cx + 17, cy + 14, 14 if len(d["hanzi"]) <= 2 else 7, kind="han", anchor="center")
            ui.text(T.TD_SKILL if is_skill else str(int(cost)), cx + 17, cy + 31, 7,
                    "#8E5AC8" if is_skill else "#2E6B2E", anchor="center")
            ui.text(T.TD_SKILL_USED if used else f"{int(d['power'] * 100)}%", cx + 17, cy + 42, 6, "#5A5A5A", anchor="center")
            ui.widgets[f"td_card_{i}"] = ui.rect(cx, cy, 34, 52)
            if top and not self.sending:
                if ui.hover(cx, cy, 34, 52):
                    st = sim.roles[role]
                    tip = f"{d['hanzi']} {d.get('pinyin', '')} · {role}"
                    if is_skill:
                        tip = f"{d['hanzi']}: {d['skill'].get('desc_vi', '')}"
                    else:
                        tip += "\n" + stats_text(role, st, d["power"])
                    ui.set_tooltip(tip)
                if ui.click_in(cx, cy, 34, 52) or ui.key(pygame.K_1 + i):
                    if is_skill:
                        if not used:
                            self.skill(w)
                    else:
                        self.card = None if self.card == w else w
                        self.picked = None

    def draw_side(self, ui, top):
        sim = self.sim
        x, y, w = 304, 24, 170
        ui.fill(x, y, w, 238, (244, 235, 217, 235))
        ui.border(x, y, w, 238, "#8B5A2B")
        enabled = top and not self.sending
        yy = y + 6
        if self.picked and self.picked in sim.plants:
            pl = sim.plants[self.picked]
            d = self.params["plants"][pl.word]
            ui.text(d["hanzi"], x + 16, yy + 12, 18 if len(d["hanzi"]) <= 2 else 9, kind="han", anchor="center")
            ui.text(f"{d.get('pinyin', '')} · {T.TD_LEVEL.format(n=pl.level)}", x + 34, yy + 4, 8, kind="han")
            ui.text(f"{int(d['power'] * pl.buff * 100)}%", x + 34, yy + 16, 7, "#5A5A5A")
            yy += 30
            yy = ui.text(stats_text(pl.role, sim.roles[pl.role], d["power"] * pl.buff, pl.level,
                                    self.params["upgrade"]["level_mult"]), x + 6, yy, 7, max_w=w - 12).bottom + 4
            cost = sim.cost_to_upgrade(pl)
            if cost is None:
                ui.button("td_upgrade", x + 6, yy, 76, 15, T.TD_UPGRADE_MAX, size=7, enabled=False)
            elif ui.button("td_upgrade", x + 6, yy, 76, 15, T.TD_UPGRADE.format(c=int(cost)), size=7, style="green",
                           enabled=enabled and not self.busy and sim.qi >= cost):
                self.upgrade()
            if ui.button("td_sell", x + 88, yy, 76, 15, T.TD_SELL.format(c=int(pl.spent * self.params["sell_refund"])),
                         size=7, enabled=enabled and not self.busy):
                self.sell()
            yy += 22
        elif self.card:
            d = self.params["plants"][self.card]
            ui.text(T.TD_PLACE_HINT.format(hz=d["hanzi"]), x + 6, yy, 7, max_w=w - 12, kind="han")
            yy += 22
            yy = ui.text(stats_text(d["role"], sim.roles[d["role"]], d["power"]), x + 6, yy, 7, max_w=w - 12).bottom + 4
        else:
            yy = ui.text(T.TD_PICK_HINT, x + 6, yy, 7, "#5A5A5A", max_w=w - 12).bottom + 4
        if sim.combos:
            names = " ".join(next(c["name_vi"] for c in self.params["combos"] if c["id"] == cid) for cid in sim.combos)
            ui.text(T.TD_COMBO.format(names=names), x + 6, yy, 8, "#6A994E", kind="han")
        by = y + 238 - 86
        can_wave = sim.phase == td_sim.BUILD and not self.busy and sim.wave < sim.total
        if ui.button("td_wave", x + 6, by, w - 12, 18, T.TD_START_WAVE, style="primary", enabled=enabled and can_wave):
            self.start_wave()
        left = self.tu_khi_left()
        can_tk = sim.phase == td_sim.WAVE and not self.busy and left <= 0
        label = T.TD_TU_KHI if left <= 0 or sim.phase != td_sim.WAVE else T.TD_TU_KHI_WAIT.format(n=int(math.ceil(left)))
        if ui.button("td_tukhi", x + 6, by + 22, w - 12, 18, label, style="green", enabled=enabled and can_tk,
                     key=pygame.K_q if enabled else None):
            self.ask("tu_khi")
        if ui.button("td_speed", x + 6, by + 44, (w - 18) / 2, 16, T.TD_SPEED.format(n=self.speed), size=7,
                     enabled=enabled):
            i = self.speeds.index(self.speed) if self.speed in self.speeds else 0
            self.speed = self.speeds[(i + 1) % len(self.speeds)]
            if self.host:
                self.host.speed = self.speed
        if ui.button("td_leave", x + 12 + (w - 18) / 2, by + 44, (w - 18) / 2, 16, T.TD_LEAVE, size=7,
                     enabled=enabled, key=pygame.K_ESCAPE if enabled else None):
            self.leave()


# ------------------------------------------------------------------ result
class TdResultScene(Scene):
    def __init__(self, game, play: TdPlayScene, r: dict):
        super().__init__(game)
        self.play, self.r = play, r
        self.t = 0.0
        game.audio.play("discover" if r.get("result") == "won" else "wrong")

    def update(self, dt, top):
        self.t += dt

    def back(self, then=None) -> None:
        self.close()
        self.play.close()
        host = self.play.host
        if host:
            host.reload(select=then)

    def draw_ui(self, ui):
        ui.dim(150)
        r = self.r
        x, y, w, h = 110, 50, 260, 170
        endless = self.play.params.get("waves") is None
        won = r.get("result") == "won"
        title = T.TD_ENDLESS_OVER if endless else (T.TD_WON if won else T.TD_LOST)
        ui.panel(x, y, w, h, title)
        if endless:
            ui.text(T.TD_RESULT_WAVES.format(n=r.get("waves_cleared", 0)), x + w / 2, y + 30, 12, "#BC4749",
                    anchor="center")
            if r.get("record"):
                ui.text(T.TD_RESULT_RECORD, x + w / 2, y + 48, 9, "#C99A3A", anchor="center")
        else:
            k = min(1.0, self.t / 0.8)
            stars = r.get("stars", 0)
            for i in range(3):
                draw_star(ui, x + w / 2 - 34 + i * 34, y + 34, 13, i < stars and k >= (i + 1) / 3)
            ui.text(T.TD_RESULT_STARS.format(hp=r.get("core_hp", 0), m=self.play.params["core_hp"]), x + w / 2, y + 58,
                    8, anchor="center")
        rew = r.get("rewards") or {}
        if rew and any(rew.get(k) for k in ("spirit_stones", "immortal_jade", "items", "seed")):
            line = T.TD_RESULT_REWARDS.format(r=reward_text(rew))
            ui.text(line, x + w / 2, y + 76, 8, "#8B5A2B", anchor="midtop", max_w=w - 24)
            if rew.get("replay"):
                ui.text(T.TD_RESULT_REPLAY.format(n=r.get("daily_left", 0)), x + w / 2, y + 100, 7, "#5A5A5A",
                        anchor="midtop")
        else:
            ui.text(T.TD_RESULT_NO_REWARD, x + w / 2, y + 80, 8, "#8E877A", anchor="midtop")
        bw = 76
        nxt = r.get("next_level")
        if nxt and not endless:
            if ui.button("td_result_next", x + 10, y + h - 24, bw, 16, T.TD_RESULT_NEXT, style="primary",
                         key=pygame.K_RETURN):
                self.back(then=nxt)
                return
        if ui.button("td_result_retry", x + w / 2 - bw / 2, y + h - 24, bw, 16, T.TD_RESULT_RETRY):
            lid = self.play.params.get("level", "endless")
            self.back(then=lid if lid != "endless" else None)
            return
        if ui.button("td_result_map", x + w - bw - 10, y + h - 24, bw, 16, T.TD_RESULT_MAP, key=pygame.K_ESCAPE):
            self.back()
