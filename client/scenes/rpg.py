"""Stage 4 screens: the combat question card, death, cultivation (Tu Vi, stats, Pháp Chữ,
Thiên Kiếp), forge, quests, Yêu Quái Phổ and meditation."""
from __future__ import annotations

import math
import random

import pygame

from .. import strings_vi as T
from ..engine import sprites
from .base import Scene
from .quiz import QuizScene


def fmt_wait(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else f"{s} giây"


# ------------------------------------------------------------------ combat question
class CombatQuizScene(QuizScene):
    """The Vấn Đạo card (spec 8.1): lower part of the screen, the fight stays visible; the
    answer and its explanation show for 2 seconds, then the fight goes on."""
    compact = True
    modal = False
    toast_y = 70
    draws_world = False

    def __init__(self, game, question: dict, monster_id: str, on_result=None):
        super().__init__(game, question, on_result=on_result, show_timer=True)
        self.monster_id = monster_id
        self.auto_close_after = 2.0

    def submit(self, answer: dict):
        super().submit(answer)

    def draw_result_extra(self, ui, bx, by, bw, bh):
        c = (self.result or {}).get("combat") or {}
        if c.get("shield_broken"):
            txt = f"{T.SHIELD_BROKEN} {T.NGO_DAO} -{c.get('damage', 0)}" + (" (chí mạng!)" if c.get("crit") else "")
            ui.text(txt, bx + bw - 10, by + 8, 9, "#6A994E", anchor="topright")
        elif c.get("mac_kich"):
            ui.text(f"{T.MAC_KICH} -{c['mac_kich']}", bx + bw - 10, by + 8, 9, "#BC4749", anchor="topright")
        if self.result and self.result.get("correct") and self.result_t < 0.05:
            self.auto_close_after = 1.2  # a right answer gets back to the fight a little faster

    def draw_ui(self, ui):
        super().draw_ui(ui)
        x, y, w, h = self.panel_rect()
        if not self.result:
            ui.text(T.HOI_THE, x + w - 12, y + 8, 7, "#6A994E", anchor="topright")


class DeathOverlay(Scene):
    modal = False

    def __init__(self, game, seconds: float):
        super().__init__(game)
        self.left = seconds

    def update(self, dt, top):
        self.left -= dt
        if self.left <= -0.5:
            self.close()

    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (30, 10, 12, 150))
        ui.text(T.DEAD_TITLE, 240, 110, 20, "#F08A8C", anchor="center")
        ui.text(T.DEAD_TEXT, 240, 134, 8, "#F4EBD9", anchor="midtop", max_w=300)


# ------------------------------------------------------------------ cultivation
class CharacterScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.inv = None
        self.reload()

    def reload(self):
        self.game.refresh_cult()
        self.api.get("/inventory", lambda r: setattr(self, "inv", r), self.game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 30, 18, 420, 238
        ui.panel(x, y, w, h, T.CHAR_TITLE)
        c = self.game.state.cult
        ch = self.game.state.character
        if not c:
            ui.text("...", 240, 120, 10, anchor="center")
        else:
            look = sprites.character(ch.get("appearance", {}))[("down", 0)]
            ui.fill(x + 12, y + 14, 52, 60, "#E3D5BA")
            ui.image(look, x + 38, y + 44, zoom=2, anchor="center")
            from .library import portrait_frame, title_after
            me = self.game.state.me
            portrait_frame(ui, me.get("frame"), x + 12, y + 14, 52, 60)
            title_after(ui, me.get("title"), ui.text(ch.get("display_name", ""), x + 72, y + 14, 10), y + 17)
            ui.text(c["label"], x + 72, y + 28, 9, "#6A994E")
            need = c.get("need") or 1
            ui.progress(x + 72, y + 42, 150, 6, c["xp"] / need, "#E9C46A")
            ui.text(f"{T.TU_VI} {c['xp']}/{c.get('need') or '—'}", x + 72, y + 50, 7, "#5A5A5A")
            st = c.get("stats", {})
            sy = y + 80
            for i, k in enumerate(["max_hp", "max_qi", "atk", "def", "crit", "ink_res"]):
                ui.text(f"{T.STATS_VI[k]}: {st.get(k, 0)}", x + 14 + (i % 2) * 104, sy + (i // 2) * 12, 8)
            # breakthrough
            by = y + 124
            if c.get("pill"):
                if c.get("xp", 0) >= (c.get("need") or 1 << 30):
                    ui.text(T.XP_FULL, x + 14, by, 8, "#C99A3A")
                    if c.get("tribulation_ready_in"):
                        ui.text(T.TRIB_WAIT.format(t=fmt_wait(c["tribulation_ready_in"])), x + 14, by + 12, 8,
                                "#BC4749")
                    elif not c.get("has_pill"):
                        ui.text(T.NEED_PILL.format(pill=c.get("pill_name")), x + 14, by + 12, 8, "#BC4749")
                if ui.button("ch_trib", x + 14, by + 26, 130, 16, T.BREAKTHROUGH, style="gold",
                             enabled=bool(c.get("can_tribulation"))):
                    self.close()
                    self.game.push(TribulationScene(self.game))
                    return
            # equipped gear
            gx = x + 232
            ui.text(T.BAG_GEAR, gx, y + 14, 9)
            eq = {e["equipped"]: e for e in (self.inv or {}).get("equipment", []) if e.get("equipped")}
            for i, (slot, name) in enumerate(T.GEAR_SLOTS.items()):
                e = eq.get(slot)
                ry = y + 28 + i * 14
                ui.text(name, gx, ry, 7, "#8E877A")
                if e:
                    lvl = f" +{e['enhance']}" if e["enhance"] else ""
                    ui.text(e["name_vi"] + lvl, gx + 48, ry, 8, e["color"])
                else:
                    ui.text(T.NO_WEAPON if slot == "weapon" else "—", gx + 48, ry, 8, "#B8AE9C")
            # skills
            ui.text(T.SKILLS_TITLE, gx, y + 120, 9)
            for i, sk in enumerate(c.get("skills", [])):
                ry = y + 134 + i * 16
                ui.fill(gx, ry, 14, 14, "#2B2B2B" if sk["learned"] else "#CFC6B4")
                ui.text(sk["hanzi"], gx + 7, ry + 7, 9, "#E9C46A" if sk["learned"] else "#8E877A", kind="han",
                        anchor="center")
                ui.text(sk["name_vi"], gx + 18, ry, 7)
                info = T.SKILL_LEVEL.format(lv=sk["level"], m=sk["mastery"]) if sk["learned"] else T.SKILL_LOCKED
                ui.text(info, gx + 18, ry + 7, 6, "#5A5A5A")
                if ui.hover(gx, ry, 180, 14):
                    ui.set_tooltip(f"{sk['name_vi']} ({sk['hanzi']})\n{sk['desc_vi']}\nLinh Lực {sk['qi']} · hồi "
                                   f"{sk['cooldown']} giây")
            # stage 8: the worn Linh Thú and the pill buffs running now
            pet = c.get("pet")
            py_ = y + 172
            if pet:
                ui.image(sprites.pet(pet["pet_type"], int(ui.time * 3) % 2), x + 24, py_ + 8, zoom=1.5, anchor="center")
                ui.text(f"{pet['name_vi']} {pet['hanzi']} · {T.PETS_LEVEL.format(l=pet['level'], m=pet['max_level'])}",
                        x + 38, py_ + 2, 7, "#2B2B2B", kind="han")
                if ui.hover(x + 12, py_, 200, 16):
                    ui.set_tooltip(pet["skill_vi"])
            if ui.button("ch_pets", x + 14, py_ + 18, 70, 14, T.HUD_PETS + " (O)", size=7):
                self.game.open_pets()
                return
            if c.get("buffs"):
                ui.text(T.ALCHEMY_BUFFS.format(b=", ".join(f"{b['name_vi']} {b['seconds_left'] // 60 + 1}'"
                                                            for b in c["buffs"])), x + 90, py_ + 21, 7, "#6A994E")
        if ui.button("ch_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


class TribulationScene(Scene):
    """Thiên Kiếp (spec 7.3): 20 questions, lightning for every wrong answer."""

    def __init__(self, game):
        super().__init__(game)
        self.state = "intro"
        self.progress = (0, 20, 0)
        self.result = None
        self.flash = 0.0
        self.bolts: list[tuple[float, list]] = []
        self.t = 0.0
        self.busy = False

    def update(self, dt, top):
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 2)
        self.bolts = [(life - dt, pts) for life, pts in self.bolts if life - dt > 0]

    def strike(self):
        self.flash = 1.0
        self.game.audio.play("wrong")
        pts, x, y = [], 240 + random.uniform(-60, 60), 0
        while y < 200:
            pts.append((x, y))
            x += random.uniform(-14, 14)
            y += random.uniform(12, 24)
        self.bolts.append((0.5, pts))

    def start(self):
        self.busy = True

        def ok(r):
            self.busy = False
            if r.get("question"):
                self.state = "running"
                self.ask(r["question"])
            elif r.get("result"):
                self.finish(r["result"])

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/cultivation/breakthrough/start", {}, ok, err)

    def ask(self, q: dict):
        self.progress = (q.get("number", 1), q.get("total", 20), q.get("correct_so_far", 0))
        self.game.push(QuizScene(self.game, q, on_result=self.on_result, show_timer=True))

    def on_result(self, res: dict):
        if not res.get("correct"):
            self.strike()
        if res.get("tribulation"):
            self.finish(res["tribulation"])
        elif res.get("next"):
            self.ask(res["next"])

    def finish(self, result: dict):
        self.state, self.result = "done", result
        self.game.refresh_cult()
        self.game.refresh_me()
        if result.get("passed"):
            self.game.audio.play("discover")

    def draw_ui(self, ui):
        ui.fill(0, 0, 480, 270, (16, 16, 30, 220))
        for life, pts in self.bolts:
            win = [ui.d.to_window(px, py) for px, py in pts]
            if len(win) > 1:
                pygame.draw.lines(ui.win, pygame.Color("#FFF6B0"), False, win, max(2, ui.s * 2))
        if self.flash:
            ui.fill(0, 0, 480, 270, (255, 255, 230, int(140 * self.flash)))
        x, y, w, h = 80, 30, 320, 210
        ui.panel(x, y, w, h, T.TRIB_TITLE)
        c = self.game.state.cult or {}
        if self.state == "intro":
            ui.text(T.TRIB_INTRO.format(n=20, t=30, p=80), x + 16, y + 20, 8, max_w=w - 32)
            ui.text(f"{c.get('label', '')} → {T.REALMS.get(c.get('next_realm') or '', c.get('next_realm') or '')}", x + w / 2, y + 110, 10, "#6A994E",
                    anchor="center")
            if ui.button("trib_go", x + w / 2 - 50, y + 140, 100, 18, T.TRIB_START, style="gold",
                         enabled=not self.busy, key=pygame.K_RETURN):
                self.start()
        elif self.state == "running":
            n, total, correct = self.progress
            ui.text(T.TRIB_PROGRESS.format(n=n, total=total, c=correct), x + w / 2, y + 60, 12, anchor="center")
            ui.progress(x + 30, y + 80, w - 60, 6, (n - 1) / max(1, total), "#E9C46A")
        else:
            r = self.result or {}
            if r.get("passed"):
                ui.text(T.TRIB_PASS.format(label=r.get("label", "")), x + w / 2, y + 60, 11, "#6A994E",
                        anchor="midtop", max_w=w - 30)
                ui.text(T.TRIB_REWARD.format(n=r.get("jade", 0)), x + w / 2, y + 100, 10, "#C99A3A", anchor="center")
            else:
                ui.text(T.TRIB_FAIL.format(c=r.get("correct", 0), total=r.get("total", 20), xp=r.get("xp_lost", 0)),
                        x + w / 2, y + 60, 10, "#BC4749", anchor="midtop", max_w=w - 30)
        if self.state != "running" and ui.button("trib_close", x + w / 2 - 35, y + h - 22, 70, 15, T.CLOSE,
                                                 key=pygame.K_ESCAPE):
            self.close()


class MeditateScene(Scene):
    """Bàn đả tọa: one review question at a time, Tu Vi only for right answers (spec 7.3)."""

    def __init__(self, game):
        super().__init__(game)
        self.wait = 0.0
        self.busy = False
        self.last = None

    def update(self, dt, top):
        self.wait = max(0.0, self.wait - dt)

    def ask(self):
        self.busy = True

        def ok(q):
            self.busy = False
            self.game.push(QuizScene(self.game, q, on_result=self.done, show_timer=True))

        def err(e):
            self.busy = False
            if e.code == "meditate_wait":
                digits = "".join(ch for ch in e.message_vi if ch.isdigit())
                self.wait = float(digits or 10)
            self.game.api_error(e)
        self.api.post("/cultivation/meditate", {}, ok, err)

    def done(self, res: dict):
        self.last = res
        self.wait = float(res.get("next_in", 0))

    def draw_ui(self, ui):
        ui.dim(120)
        x, y, w, h = 120, 60, 240, 150
        ui.panel(x, y, w, h, T.MEDITATE_TITLE)
        ui.text(T.MEDITATE_TEXT.format(xp=15), x + 14, y + 16, 8, max_w=w - 28)
        if self.last and self.last.get("xp"):
            ui.text(T.LOOT_XP.format(n=self.last["xp"]["gained"]), x + w / 2, y + 66, 10, "#C99A3A", anchor="center")
        label = T.MEDITATE_GO if self.wait <= 0 else T.MEDITATE_WAIT.format(t=fmt_wait(math.ceil(self.wait)))
        if ui.button("med_go", x + 40, y + h - 46, w - 80, 16, label, style="green",
                     enabled=self.wait <= 0 and not self.busy, key=pygame.K_RETURN):
            self.ask()
        if ui.button("med_close", x + w / 2 - 35, y + h - 22, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


# ------------------------------------------------------------------ forge
class ForgeScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.inv = None
        self.busy = False
        self.scroll = 0
        self.reload()

    def reload(self):
        self.api.get("/inventory", lambda r: setattr(self, "inv", r), self.game.api_error)

    def enhance(self, e):
        self.busy = True

        def ok(r):
            self.busy = False
            if r["success"]:
                self.game.toast(T.FORGE_OK.format(name=r["item"]["name_vi"], lv=r["item"]["enhance"]), "#6A994E")
                self.game.audio.play("discover")
            else:
                self.game.toast(T.FORGE_FAIL, "#BC4749")
                self.game.audio.play("wrong")
            self.game.state.me["spirit_stones"] = r.get("spirit_stones", self.game.state.me.get("spirit_stones"))
            self.reload()

        def err(er):
            self.busy = False
            self.game.api_error(er)
        self.api.post("/forge/enhance", {"instance_id": e["id"]}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 24, 400, 226
        ui.panel(x, y, w, h, T.FORGE_TITLE)
        ui.text(T.FORGE_HINT, x + w / 2, y + 12, 7, "#5A5A5A", anchor="center")
        if ui.button("forge_rods", x + w - 76, y + 18, 64, 13, T.ROD_FORGE, size=7, style="gold"):
            from .fishing import RodForgeScene   # stage 6: rods are upgraded here (spec 11.2)
            self.game.push(RodForgeScene(self.game))
            return
        mats = {i["item_id"]: i["qty"] for i in (self.inv or {}).get("items", [])}
        ui.text(f"Mực Tinh: {mats.get('muc_tinh', 0)}", x + 14, y + 22, 8, "#4A7CC8")
        eqs = (self.inv or {}).get("equipment")
        if eqs is None:
            ui.text("...", 240, 120, 10, anchor="center")
        elif not eqs:
            ui.text(T.FORGE_EMPTY, x + 14, y + 40, 8, max_w=w - 28)
        else:
            per = 8
            if ui.inp.wheel:
                self.scroll = max(0, min(len(eqs) - per, self.scroll - ui.inp.wheel))
            for i, e in enumerate(eqs[self.scroll:self.scroll + per]):
                ry = y + 34 + i * 20
                ui.fill(x + 10, ry, w - 20, 18, "#FFFDF7" if i % 2 else "#F8F1E3")
                ui.fill(x + 10, ry, 3, 18, e["color"])
                lvl = f" +{e['enhance']}" if e["enhance"] else ""
                ui.text(e["name_vi"] + lvl, x + 18, ry + 1, 8, e["color"])
                carved = "".join(c["hanzi"] for c in e.get("inscriptions", []))   # Khắc Văn (stage 8)
                if carved:
                    ui.text(carved, x + 22 + ui.text_size(e["name_vi"] + lvl, 8)[0], ry + 5, 7, "#C99A3A", kind="han",
                            anchor="midleft")
                stats = " ".join(f"{T.STATS_VI.get(k, k)} {v}" for k, v in e["stats"].items())
                ui.text(f"{e['slot_vi']} · {e['rarity_vi']} · {stats}", x + 18, ry + 11, 6, "#5A5A5A")
                if ui.button(f"forge_ins_{e['id']}", x + w - 134, ry + 2, 36, 14, T.INSCRIBE_BUTTON, size=7,
                             tooltip=f"{len(e.get('inscriptions', []))}/{e.get('inscribe_slots', 1)}"):
                    from .inscribe import InscribeScene
                    self.game.push(InscribeScene(self.game, e["id"], on_close=self.reload))
                    return
                n = e.get("next_enhance")
                if n:
                    ui.text(T.FORGE_COST.format(p=n["success_pct"], s=n["stones"], q=n["material_qty"],
                                                m=n["material_name"]), x + w - 138, ry + 9, 6, "#5A5A5A",
                            anchor="midright")
                    if ui.button(f"forge_{e['id']}", x + w - 92, ry + 2, 78, 14, T.FORGE_GO, size=7, style="gold",
                                 enabled=not self.busy):
                        self.enhance(e)
                else:
                    ui.text(T.FORGE_MAX, x + w - 20, ry + 9, 7, "#C99A3A", anchor="midright")
        if ui.button("forge_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


# ------------------------------------------------------------------ quests
class QuestScene(Scene):
    """Story chains and, from stage 8, the daily tasks (two tabs, the list scrolls)."""

    def __init__(self, game, tab: str = "main"):
        super().__init__(game)
        self.busy = False
        self.tab = tab
        self.scroll = 0
        game.refresh_quests()

    def claim(self, q):
        self.busy = True

        def ok(r):
            self.busy = False
            rw = r.get("rewards", {})
            parts = []
            for it in rw.get("items", []):
                parts.append(T.LOOT_ITEM.format(name=it["name_vi"], qty=it["qty"]))
            for e in rw.get("equipment", []):
                parts.append(e["name_vi"])
            self.game.toast(", ".join(parts) or "Đã nhận thưởng", "#6A994E")
            if rw.get("bonus"):
                self.game.toast(T.QUEST_BONUS.format(r=", ".join(rw["bonus"]["rewards_vi"])), "#C99A3A")
            self.game.audio.play("coin")
            self.game.on_xp(rw.get("xp"))
            self.game.refresh_me()
            self.game.refresh_quests()
            self.game.refresh_cult()
            self.game.refresh_inv()

        def err(e):
            self.busy = False
            self.game.api_error(e)
        self.api.post("/quests/claim", {"quest_id": q["id"]}, ok, err)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 50, 20, 380, 232
        ui.panel(x, y, w, h, T.QUESTS_TITLE)
        data = self.game.state.quests or {}
        for i, (k, label) in enumerate((("main", T.QUESTS_TAB_MAIN), ("daily", T.QUESTS_TAB_DAILY))):
            n_done = sum(1 for q in data.get("quests" if k == "main" else "daily", []) if q["state"] == "done")
            text = f"{label} ({n_done})" if n_done else label
            if ui.button(f"quest_tab_{k}", x + 10 + i * 84, y + 8, 80, 13, text, size=7, selected=self.tab == k):
                self.tab, self.scroll = k, 0
        qs = data.get("quests" if self.tab == "main" else "daily")
        top = y + 26
        if self.tab == "daily" and data.get("daily_bonus"):
            b = data["daily_bonus"]
            ui.text(T.QUESTS_DAILY_BONUS_GOT if b["claimed"] else
                    T.QUESTS_DAILY_BONUS.format(r=", ".join(b["rewards_vi"])), x + w - 12, y + 10, 7, "#C99A3A",
                    anchor="topright")
        if qs is None:
            ui.text("...", 240, 120, 10, anchor="center")
        elif not qs:
            ui.text(T.QUESTS_NONE, x + 14, top + 4, 8)
        rows = qs or []
        per, rh = 4, 46
        if ui.inp.wheel:
            self.scroll = max(0, min(max(0, len(rows) - per), self.scroll - ui.inp.wheel))
        for i, q in enumerate(rows[self.scroll:self.scroll + per]):
            ry = top + i * (rh + 2)
            ui.fill(x + 10, ry, w - 20, rh, "#FFFDF7" if q["state"] != "claimed" else "#EDE4D2")
            ui.border(x + 10, ry, w - 20, rh, "#C9B48A")
            ui.text(f"{q['chain_vi']} · {q['title_vi']}", x + 18, ry + 3, 8)
            ui.text(q["desc_vi"], x + 18, ry + 14, 6, "#5A5A5A", max_w=w - 120)
            o = q["objective"]
            ui.text(T.QUEST_PROGRESS.format(n=q["progress"], c=o["count"]), x + w - 18, ry + 4, 8,
                    "#6A994E" if q["state"] in ("done", "claimed") else "#BC4749", anchor="topright")
            ui.text(T.QUEST_REWARDS.format(r=", ".join(q["rewards_vi"])), x + 18, ry + 36, 6, "#C99A3A",
                    max_w=w - 120)
            if q["state"] == "done" and ui.button(f"qclaim_{q['id']}", x + w - 96, ry + 26, 80, 15, T.QUEST_CLAIM,
                                                   style="gold", enabled=not self.busy):
                self.claim(q)
            elif q["state"] == "claimed":
                ui.text(T.LIBRARY_CLAIMED, x + w - 20, ry + 32, 7, "#8E877A", anchor="midright")
        if len(rows) > per:
            ui.text(f"{self.scroll + 1}-{min(len(rows), self.scroll + per)}/{len(rows)}", x + 14, y + h - 14, 7,
                    "#8E877A")
        if ui.button("quest_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()


# ------------------------------------------------------------------ Yêu Quái Phổ
class MonsterBookScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.data = None
        self.page = 0
        self.api.get("/codex/monster", lambda r: setattr(self, "data", r), game.api_error)

    def draw_ui(self, ui):
        ui.dim()
        x, y, w, h = 40, 24, 400, 226
        ui.panel(x, y, w, h, T.MONSTER_BOOK)
        if ui.button("mb_to_disc", x + 12, y + 10, 90, 13, T.DISCOVERY_BOOK, size=7):
            from .book import BookScene
            self.close()
            self.game.push(BookScene(self.game))
            return
        if self.data:
            ui.text(f"{self.data['found']}/{self.data['total']}", x + w - 14, y + 12, 8, "#BC4749", anchor="topright")
            per = 3
            pages = max(1, (len(self.data["entries"]) + per - 1) // per)
            self.page = min(self.page, pages - 1)
            if pages > 1:
                if ui.button("mb_prev", x + 12, y + h - 20, 30, 14, "<", enabled=self.page > 0):
                    self.page -= 1
                ui.text(f"{self.page + 1}/{pages}", x + 58, y + h - 13, 7, anchor="center")
                if ui.button("mb_next", x + 74, y + h - 20, 30, 14, ">", enabled=self.page < pages - 1):
                    self.page += 1
            for i, e in enumerate(self.data["entries"][self.page * per:(self.page + 1) * per]):
                ry = y + 28 + i * 58
                ui.fill(x + 10, ry, w - 20, 54, "#FFFDF7")
                ui.border(x + 10, ry, w - 20, 54)
                if e.get("td"):   # Mặc Quái of the Thủ Vườn levels
                    from .td import monster_frames
                    frames = monster_frames(e["id"][3:])
                else:
                    frames = sprites.monster(e["sprite"])
                img = frames[int(ui.time * 2) % len(frames)]
                if not e["found"]:
                    sil = img.copy()
                    sil.fill((40, 40, 40, 255), special_flags=pygame.BLEND_RGBA_MIN)
                    ui.image(sil, x + 36, ry + 27, zoom=2, anchor="center")
                    ui.text("? ? ?  · " + T.MB_UNKNOWN, x + 70, ry + 20, 9, "#B8AE9C")
                    continue
                ui.image(img, x + 36, ry + 27, zoom=2, anchor="center")
                rank = f" · {e['rank_vi']}" if e.get("rank_vi") and e["rank"] != "normal" else ""
                ui.text(e["name_vi"] + rank, x + 70, ry + 4, 9)
                ui.text(T.MB_KILLS.format(n=e["kills"]), x + w - 18, ry + 4, 8, "#6A994E", anchor="topright")
                if e["qtypes_vi"]:
                    ui.text(T.MB_QTYPES.format(q=", ".join(e["qtypes_vi"])), x + 70, ry + 16, 7, "#5A5A5A",
                            max_w=w - 90)
                ui.text(T.MB_WEAK.format(w=e["weakness_vi"]), x + 70, ry + 27, 7, "#5A5A5A", max_w=w - 90)
                if e["drops_vi"]:
                    ui.text(T.MB_DROPS.format(d=", ".join(e["drops_vi"])), x + 70, ry + 37, 6, "#8E877A",
                            max_w=w - 90, line_gap=1.0)
        if ui.button("mb_close", x + w / 2 - 35, y + h - 20, 70, 14, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()
