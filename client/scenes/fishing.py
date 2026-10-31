"""Câu cá on the client (spec 11): F at the water casts, the float dips when the server says
the fish bites, a rare fish asks a question, then the reel minigame. The minigame runs the
same code as the server (engine/fishing_sim.py); only the steps where the button changed are
sent, the server plays them again and tells us what we caught.

Also Ngư Ông's shop (rods, baits), rod upgrades at the Lò Rèn and the Ngư Phổ."""
from __future__ import annotations

import math
import random

import pygame

from .. import strings_vi as T
from ..engine import fishing_sim as fs
from .base import Scene
from .quiz import QuizScene

REACH = 18          # px from the water's edge; the server allows a little more
CAST_SECONDS = 0.6
OVER_SECONDS = 1.6


# ------------------------------------------------------------------ water and drawing helpers
def water_near(tmap, x: float, y: float, facing: str = "down", reach: float = REACH):
    """(water area, float position) when the feet at (x, y) stand at the water, else None."""
    for o in tmap.objects:
        if o.type != "area" or o.props.get("kind") not in ("pond", "fishing"):
            continue
        if o.x - reach <= x <= o.x + o.w + reach and o.y - reach <= y <= o.y + o.h + reach:
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.get(facing, (0, 1))
            bx = min(max(x + dx * 30, o.x + 6), o.x + o.w - 6)
            by = min(max(y - 6 + dy * 30, o.y + 6), o.y + o.h - 6)
            return o, (bx, by)
    return None


_ICONS: dict = {}


def fish_icon(shape: str, color: str, color2: str | None = None, dark: bool = False) -> pygame.Surface:
    """A small fish drawn in code (22x12): round, long, eel or squid; a silhouette when dark."""
    key = (shape, color, color2, dark)
    if key in _ICONS:
        return _ICONS[key]
    s = pygame.Surface((22, 12), pygame.SRCALPHA)
    body = pygame.Color("#3A342C") if dark else pygame.Color(color)
    edge = pygame.Color("#2B2B2B")
    accent = pygame.Color(color2) if (color2 and not dark) else None
    if shape == "eel":
        for i in range(18):
            cx = 2 + i
            cy = 6 + int(round(math.sin(i / 2.6) * 2))
            pygame.draw.circle(s, body, (cx, cy), 2 if i < 15 else 1)
        if not dark:
            s.set_at((3, 5), edge)
    elif shape == "squid":
        pygame.draw.ellipse(s, body, (2, 2, 12, 8))
        for i in range(4):
            pygame.draw.line(s, body, (13, 3 + i * 2), (20, 2 + i * 3))
        if not dark:
            s.set_at((5, 5), edge)
            if accent:
                pygame.draw.line(s, accent, (4, 3), (11, 3))
    else:
        h = 8 if shape == "round" else 6
        top = 6 - h // 2
        pygame.draw.polygon(s, body, [(15, 6), (21, top), (21, top + h)])     # tail
        pygame.draw.ellipse(s, body, (1, top, 16, h))
        pygame.draw.ellipse(s, edge, (1, top, 16, h), 1)
        if accent:
            for xx in (6, 10):
                pygame.draw.line(s, accent, (xx, top + 1), (xx, top + h - 2))
        if not dark:
            s.set_at((4, 5), edge)
    _ICONS[key] = s
    return s


def draw_rod(surf: pygame.Surface, scene: "FishingScene", cx: int, cy: int, t: float) -> None:
    """The line from the hand to the float, the float bobbing (dipping when a fish bites)."""
    p = scene.host.player
    hx, hy = p.x + (6 if p.facing != "left" else -6) - cx, p.y - 18 - cy
    tip = (hx + (8 if p.facing != "left" else -8), hy - 10)
    pygame.draw.line(surf, (110, 84, 46), (hx, hy), tip, 1)
    if scene.phase == "casting":
        k = min(1.0, scene.t / CAST_SECONDS)
        bx = tip[0] + (scene.bob[0] - cx - tip[0]) * k
        by = tip[1] + (scene.bob[1] - cy - tip[1]) * k - math.sin(k * math.pi) * 18
    else:
        bx, by = scene.bob[0] - cx, scene.bob[1] - cy
        if scene.phase == "bite":
            by += 2 + int(t * 20) % 2
        elif scene.phase == "reel":
            bx += math.sin(t * 9) * 2
            by += 1
        else:
            by += math.sin(t * 3) * 1
    pygame.draw.line(surf, (235, 235, 235), tip, (int(bx), int(by)), 1)
    if scene.phase in ("waiting", "bite", "reel"):
        r = 3 + (int(t * 4) % 3 if scene.phase == "bite" else 0)
        pygame.draw.circle(surf, (210, 230, 240), (int(bx), int(by) + 2), r + 2, 1)
    pygame.draw.circle(surf, (188, 71, 73), (int(bx), int(by)), 2)
    surf.set_at((int(bx), int(by) - 2), (244, 235, 217))


def draw_rain(surf: pygame.Surface, t: float) -> None:
    """Thin slanted streaks (spec 7.1: rain changes which fish bite)."""
    w, h = surf.get_size()
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    veil.fill((60, 70, 90, 40))
    surf.blit(veil, (0, 0))
    rng = random.Random(7)
    for _ in range(90):
        x0, y0, sp = rng.uniform(0, w + 60), rng.uniform(0, h), rng.uniform(180, 260)
        y = (y0 + t * sp) % (h + 20) - 10
        x = (x0 - t * sp * 0.35) % (w + 60) - 30
        pygame.draw.line(surf, (190, 205, 225), (int(x), int(y)), (int(x - 3), int(y + 7)), 1)


class WeatherWatch:
    """Asks the server about the rain in this zone once a minute (it is the same for everyone)."""

    def __init__(self, zone: str):
        self.zone, self.rain, self.left = zone, False, 0.0

    def update(self, dt: float, api) -> None:
        self.left -= dt
        if self.left <= 0 and api.token:
            self.left = 60.0
            api.get(f"/world/weather?zone={self.zone}", lambda d: setattr(self, "rain", bool(d.get("rain"))),
                    lambda e: None)


def conditions_text(c: dict) -> str:
    return T.FISH_CONDITIONS.format(zone=T.ZONE_NAMES.get(c.get("zone"), c.get("zone", "")),
                                    time=T.FISH_NIGHT if c.get("night") else T.FISH_DAY,
                                    weather=T.FISH_RAIN if c.get("rain") else T.FISH_CLEAR)


# ------------------------------------------------------------------ the fishing session
class FishQuizScene(QuizScene):
    """A rare fish bit: the question card sits low, the lake stays visible."""
    compact = True
    modal = False
    toast_y = 70

    def __init__(self, game, question: dict, hint: str, on_result=None):
        super().__init__(game, question, on_result=on_result, show_timer=True)
        self.hint = hint
        self.auto_close_after = 1.6

    def draw_ui(self, ui):
        super().draw_ui(ui)
        x, y, w, h = self.panel_rect()
        if not self.result:
            ui.fill(x, y - 14, w, 12, (20, 18, 15, 190))
            ui.text(self.hint, x + w / 2, y - 8, 7, "#E9C46A", anchor="center")


class FishingScene(Scene):
    modal = False
    toast_y = 70

    def __init__(self, game, host, spot: str, bob: tuple[float, float]):
        super().__init__(game)
        self.host, self.spot, self.bob = host, spot, bob
        host.fishing = self
        self.phase = "casting"          # casting -> waiting -> bite -> (quiz) -> reel -> over
        self.t = 0.0
        self.cast: dict | None = None
        self.left = 0.0
        self.msg = T.FISH_CASTING
        self.msg_color = "#F4EBD9"
        self.hooking = False
        self.reel: fs.Reel | None = None
        self.rarity = "pham"
        self.flips: list[int] = []
        self.hold = False
        self.acc = 0.0
        self.sent = False
        self.result: dict | None = None
        self.finished = False
        self.cast_sent = False   # sent a moment later, once the server has applied our last steps
        game.audio.play("step")

    # ------------------------------------------------------------ server replies
    def on_error(self, e) -> None:
        self.game.api_error(e)
        self.end()

    def on_cast(self, r: dict) -> None:
        self.cast = r
        self.left = float(r["bite_in"]) - max(0.0, CAST_SECONDS - self.t)
        self.phase = "waiting" if self.t >= CAST_SECONDS else "casting"
        self.msg = T.FISH_WAITING

    def strike(self) -> None:
        if self.cast is None or self.hooking or self.phase not in ("waiting", "bite"):
            return
        self.hooking = True
        self.api.post("/fishing/hook", {"cast_id": self.cast["cast_id"]}, self.on_hook, self.on_error)

    def on_hook(self, r: dict) -> None:
        st = r.get("stage")
        if st == "early":
            self.over(T.FISH_EARLY, "#BC4749")
        elif st == "late":
            self.over(T.FISH_LATE, "#BC4749")
        elif st == "quiz":
            self.rarity = r.get("rarity", "linh")
            self.phase = "quiz"
            self.ask(r["question"], r.get("need", 1), 0)
        elif st == "reel":
            self.rarity = r.get("rarity", "pham")
            self.start_reel(r["params"])

    def ask(self, q: dict, need: int, right: int) -> None:
        hint = T.FISH_QUIZ_HINT.format(r=T.RARITY_NAMES.get(self.rarity, ""))
        if need > 1:
            hint = T.FISH_QUIZ_TWO.format(n=right)
        self.game.push(FishQuizScene(self.game, q, hint, on_result=self.on_quiz))

    def on_quiz(self, res: dict) -> None:
        f = res.get("fishing") or {}
        if f.get("stage") == "quiz":
            self.ask(f["next_question"], f.get("need", 2), f.get("right", 1))
        elif f.get("stage") == "reel":
            wide = f.get("quiz_mult", 1.0) > 1
            self.game.toast(T.FISH_ZONE_WIDE if wide else T.FISH_ZONE_NARROW, "#6A994E" if wide else "#BC4749")
            self.start_reel(f["params"])
        else:
            self.over(T.FISH_ESCAPED, "#BC4749")

    def start_reel(self, params: dict) -> None:
        self.reel = fs.Reel(params)
        self.phase = "reel"
        self.flips, self.hold, self.acc, self.sent = [], False, 0.0, False
        self.msg = T.FISH_REEL_HINT
        self.game.audio.play("crack")

    def send_reel(self) -> None:
        self.sent = True

        def ok(r):
            self.result = r
            res = r.get("result")
            if res == fs.CAUGHT:
                self.game.audio.play("discover")
                self.game.refresh_inv()
                self.game.refresh_quests()
                self.finished = True
                self.end()
                self.game.push(CatchScene(self.game, r))
            else:
                self.game.audio.play("wrong")
                self.over(T.FISH_SNAPPED if res == fs.SNAPPED else T.FISH_ESCAPED, "#BC4749")
        self.api.post("/fishing/reel", {"cast_id": self.cast["cast_id"], "toggles": self.flips}, ok, self.on_error)

    # ------------------------------------------------------------ flow
    def over(self, msg: str, color: str = "#F4EBD9") -> None:
        self.phase = "over"
        self.finished = True
        self.msg, self.msg_color = msg, color
        self.left = OVER_SECONDS

    def end(self) -> None:
        if self.host.fishing is self:
            self.host.fishing = None
        if self in self.game.scenes:
            self.close()

    def on_exit(self) -> None:
        if self.host.fishing is self:
            self.host.fishing = None
        if not self.finished:   # closed early (Esc, a fight...): give the cast up
            self.finished = True
            self.api.post("/fishing/cancel", {}, None, lambda e: None)

    def holding(self, top: bool) -> bool:
        if not top:
            return False
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_SPACE] or keys[pygame.K_f] or pygame.mouse.get_pressed()[0])

    def update(self, dt, top):
        self.t += dt
        if not self.cast_sent and self.t >= 0.25:
            self.cast_sent = True
            self.api.post("/fishing/cast", {"spot": self.spot}, self.on_cast, self.on_error)
        if self.phase == "casting":
            if self.t >= CAST_SECONDS and self.cast is not None:
                self.phase = "waiting"
        elif self.phase == "waiting":
            self.left -= dt
            if self.left <= 0:
                self.phase = "bite"
                self.left = float(self.cast.get("window", 1.3))
                self.msg = T.FISH_BITE
                self.game.audio.play("reveal")
        elif self.phase == "bite":
            self.left -= dt
            if self.left < -0.4 and not self.hooking:
                self.over(T.FISH_LATE, "#BC4749")
                self.api.post("/fishing/cancel", {}, None, lambda e: None)
        elif self.phase == "reel" and self.reel is not None and not self.sent:
            hold = self.holding(top)
            self.acc += min(dt, 0.1) * 1000
            while self.acc >= fs.STEP_MS and self.reel.result is None:
                if hold != self.hold:
                    self.flips.append(self.reel.steps)
                    self.hold = hold
                self.reel.step(hold)
                self.acc -= fs.STEP_MS
            if self.reel.result is not None:
                self.send_reel()
        elif self.phase == "over":
            self.left -= dt
            if self.left <= 0:
                self.end()

    # ------------------------------------------------------------ drawing
    def draw_ui(self, ui):
        top = self.game.top is self
        if self.phase == "reel" and self.reel is not None:
            self.draw_meter(ui)
        if self.phase == "quiz":
            return
        w = max(220, ui.text_size(self.msg, 8)[0] + 20)
        x, y = 240 - w / 2, 200
        ui.fill(x, y, w, 22, (20, 18, 15, 200))
        ui.border(x, y, w, 22, "#8B5A2B")
        col = "#E9C46A" if self.phase == "bite" else self.msg_color
        ui.text(self.msg, 240, y + 11, 8, col, anchor="center")
        if self.phase == "bite":
            ui.text("!", 240, y - 12, 20, "#BC4749", anchor="center")
        if not top:
            return
        if self.phase in ("waiting", "bite") and (ui.key(pygame.K_f) or ui.key(pygame.K_SPACE) or ui.inp.clicked):
            ui.consume_click()
            self.strike()
        if self.phase != "reel" and ui.button("fish_cancel", 240 - 40, y + 25, 80, 12, T.FISH_CANCEL, size=7,
                                              key=pygame.K_ESCAPE):
            self.end()

    def draw_meter(self, ui):
        r = self.reel
        x, y, w, h = 404, 36, 18, 180
        col = T.RARITY_COLORS.get(self.rarity, "#7D7468")
        ui.fill(x - 26, y - 6, 66, h + 30, (20, 18, 15, 210))
        ui.border(x - 26, y - 6, 66, h + 30, col, 2)
        ui.fill(x, y, w, h, "#2E4A5E")
        half = r.p["zone"] / 2
        zy = y + h * (1 - (r.fish + half))
        ui.fill(x + 1, zy, w - 2, h * r.p["zone"], (106, 153, 78, 230) if r.inside else (106, 153, 78, 150))
        ui.image(fish_icon("round", col), x + w / 2, zy + h * half, zoom=0.7, anchor="center")
        hy = y + h * (1 - r.hook)
        ui.fill(x - 3, hy - 1.5, w + 6, 3, "#E9C46A")
        ui.fill(x - 20, y, 6, h, "#3A342C")                       # strain (left)
        ui.fill(x - 20, y + h * (1 - min(1.0, r.strain)), 6, h * min(1.0, r.strain), "#BC4749")
        ui.fill(x + w + 4, y, 6, h, "#3A342C")                     # catch (right)
        k = max(0.0, min(1.0, r.progress))
        ui.fill(x + w + 4, y + h * (1 - k), 6, h * k, "#B5D67A")
        ui.text(T.FISH_STRAIN, x - 17, y + h + 8, 6, "#F08A8C", anchor="center")
        ui.text(T.FISH_PROGRESS, x + w + 7, y + h + 8, 6, "#B5D67A", anchor="center")
        ui.text(T.RARITY_NAMES.get(self.rarity, ""), x + w / 2, y - 1, 7, col, anchor="midbottom")


class CatchScene(Scene):
    """The fish that was landed: name, characters, size, records, what went into the bag."""

    def __init__(self, game, r: dict):
        super().__init__(game)
        self.r = r
        self.t = 0.0
        game.on_xp(r.get("xp"))
        for m in r.get("milestones", []):
            game.toast(T.FISH_MILESTONE.format(n=m["species"], r=reward_text(m)), "#C99A3A")

    def update(self, dt, top):
        self.t += dt

    def draw_ui(self, ui):
        ui.dim(120)
        r, f = self.r, self.r["fish"]
        x, y, w, h = 110, 50, 260, 170
        col = T.RARITY_COLORS.get(f["rarity"], "#7D7468")
        ui.panel(x, y, w, h, T.FISH_CAUGHT)
        k = min(1.0, self.t / 0.4)
        ui.image(fish_icon(f["shape"], f["color"], f.get("color2")), x + 52, y + 46, zoom=2 + 1.5 * k, anchor="center")
        ui.text(f["name_vi"], x + 104, y + 18, 11, col)
        ui.text(f"{f['hanzi']}  {f['pinyin']}", x + 104, y + 33, 10, "#BC4749", kind="han")
        note = T.FISH_FICTIONAL if f.get("fictional") else (T.FISH_MYTHICAL if f.get("mythical") else "")
        if note:
            ui.text(note, x + 104, y + 47, 6, "#8E877A")
        ui.text(f"{T.RARITY_NAMES.get(f['rarity'], '')} · {T.FISH_SIZE.format(cm=r['size_cm'])}", x + 104, y + 56, 8)
        yy = y + 80
        for flag, txt, c in (("server_record", T.FISH_SERVER_RECORD, "#C99A3A"), ("new_species", T.FISH_NEW, "#6A994E"),
                             ("personal_record", T.FISH_RECORD, "#4A7CC8"), ("small", T.FISH_SMALL, "#8E877A")):
            if r.get(flag) and not (flag == "personal_record" and r.get("new_species")):
                ui.text(txt, x + w / 2, yy, 8, c, anchor="midtop")
                yy += 11
        got = ", ".join(f"{i['qty']} {item_name(i['item'], f)}" for i in r.get("items", []))
        ui.text(T.FISH_GOT.format(items=got), x + w / 2, yy + 2, 7, "#5A5A5A", anchor="midtop", max_w=w - 20)
        ui.text(f["desc_vi"], x + 14, y + h - 46, 7, "#5A5A5A", max_w=w - 28)
        if ui.button("catch_ok", x + w / 2 - 35, y + h - 20, 70, 14, T.OK, style="primary", key=pygame.K_RETURN) or \
                ui.key(pygame.K_ESCAPE) or ui.key(pygame.K_SPACE):
            self.close()


def item_name(item_id: str, fish: dict) -> str:
    if item_id == "ca_nho":
        return "Cá Nhỏ"
    if item_id == "vay_linh_ngu":
        return "Vảy Linh Ngư"
    return fish["name_vi"]


def reward_text(m: dict) -> str:
    parts = []
    if m.get("spirit_stones"):
        parts.append(f"{m['spirit_stones']} Linh Thạch")
    if m.get("immortal_jade"):
        parts.append(f"{m['immortal_jade']} {T.JADE}")
    return ", ".join(parts)


# ------------------------------------------------------------------ Ngư Ông, Lò Rèn
def rod_stats_text(st: dict) -> str:
    return T.ROD_STATS.format(pull=f"{st['pull']:.2f}", line=f"{st['line']:.2f}", luck=f"{st['luck']:.2f}",
                              bite=int(st["bite"] * 100), zone=int(st["zone"] * 100))


class FishShopScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.busy = False
        self.api.get("/fishing", self.loaded, game.api_error)

    def loaded(self, d: dict) -> None:
        self.data = d
        self.busy = False
        if "spirit_stones" in d:
            self.game.state.me["spirit_stones"] = d["spirit_stones"]

    def post(self, path: str, body: dict, toast: str | None = None) -> None:
        self.busy = True

        def ok(d):
            self.loaded(d)
            self.game.refresh_me()
            self.game.refresh_inv()
            if toast:
                self.game.toast(toast, "#6A994E")
                self.game.audio.play("coin")

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post(path, body, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 24, 18, 432, 236
        ui.panel(x, y, w, h, T.SHOP_FISH_TITLE)
        ui.text(T.SHOP_FISH_HINT, x + w / 2, y + 10, 7, "#5A5A5A", anchor="center")
        d = self.data
        if d is None:
            ui.text("...", 240, 130, 10, anchor="center")
        else:
            stones = self.game.state.me.get("spirit_stones", 0)
            ui.text(f"{stones} Linh Thạch · {T.SCALES_HAVE.format(n=d.get('scales', 0))}", x + w - 12, y + 22, 7,
                    "#8B5A2B", anchor="topright")
            ui.text(conditions_text(d.get("conditions") or {}), x + 12, y + 22, 7, "#4A7CC8")
            ui.text(T.SHOP_RODS, x + 12, y + 34, 9, "#BC4749")
            ry = y + 46
            for rod in d["rods"]:
                col = T.RARITY_COLORS.get(rod["rarity"], "#7D7468")
                ui.fill(x + 10, ry, 252, 30, "#FFFDF7")
                ui.border(x + 10, ry, 252, 30, col)
                name = rod["name_vi"] + (f" · {T.ROD_LEVEL.format(lv=rod['level'])}" if rod["level"] else "")
                ui.text(name, x + 15, ry + 3, 8, col)
                ui.text(rod_stats_text(rod["stats"]), x + 15, ry + 14, 6, "#5A5A5A", max_w=170)
                bx = x + 200
                if rod["equipped"]:
                    ui.text(T.SHOP_IN_USE, bx + 28, ry + 15, 7, "#6A994E", anchor="center")
                elif rod["owned"]:
                    if ui.button(f"rod_use_{rod['id']}", bx, ry + 8, 56, 14, T.SHOP_USE, enabled=not self.busy):
                        self.post("/fishing/equip", {"rod": rod["id"]})
                elif rod["price"]:
                    p = rod["price"]
                    items = p.get("items") or {}
                    label = (T.ROD_PRICE_SCALES.format(s=p["spirit_stones"], v=items.get("vay_linh_ngu", 0))
                             if items else T.ROD_PRICE.format(s=p["spirit_stones"]))
                    if items.get("thien_tam_ti"):
                        label += T.ROD_PRICE_SILK.format(n=items["thien_tam_ti"])
                    if ui.button(f"rod_buy_{rod['id']}", bx, ry + 8, 56, 14, T.SHOP_BUY, style="gold",
                                 enabled=not self.busy, tooltip=label + " · " + T.ROD_NEED_REALM.format(
                                     realm=T.REALMS.get(rod["min_realm"], rod["min_realm"]))):
                        self.post("/fishing/buy", {"item_id": rod["id"]}, f"{T.SHOP_BUY}: {rod['name_vi']}")
                else:
                    ui.text(T.SHOP_NOT_SOLD, bx + 28, ry + 15, 7, "#8E877A", anchor="center")
                if ui.hover(x + 10, ry, 180, 30):
                    ui.set_tooltip(rod["desc_vi"] + ("\n" + rod["source_vi"] if rod.get("source_vi") else ""))
                ry += 32
            bx0 = x + 272
            ui.text(T.SHOP_BAITS, bx0, y + 34, 9, "#BC4749")
            by = y + 46
            if ui.button("bait_none", bx0, by, 148, 13, T.FISH_NO_BAIT, selected=d["bait"] is None, size=7,
                         enabled=not self.busy):
                self.post("/fishing/equip", {"no_bait": True})
            by += 17
            for b in d["baits"]:
                ui.fill(bx0, by, 148, 38, "#FFFDF7")
                ui.border(bx0, by, 148, 38, "#8B5A2B")
                ui.text(f"{b['name_vi']} ×{b['qty']}", bx0 + 4, by + 3, 8)
                if ui.hover(bx0, by, 148, 14):
                    ui.set_tooltip(b["desc_vi"])
                if ui.button(f"bait_use_{b['id']}", bx0 + 104, by + 2, 40, 11, T.SHOP_IN_USE if b["equipped"] else T.SHOP_USE,
                             size=6, selected=b["equipped"], enabled=not self.busy and b["qty"] > 0):
                    self.post("/fishing/equip", {"bait": b["id"]})
                if b["buy"]:
                    if ui.button(f"bait_buy_{b['id']}", bx0 + 4, by + 21, 90, 13, T.SHOP_BUY10.format(p=b["buy"] * 10),
                                 size=7, style="gold", enabled=not self.busy):
                        self.post("/fishing/buy", {"item_id": b["id"], "qty": 10}, f"+10 {b['name_vi']}")
                elif b["craft"]:
                    c = b["craft"]
                    if ui.button(f"bait_craft_{b['id']}", bx0 + 4, by + 21, 140, 13,
                                 T.SHOP_CRAFT.format(n=1, src=c["from_name_vi"], m=c["makes"]) + f" · có {c['have']}",
                                 size=6, enabled=not self.busy and c["have"] > 0):
                        self.post("/fishing/craft", {"bait_id": b["id"], "times": 1}, f"+{c['makes']} {b['name_vi']}")
                by += 41
        if ui.button("fishshop_book", x + 12, y + h - 20, 70, 14, T.FISH_BOOK):
            self.close()
            self.game.push(FishBookScene(self.game))
            return
        if ui.button("fishshop_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


class RodForgeScene(Scene):
    """Spec 11.2: rods are upgraded at the Lò Rèn."""

    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.busy = False
        self.api.get("/fishing", self.loaded, game.api_error)

    def loaded(self, d):
        self.data = d
        self.busy = False

    def upgrade(self, rod: dict) -> None:
        self.busy = True

        def ok(d):
            self.loaded(d)
            self.game.refresh_me()
            self.game.toast(T.ROD_UPGRADED.format(name=rod["name_vi"], lv=T.ROD_LEVEL.format(lv=d["level"])), "#6A994E")
            self.game.audio.play("discover")

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/fishing/upgrade", {"rod_id": rod["id"]}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 70, 30, 340, 210
        ui.panel(x, y, w, h, T.ROD_FORGE_TITLE)
        ui.text(T.ROD_FORGE_HINT, x + w / 2, y + 12, 7, "#5A5A5A", anchor="center", max_w=w - 20)
        d = self.data
        if d is not None:
            ui.text(T.SCALES_HAVE.format(n=d.get("scales", 0)), x + 14, y + 28, 8, "#4A7CC8")
            ry = y + 42
            for rod in [r for r in d["rods"] if r["owned"]]:
                col = T.RARITY_COLORS.get(rod["rarity"], "#7D7468")
                ui.fill(x + 12, ry, w - 24, 30, "#FFFDF7")
                ui.border(x + 12, ry, w - 24, 30, col)
                ui.text(f"{rod['name_vi']} · {T.ROD_LEVEL.format(lv=rod['level'])}", x + 17, ry + 3, 8, col)
                ui.text(rod_stats_text(rod["stats"]), x + 17, ry + 15, 6, "#5A5A5A", max_w=190)
                c = rod.get("upgrade_cost")
                if c:
                    if ui.button(f"rod_up_{rod['id']}", x + w - 120, ry + 8, 100, 14,
                                 T.ROD_UPGRADE.format(s=c["spirit_stones"], v=c["vay_linh_ngu"]), size=7,
                                 style="gold", enabled=not self.busy):
                        self.upgrade(rod)
                else:
                    ui.text(T.ROD_MAX, x + w - 70, ry + 15, 7, "#8E877A", anchor="center")
                ry += 33
        if ui.button("rodforge_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


# ------------------------------------------------------------------ Ngư Phổ (Tàng Thư Các)
class FishBookScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.records: list | None = None
        self.tab = "species"
        self.api.get("/codex/fish", lambda d: setattr(self, "data", d), game.api_error)

    def show_records(self) -> None:
        self.tab = "records"
        if self.records is None:
            self.api.get("/fishing/records", lambda d: setattr(self, "records", d.get("records", [])),
                         self.game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 20, 14, 440, 244
        ui.panel(x, y, w, h, T.FISH_BOOK_TITLE)
        if ui.button("fishbook_species", x + 10, y + 6, 60, 13, T.FISH_BOOK_SPECIES, size=7, selected=self.tab == "species"):
            self.tab = "species"
        if ui.button("fishbook_records", x + 74, y + 6, 60, 13, T.FISH_BOOK_RECORDS, size=7, selected=self.tab == "records"):
            self.show_records()
        d = self.data
        if d:
            ui.text(T.FISH_BOOK_FOUND.format(f=d["found"], t=d["total"]), x + w - 12, y + 9, 8, "#BC4749",
                    anchor="topright")
        if self.tab == "species" and d:
            cols = 6
            cw, chh = 70, 32
            for i, e in enumerate(d["species"]):
                cx = x + 10 + (i % cols) * (cw + 0.5)
                cy = y + 24 + (i // cols) * (chh + 2)
                col = T.RARITY_COLORS.get(e["rarity"], "#7D7468")
                ui.fill(cx, cy, cw - 2, chh, "#FFFDF7" if e["caught"] else "#E9E0CC")
                ui.border(cx, cy, cw - 2, chh, col)
                if e["caught"]:
                    ui.image(fish_icon(e["shape"], e["color"], e.get("color2")), cx + 13, cy + 10, zoom=1, anchor="center")
                    ui.text(e["hanzi"], cx + 26, cy + 3, 8, "#BC4749", kind="han")
                    ui.text(e["name_vi"], cx + 3, cy + 20, 6, max_w=cw - 6)
                    tip = (f"{e['name_vi']} · {e['hanzi']} ({e['pinyin']}) · {T.RARITY_NAMES[e['rarity']]}\n"
                           f"{T.FISH_BOOK_ENTRY.format(n=e['count'], cm=e['best_size_cm'])}\n{e['hint_vi']}\n{e['desc_vi']}")
                    if e.get("fictional"):
                        tip += "\n" + T.FISH_FICTIONAL
                else:
                    ui.image(fish_icon(e["shape"], "#000000", dark=True), cx + 13, cy + 10, zoom=1, anchor="center")
                    ui.text("？", cx + 30, cy + 3, 8, "#8E877A", kind="han")
                    ui.text(T.RARITY_NAMES[e["rarity"]], cx + 3, cy + 20, 6, col)
                    tip = T.FISH_BOOK_HINT_UNKNOWN.format(hint=e["hint_vi"])
                ui.widgets[f"fish_{e['id']}"] = ui.rect(cx, cy, cw - 2, chh)
                if ui.hover(cx, cy, cw - 2, chh):
                    ui.set_tooltip(tip)
            my = y + h - 36
            ms = " · ".join(f"{m['species']}: {reward_text(m)}" + (" ✓" if m["claimed"] else "") for m in d["milestones"])
            ui.text(ms, x + w / 2, my, 7, "#8B5A2B", anchor="center", max_w=w - 20)
        elif self.tab == "records":
            if self.records is None:
                ui.text("...", 240, 130, 10, anchor="center")
            elif not self.records:
                ui.text(T.FISH_RECORDS_EMPTY, 240, 120, 9, "#5A5A5A", anchor="center")
            else:
                for i, rec in enumerate(self.records[:28]):
                    cx = x + 12 + (i % 2) * 214
                    cy = y + 26 + (i // 2) * 13
                    col = T.RARITY_COLORS.get(rec["rarity"], "#7D7468")
                    ui.text(f"{rec['name_vi']} {rec['hanzi']}", cx, cy, 7, col, kind="han")
                    best = rec["top"][0]
                    ui.text(f"{best['size_cm']} cm · {best['name']}", cx + 200, cy, 7,
                            "#BC4749" if best.get("me") else "#2B2B2B", anchor="topright")
        if ui.button("fishbook_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
