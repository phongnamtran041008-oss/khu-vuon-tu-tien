"""Động Phủ — the player's own abode (spec 6, 7.1): walk around, tend the word garden,
talk to Trúc Lão, open the gacha altar, the discovery tablet and the sentence table."""
from __future__ import annotations

import math
import random

import pygame

from .. import strings_vi as T
from ..art.palette import rgb
from ..engine import sprites
from ..engine.beeflock import Flock
from ..engine.effects import Effects
from ..engine.tilemap import load_map
from ..ui.dialog import DialogScene
from .base import Scene

SPEED = 74.0
PLOT = 32
FOOT_W, FOOT_H = 10, 6


class Player:
    def __init__(self, x: float, y: float, facing: str, appearance: dict):
        self.x, self.y = x, y
        self.facing = facing if facing in ("up", "down", "left", "right") else "down"
        self.appearance = appearance
        self.walk_t = 0.0
        self.moving = False

    def foot_rect(self, x=None, y=None) -> pygame.Rect:
        x = self.x if x is None else x
        y = self.y if y is None else y
        return pygame.Rect(int(x - FOOT_W / 2), int(y - FOOT_H), FOOT_W, FOOT_H)

    def frame(self) -> pygame.Surface:
        frames = sprites.character(self.appearance)
        f = (0, 1, 0, 2)[int(self.walk_t * 8) % 4] if self.moving else 0
        return frames[(self.facing, f)]


class AbodeScene(Scene):
    draws_world = True
    modal = False
    toast_y = 70

    def __init__(self, game):
        super().__init__(game)
        self.map = load_map("abode")
        ch = game.state.character
        spawn = self.map.find("spawn")[0]
        x, y = ch.get("x", spawn.x), ch.get("y", spawn.y)
        if ch.get("zone_id") != "abode":
            x, y = spawn.x, spawn.y
        self.player = Player(float(x), float(y), ch.get("facing", "down"), ch.get("appearance", {}))
        if self.map.blocked(self.player.foot_rect()):
            self.player.x, self.player.y = spawn.x, spawn.y
        g = self.map.find("area", "garden")[0]
        self.garden_origin = (g.x, g.y)
        self.cam = [0, 0]
        self.t = 0.0
        self.fx = Effects()
        self.target = None
        self.last_saved = (self.player.x, self.player.y, self.player.facing)
        self.save_timer = 0.0
        self.refresh_timer = 0.0
        self.tutorial_step = game.state.me.get("tutorial_step", 0)
        self.fog = {}  # plot id -> list of drifting ink blobs
        self._label_cache = {}
        self.flock = Flock()          # spirit bees flying around (stage 5)
        self.pet_follow = None        # the worn Linh Thú trotting after the player (stage 8)
        hv = [o for o in self.map.objects if o.props.get("action") == "hive"]
        self.hive_obj = hv[0] if hv else None
        self.egg_hint_shown = False
        self.fishing = None           # the FishingScene casting from here (stage 6)
        from .fishing import WeatherWatch
        self.weather = WeatherWatch("abode")

    # ------------------------------------------------------------ lifecycle
    def on_enter(self):
        self.refresh_garden()
        self.refresh_me()
        if self.tutorial_step == 0:
            self.game.push(DialogScene(self.game, T.TUTORIAL[0], on_done=lambda: self.set_tutorial(1)))

    def on_exit(self):
        self.save_position()

    def save_position(self):
        p = self.player
        cur = (round(p.x, 1), round(p.y, 1), p.facing)
        if cur == self.last_saved or not self.api.token:
            return
        self.last_saved = cur
        self.api.post("/character/position", {"zone_id": "abode", "x": cur[0], "y": cur[1], "facing": cur[2]},
                      lambda r: None, lambda e: None)

    def set_tutorial(self, step: int) -> None:
        if step <= self.tutorial_step:
            return
        self.tutorial_step = step
        self.game.state.me["tutorial_step"] = step
        self.api.post("/tutorial", {"step": step}, lambda r: None, lambda e: None)

    def tutorial_event(self, event: str) -> None:
        """plant -> learn -> answered: each first time moves the tutorial on."""
        nxt = {"plant": 2, "learn": 3, "answered": 4}.get(event)
        if nxt and self.tutorial_step == nxt - 1:
            self.set_tutorial(nxt)
            on_done = (lambda: self.set_tutorial(5)) if nxt == 4 else None
            self.game.push(DialogScene(self.game, T.TUTORIAL[nxt], on_done=on_done))

    # ------------------------------------------------------------ data
    def refresh_me(self):
        def ok(me):
            self.game.state.me.update(me)
        self.api.get("/me", ok, lambda e: None)

    def refresh_garden(self, then=None):
        def ok(g):
            self.game.state.garden = g
            self.game.state.garden_at = self.game.now
            if g.get("discoveries"):
                self.show_discoveries(g["discoveries"])
            for pz in g.get("pollinated", []):   # spec 10.2: a full pollen bar
                p = self.plot_by_id(pz["plot_id"])
                if p:
                    cx, cy = self.plot_center(p)
                    self.fx.burst(cx, cy - 6, "o", 16, 25)
                self.game.toast(T.POLLINATED_NOW.format(hz=pz["hanzi"]), "#C99A3A")
            if (not g.get("bees") and not self.egg_hint_shown and self.tutorial_step >= 5
                    and any(q["id"] == "lp1_trung_ong" and q["state"] == "active"
                            for q in (self.game.state.quests or {}).get("quests", []))):
                self.egg_hint_shown = True
                self.game.toast(T.STARTER_EGG_HINT, "#C99A3A")
            for ev in g.get("fire_events", []):
                p = self.plot_by_id(ev["plot_id"])
                if p:
                    cx, cy = self.plot_center(p)
                    self.fx.burst(cx, cy, "r", 18, 30)
                    self.game.toast("Lửa bén sang cây 木! Sương mực tăng lên.", "#BC4749")
            if then:
                then()
        self.api.get("/garden", ok, self.game.api_error)

    def plots(self) -> list[dict]:
        return self.game.state.garden.get("plots", [])

    def decorations(self) -> list[str]:
        return self.game.state.garden.get("decorations", [])

    def plot_by_id(self, pid: int) -> dict | None:
        return next((p for p in self.plots() if p["id"] == pid), None)

    def plot_at_world(self, wx: float, wy: float) -> dict | None:
        ox, oy = self.garden_origin
        gx, gy = int((wx - ox) // PLOT), int((wy - oy) // PLOT)
        return next((p for p in self.plots() if p["x"] == gx and p["y"] == gy), None)

    def plot_rect(self, p: dict) -> pygame.Rect:
        ox, oy = self.garden_origin
        return pygame.Rect(int(ox + p["x"] * PLOT), int(oy + p["y"] * PLOT), PLOT, PLOT)

    def plot_center(self, p: dict) -> tuple[float, float]:
        r = self.plot_rect(p)
        return r.centerx, r.centery

    def seconds_left(self, p: dict) -> float | None:
        s = p.get("seconds_until_due")
        if s is None:
            return None
        return max(0.0, s - (self.game.now - self.game.state.garden_at))

    def is_due(self, p: dict) -> bool:
        if not p.get("word") or p.get("ripe") or p.get("stage", 0) == 0:
            return False
        left = self.seconds_left(p)
        return left is not None and left <= 0

    def update_plot(self, view: dict) -> None:
        g = self.game.state.garden
        for i, p in enumerate(g.get("plots", [])):
            if p["id"] == view["id"]:
                if "seconds_until_due" in view:
                    # re-base the countdown on "now"
                    view = dict(view)
                    elapsed = self.game.now - self.game.state.garden_at
                    if view.get("seconds_until_due") is not None:
                        view["seconds_until_due"] = view["seconds_until_due"] + elapsed
                merged = {**p, **view}
                if not view.get("word"):
                    for k in ("stage", "ripe", "due", "seconds_until_due", "wither", "auras"):
                        merged.pop(k, None)
                g["plots"][i] = merged

    # ------------------------------------------------------------ events from overlays
    def show_discoveries(self, found: list[dict]) -> None:
        from .book import DiscoveryPopup
        for d in found:
            self.game.audio.play("discover")
            self.game.push(DiscoveryPopup(self.game, d))

    def on_answer(self, plot: dict, result: dict) -> None:
        """Called by the quiz overlay after a garden answer."""
        cx, cy = self.plot_center(plot)
        if result.get("plot"):
            before = plot.get("stage", 0)
            self.update_plot(result["plot"])
            after = result["plot"].get("stage", before)
            if result.get("correct"):
                if plot.get("wither", 0) >= 30:
                    self.fx.ink_to_light(cx, cy)
                else:
                    self.fx.burst(cx, cy, "o", 16, 35)
                if after > before:
                    self.fx.float_text(T.STAGES[after], cx, cy - 18, "#6A994E")
        reward = (result.get("reward") or {}).get("spirit_stones")
        if reward:
            self.fx.float_text(T.REWARD.format(n=reward), cx, cy - 8)
            self.game.state.me["spirit_stones"] = result.get("spirit_stones", self.game.state.me.get("spirit_stones"))
            self.game.audio.play("coin")
        bonus = result.get("pet_bonus")       # Trâu / Rồng (stage 8)
        if bonus:
            self.game.toast(T.PET_BONUS_TRAU.format(n=bonus["extra"]) if bonus["pet"] == "trau"
                            else T.PET_BONUS_RONG.format(s=bonus.get("streak", 5)), "#C99A3A")
        if result.get("mishap"):
            self.play_mishap(result["mishap"], cx, cy)
        if result.get("discoveries"):
            self.show_discoveries(result["discoveries"])
        self.tutorial_event("answered")

    def play_mishap(self, m: dict, cx: float, cy: float) -> None:
        eff = m.get("effect")
        if eff in ("horse_run", "horse_blush"):
            self.fx.run_across("horse", cy + 20, self.cam[0], "妈?" if eff == "horse_run" else "♥")
        elif eff in ("villager_blush", "merchant_confused"):
            self.fx.run_across("villager", cy + 24, self.cam[0], "!!" if eff == "villager_blush" else "?")
        elif eff == "plants_sleep":
            for p in self.plots():
                if p.get("word"):
                    x, y = self.plot_center(p)
                    self.fx.bubble("Zzz", x, y - 10)
        elif eff == "lightning_flash":
            self.fx.flash = 1.0
            self.fx.shake = 0.5
        elif eff == "flowers_talk":
            for p in self.plots()[:6]:
                if p.get("word"):
                    x, y = self.plot_center(p)
                    self.fx.bubble(random.choice(["blablabla", "nói gì cơ?", "话话话"]), x, y - 12)
        elif eff == "lose_stones":
            self.fx.float_text(f"-{m.get('stones_lost', 0)} Linh Thạch", cx, cy - 4, "#BC4749")
            if m.get("stones_lost"):
                self.game.state.me["spirit_stones"] = max(0, self.game.state.me.get("spirit_stones", 0) - m["stones_lost"])
        elif eff == "float_up":
            for p in self.plots():
                if p.get("word"):
                    x, y = self.plot_center(p)
                    self.fx.burst(x, y, "a", 6, 15)
        elif eff == "flower_in_teapot":
            self.fx.bubble("🌸?" if self.game.fonts._ui_has("🌸") else "茶+花?", cx, cy - 12)
        self.fx.bubble(f"{m.get('wrong_hanzi', '')} {m.get('wrong_pinyin', '')} = {m.get('wrong_vi', '')}", cx, cy - 26, 3.5)

    # ------------------------------------------------------------ update
    def update(self, dt, top):
        self.t += dt
        self.fx.update(dt)
        self.update_bees(dt)
        self.update_pet(dt)
        self.weather.update(dt, self.api)
        self.save_timer += dt
        self.refresh_timer += dt
        if self.save_timer > 60:
            self.save_timer = 0
            self.save_position()
        if self.refresh_timer > 45 and top:
            self.refresh_timer = 0
            self.refresh_garden()
        if not top or self.game.chatbox.typing:
            self.player.moving = False
            if not top:
                return
            self.target = self.find_target()
            return
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        p = self.player
        p.moving = bool(dx or dy)
        if p.moving:
            if dx and dy:
                dx, dy = dx * 0.7071, dy * 0.7071
            if abs(dx) > abs(dy):
                p.facing = "right" if dx > 0 else "left"
            elif dy:
                p.facing = "down" if dy > 0 else "up"
            nx = p.x + dx * SPEED * dt
            if not self.map.blocked(p.foot_rect(nx, p.y)):
                p.x = nx
            ny = p.y + dy * SPEED * dt
            if not self.map.blocked(p.foot_rect(p.x, ny)):
                p.y = ny
            p.walk_t += dt
        self.target = self.find_target()

    # ------------------------------------------------------------ spirit bees (stage 5)
    def bee_list(self) -> list[dict]:
        return self.game.state.garden.get("bees", [])

    def hive_info(self) -> dict:
        return self.game.state.garden.get("hive") or {}

    def hive_center(self) -> tuple[float, float]:
        o = self.hive_obj
        if o is None:
            return self.player.x, self.player.y - 20
        return o.x + o.w / 2, o.y + 12

    def flower_plots(self) -> list[dict]:
        return [p for p in self.plots() if p.get("word") and p.get("stage", 0) >= 3 and not p.get("pollinated")]

    def update_bees(self, dt: float) -> None:
        now = self.game.now
        hx, hy = self.hive_center()
        flowers = self.flower_plots()
        guards = 0
        for b in self.bee_list():
            fb = self.flock.get(str(b["id"]), b["sp"], hx, hy + 14, now)
            if b["role"] == "guard":
                side = -1 if guards % 2 == 0 else 1
                guards += 1
                fb.update(dt, self.player.x + side * (10 + guards * 3), self.player.y - 2, 7, 90, 18)
            elif b["role"] == "pollinate" and flowers:
                if now >= fb.task_until or fb.task not in {p["id"] for p in flowers}:
                    fb.task = random.choice(flowers)["id"]
                    fb.task_until = now + random.uniform(2.5, 4.5)
                p = self.plot_by_id(fb.task)
                cx, cy = self.plot_center(p) if p else (hx, hy)
                fb.update(dt, cx, cy + 4, 5, 55, 14)
                if p and math.hypot(fb.x - cx, fb.y - cy - 4) < 10 and random.random() < dt * 3:
                    self.fx.sparkle(fb.x, fb.y - fb.z + 4, "o")      # hạt phấn vàng
            else:
                fb.update(dt, hx, hy + 14, 14, 45, 10)
        self.flock.prune(now)

    def update_pet(self, dt: float) -> None:
        kind = self.game.worn_pet()
        if not kind:
            self.pet_follow = None
            return
        if self.pet_follow is None or self.pet_follow.kind != kind:
            from ..engine.petfollow import PetFollower
            self.pet_follow = PetFollower(self.player.x, self.player.y)
            self.pet_follow.kind = kind
        self.pet_follow.update(dt, self.player.x, self.player.y, self.player.facing)

    def bee_drawables(self, cx: int, cy: int) -> list:
        out = []
        species = self.game.state.bee_species
        for fb in self.flock.bees.values():
            look = (species.get(fb.sp) or {}).get("look")
            img = sprites.bee(look, fb.frame(), fb.left)
            out.append((fb.y + 6, img, (int(fb.x - 4) - cx, int(fb.y - fb.z - 4) - cy), (fb.x, fb.y)))
        return out

    def find_target(self):
        p = self.player
        off = {"up": (0, -10), "down": (0, 6), "left": (-10, -3), "right": (10, -3)}[p.facing]
        fx, fy = p.x + off[0], p.y + off[1]
        best, best_d = None, 22.0
        for o in self.map.objects:
            if o.type in ("npc", "interact"):
                cx, cy = o.x + o.w / 2, o.y + o.h
                d = math.hypot(cx - fx, cy - fy)
                if d < best_d:
                    best, best_d = ("object", o), d
        plot = self.plot_at_world(p.x, p.y - 3) or self.plot_at_world(fx, fy)
        if plot and (best is None or best_d > 12):
            best = ("plot", plot)
        return best

    # ------------------------------------------------------------ interaction
    def interact(self, target) -> None:
        kind, obj = target
        if kind == "plot":
            self.open_plot(obj)
            return
        action = obj.props.get("action") or ("talk" if obj.type == "npc" else None)
        if action == "talk":
            self.game.push(DialogScene(self.game, [random.choice(T.MASTER_IDLE)]))
        elif action == "gacha":
            from .gacha import GachaScene
            self.game.push(GachaScene(self.game, on_close=self.after_gacha))
        elif action == "discoveries":
            from .book import BookScene
            self.game.push(BookScene(self.game))
        elif action == "craft":
            from .craft import CraftScene
            self.game.push(CraftScene(self.game))
        elif action == "hive":
            self.open_hive()
        elif action == "alchemy":        # stage 8: the Đan Lô of the abode
            self.save_position()
            self.game.open_alchemy()
        elif action == "meditate":
            from .rpg import MeditateScene
            self.save_position()   # the server checks that we are at home
            self.game.push(MeditateScene(self.game))
        elif action == "exit":
            self.leave_to_village()

    def start_fishing(self, bob) -> None:
        from .fishing import FishingScene
        self.player.moving = False
        self.game.push(FishingScene(self.game, self, "abode", bob))

    def leave_to_village(self) -> None:
        """Through the bamboo gate into the shared world (stage 3)."""
        self.save_position()
        self.game.go_village()

    def after_gacha(self):
        self.refresh_me()

    def open_plot(self, plot: dict) -> None:
        from .garden_ui import PlotPanel
        self.game.push(PlotPanel(self.game, self, plot["id"]))

    # ------------------------------------------------------------ drawing
    def _cam(self, surf) -> tuple[int, int]:
        w, h = surf.get_size()
        cx = int(self.player.x - w / 2)
        cy = int(self.player.y - 12 - h / 2)
        cx = max(0, min(self.map.px_w - w, cx))
        cy = max(0, min(self.map.px_h - h, cy))
        if self.fx.shake:
            cx += random.randint(-2, 2)
            cy += random.randint(-2, 2)
        self.cam = [cx, cy]
        return cx, cy

    def _label(self, hanzi: str) -> pygame.Surface:
        if hanzi not in self._label_cache:
            tag = sprites.tag().copy()
            size = 10 if len(hanzi) == 1 else 5
            txt = self.game.fonts.render(hanzi if len(hanzi) <= 2 else hanzi[:2], size, (43, 43, 43), 1,
                                         kind="han", antialias=False)
            if len(hanzi) > 1:
                tag = pygame.Surface((max(13, txt.get_width() + 4), 13), pygame.SRCALPHA)
                pygame.draw.rect(tag, rgb("w"), (0, 0, tag.get_width(), 11))
                pygame.draw.rect(tag, rgb("k"), (0, 0, tag.get_width(), 11), 1)
            tag.blit(txt, ((tag.get_width() - txt.get_width()) // 2, (11 - txt.get_height()) // 2 + 0))
            self._label_cache[hanzi] = tag
        return self._label_cache[hanzi]

    def _small_text(self, text: str, color: str) -> pygame.Surface:
        return self.game.fonts.render(text, 7, color, 1)

    def draw_world(self, surf):
        cx, cy = self._cam(surf)
        self.map.draw_ground(surf, (cx, cy), self.t)
        self.draw_garden(surf, cx, cy)
        # y-sorted props, NPC and player
        drawables = []
        for o in self.map.objects:
            name = o.props.get("sprite")
            if name:
                img = sprites.prop(name, int(o.props.get("variant", 0) or 0),
                                   int(self.t * 3) % 4 if name in sprites.ANIMATED_PROPS else 0)
                drawables.append((o.foot_y, img, (int(o.x) - cx, int(o.y) - cy)))
            elif o.type == "npc":
                img = sprites.truc_lao()[1 if int(self.t * 10) % 37 == 0 else 0]
                drawables.append((o.foot_y, img, (int(o.x) - cx, int(o.y) - cy)))
        deco = self.decorations()
        if "small_forest" in deco:
            gx, gy = self.garden_origin
            for i in range(3):
                img = sprites.prop("bamboo", 30 + i)
                drawables.append((gy - 8, img, (int(gx - 20 + i * 8) - cx, int(gy - 40) - cy)))
        img = self.player.frame()
        drawables.append((self.player.y, img, (int(self.player.x - 8) - cx, int(self.player.y - 24) - cy)))
        pf = self.pet_follow
        if pf is not None:             # the worn Linh Thú (stage 8)
            pygame.draw.ellipse(surf, (40, 50, 30), (int(pf.x - 5) - cx, int(pf.y - 1) - cy, 10, 3))
            drawables.append((pf.y, sprites.pet(pf.kind, pf.frame, pf.left), (int(pf.x - 8) - cx, int(pf.y - 13) - cy)))
        hive = self.hive_info()
        if self.hive_obj is not None:
            for i, d in enumerate(hive.get("decorations", [])):   # spec 10.1: trang trí tổ ong
                dimg = sprites.decoration(d, int(self.t * 3) % 4)
                ox = self.hive_obj.x + (-14 - i * 10 if i % 2 == 0 else 28 + (i // 2) * 10)
                oy = self.hive_obj.y + self.hive_obj.h - dimg.get_height()
                drawables.append((oy + dimg.get_height(), dimg, (int(ox) - cx, int(oy) - cy)))
        for fy, bimg, pos, ground in self.bee_drawables(cx, cy):
            pygame.draw.ellipse(surf, (40, 50, 30), (int(ground[0] - 2) - cx, int(ground[1]) - cy, 4, 2))
            drawables.append((fy, bimg, pos))
        for _, img, pos in sorted(drawables, key=lambda d: d[0]):
            surf.blit(img, pos)
        if self.fishing is not None:
            from .fishing import draw_rod
            draw_rod(surf, self.fishing, cx, cy, self.t)
        # interaction marker
        if self.target and self.game.top is self:
            kind, obj = self.target
            if kind == "plot":
                r = self.plot_rect(obj).move(-cx, -cy)
                pygame.draw.rect(surf, rgb("o"), r, 1)
            else:
                bob = int(math.sin(self.t * 6) * 2)
                pygame.draw.polygon(surf, rgb("o"), [(int(obj.x + obj.w / 2) - cx - 3, int(obj.y) - cy - 8 + bob),
                                                     (int(obj.x + obj.w / 2) - cx + 3, int(obj.y) - cy - 8 + bob),
                                                     (int(obj.x + obj.w / 2) - cx, int(obj.y) - cy - 4 + bob)])
        self.fx.draw(surf, (cx, cy), self._small_text, self.t)
        from .world import darkness
        d = darkness(self.game.day_phase())
        if d > 0:  # same day/night as the shared world (spec 7.1)
            night = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            night.fill((18, 22, 58, int(90 * d)))
            surf.blit(night, (0, 0))
        if self.weather.rain:
            from .fishing import draw_rain
            draw_rain(surf, self.t)

    def draw_garden(self, surf, cx, cy):
        frame = int(self.t * 1.3) % 2
        for p in self.plots():
            r = self.plot_rect(p).move(-cx, -cy)
            if r.right < 0 or r.bottom < 0 or r.left > surf.get_width() or r.top > surf.get_height():
                continue
            surf.blit(sprites.bed(not p["unlocked"]), r.topleft)
            if not p["unlocked"]:
                if p.get("can_unlock") and int(self.t * 2) % 2:
                    pygame.draw.rect(surf, rgb("o"), r, 1)
                continue
            for aura in p.get("auras", []):
                col = rgb("a") if aura == "water" else rgb("r")
                pygame.draw.rect(surf, col, r.inflate(-2, -2), 1)
            w = p.get("word")
            if not w:
                continue
            wither = p.get("wither", 0) or 0
            img = sprites.plant(p.get("stage", 0), w.get("rarity", "common"), w["id"], frame, int(wither // 10))
            surf.blit(img, (r.x + 4, r.y + 3))
            if wither >= 30:
                self.draw_fog(surf, p, r, wither)
            surf.blit(self._label(w["hanzi"]), (r.x + 1, r.y + 19))
            if p.get("pollinated"):           # spec 10.2: Đã thụ phấn
                pygame.draw.circle(surf, rgb("O"), (r.right - 5, r.bottom - 5), 3)
                pygame.draw.circle(surf, rgb("o"), (r.right - 5, r.bottom - 5), 2)
                if random.random() < 0.04:
                    self.fx.sparkle(r.right - 5 + cx, r.bottom - 8 + cy, "o")
            elif p.get("stage", 0) >= 3 and (p.get("pollen") or 0) > 0:
                pygame.draw.rect(surf, rgb("k"), (r.x + 15, r.bottom - 4, 15, 3))
                pygame.draw.rect(surf, rgb("o"), (r.x + 16, r.bottom - 3, max(1, int(13 * p["pollen"] / 100)), 1))
            if p.get("needs_review"):
                pygame.draw.circle(surf, rgb("r"), (r.x + 12, r.y + 20), 2)
            if self.is_due(p):
                bob = int(abs(math.sin(self.t * 4)) * 3)
                pygame.draw.rect(surf, rgb("o"), (r.right - 9, r.y + 1 - bob, 7, 9))
                pygame.draw.rect(surf, rgb("k"), (r.right - 9, r.y + 1 - bob, 7, 9), 1)
                pygame.draw.line(surf, rgb("k"), (r.right - 6, r.y + 3 - bob), (r.right - 6, r.y + 6 - bob))
                surf.set_at((r.right - 6, r.y + 8 - bob), rgb("k"))
            if p.get("ripe") and random.random() < 0.15:
                self.fx.sparkle(r.centerx + cx, r.y + 10 + cy, "o" if w.get("rarity") != "common" else "W")

    def draw_fog(self, surf, p, r, wither):
        blobs = self.fog.setdefault(p["id"], [(random.uniform(0, 6.28), random.uniform(4, 10)) for _ in range(4)])
        fog = pygame.Surface((PLOT, PLOT), pygame.SRCALPHA)
        alpha = int(40 + wither * 1.4)
        for i, (ph, rad) in enumerate(blobs):
            ox = 16 + math.cos(self.t * 0.4 + ph) * 8
            oy = 16 + math.sin(self.t * 0.3 + ph * 2) * 7
            pygame.draw.circle(fog, (30, 28, 32, min(150, alpha)), (int(ox), int(oy)), int(rad))
        surf.blit(fog, r.topleft)

    # ------------------------------------------------------------ HUD
    def draw_ui(self, ui):
        top = self.game.top is self
        me = self.game.state.me
        ch = self.game.state.character
        # player card
        ui.fill(4, 4, 128, 34, (244, 235, 217, 235))
        ui.border(4, 4, 128, 34, "#8B5A2B")
        head = self.player.frame().subsurface(pygame.Rect(2, 1, 12, 11)) if self.player.facing != "up" else \
            sprites.character(self.player.appearance)[("down", 0)].subsurface(pygame.Rect(2, 1, 12, 11))
        ui.fill(7, 7, 28, 28, "#E3D5BA")
        ui.image(head, 21, 21, zoom=2, anchor="center")
        from .library import portrait_frame
        portrait_frame(ui, me.get("frame"), 7, 7, 28, 28)
        ui.text(ch.get("display_name", ""), 39, 7, 9)
        if me.get("title"):
            ui.text(f"«{me['title']}»", 39, 28, 6, "#B8862E")
        ui.text(T.REALMS.get(ch.get("realm", "pham_nhan"), ""), 39, 19, 8, "#6A994E")
        ui.image(sprites.icon("stone"), 7, 41, zoom=1)
        ui.text(f"{me.get('spirit_stones', 0):,}".replace(",", "."), 18, 44, 9, "#FFFFFF", anchor="midleft")
        ui.text(f"{me.get('spirit_stones', 0):,}".replace(",", "."), 17.5, 43.5, 9, "#2B2B2B", anchor="midleft")
        # chat first: while typing, letters must not trigger the hotkeys below
        self.game.chatbox.draw(ui, in_zone=False, enabled=top)
        typing = self.game.chatbox.typing
        # menu buttons
        bx = 480 - 4
        for wid, label, key, action in [("hud_menu", T.HUD_MENU, pygame.K_ESCAPE, self.open_settings),
                                        ("hud_friends", T.HUD_FRIENDS, pygame.K_p, self.game.open_friends),
                                        ("hud_quests", T.HUD_QUESTS, pygame.K_j, self.game.open_quests),
                                        ("hud_char", T.HUD_CHAR, pygame.K_k, self.game.open_char),
                                        ("hud_gacha", T.HUD_GACHA, pygame.K_g, self.open_gacha),
                                        ("hud_hive", T.HUD_HIVE, pygame.K_h, self.open_hive),
                                        ("hud_book", T.HUD_BOOK, pygame.K_b, self.open_book),
                                        ("hud_craft", T.HUD_CRAFT, pygame.K_c, self.open_craft),
                                        ("hud_bag", T.HUD_BAG, pygame.K_TAB, self.open_bag)]:
            w = ui.text_size(label, 8)[0] + 10
            bx -= w + 3
            if ui.button(wid, bx, 252, w, 14, label, key=key if (top and not typing) else None, enabled=top):
                action()
        if top and not typing and ui.key(pygame.K_l):
            self.game.open_library()
        if top and not typing and ui.key(pygame.K_o):
            self.game.open_pets()
        if not top or typing:
            return
        # hover tooltip for plots
        mx, my = ui.inp.mouse
        wx, wy = mx + self.cam[0], my + self.cam[1]
        hp = self.plot_at_world(wx, wy)
        if hp and ui.hover(0, 0, 480, 245):
            ui.set_tooltip(self.plot_tooltip(hp))
        # interaction hint
        if self.target:
            kind, obj = self.target
            label = T.ACTIONS["plot"] if kind == "plot" else T.ACTIONS.get(
                obj.props.get("action") or ("talk" if obj.type == "npc" else ""), obj.name)
            ui.text(T.PRESS_E.format(action=label), 240, 230, 9, "#FFFFFF", anchor="center")
            if ui.key(pygame.K_e):
                self.interact(self.target)
                return
        # the pond (stage 6, spec 11.1: F at the water)
        from .fishing import water_near
        spot = water_near(self.map, self.player.x, self.player.y, self.player.facing)
        if spot:
            if not self.target:
                ui.text(T.PRESS_F, 240, 230, 9, "#FFFFFF", anchor="center")
            if ui.key(pygame.K_f):
                self.start_fishing(spot[1])
                return
        # tutorial hint
        if self.tutorial_step in (1, 2, 3):
            hint = {1: "Gieo hạt 水 vào một ô đất trong vườn",
                    2: "Bấm vào cây vừa gieo để xem thẻ chữ",
                    3: "Đợi cây đến giờ ôn (dấu ! vàng) rồi bấm vào để ôn"}[self.tutorial_step]
            w = ui.text_size(hint, 8)[0] + 12
            ui.fill(240 - w / 2, 4, w, 13, (188, 71, 73, 220))
            ui.text(hint, 240, 10.5, 8, "#FFFFFF", anchor="center")
        # clicks in the world
        if ui.inp.clicked and my < 248 and not ui.hover(0, 150, 214, 100):
            if hp and hp is not None:
                ui.consume_click()
                self.open_plot(hp)
                return
            for o in self.map.objects:
                if o.type in ("npc", "interact") and o.rect.collidepoint(wx, wy):
                    ui.consume_click()
                    self.interact(("object", o))
                    return

    def plot_tooltip(self, p: dict) -> str:
        if not p["unlocked"]:
            if p.get("can_unlock"):
                return T.PLOT_LOCKED + " · " + T.PLOT_UNLOCK.format(cost=p.get("unlock_cost"))
            return T.PLOT_LOCKED + " · " + T.PLOT_UNLOCK_FAR
        w = p.get("word")
        if not w:
            return T.PLOT_EMPTY
        lines = [f"{w['hanzi']}  {w.get('pinyin') or ''}", T.STAGES[p.get("stage", 0)]]
        if p.get("ripe"):
            lines.append("Chín rồi, thu hoạch thôi!")
        elif p.get("stage", 0) > 0:
            left = self.seconds_left(p)
            lines.append(T.DUE_NOW if self.is_due(p) else T.DUE_IN.format(t=fmt_secs(left or 0)))
        if (p.get("wither") or 0) >= 1:
            lines.append(T.WITHER.format(p=int(p["wither"])))
        for a in p.get("auras", []):
            lines.append(T.AURA[a])
        if p.get("needs_review"):
            lines.append(T.NEEDS_REVIEW)
        if p.get("pollinated"):
            lines.append(T.POLLINATED)
        elif p.get("stage", 0) >= 3 and p.get("pollen"):
            lines.append(T.POLLEN.format(p=int(p["pollen"])))
        return "\n".join(lines)

    def open_settings(self):
        from .settings import SettingsScene
        self.game.push(SettingsScene(self.game, in_game=True))

    def open_gacha(self):
        from .gacha import GachaScene
        self.game.push(GachaScene(self.game, on_close=self.after_gacha))

    def open_hive(self):
        self.game.open_hive(on_close=self.refresh_me)

    def open_book(self):
        from .book import BookScene
        self.game.push(BookScene(self.game))

    def open_craft(self):
        from .craft import CraftScene
        self.game.push(CraftScene(self.game))

    def open_bag(self):
        from .bag import BagScene
        self.game.push(BagScene(self.game, self))


def fmt_secs(s: float) -> str:
    s = int(s)
    if s >= 86400:
        return f"{s // 86400} ngày {s % 86400 // 3600} giờ"
    if s >= 3600:
        return f"{s // 3600} giờ {s % 3600 // 60:02d} phút"
    return f"{s // 60:02d}:{s % 60:02d}"
