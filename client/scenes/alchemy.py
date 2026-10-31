"""Luyện đan (spec 12.3): the list of đan phương at a furnace, upgrading the abode's furnace,
and the canh lửa minigame. The server takes the ingredients when the fire is lit, decides
where each văn hỏa zone sits and replays the presses with engine/alchemy_fire.py (the same
file as the server's); the client only shows the needle and sends how long it ran."""
from __future__ import annotations

import pygame

from .. import strings_vi as T
from ..engine import alchemy_fire, sprites
from .base import Scene

MIN_PRESS_MS = 120
MAX_NEEDLE_MS = 20000


class AlchemyScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.busy = False
        self.scroll = 0
        self.reload()

    def reload(self):
        self.api.get("/alchemy", lambda r: setattr(self, "data", r), self.game.api_error)

    def on_resume(self):
        self.reload()

    def brew(self, rid: str):
        self.busy = True

        def ok(r):
            self.busy = False
            self.game.refresh_inv()
            self.game.refresh_me()
            self.game.push(FireScene(self.game, r["fire"], on_close=self.reload))

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/alchemy/start", {"recipe_id": rid}, ok, err)

    def upgrade(self):
        self.busy = True

        def ok(r):
            self.busy = False
            self.data = r
            self.game.toast(T.ALCHEMY_UPGRADED.format(name=r["furnace"]["name_vi"]), "#C99A3A")
            self.game.audio.play("discover")
            self.game.refresh_me()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/alchemy/furnace/upgrade", {}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 30, 18, 420, 236
        ui.panel(x, y, w, h, T.ALCHEMY_TITLE)
        d = self.data
        if d is None:
            ui.text("...", 240, 130, 10, anchor="center")
            if ui.key(pygame.K_ESCAPE):
                self.close()
            return
        f = d["furnace"]
        where = d["where"]
        head = T.ALCHEMY_HOME.format(name=f["name_vi"], lv=f["level"]) if where == "home" else \
            T.ALCHEMY_PUBLIC if where == "public" else T.ALCHEMY_FAR
        ui.text(head, x + 12, y + 12, 8, "#5A5A5A" if where != "far" else "#BC4749")
        if d.get("buffs"):
            ui.text(T.ALCHEMY_BUFFS.format(b=", ".join(f"{b['name_vi']} {b['seconds_left'] // 60 + 1}'"
                                                        for b in d["buffs"])),
                    x + w - 12, y + 12, 7, "#6A994E", anchor="topright")
        ui.image(sprites.prop("furnace", 0, int(ui.time * 3) % 4), x + 30, y + 64, zoom=2, anchor="center")
        if d.get("open"):
            fire = d["open"]
            if ui.button("alc_resume", x + 8, y + 96, 46, 15, T.ALCHEMY_RESUME, size=7, style="primary"):
                self.game.push(FireScene(self.game, fire, on_close=self.reload))
                return
        # upgrade (abode only)
        if where == "home" and f.get("next"):
            nx = f["next"]
            mats = ", ".join(f"{m['qty']} {m['name_vi']} ({m['have']})" for m in nx["materials"])
            ok = all(m["have"] >= m["qty"] for m in nx["materials"])
            if ui.button("alc_upgrade", x + 4, y + h - 40, 56, 15, T.ALCHEMY_UPGRADE.format(p=nx["cost"]["spirit_stones"]),
                         size=5, style="gold", enabled=ok and not self.busy,
                         tooltip=T.ALCHEMY_UPGRADE_NEED.format(name=nx["name_vi"], m=mats)):
                self.upgrade()
        # the recipes
        rows = d["recipes"]
        per = 7
        if ui.inp.wheel:
            self.scroll = max(0, min(len(rows) - per, self.scroll - ui.inp.wheel))
        lx, lw = x + 62, w - 72
        for i, rcp in enumerate(rows[self.scroll:self.scroll + per]):
            ry = y + 24 + i * 28
            ui.fill(lx, ry, lw, 26, "#FFFDF7" if rcp["known"] else "#EDE4D2")
            ui.border(lx, ry, lw, 26, "#C9B48A")
            ui.text(rcp["hanzi"], lx + 4, ry + 13, 12, "#2B2B2B" if rcp["known"] else "#8E877A", kind="han",
                    anchor="midleft")
            ui.text(rcp["name_vi"], lx + 46, ry + 2, 8, "#2B2B2B" if rcp["known"] else "#8E877A")
            if rcp["known"]:
                ings = "  ".join(f"{g['name_vi']} {g['have']}/{g['qty']}" for g in rcp["ingredients"])
                ui.text(ings, lx + 46, ry + 13, 6, "#5A5A5A", max_w=lw - 160)
                y_ = rcp["yield"]
                ui.text(T.ALCHEMY_FEE.format(n=rcp["fee"]) + " · " +
                        T.ALCHEMY_YIELD.format(h=y_["ha"], m=y_["trung"], t=y_["thuong"]),
                        lx + lw - 74, ry + 2, 6, "#8E877A", anchor="topright")
                if not rcp["realm_ok"]:
                    ui.text(T.ALCHEMY_REALM.format(r=rcp["min_realm_vi"]), lx + lw - 6, ry + 13, 7, "#BC4749",
                            anchor="midright")
                elif ui.button(f"alc_brew_{rcp['id']}", lx + lw - 66, ry + 6, 60, 15, T.ALCHEMY_BREW, size=7,
                               style="primary", enabled=rcp["ready"] and where != "far" and not self.busy
                               and not d.get("open"), tooltip=rcp["desc_vi"]):
                    self.brew(rcp["id"])
                    return
                if rcp["have_pills"]:
                    ui.text(T.ALCHEMY_HAVE.format(n=rcp["have_pills"]), lx + lw - 74, ry + 15, 6, "#6A994E",
                            anchor="topright")
            else:
                ui.text(T.ALCHEMY_UNKNOWN, lx + 46, ry + 13, 7, "#8E877A")
                if rcp.get("sources_vi"):
                    ui.text(T.ALCHEMY_SOURCES.format(s=", ".join(rcp["sources_vi"])), lx + lw - 6, ry + 13, 6,
                            "#8E877A", anchor="midright")
        if ui.button("alc_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


class FireScene(Scene):
    """Canh lửa: three presses, each followed by one character of the pill's name."""

    def __init__(self, game, fire: dict, on_close=None):
        super().__init__(game)
        self.fire = fire
        self.on_close = on_close
        self.round = 0
        self.round_ms = 0.0
        self.timings: list[int] = []
        self.answers: list[str | None] = []
        self.hits: list[str] = []
        self.state = "run"           # run | char | send | result
        self.result: dict | None = None
        self.t = 0.0
        self.flash = 0.0

    @property
    def n(self) -> int:
        return len(self.fire["zones"])

    def update(self, dt, top):
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 2)
        if self.state == "run" and top:
            self.round_ms += dt * 1000
            if self.round_ms >= MAX_NEEDLE_MS:      # left burning: counts as a press where it stands
                self.press()

    def pos(self) -> float:
        return alchemy_fire.needle(int(self.round_ms), self.fire["periods"][self.round], self.fire["bar"])

    def press(self):
        if self.state != "run" or self.round_ms < MIN_PRESS_MS:
            return
        ms = int(self.round_ms)
        z = self.fire["zones"][self.round]
        hit = alchemy_fire.judge(alchemy_fire.needle(ms, self.fire["periods"][self.round], self.fire["bar"]),
                                 z["center"], z["width"], z["perfect"])
        self.timings.append(ms)
        self.hits.append(hit)
        self.flash = 1.0
        self.game.audio.play("correct" if hit != "miss" else "wrong")
        self.state = "char"
        self.game.ui.set_value("fire_pinyin", "")
        if self.fire["chars"][self.round]["ask"]:
            self.game.ui.set_focus("fire_pinyin")

    def next_char(self, typed: str | None):
        self.answers.append(typed)
        self.game.ui.set_focus(None)
        self.round += 1
        self.round_ms = 0.0
        if self.round >= self.n:
            self.send()
        else:
            self.state = "run"

    def send(self):
        self.state = "send"

        def ok(r):
            self.result = r
            self.state = "result"
            good = r.get("made", 0) > 0
            self.game.audio.play("discover" if r.get("quality") == "thuong" else "coin" if good else "wrong")
            self.game.on_xp(r.get("xp"))
            self.game.refresh_inv()

        def err(e):
            self.game.api_error(e)
            self.close()
        self.api.post("/alchemy/finish", {"session_id": self.fire["session_id"], "timings": self.timings,
                                          "pinyin_answers": self.answers}, ok, err)

    def close(self):
        super().close()
        if self.on_close:
            self.on_close()

    # ------------------------------------------------------------ drawing
    def draw_bar(self, ui, bx, by, bw, bh):
        bar = self.fire["bar"]
        for i in range(int(bw)):                       # cool blue -> fierce red
            k = i / bw
            ui.fill(bx + i, by, 1, bh, (int(70 + 160 * k), int(110 - 50 * k), int(190 - 150 * k)))
        z = self.fire["zones"][min(self.round, self.n - 1)]
        zx = bx + (z["center"] - z["width"] / 2) / bar * bw
        ui.fill(zx, by - 2, z["width"] / bar * bw, bh + 4, (233, 196, 106, 170))
        px = bx + (z["center"] - z["perfect"] / 2) / bar * bw
        ui.fill(px, by - 2, z["perfect"] / bar * bw, bh + 4, (255, 246, 200, 230))
        ui.border(bx, by, bw, bh, "#2B2B2B")
        if self.state == "run":
            nx = bx + self.pos() / bar * bw
            ui.fill(nx - 1, by - 6, 2, bh + 12, "#2B2B2B")
            ui.fill(nx - 3, by - 8, 6, 3, "#2B2B2B")

    def draw_ui(self, ui):
        ui.dim(170)
        x, y, w, h = 50, 30, 380, 210
        f = self.fire
        ui.panel(x, y, w, h, T.FIRE_TITLE.format(name=f["name_vi"]))
        ui.text(f["hanzi"], x + 46, y + 40, 18, "#BC4749", kind="han", anchor="center")
        img = sprites.prop("furnace", 0, int(self.t * 6) % 4)
        ui.image(img, x + 46, y + 92, zoom=2.5 + self.flash * 0.3, anchor="center")
        for i in range(self.n):
            col = {"perfect": "#E9C46A", "good": "#6A994E", "miss": "#BC4749"}.get(
                self.hits[i] if i < len(self.hits) else "", "#CFC6B4")
            ui.fill(x + 26 + i * 14, y + 128, 10, 10, col)
            ui.border(x + 26 + i * 14, y + 128, 10, 10, "#2B2B2B")
        rx = x + 96
        if self.state == "result":
            self.draw_result(ui, x, y, w, h)
            return
        if self.state == "send":
            ui.text(T.FIRE_SENDING, rx + 130, y + 100, 9, "#5A5A5A", anchor="center")
            return
        ui.text(T.FIRE_PRESS.format(n=self.round + 1, t=self.n), rx, y + 14, 8, "#BC4749")
        ui.text(T.FIRE_HINT, rx, y + 26, 7, "#5A5A5A", max_w=w - 110)
        self.draw_bar(ui, rx, y + 62, w - 112, 14)
        if self.state == "run":
            if ui.button("fire_press", rx + (w - 112) / 2 - 40, y + 92, 80, 20, "Bấm!", style="primary",
                         key=pygame.K_SPACE) or ui.click_in(rx, y + 50, w - 112, 36):
                self.press()
            return
        # a character of the name, after the press
        ch = f["chars"][self.round]
        hit = self.hits[-1]
        ui.text(T.FIRE_HITS[hit], rx + (w - 112) / 2, y + 90, 9,
                {"perfect": "#C99A3A", "good": "#6A994E", "miss": "#BC4749"}[hit], anchor="center")
        ui.text(ch["c"], rx + 26, y + 136, 26, "#2B2B2B", kind="han", anchor="center")
        if ch["ask"]:
            ui.text(T.FIRE_TYPE, rx + 52, y + 112, 7, "#5A5A5A", max_w=w - 160)
            val = ui.input_box("fire_pinyin", rx + 52, y + 126, 120, 18, placeholder="pinyin", max_len=12)
            if (ui.button("fire_ok", rx + 178, y + 126, 60, 18, T.OK, style="primary") or ui.submitted("fire_pinyin")) \
                    and val.strip():
                self.next_char(val.strip())
        else:
            ui.text(T.FIRE_LEARN.format(c=ch["c"], p=ch["pinyin"], hv=ch["hv"]), rx + 52, y + 120, 8, "#2B2B2B",
                    max_w=w - 160)
            if ui.button("fire_next", rx + 178, y + 150, 60, 16, T.FIRE_NEXT, style="primary", key=pygame.K_RETURN):
                self.next_char(None)

    def draw_result(self, ui, x, y, w, h):
        r = self.result or {}
        rx = x + 96
        if r.get("made"):
            ui.text(T.FIRE_RESULT.format(q=r["quality_vi"], n=r["made"], name=r["pill_name_vi"]), rx, y + 16, 10,
                    "#C99A3A" if r["quality"] == "thuong" else "#2B2B2B", max_w=w - 110)
            if r.get("extra"):
                ui.text(T.FIRE_EXTRA, rx, y + 32, 7, "#6A994E")
        else:
            ui.text(T.FIRE_RESULT_NONE if not r.get("expired") else T.FIRE_RESULT_NONE, rx, y + 16, 9, "#BC4749",
                    max_w=w - 110)
        for i, c in enumerate(r.get("chars", [])):
            cy = y + 52 + i * 22
            ui.text(c["c"], rx + 10, cy + 8, 14, "#2B2B2B", kind="han", anchor="center")
            if c["right"] is None:
                line, col = f"{c['pinyin']} · {c['hv']}", "#5A5A5A"
            elif c["right"]:
                line, col = T.FIRE_PINYIN_RIGHT.format(c="", p=c["pinyin"]).strip(), "#6A994E"
            else:
                line, col = T.FIRE_PINYIN_WRONG.format(c="", p=c["pinyin"]).strip(), "#BC4749"
            ui.text(line, rx + 26, cy + 8, 8, col, kind="han", anchor="midleft")
            hit = (r.get("hits") or ["", "", ""])[i]
            ui.text(T.FIRE_HITS.get(hit, ""), x + w - 16, cy + 8, 7, "#8E877A", anchor="midright")
        if ui.button("fire_done", x + w / 2 - 40, y + h - 22, 80, 16, T.FIRE_DONE, style="primary",
                     key=pygame.K_RETURN) or ui.key(pygame.K_ESCAPE):
            self.close()
