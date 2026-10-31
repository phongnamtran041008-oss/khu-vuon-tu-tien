"""Linh Phong Sào — the spirit-bee hive (spec 10): a hexagon comb where every bee has a
cell. Pick a bee to see it, feed it, give it a role (ở tổ / thụ phấn / hộ vệ) or release
it; drag a bee (or pick it, then click an empty cell) to move it. Eggs hatch here.
Ong Phổ, the bee codex, is in this file too. All numbers come from the server."""
from __future__ import annotations

import math

import pygame

from .. import strings_vi as T
from ..engine import sprites
from ..ui.dialog import DialogScene
from .base import MessageBox, Scene

HEX_W, HEX_H = 32, 28          # pointy-top cell, base pixels
COL_STEP, ROW_STEP = 34, 25


def hex_points(cx: float, cy: float, w: float = HEX_W, h: float = HEX_H) -> list[tuple[float, float]]:
    hw, hh = w / 2, h / 2
    return [(cx, cy - hh), (cx + hw, cy - hh / 2), (cx + hw, cy + hh / 2), (cx, cy + hh),
            (cx - hw, cy + hh / 2), (cx - hw, cy - hh / 2)]


def draw_hex(ui, cx, cy, fill, edge="#8B5A2B", width=1, w=HEX_W, h=HEX_H) -> None:
    pts = [ui.d.to_window(x, y) for x, y in hex_points(cx, cy, w, h)]
    c = pygame.Color(fill) if isinstance(fill, str) else fill
    if len(c) == 4 and c.a < 255:
        surf = pygame.Surface(ui.win.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(surf, c, pts)
        ui.win.blit(surf, (0, 0))
    else:
        pygame.draw.polygon(ui.win, c, pts)
    pygame.draw.polygon(ui.win, pygame.Color(edge), pts, max(1, width * ui.s))


def bee_img(look: dict | None, t: float, seed: int = 0, left: bool = False) -> pygame.Surface:
    return sprites.bee(look, int(t * 12 + seed) % 2, left)


class HiveScene(Scene):
    def __init__(self, game, on_close=None):
        super().__init__(game)
        self.on_close = on_close
        self.hive: dict | None = None
        self.sel: int | None = None          # selected bee id
        self.drag: int | None = None         # bee id being dragged
        self._was_down = False
        self.busy = False
        self.reload()

    def on_enter(self):
        if not self.game.session.data.get("hive_intro_seen"):
            self.game.session.save(hive_intro_seen=True)
            self.game.push(DialogScene(self.game, T.HIVE_INTRO))

    # ------------------------------------------------------------ data
    def reload(self, then=None):
        def ok(h):
            self.set_hive(h)
            if then:
                then()
        self.api.get("/hive", ok, self.game.api_error)

    def set_hive(self, h: dict) -> None:
        self.hive = h
        self.game.state.hive = h
        if self.sel is not None and not any(b["id"] == self.sel for b in h["bees"]):
            self.sel = None
        if self.sel is None and h["bees"]:
            self.sel = h["bees"][0]["id"]

    def post(self, path: str, body: dict | None = None, ok=None) -> None:
        if self.busy:
            return
        self.busy = True

        def done(r):
            self.busy = False
            if isinstance(r, dict) and "bees" in r and "open_cells" in r:
                self.set_hive(r)
            if ok:
                ok(r)
            else:
                self.reload()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post(path, body or {}, done, err)

    def bee(self, bid: int | None) -> dict | None:
        if self.hive is None or bid is None:
            return None
        return next((b for b in self.hive["bees"] if b["id"] == bid), None)

    def bee_at(self, cell: int) -> dict | None:
        return next((b for b in (self.hive or {}).get("bees", []) if b["slot"] == cell), None)

    # ------------------------------------------------------------ actions
    def collect(self):
        def ok(r):
            self.game.toast(T.HIVE_COLLECTED.format(h=r["honey"], w=r["wax"]), "#C99A3A")
            self.game.audio.play("coin")
            self.game.refresh_inv()
            self.reload()
        self.post("/hive/collect", ok=ok)

    def hatch(self, item_id: str):
        def ok(r):
            self.game.push(HatchScene(self.game, r))
            self.sel = r["bee"]["id"]
            self.game.refresh_quests()
            for m in r.get("milestones", []):
                self.game.toast(T.BEE_MILESTONE_GOT.format(n=m["species"], r=_reward_vi(m)), "#C99A3A")
            self.reload()
        self.post("/hive/hatch", {"item_id": item_id}, ok)

    def move(self, bid: int, cell: int):
        self.post("/bees/move", {"bee_id": bid, "slot": cell}, ok=lambda r: None)

    def set_role(self, bid: int, role: str):
        def ok(r):
            self.game.audio.play("click")
            self.game.refresh_quests()
            ab = self._abode()
            if ab is not None:
                ab.refresh_garden()
        self.post("/bees/role", {"bee_id": bid, "role": role}, ok)

    def feed(self, bid: int, food: str):
        b = self.bee(bid)
        name = b["name_vi"] if b else ""

        def ok(r):
            if r.get("favorite"):
                self.game.toast(T.BEE_FED_FAV.format(xp=r["xp_gained"], b=r["bond_gained"]), "#BC4749")
                self.game.audio.play("discover")
            else:
                self.game.toast(T.BEE_FED.format(xp=r["xp_gained"]), "#6A994E")
            if r.get("favorite_discovered"):
                self.game.message(T.BEE_FAV_FOUND.format(name=name, food=r.get("favorite_vi", "")), T.BEE_BOOK)
            if r.get("levels_gained"):
                self.game.toast(T.BEE_LEVEL_UP.format(name=name, lv=r["level"]), "#C99A3A")
            self.game.refresh_quests()
            self.reload()
        self.post("/bees/feed", {"bee_id": bid, "food": food}, ok)

    def release(self, b: dict):
        wax = {"pham": 1, "linh": 2, "huyen": 4, "dia": 8, "thien": 15}.get(b["rarity"], 1)

        def go():
            self.post("/bees/release", {"bee_id": b["id"]},
                      lambda r: (self.game.toast(T.BEE_RELEASED.format(w=r["wax"]), "#8B5A2B"), self.reload()))
        self.game.push(MessageBox(self.game, T.BEE_RELEASE_CONFIRM.format(name=b["name_vi"], lv=b["level"], wax=wax),
                                  T.BEE_RELEASE, ok=T.BEE_RELEASE, cancel=T.CANCEL, on_ok=go))

    def upgrade(self):
        def ok(r):
            self.game.toast(T.HIVE_UPGRADED.format(lv=r["level"]), "#C99A3A")
            self.game.audio.play("discover")
            self.game.refresh_inv()
        self.post("/hive/upgrade", ok=ok)

    def _abode(self):
        from .abode import AbodeScene
        return next((s for s in self.game.scenes if isinstance(s, AbodeScene)), None)

    def close(self):
        super().close()
        ab = self._abode()
        if ab is not None:
            ab.refresh_garden()
        if self.on_close:
            self.on_close()

    # ------------------------------------------------------------ layout
    def cell_center(self, idx: int) -> tuple[float, float]:
        cols = self.hive["columns"]
        c, r = idx % cols, idx // cols
        return 32 + c * COL_STEP + (COL_STEP / 2 if r % 2 else 0), 70 + r * ROW_STEP

    def cell_under(self, mx: float, my: float) -> int | None:
        if self.hive is None:
            return None
        best, bd = None, 15.0
        for i in range(self.hive["columns"] * self.hive["rows"]):
            cx, cy = self.cell_center(i)
            d = math.hypot(cx - mx, cy - my)
            if d < bd:
                best, bd = i, d
        return best

    # ------------------------------------------------------------ drawing
    def draw_ui(self, ui):
        ui.dim(170)
        x, y, w, h = 8, 8, 464, 254
        ui.panel(x, y, w, h)
        ui.fill(x, y, w, 15, "#C99A3A")
        title = T.HIVE_TITLE + " 蜂巢"
        ui.text(title, x + 8, y + 7.5, 9, "#2B2B2B", anchor="midleft")
        info_x = x + 16 + ui.text_size(title, 9)[0]
        if ui.button("hv_close", x + w - 52, y + 2, 48, 11, T.CLOSE, key=pygame.K_ESCAPE, size=7):
            self.close()
            return
        hv = self.hive
        if hv is None:
            ui.text("...", 240, 130, 10, anchor="center")
            return
        if ui.button("hv_book", x + w - 104, y + 2, 48, 11, T.BEE_BOOK, size=7):
            self.game.push(BeeBookScene(self.game))
        ui.text(T.HIVE_LEVEL.format(lv=hv["level"], mx=hv["level_max"]) + " · " +
                T.HIVE_CELLS.format(n=hv["cells"], mx=hv["cells_max"]) + " · " +
                T.HIVE_GUARDS.format(n=hv["guard_used"], mx=hv["guard_slots"]) + " · " +
                T.HIVE_POLLINATORS.format(n=hv["pollinate_used"], mx=hv["pollinate_max"]),
                info_x, y + 7.5, 7, "#3A342C", anchor="midleft")
        self.draw_honey(ui, x + 6, y + 19)
        self.draw_comb(ui)
        self.draw_bottom(ui, x + 6, 200)
        self.draw_details(ui, 252, 28, 214, 228)

    def draw_honey(self, ui, x, y):
        hv = self.hive
        cap = hv["capacity"]
        ui.progress(x, y + 2, 110, 7, hv["honey"] / max(1, cap), "#E9C46A", back="#E3D5BA")
        ui.text(T.HIVE_HONEY.format(h=int(hv["honey"]), cap=cap), x + 2, y + 5.5, 6, "#2B2B2B", anchor="midleft")
        ui.text(T.HIVE_RATE.format(r=f"{hv['honey_per_hour']:.1f}") + " · " + T.HIVE_WAX.format(w=int(hv["wax"])),
                x + 114, y + 5.5, 6, "#5A5A5A", anchor="midleft")
        if ui.button("hv_collect", x + 196, y, 42, 11, T.HIVE_COLLECT, size=7, style="gold",
                     enabled=(hv["honey"] >= 1 or hv["wax"] >= 1) and not self.busy):
            self.collect()

    def draw_comb(self, ui):
        hv = self.hive
        opened = set(hv["open_cells"])
        mx, my = ui.inp.mouse
        down = ui.inp.mouse_down and ui.enabled
        hover_cell = self.cell_under(mx, my)
        if down and not self._was_down and hover_cell is not None and self.bee_at(hover_cell):
            self.drag = self.bee_at(hover_cell)["id"]            # pick a bee up
        self._was_down = down
        t = ui.time
        for i in range(hv["columns"] * hv["rows"]):
            cx, cy = self.cell_center(i)
            b = self.bee_at(i)
            if i not in opened:
                draw_hex(ui, cx, cy, "#5A4A36", "#3A342C")
                continue
            fill = "#F2D58A" if b is None else "#E9C46A"
            if b is not None and b["id"] == self.sel:
                fill = "#FFF0C0"
            draw_hex(ui, cx, cy, fill, "#8B5A2B", 2 if (b and b["id"] == self.sel) else 1)
            ui.widgets[f"hv_cell_{i}"] = ui.rect(cx - 12, cy - 11, 24, 22)
            if b is None:
                continue
            if self.drag == b["id"] and down:
                continue
            bob = math.sin(t * 3 + i) * 1.2
            ui.image(bee_img(b["look"], t, i), cx, cy - 2 + bob, zoom=2, anchor="center")
            role_col = {"hive": "#C99A3A", "pollinate": "#E89AB0", "guard": "#BC4749"}[b["role"]]
            ui.fill(cx - 13, cy + 5, 9, 7, role_col)
            ui.text({"hive": "巢", "pollinate": "花", "guard": "卫"}[b["role"]], cx - 8.5, cy + 8.5, 5, "#FFFFFF",
                    kind="han", anchor="center")
            ui.text(str(b["level"]), cx + 10, cy + 8, 6, "#2B2B2B", anchor="center")
            ui.fill(cx + 4, cy - 12, 5, 3, b["rarity_color"])
        # unlock-next marker on the next cell to open
        nxt = hv.get("next_cell")
        if nxt is not None and len(hv["open_cells"]) < hv["columns"] * hv["rows"]:
            from_order = self._order_next(opened)
            if from_order is not None:
                cx, cy = self.cell_center(from_order)
                ui.text("+", cx, cy, 12, "#F4EBD9" if nxt["ok"] else "#8E877A", anchor="center")
        # drag ghost and drop
        if self.drag is not None:
            b = self.bee(self.drag)
            if b is not None and down:
                ui.image(bee_img(b["look"], t), mx, my, zoom=2, anchor="center")
        if ui.inp.clicked and ui.enabled and hover_cell is not None and ui.hover(14, 50, 228, 140):
            ui.consume_click()
            target = self.bee_at(hover_cell)
            if self.drag is not None:
                src = self.bee(self.drag)
                self.drag = None
                if src is not None and src["slot"] != hover_cell and hover_cell in opened:
                    self.move(src["id"], hover_cell)
                    self.sel = src["id"]
                    return
            if target is not None:
                self.sel = target["id"]
            elif hover_cell in opened and self.sel is not None:
                self.move(self.sel, hover_cell)          # pick, then click an empty cell
        elif ui.inp.clicked:
            self.drag = None
        if hover_cell is not None and ui.hover(14, 50, 228, 140) and not down:
            b = self.bee_at(hover_cell)
            if b is not None:
                ui.set_tooltip(f"{b['name_vi']} {b['hanzi']} · {T.BEE_LEVEL.format(lv=b['level'])} · {b['role_vi']}")
            elif hover_cell not in opened:
                ui.set_tooltip(T.HIVE_LOCKED_CELL)
        if not hv["bees"]:
            ui.text(T.HIVE_NO_BEES, 128, 186, 7, "#5A5A5A", anchor="center")

    def _order_next(self, opened: set) -> int | None:
        """The cell the server opens next: the closest one to the comb's middle not open yet."""
        cols, rows = self.hive["columns"], self.hive["rows"]
        n = cols * rows

        def centre(i):
            c, r = i % cols, i // cols
            return c + (0.5 if r % 2 else 0.0), r * 0.866
        mx_ = sum(centre(i)[0] for i in range(n)) / n
        my_ = sum(centre(i)[1] for i in range(n)) / n
        rest = [i for i in range(n) if i not in opened]
        if not rest:
            return None
        return min(rest, key=lambda i: (round(math.hypot(centre(i)[0] - mx_, centre(i)[1] - my_), 3), i))

    def draw_bottom(self, ui, x, y):
        hv = self.hive
        ui.text(T.HIVE_EGGS, x, y + 4, 7, "#5A5A5A", anchor="midleft")
        ex = x + 42
        if not hv["eggs"]:
            ui.text("—", ex, y + 4, 7, "#8E877A", anchor="midleft")
        for e in hv["eggs"][:5]:
            col = {"pham": "#7D7468", "linh": "#6A994E", "huyen": "#4A7CC8", "dia": "#8E5AC8",
                   "thien": "#C99A3A"}[e["rarity"]]
            ui.image(sprites.egg(col)[0], ex + 6, y + 6, zoom=1, anchor="center")
            if ui.button(f"hv_hatch_{e['item_id']}", ex + 13, y, 26, 11, f"{T.HIVE_HATCH}×{e['qty']}", size=6,
                         style="green", enabled=not self.busy, tooltip=e["name_vi"]):
                self.hatch(e["item_id"])
            ex += 44
        nxt = hv.get("next_cell")
        by = y + 16
        if nxt is not None:
            tip = (T.HIVE_UNLOCK_TIP.format(n=nxt["cell"], s=nxt["spirit_stones"]) if nxt["ok"] else
                   T.HIVE_UNLOCK_NEED.format(n=nxt["cell"], k=nxt["species_required"], f=hv["species_found"]))
            if ui.button("hv_unlock", x, by, 74, 13, T.HIVE_UNLOCK.format(s=nxt["spirit_stones"]), size=7,
                         enabled=nxt["ok"] and not self.busy, tooltip=tip):
                self.post("/hive/unlock_cell", ok=lambda r: self.game.refresh_me())
        nl = hv.get("next_level")
        if nl is not None:
            items = ", ".join(f"{i['qty']} {i['name_vi']} ({i['have']})" for i in nl["items"])
            tip = T.HIVE_UPGRADE_COST.format(lv=nl["level"], s=nl["spirit_stones"], items=items, cap=nl["capacity"],
                                             m=nl["honey_mult"], deco=nl["decoration_vi"])
            have = all(i["have"] >= i["qty"] for i in nl["items"])
            if ui.button("hv_upgrade", x + 78, by, 74, 13, T.HIVE_UPGRADE, size=7, enabled=have and not self.busy,
                         tooltip=tip):
                self.upgrade()
        else:
            ui.text(T.HIVE_MAX, x + 80, by + 6.5, 7, "#8E877A", anchor="midleft")
        dx = x + 156
        for d in hv.get("decorations", []):
            ui.image(sprites.decoration(d["id"], int(ui.time * 3) % 4), dx + 5, by + 6, zoom=0.6, anchor="center")
            if ui.button(f"hv_deco_{d['id']}", dx + 10, by, 18, 13, "✓" if d["on"] else "·", size=7,
                         selected=d["on"], tooltip=d["name_vi"]):
                self.post("/hive/decoration", {"decoration": d["id"], "on": not d["on"]}, ok=lambda r: None)
            dx += 30

    def draw_details(self, ui, x, y, w, h):
        ui.fill(x, y, w, h, "#FBF5E8")
        ui.border(x, y, w, h, "#C9B48A")
        b = self.bee(self.sel)
        if b is None:
            ui.text(T.HIVE_PICK, x + 8, y + 8, 7, "#5A5A5A", max_w=w - 16)
            return
        t = ui.time
        ui.fill(x + 6, y + 6, 40, 40, "#F2D58A")
        ui.border(x + 6, y + 6, 40, 40, b["rarity_color"], 2)
        ui.image(bee_img(b["look"], t), x + 26, y + 26 + math.sin(t * 3) * 1.5, zoom=4, anchor="center")
        ui.text(b["name_vi"], x + 52, y + 8, 9)
        ui.text(f"{b['hanzi']}  {b['pinyin']}", x + 52, y + 20, 9, "#BC4749", kind="han")
        ui.text(f"{b['rarity_vi']} · hệ {b['element_vi']}" + ("" if b.get("real_word") else "  " + T.BEE_GAME_NAME),
                x + 52, y + 33, 7, b["rarity_color"])
        yy = y + 50
        ui.text(T.BEE_LEVEL.format(lv=b["level"]), x + 6, yy, 8)
        nxt = b.get("xp_next")
        ui.progress(x + 40, yy + 1, w - 48, 8, (b["xp"] / nxt) if nxt else 1.0, "#8DB360", back="#E3D5BA")
        ui.text(T.BEE_XP.format(x=b["xp"], n=nxt) if nxt else T.BEE_XP_MAX, x + 43, yy + 5, 6, "#2B2B2B",
                anchor="midleft")
        yy += 11
        ui.progress(x + 40, yy + 1, w - 48, 8, b["bond"] / max(1, b["bond_max"]), "#E89AB0", back="#E3D5BA")
        ui.text(T.BEE_BOND.format(b=b["bond"], mx=b["bond_max"]), x + 43, yy + 5, 6, "#2B2B2B", anchor="midleft")
        yy += 13
        g = b["guard"]
        yy = ui.text(T.BEE_STATS.format(h=f"{b['honey_per_hour']:.1f}", p=f"{b['pollen_per_hour']:.0f}",
                                        hp=g["hp"], atk=g["atk"]), x + 6, yy, 7, max_w=w - 12).bottom + 2
        yy = ui.text(b["skill_vi"], x + 6, yy, 7, "#4A7CC8", max_w=w - 12).bottom + 2
        if b["resonance_pct"]:
            yy = ui.text(T.BEE_RESONANCE.format(p=b["resonance_pct"]), x + 6, yy, 7, b["element_color"]).bottom + 1
        wd = b["word"]
        r = ui.text(T.BEE_WORD.format(hz=wd["hanzi"], py=wd["pinyin"], vi=wd["vi"], m=b["word_mastery"]), x + 6, yy, 7,
                    "#5A5A5A", max_w=w - 12)
        if ui.hover(x + 6, yy, w - 12, r.height):
            ui.set_tooltip(T.BEE_WORD_TIP)
        yy = r.bottom + 2
        fav = (T.BEE_FAV.format(f=b["favorite"]) if b["favorite_known"]
               else T.BEE_FAV_HINT.format(h=b["favorite_hint_vi"]))
        ui.text(fav, x + 6, yy, 7, "#8B5A2B", max_w=w - 12)
        # roles
        ry = y + h - 46
        hv = self.hive
        for i, role in enumerate(("hive", "pollinate", "guard")):
            enabled = not self.busy
            tip = T.BEE_ROLE_TIP[role]
            if role == "guard" and b["role"] != "guard" and hv["guard_used"] >= hv["guard_slots"]:
                enabled = False
                tip += f" ({T.HIVE_GUARDS.format(n=hv['guard_used'], mx=hv['guard_slots'])})"
            if role == "pollinate" and b["role"] != "pollinate" and hv["pollinate_used"] >= hv["pollinate_max"]:
                enabled = False
            if ui.button(f"hv_role_{role}", x + 6 + i * 69, ry, 65, 14, T.BEE_ROLE[role], size=7,
                         selected=b["role"] == role, enabled=enabled or b["role"] == role, tooltip=tip):
                if b["role"] != role:
                    self.set_role(b["id"], role)
        if ui.button("hv_feed", x + 6, ry + 20, 100, 16, T.BEE_FEED, style="green", enabled=not self.busy):
            self.game.push(FoodPicker(self.game, self, b))
        if ui.button("hv_release", x + w - 72, ry + 20, 66, 16, T.BEE_RELEASE, size=7, enabled=not self.busy):
            self.release(b)


def _reward_vi(m: dict) -> str:
    parts = []
    if m.get("spirit_stones"):
        parts.append(f"{m['spirit_stones']} Linh Thạch")
    if m.get("immortal_jade"):
        parts.append(f"{m['immortal_jade']} Tiên Ngọc")
    for it in m.get("items", []):
        parts.append(f"{it['name_vi']} ×{it['qty']}")
    return ", ".join(parts)


class FoodPicker(Scene):
    def __init__(self, game, hive: HiveScene, bee: dict):
        super().__init__(game)
        self.hive, self.b = hive, bee
        self.scroll = 0

    def draw_ui(self, ui):
        ui.dim(120)
        foods = (self.hive.hive or {}).get("foods", [])
        x, y, w = 140, 40, 200
        h = 40 + min(8, max(1, len(foods))) * 16
        ui.panel(x, y, w, h)
        ui.text(T.BEE_FEED_TITLE.format(name=self.b["name_vi"]), x + 8, y + 6, 8)
        if not foods:
            ui.text(T.BEE_NO_FOOD, x + 8, y + 20, 7, "#5A5A5A", max_w=w - 16)
        if ui.inp.wheel and ui.enabled:
            self.scroll = max(0, min(max(0, len(foods) - 8), self.scroll - ui.inp.wheel))
        for i, f in enumerate(foods[self.scroll:self.scroll + 8]):
            fy = y + 20 + i * 16
            label = f"{f['name_vi']}  ×{f['qty']}"
            if ui.button(f"food_{self.scroll + i}", x + 8, fy, w - 16, 14, label, size=7,
                         kind="han" if f.get("hanzi") else "ui"):
                self.close()
                self.hive.feed(self.b["id"], f["food"])
                return
        if ui.button("food_close", x + w / 2 - 30, y + h - 18, 60, 13, T.CLOSE, size=7, key=pygame.K_ESCAPE):
            self.close()


class HatchScene(Scene):
    """The egg shakes, cracks and a bee flies out (like the seed gacha)."""

    def __init__(self, game, result: dict):
        super().__init__(game)
        self.r = result
        self.t = 0.0

    def update(self, dt, top):
        prev = self.t
        self.t += dt
        if prev < 0.9 <= self.t:
            self.game.audio.play("crack")
        if prev < 1.3 <= self.t:
            self.game.audio.play("reveal" if self.r["bee"]["rarity"] in ("huyen", "dia", "thien") else "coin")

    def draw_ui(self, ui):
        ui.dim(190)
        b = self.r["bee"]
        col = b["rarity_color"]
        frames = sprites.egg(col)
        t = self.t
        cx, cy = 240, 110
        if t < 0.9:
            ui.image(frames[0], cx + math.sin(t * 40) * (1 + t * 2), cy, zoom=5, anchor="center")
        elif t < 1.3:
            ui.image(frames[1], cx, cy, zoom=5, anchor="center")
        else:
            k = min(1.0, (t - 1.3) / 0.5)
            glow = pygame.Surface((int(120 * ui.s), int(120 * ui.s)), pygame.SRCALPHA)
            c = pygame.Color(col)
            for i in range(6, 0, -1):
                pygame.draw.circle(glow, (c.r, c.g, c.b, int(30 * k)), glow.get_rect().center, int(60 * ui.s * i / 6))
            wx, wy = ui.d.to_window(cx, cy)
            ui.win.blit(glow, (wx - glow.get_width() // 2, wy - glow.get_height() // 2))
            ui.image(frames[2], cx, cy + 14, zoom=4, anchor="center")
            ui.image(bee_img(b["look"], t), cx + math.sin(t * 2) * 10 * k, cy - 20 * k + math.sin(t * 5) * 2,
                     zoom=5, anchor="center")
            if k >= 1:
                ui.text(T.HIVE_HATCHED.format(name=b["name_vi"], hanzi=b["hanzi"]), cx, cy + 50, 11, "#F4EBD9",
                        anchor="center")
                ui.text(f"{b['pinyin']} · {b['rarity_vi']} · hệ {b['element_vi']}", cx, cy + 64, 8, col,
                        anchor="center")
                if self.r.get("new_species"):
                    ui.text(T.HIVE_NEW_SPECIES, cx, cy + 76, 8, "#E9C46A", anchor="center")
                ui.text(b["desc_vi"], cx, cy + 88, 7, "#E3D5BA", anchor="midtop", max_w=300)
        if t > 1.9:
            if ui.button("hatch_ok", cx - 35, 240, 70, 15, T.OK, style="primary", key=pygame.K_RETURN) or \
                    ui.key(pygame.K_ESCAPE):
                self.close()
        elif ui.consume_click():
            self.t = max(self.t, 1.85)


class BeeBookScene(Scene):
    """Ong Phổ (spec 10.1, 9.3): every species, found or not, with favourites once known."""

    def __init__(self, game):
        super().__init__(game)
        self.book: dict | None = None
        self.sel: str | None = None
        self.api.get("/codex/bee", self._got, self.game.api_error)

    def _got(self, b):
        self.book = b
        found = [e for e in b["entries"] if e["found"]]
        if found and self.sel is None:
            self.sel = found[0]["id"]

    def draw_ui(self, ui):
        ui.dim(170)
        x, y, w, h = 14, 10, 452, 250
        ui.panel(x, y, w, h)
        ui.fill(x, y, w, 15, "#6A994E")
        ui.text(T.BEE_BOOK + "  蜂谱", x + 8, y + 7.5, 9, "#FFFFFF", anchor="midleft")
        if ui.button("bb_close", x + w - 52, y + 2, 48, 11, T.CLOSE, key=pygame.K_ESCAPE, size=7):
            self.close()
            return
        bk = self.book
        if bk is None:
            ui.text("...", 240, 130, 10, anchor="center")
            return
        ui.text(T.BEE_BOOK_FOUND.format(f=bk["found"], t=bk["total"]), x + 120, y + 7.5, 8, "#FFFFFF",
                anchor="midleft")
        t = ui.time
        for i, e in enumerate(bk["entries"]):
            cx = x + 10 + (i % 6) * 40
            cy = y + 22 + (i // 6) * 50
            sel = e["id"] == self.sel
            ui.fill(cx, cy, 36, 46, "#FFF6DC" if sel else "#F4EBD9")
            ui.border(cx, cy, 36, 46, e["rarity_color"], 2 if sel else 1)
            ui.widgets[f"bb_{e['id']}"] = ui.rect(cx, cy, 36, 46)
            if e["found"]:
                ui.image(bee_img(e["look"], t, i), cx + 18, cy + 16, zoom=3, anchor="center")
                ui.text(e["hanzi"], cx + 18, cy + 37, 8, "#2B2B2B", kind="han", anchor="center")
            else:
                ui.text("?", cx + 18, cy + 18, 16, "#C9B48A", anchor="center")
                ui.text(e["rarity_vi"], cx + 18, cy + 38, 6, e["rarity_color"], anchor="center")
            if ui.click_in(cx, cy, 36, 46):
                self.sel = e["id"]
        # milestones
        my = y + 182
        for j, m in enumerate(bk.get("milestones", [])):
            mx = x + 10 + (j % 3) * 80
            row = my + (j // 3) * 22
            col = "#6A994E" if m["claimed"] else "#8E877A"
            ui.fill(mx, row, 76, 19, "#FFFDF7")
            ui.border(mx, row, 76, 19, col)
            ui.text(f"{m['species']} loài" + (" ✓" if m["claimed"] else ""), mx + 3, row + 1, 7, col)
            ui.text(m["reward_vi"], mx + 3, row + 10, 6, "#5A5A5A", max_w=72)
        # details
        dx, dy, dw, dh = x + 256, y + 22, w - 266, h - 30
        ui.fill(dx, dy, dw, dh, "#FBF5E8")
        ui.border(dx, dy, dw, dh, "#C9B48A")
        e = next((v for v in bk["entries"] if v["id"] == self.sel), None)
        if e is None or not e["found"]:
            ui.text(T.BEE_BOOK_UNKNOWN, dx + 8, dy + 8, 8, "#8E877A")
            return
        ui.image(bee_img(e["look"], t), dx + 24, dy + 22, zoom=5, anchor="center")
        ui.text(e["name_vi"], dx + 48, dy + 6, 9)
        ui.text(f"{e['hanzi']}  {e['pinyin']}", dx + 48, dy + 18, 9, "#BC4749", kind="han")
        ui.text(f"{e['rarity_vi']} · hệ {e['element_vi']}", dx + 48, dy + 31, 7, e["rarity_color"])
        yy = dy + 46
        word = e["word"]
        yy = ui.text(f"{word['hanzi']} {word['pinyin']}: {word['vi']}" + (
            "  · " + T.BEE_REAL_WORD.format(hz=e["hanzi"]) if e.get("real_word") else "  " + T.BEE_GAME_NAME),
            dx + 6, yy, 7, "#5A5A5A", max_w=dw - 12, kind="ui").bottom + 3
        yy = ui.text(e["desc_vi"], dx + 6, yy, 7, max_w=dw - 12).bottom + 3
        yy = ui.text(e["skill_vi"], dx + 6, yy, 7, "#4A7CC8", max_w=dw - 12).bottom + 3
        g = e["guard"]
        yy = ui.text(T.BEE_BOOK_STATS.format(h=e["honey"], p=e["pollen"], hp=g["hp"], atk=g["atk"]), dx + 6, yy, 7,
                     "#5A5A5A", max_w=dw - 12).bottom + 3
        fav = T.BEE_FAV.format(f=e["favorite"]) if e["favorite_known"] else T.BEE_FAV_HINT.format(h=e["favorite_hint_vi"])
        yy = ui.text(fav, dx + 6, yy, 7, "#8B5A2B", max_w=dw - 12).bottom + 3
        ui.text(T.BEE_BOOK_HATCHED.format(n=e["hatched"], lv=e["best_level"], o=e["owned"]), dx + 6, yy, 7, "#5A5A5A",
                max_w=dw - 12)
