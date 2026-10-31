"""Tàng Thư Các (spec 9.3): every book with its % and milestone rewards, a search over all of
them, the Bách Thảo Phổ (one page per plant) and the Sổ Lỗi (spec 8.3)."""
from __future__ import annotations

import urllib.parse

import pygame

from .. import strings_vi as T
from ..art import build as B
from ..art.palette import RARITY_COLORS
from .base import Scene

BOOK_ICON = {"plant": "草", "monster": "妖", "bee": "蜂", "fish": "鱼", "discovery": "字", "treasure": "宝",
             "pet": "兽"}


def portrait_frame(ui, frame: str | None, x: float, y: float, w: float, h: float) -> None:
    """The avatar frame chosen in the Tàng Thư Các, drawn around a portrait box."""
    col = T.FRAME_COLORS.get(frame or "")
    if col:
        ui.border(x - 1, y - 1, w + 2, h + 2, col, 2)
        ui.fill(x - 2, y - 2, 4, 4, col)
        ui.fill(x + w - 2, y + h - 2, 4, 4, col)


def title_after(ui, title: str | None, rect, y: float) -> None:
    """The chosen title, small and golden, right after the character's name."""
    if title:
        ui.text(f"«{title}»", rect.right + 2, y, 6, "#B8862E")


class LibraryScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.results: dict | None = None
        self.last_q = ""
        self.typed_at = 0.0
        self.t = 0.0
        game.ui.set_value("lib_search", "")
        self.reload()

    def reload(self) -> None:
        self.api.get("/library", lambda d: setattr(self, "data", d), self.game.api_error)

    def search(self, q: str) -> None:
        self.last_q = q
        if not q.strip():
            self.results = None
            return
        self.api.get("/library/search?q=" + urllib.parse.quote(q), lambda r: setattr(self, "results", r),
                     self.game.api_error)

    def claim(self, book: str, pct: int) -> None:
        def ok(r):
            self.data = r
            c = r["claimed"]
            name = next(b["name_vi"] for b in r["books"] if b["id"] == c["book"])
            self.game.toast(T.LIBRARY_GOT.format(p=c["pct"], book=name, r=c["reward_vi"]), "#C99A3A")
            self.game.audio.play("coin")
            self.game.refresh_me()
        self.api.post("/library/claim", {"book": book, "pct": pct}, ok, self.game.api_error)

    def open_book(self, book: str) -> None:
        g = self.game
        if book == "plant":
            g.push(HerbBookScene(g))
        elif book == "monster":
            from .rpg import MonsterBookScene
            g.push(MonsterBookScene(g))
        elif book == "bee":
            g.open_bee_book()
        elif book == "fish":
            from .fishing import FishBookScene
            g.push(FishBookScene(g))
        elif book == "treasure":
            g.push(TreasureBookScene(g))
        elif book == "pet":
            from .pets import PetBookScene
            g.push(PetBookScene(g))
        else:
            from .book import BookScene
            g.push(BookScene(g))

    def on_resume(self) -> None:
        self.reload()

    def update(self, dt, top):
        self.t += dt
        q = self.game.ui.value("lib_search")
        if q != self.last_q and self.t - self.typed_at > 0.4:
            self.search(q)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 20, 14, 440, 244
        ui.panel(x, y, w, h, T.LIBRARY_TITLE)
        ui.text(T.LIBRARY_HINT, x + 12, y + 10, 7, "#5A5A5A")
        before = ui.value("lib_search")
        q = ui.input_box("lib_search", x + w - 182, y + 8, 170, 14, T.LIBRARY_SEARCH, max_len=24, kind="han")
        if q != before:
            self.typed_at = self.t
        if ui.submitted("lib_search"):
            self.search(q)
        d = self.data
        if q.strip():
            if ui.button("lib_search_clear", x + w - 200, y + 8, 16, 14, "×", size=8):
                ui.set_value("lib_search", "")
                self.search("")
            elif self.results is not None:
                self.draw_results(ui, x + 12, y + 28, w - 24)
        elif d:
            rh = 23      # seven books since stage 8 (Linh Thú Phổ)
            for i, b in enumerate(d["books"]):
                ry = y + 28 + i * rh
                bw = w - 24
                ui.fill(x + 12, ry, bw, rh - 2, "#FFFDF7")
                ui.border(x + 12, ry, bw, rh - 2)
                ui.text(BOOK_ICON.get(b["id"], "?"), x + 26, ry + 10, 12, "#BC4749", kind="han", anchor="center")
                ui.text(b["name_vi"], x + 42, ry, 9)
                ui.text(T.LIBRARY_BOOK_ROW.format(f=b["found"], t=b["total"], p=b["pct"]), x + 42, ry + 11, 7, "#5A5A5A")
                ui.progress(x + 110, ry + 13, 60, 4, b["pct"] / 100, "#6A994E")
                mx = x + 176
                for m in b["milestones"]:
                    wid = f"lib_claim_{b['id']}_{m['pct']}"
                    label = f"{m['pct']}%"
                    if m["claimed"]:
                        ui.button(wid, mx, ry + 4, 30, 13, label + "✓", size=6, enabled=False,
                                  tooltip=f"{T.LIBRARY_CLAIMED}: {m['reward_vi']}")
                    elif ui.button(wid, mx, ry + 4, 30, 13, label, size=6, style="gold" if m["ready"] else "normal",
                                   enabled=m["ready"], tooltip=m["reward_vi"]):
                        self.claim(b["id"], m["pct"])
                    mx += 32
                if ui.button(f"lib_open_{b['id']}", x + 12 + bw - 46, ry + 4, 40, 13, T.LIBRARY_OPEN, size=7,
                             style="primary"):
                    self.open_book(b["id"])
                    return
            self.draw_badges(ui, x + 12, y + 28 + len(d["books"]) * rh + 2)
        if d and ui.button("lib_shop", x + w - 236, y + h - 22, 70, 15, T.LIBRARY_SHOP):
            self.game.push(LibraryShopScene(self.game, self))
        if ui.button("lib_mistakes", x + w - 160, y + h - 22, 70, 15, T.LIBRARY_MISTAKES):
            self.game.push(MistakesScene(self.game))
        if ui.button("lib_close", x + w - 84, y + h - 22, 70, 15, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def wear(self, title: str | None = None, frame: str | None = None) -> None:
        body = {k: v for k, v in (("title", title), ("frame", frame)) if v is not None}

        def ok(r):
            self.data = r
            self.game.state.me["title"], self.game.state.me["frame"] = r.get("title"), r.get("frame")
        self.api.post("/library/wear", body, ok, self.game.api_error)

    def draw_badges(self, ui, x, y):
        """Titles and avatar frames earned from milestones: pick the one to show."""
        d = self.data
        if d["titles"]:
            ui.text(T.LIBRARY_TITLE_PICK, x, y + 3, 7, "#8B5A2B")
            bx = x + 50
            for i, t in enumerate([""] + d["titles"]):
                label = t or T.LIBRARY_NONE
                bw = ui.text_size(label, 6)[0] + 8
                if ui.button(f"lib_title_{i}", bx, y, bw, 11, label, size=6, selected=(d.get("title") or "") == t):
                    self.wear(title=t)
                bx += bw + 2
            y += 13
        if d["frames"]:
            ui.text(T.LIBRARY_FRAME_PICK, x, y + 3, 7, "#8B5A2B")
            bx = x + 50
            for i, f in enumerate([{"id": "", "name_vi": T.LIBRARY_NONE}] + d["frames"]):
                bw = ui.text_size(f["name_vi"], 6)[0] + 8
                if ui.button(f"lib_frame_{i}", bx, y, bw, 11, f["name_vi"], size=6,
                             selected=(d.get("frame") or "") == f["id"]):
                    self.wear(frame=f["id"])
                bx += bw + 2

    def draw_results(self, ui, x, y, w):
        r = self.results
        ui.fill(x, y, w, 186, "#FFFDF7")
        ui.border(x, y, w, 186, "#8B5A2B")
        if r.get("q") != self.last_q.strip():
            return
        if not r["results"]:
            ui.text(T.LIBRARY_SEARCH_NONE, x + 6, y + 6, 7, "#8E877A", max_w=w - 12)
            return
        for i, it in enumerate(r["results"][:14]):
            ry = y + 4 + i * 12.5
            ui.text(BOOK_ICON.get(it["book"], "?"), x + 8, ry + 5, 7, "#BC4749", kind="han", anchor="center")
            ui.text(f"{it['title']}  {it['sub']}", x + 16, ry, 7, kind="han", max_w=w - 20)
            ui.widgets[f"lib_res_{i}"] = ui.rect(x, ry, w, 12)
            if ui.click_in(x, ry, w, 12):
                if it["book"] == "plant":
                    self.game.push(HerbBookScene(self.game, focus=it["id"]))
                else:
                    self.open_book(it["book"])
        extra = r.get("more", 0) + max(0, len(r["results"]) - 14)
        if extra:
            ui.text(T.LIBRARY_SEARCH_MORE.format(n=extra), x + 6, y + 177, 6, "#8E877A")


class HerbBookScene(Scene):
    """Bách Thảo Phổ: the grid of every plant; a page for the chosen one."""
    PER = 24

    def __init__(self, game, focus: str | None = None):
        super().__init__(game)
        self.data: dict | None = None
        self.page = 0
        self.sel: str | None = focus

        def ok(d):
            self.data = d
            ids = [p["word_id"] for p in d["plants"]]
            if self.sel in ids:
                self.page = ids.index(self.sel) // self.PER
            elif self.sel is None:
                self.sel = next((p["word_id"] for p in d["plants"] if p["found"]), None)
        self.api.get("/codex/plant", ok, game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 16, 14, 448, 244
        ui.panel(x, y, w, h, T.HERB_BOOK_TITLE)
        d = self.data
        if d:
            ui.text(T.HERB_FOUND.format(f=d["found"], t=d["total"]), x + 12, y + 10, 7, "#BC4749")
            plants = d["plants"]
            pages = max(1, (len(plants) + self.PER - 1) // self.PER)
            for i, p in enumerate(plants[self.page * self.PER:(self.page + 1) * self.PER]):
                cx = x + 12 + (i % 6) * 34
                cy = y + 24 + (i // 6) * 44
                self.draw_cell(ui, p, cx, cy)
            if ui.button("herb_prev", x + 12, y + h - 22, 30, 14, "<", enabled=self.page > 0, key=pygame.K_LEFT):
                self.page -= 1
            ui.text(T.HERB_PAGE.format(n=self.page + 1, t=pages), x + 72, y + h - 15, 7, anchor="center")
            if ui.button("herb_next", x + 102, y + h - 22, 30, 14, ">", enabled=self.page < pages - 1,
                         key=pygame.K_RIGHT):
                self.page += 1
            sel = next((p for p in plants if p["word_id"] == self.sel), None)
            if sel and sel["found"]:
                self.draw_page(ui, sel, x + 222, y + 22, w - 234)
        if ui.button("herb_close", x + w - 84, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def draw_cell(self, ui, p, cx, cy):
        ui.fill(cx, cy, 32, 40, "#FFFDF7" if p["found"] else "#E3D5BA")
        if p["found"]:
            col = T.WORD_RARITY_COLORS.get(p["rarity"], "#2B2B2B")
            ui.border(cx, cy, 32, 40, col, 2 if self.sel == p["word_id"] else 1)
            ui.text(p["hanzi"], cx + 16, cy + 15, 13 if len(p["hanzi"]) <= 2 else 6, kind="han", anchor="center")
            ui.text(p["pinyin"], cx + 16, cy + 32, 5, "#5A5A5A", kind="han", anchor="center")
            ui.widgets[f"herb_{p['word_id']}"] = ui.rect(cx, cy, 32, 40)
            if ui.click_in(cx, cy, 32, 40):
                self.sel = p["word_id"]
        elif p["hidden"]:      # an empty frame: not even a shape until discovered
            for k in range(0, 32, 4):
                ui.fill(cx + k, cy, 2, 1, "#B8AE9C")
                ui.fill(cx + k, cy + 39, 2, 1, "#B8AE9C")
            for k in range(0, 40, 4):
                ui.fill(cx, cy + k, 1, 2, "#B8AE9C")
                ui.fill(cx + 31, cy + k, 1, 2, "#B8AE9C")
            if ui.hover(cx, cy, 32, 40):
                ui.set_tooltip(T.HERB_HIDDEN)
        else:                  # a dark silhouette with "?"
            ui.border(cx, cy, 32, 40, "#B8AE9C")
            ui.image(_shadow(p["word_id"]), cx + 16, cy + 18, 1.0, anchor="center")
            ui.text("?", cx + 16, cy + 33, 8, "#8E877A", anchor="center")
            if ui.hover(cx, cy, 32, 40):
                ui.set_tooltip(T.HERB_UNKNOWN)

    def draw_page(self, ui, p, x, y, w):
        ui.fill(x, y, w, 196, "#FFFDF7")
        ui.border(x, y, w, 196, "#8B5A2B")
        r = p["rarity"] if p["rarity"] in RARITY_COLORS else "common"
        for s in range(1, 6):
            ui.image(B.plant(s, r, p["word_id"]), x + 8 + (s - 1) * 24, y + 4, 1.0)
        ui.text(p["hanzi"], x + 30, y + 48, 26 if len(p["hanzi"]) <= 2 else 12, kind="han", anchor="center")
        ui.text(p["pinyin"], x + 62, y + 34, 11, "#BC4749", kind="han")
        ui.text(p["meaning_vi"], x + 62, y + 50, 8, max_w=w - 70)
        if p.get("has_audio") and self.game.audio.has_word(p["word_id"]):
            if ui.button("herb_listen", x + w - 40, y + 32, 34, 12, T.HERB_LISTEN, size=6):
                self.game.audio.play_word(p["word_id"])
        yy = y + 70
        ui.text(T.HERB_ROLE.format(r=p["role_vi"]), x + 6, yy, 8, T.TD_ROLE_COLORS.get(p["role"], "#2B2B2B"))
        yy = ui.text(p["role_desc_vi"], x + 6, yy + 11, 6, "#5A5A5A", max_w=w - 12).bottom + 1
        from .td import stats_text
        if p.get("skill"):
            yy = ui.text(p["skill"].get("desc_vi", ""), x + 6, yy, 6, "#8E5AC8", max_w=w - 12).bottom + 1
        else:
            yy = ui.text(stats_text(p["role"], p["role_stats"], p.get("power", 1.0)), x + 6, yy, 6, max_w=w - 12).bottom + 1
        yy = ui.text(T.HERB_MASTERY.format(m=p["mastery"], c=p["times_correct"], w=p["times_wrong"]), x + 6, yy + 1, 7,
                     "#6A994E").bottom + 1
        if p.get("example"):
            ex = p["example"]
            zh = "".join(t["t"] for t in ex.get("tokens", []))
            yy = ui.text(T.HERB_EXAMPLE.format(zh=zh), x + 6, yy, 7, kind="han", max_w=w - 12).bottom
            if ex.get("vi"):
                yy = ui.text(ex["vi"], x + 6, yy, 6, "#5A5A5A", max_w=w - 12).bottom + 1
        parts = []
        for c in p.get("chars") or []:
            part = f"{c['char']} = {' + '.join(c.get('components') or [])}" if c.get("components") else ""
            if part and part not in parts and len(c.get("components") or []) > 1:
                parts.append(part)
        if parts:
            yy = ui.text(T.HERB_PARTS.format(p="; ".join(parts)), x + 6, yy, 7, kind="han", max_w=w - 12).bottom + 1
        ui.text(f"{T.MASTER}: {p['quip_vi']}", x + 6, max(yy + 1, y + 196 - 30), 6, "#8B5A2B", max_w=w - 12)


_SHADOWS: dict = {}


def _shadow(key: str) -> pygame.Surface:
    if key not in _SHADOWS:
        s = B.plant(4, "common", key).copy()
        s.fill((60, 54, 44, 255), special_flags=pygame.BLEND_RGBA_MIN)
        _SHADOWS[key] = s
    return _SHADOWS[key]


class MistakesScene(Scene):
    """Sổ Lỗi: words answered wrong most often, each with a practice question."""

    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.reload()

    def reload(self) -> None:
        self.api.get("/library/mistakes", lambda d: setattr(self, "data", d), self.game.api_error)

    def practice(self, word_id: str) -> None:
        from .quiz import QuizScene

        def ok(q):
            self.game.push(QuizScene(self.game, q, on_result=lambda r: self.reload()))
        self.api.post("/quiz/practice", {"word_id": word_id}, ok, self.game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 50, 20, 380, 232
        ui.panel(x, y, w, h, T.MISTAKES_TITLE)
        ui.text(T.MISTAKES_HINT, x + w / 2, y + 12, 7, "#5A5A5A", anchor="center")
        words = (self.data or {}).get("words")
        if words is not None and not words:
            ui.text(T.MISTAKES_EMPTY, x + w / 2, y + 100, 9, anchor="center")
        for i, wd in enumerate((words or [])[:12]):
            ry = y + 24 + i * 16
            ui.fill(x + 10, ry, w - 20, 14, "#FFFDF7")
            ui.text(wd["hanzi"], x + 26, ry + 7, 10, kind="han", anchor="center")
            ui.text(f"{wd['pinyin']} · {wd['meaning_vi']}", x + 46, ry + 2, 7, kind="han", max_w=170)
            ui.text(T.MISTAKES_ROW.format(w=wd["times_wrong"], c=wd["times_correct"], a=int(wd["accuracy"] * 100)),
                    x + 222, ry + 3, 6, "#BC4749")
            if ui.button(f"mis_{wd['word_id']}", x + w - 56, ry + 1, 44, 12, T.MISTAKES_PRACTICE, size=6):
                self.practice(wd["word_id"])
        if ui.button("mis_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


class LibraryShopScene(Scene):
    """The Thủ Thư's shelf (spec 8.4, 12.3): bí kíp and đan phương can be bought at the Tàng Thư Các."""

    def __init__(self, game, host: LibraryScene):
        super().__init__(game)
        self.host = host
        self.tab = "manual"          # bí kíp, or đan phương (stage 8)

    def buy(self, item_id: str) -> None:
        def ok(r):
            self.host.data = r
            self.game.toast(T.LIBRARY_BOUGHT.format(name=r["name_vi"]), "#6A994E")
            self.game.audio.play("coin")
            self.game.refresh_me()
            self.game.refresh_inv()
        self.api.post("/library/buy", {"item_id": item_id}, ok, self.game.api_error)

    def draw_ui(self, ui):
        ui.dim(160)
        d = self.host.data or {}
        x, y, w, h = 50, 24, 380, 224
        ui.panel(x, y, w, h, T.LIBRARY_SHOP_TITLE)
        for i, (k, label) in enumerate((("manual", T.LIBRARY_SHOP_TAB_MANUALS), ("recipe", T.LIBRARY_SHOP_TAB_RECIPES))):
            if ui.button(f"lib_shop_tab_{k}", x + 10 + i * 76, y + 8, 72, 13, label, size=7, selected=self.tab == k):
                self.tab = k
        hint = T.LIBRARY_SHOP_HINT if self.tab == "manual" else T.LIBRARY_SHOP_HINT_RECIPES
        ui.text(hint, x + 12, y + 24, 7, "#5A5A5A", max_w=w - 24)
        at = d.get("at_desk")
        if not at:
            ui.text(T.LIBRARY_SHOP_FAR, x + 12, y + 44, 7, "#BC4749", max_w=w - 24)
        rows = [it for it in d.get("shop", []) if it.get("kind", "manual") == self.tab]
        for i, it in enumerate(rows[:8]):
            ry = y + 56 + i * 20
            ui.fill(x + 12, ry, w - 24, 18, "#FFFDF7")
            ui.border(x + 12, ry, w - 24, 18)
            ui.text(it["name_vi"], x + 18, ry + 9, 8, anchor="midleft")
            if ui.hover(x + 12, ry, w - 130, 18):
                ui.set_tooltip(it["desc_vi"])
            owned_recipe = self.tab == "recipe" and it["have"] > 0
            note = T.LIBRARY_SHOP_LEARNED if it["learned"] else (
                T.LIBRARY_SHOP_HAVE.format(n=it["have"]) if it["have"] else "")
            if owned_recipe:
                note = T.LIBRARY_SHOP_OWNED
            if note:
                ui.text(note, x + w - 108, ry + 9, 6, "#6A994E", anchor="midright")
            if ui.button(f"lib_buy_{it['item_id']}", x + w - 102, ry + 2, 84, 14,
                         T.LIBRARY_SHOP_BUY.format(p=it["price"]), size=7, style="gold",
                         enabled=bool(at) and not owned_recipe):
                self.buy(it["item_id"])
        if ui.button("lib_shop_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


class TreasureBookScene(Scene):
    """Bảo Vật Phổ: equipment, pills and rods ever owned."""

    def __init__(self, game):
        super().__init__(game)
        self.data: dict | None = None
        self.api.get("/codex/treasure", lambda d: setattr(self, "data", d), game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 30, 20, 420, 232
        ui.panel(x, y, w, h, T.TREASURE_TITLE)
        d = self.data
        if d:
            ui.text(T.TREASURE_FOUND.format(f=d["found"], t=d["total"]), x + 12, y + 10, 7, "#BC4749")
            for i, e in enumerate(d["entries"][:24]):
                cx = x + 12 + (i % 4) * 100
                cy = y + 24 + (i // 4) * 30
                ui.fill(cx, cy, 96, 27, "#FFFDF7" if e["found"] else "#E3D5BA")
                ui.border(cx, cy, 96, 27, "#2B2B2B" if e["found"] else "#B8AE9C")
                ui.text(e["kind_vi"], cx + 4, cy + 2, 6, "#8E877A")
                ui.text(e["name_vi"] if e["found"] else "? ? ?", cx + 4, cy + 12, 8,
                        "#2B2B2B" if e["found"] else "#8E877A", max_w=90)
                ui.widgets[f"tr_{e['id']}"] = ui.rect(cx, cy, 96, 27)
                if ui.hover(cx, cy, 96, 27):
                    ui.set_tooltip(e.get("desc_vi") if e["found"] else T.TREASURE_UNKNOWN)
        if ui.button("tr_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
