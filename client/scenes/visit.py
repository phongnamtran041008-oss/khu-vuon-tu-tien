"""Visiting a friend's abode (spec 15.3): walk around their garden, look only, and
"tưới giúp" plants whose word you have learned (both of you get Linh Thạch)."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..ui.dialog import DialogScene
from .abode import AbodeScene
from .base import Scene


class VisitScene(AbodeScene):
    modal = True
    opaque = True

    def __init__(self, game, owner_id: int, owner_name: str):
        self.owner_id, self.owner_name = owner_id, owner_name
        self.data: dict = {"plots": []}
        super().__init__(game)
        spawn = self.map.find("spawn")[0]
        self.player.x, self.player.y, self.player.facing = float(spawn.x), float(spawn.y), "up"
        self.tutorial_step = 99

    # the owner's data instead of ours
    def plots(self) -> list[dict]:
        return self.data.get("plots", [])

    def decorations(self) -> list[str]:
        return self.data.get("decorations", [])

    def bee_list(self) -> list[dict]:
        return [b for b in self.data.get("bees", []) if b.get("role") != "guard"]   # the guards went out with the owner

    def hive_info(self) -> dict:
        return self.data.get("hive") or {}

    def on_enter(self):
        self.refresh_garden()

    def on_exit(self):
        pass

    def save_position(self):
        pass

    def refresh_me(self):
        pass

    def refresh_garden(self, then=None):
        def ok(d):
            self.data = d
            if then:
                then()

        def err(e):
            self.game.api_error(e)
            self.close()
        self.api.get(f"/friends/{self.owner_id}/garden", ok, err)

    def is_due(self, p: dict) -> bool:
        return False

    def interact(self, target) -> None:
        kind, obj = target
        if kind == "plot":
            self.open_plot(obj)
        elif obj.props.get("action") == "exit":
            self.close()
        elif obj.type == "npc":
            self.game.push(DialogScene(self.game, T.VISIT_MASTER))
        else:
            self.game.toast(T.VISIT_OWNER_ITEM, "#5A5A5A")

    def open_plot(self, plot: dict) -> None:
        if plot.get("word"):
            self.game.push(HelpPanel(self.game, self, plot))

    def plot_tooltip(self, p: dict) -> str:
        w = p.get("word")
        if not p["unlocked"]:
            return T.PLOT_LOCKED
        if not w:
            return T.PLOT_EMPTY
        lines = [w["hanzi"] + (f"  {w['pinyin']}" if w.get("pinyin") else ""), T.STAGES[p.get("stage", 0)]]
        if (p.get("wither") or 0) >= 1:
            lines.append(T.WITHER.format(p=int(p["wither"])))
        lines.append(T.HELP_TIP_OK if p.get("helpable") else
                     (T.HELP_TIP_YOUNG if p.get("stage", 0) == 0 else T.HELP_TIP_UNKNOWN))
        return "\n".join(lines)

    def draw_ui(self, ui):
        top = self.game.top is self
        d = self.data
        title = T.VISIT_TITLE.format(name=self.owner_name)
        w = max(ui.text_size(title, 10)[0], ui.text_size(T.VISIT_HINT.format(n=d.get("help_reward", 10)), 7)[0]) + 20
        ui.fill(240 - w / 2, 4, w, 30, (244, 235, 217, 235))
        ui.border(240 - w / 2, 4, w, 30, "#8B5A2B")
        ui.text(title, 240, 7, 10, anchor="midtop")
        ui.text(T.VISIT_HINT.format(n=d.get("help_reward", 10)), 240, 21, 7, "#5A5A5A", anchor="midtop")
        from ..engine import sprites
        ui.fill(4, 38, 110, 26, (20, 18, 15, 150))
        ui.text(T.HELPS_LEFT.format(n=d.get("helps_left", 0)), 8, 41, 7, "#FFFFFF")
        ui.image(sprites.icon("stone"), 8, 52, zoom=1)
        ui.text(f"{self.game.state.me.get('spirit_stones', 0):,}".replace(",", "."), 19, 55.5, 8, "#FFFFFF",
                anchor="midleft")
        if ui.button("visit_back", 480 - 74, 252, 70, 14, T.VISIT_BACK, style="primary",
                     key=pygame.K_ESCAPE if top else None, enabled=top):
            self.close()
            return
        if not top:
            return
        mx, my = ui.inp.mouse
        wx, wy = mx + self.cam[0], my + self.cam[1]
        hp = self.plot_at_world(wx, wy)
        if hp and ui.hover(0, 36, 480, 210):
            ui.set_tooltip(self.plot_tooltip(hp))
        if self.target:
            kind, obj = self.target
            label = T.HELP if kind == "plot" else T.ACTIONS.get(
                obj.props.get("action") or ("talk" if obj.type == "npc" else ""), obj.name)
            if kind != "plot" and obj.props.get("action") == "exit":
                label = T.VISIT_BACK
            ui.text(T.PRESS_E.format(action=label), 240, 238, 9, "#FFFFFF", anchor="center")
            if ui.key(pygame.K_e):
                self.interact(self.target)
                return
        if ui.inp.clicked and 36 < my < 248 and hp:
            ui.consume_click()
            self.open_plot(hp)


class HelpPanel(Scene):
    def __init__(self, game, visit: VisitScene, plot: dict):
        super().__init__(game)
        self.visit, self.plot = visit, plot
        self.busy = False

    def draw_ui(self, ui):
        ui.dim(90)
        p, w = self.plot, self.plot["word"]
        x, y, pw, ph = 150, 120, 180, 100
        ui.panel(x, y, pw, ph)
        ui.text(w["hanzi"], x + 32, y + 30, 22, kind="han", anchor="center")
        if w.get("pinyin"):
            ui.text(w["pinyin"], x + 32, y + 52, 9, kind="han", anchor="center")
        ui.text(T.STAGES[p.get("stage", 0)], x + 64, y + 12, 9)
        if w.get("meaning_vi"):
            ui.text(w["meaning_vi"], x + 64, y + 26, 8, "#5A5A5A", max_w=pw - 72)
        if (p.get("wither") or 0) >= 1:
            ui.text(T.WITHER.format(p=int(p["wither"])), x + 64, y + 44, 8, "#5A5A5A")
        left = self.visit.data.get("helps_left", 0)
        can = p.get("helpable") and left > 0
        if not p.get("helpable"):
            ui.text(T.HELP_TIP_YOUNG if p.get("stage", 0) == 0 else T.HELP_TIP_UNKNOWN, x + pw / 2, y + ph - 34, 7,
                    "#BC4749", anchor="center", max_w=pw - 20)
        elif left <= 0:
            ui.text(T.HELP_NONE_LEFT, x + pw / 2, y + ph - 34, 7, "#BC4749", anchor="center")
        if ui.button("help_go", x + 30, y + ph - 24, pw - 60, 16, T.HELP, style="green", key=pygame.K_RETURN,
                     enabled=bool(can) and not self.busy):
            self.start()
        if ui.key(pygame.K_ESCAPE) or (ui.inp.clicked and not ui.hover(x, y, pw, ph)):
            self.close()

    def start(self) -> None:
        self.busy = True
        from .quiz import QuizScene

        def ok(q):
            self.busy = False
            self.visit.data["helps_left"] = q.get("helps_left", 0)
            self.close()
            self.game.push(QuizScene(self.game, q, on_result=self.done))

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/friends/help", {"friend_id": self.visit.owner_id, "plot_id": self.plot["id"]}, ok, err)

    def done(self, res: dict) -> None:
        if "helps_left" in res:
            self.visit.data["helps_left"] = res["helps_left"]
        n = (res.get("reward") or {}).get("spirit_stones")
        if n:
            self.game.state.me["spirit_stones"] = res.get("spirit_stones", self.game.state.me.get("spirit_stones"))
            cx, cy = self.visit.plot_center(self.plot)
            self.visit.fx.burst(cx, cy, "a", 16, 30)
            self.visit.fx.float_text(T.REWARD.format(n=n), cx, cy - 10)
            self.game.toast(T.HELP_DONE.format(n=n), "#6A994E")
            self.game.audio.play("coin")
