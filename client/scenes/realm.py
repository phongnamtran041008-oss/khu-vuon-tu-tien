"""Tổ đội and bí cảnh on the client (stage 9, spec 14, 15.3).

- PartyScene (key Y): members with their health, invite by name, leave, kick, promote.
- RealmGateScene: the Cổng Bí Cảnh in Trúc Lâm Thôn (or a Khe Nứt Mực rift in the wild):
  realms, opening hours, entries left today, enter with the party or join the queue, the puzzle
  guide, and the forge that turns Mảnh Bảo Vật into the Mặc Ảnh set.
- RealmView: lives inside the WorldScene while it shows the bi_canh map. It keeps what the
  server said about the run (room, puzzle, this player's own part of it), draws the puzzle
  props, the darkness of the maze, the room banner, the puzzle card and the result.
Everything is decided by the server; the client only shows it and sends intents (`ract`).
"""
from __future__ import annotations

import math

import pygame

from .. import strings_vi as T
from ..engine import sprites
from .base import Scene

ROOM_ORDER = ("compose", "sentence", "tone", "mirror", "maze")


def fmt_time(secs: float) -> str:
    secs = max(0, int(secs))
    return T.REALM_TIME.format(m=secs // 60, s=secs % 60)


def fmt_wait(secs: float) -> str:
    secs = max(0, int(secs))
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h} giờ {m} phút" if h else f"{max(1, m)} phút"


# ------------------------------------------------------------------ the party
class PartyScene(Scene):
    def draw_ui(self, ui):
        g = self.game
        ui.dim(100)
        x, y, w, h = 120, 34, 240, 200
        ui.panel(x, y, w, h, T.PARTY_TITLE)
        party = g.state.party
        me = g.state.me.get("id")
        cy = y + 14
        if not party:
            ui.text(T.PARTY_NONE, x + 12, cy, 7, "#5A5A5A", max_w=w - 24)
            cy += 30
        else:
            leader = party["leader"]
            for m in party["members"]:
                ui.fill(x + 10, cy, w - 20, 22, "#EFE6D2")
                r = ui.text(m["name"], x + 14, cy + 2, 8, "#2B2B2B")
                if m["uid"] == leader:
                    ui.text(T.PARTY_LEADER, r.right + 4, cy + 3, 6, "#C99A3A")
                sub = T.REALMS.get(m.get("realm") or "", "") if m["online"] else T.PARTY_OFFLINE
                if m.get("zone"):
                    sub += " · " + T.ZONE_NAMES.get(m["zone"], m["zone"])
                ui.text(sub, x + 14, cy + 12, 6, "#6A994E" if m["online"] else "#8E877A")
                if m.get("hp") is not None:
                    ui.progress(x + 120, cy + 4, 50, 5, m["hp"] / 100, "#8C8C8C" if m.get("ghost") else "#BC4749")
                if me == leader and m["uid"] != me:
                    if ui.button(f"pt_kick_{m['uid']}", x + w - 64, cy + 3, 48, 8, T.PARTY_KICK, size=6):
                        self.send("kick", uid=m["uid"])
                    if ui.button(f"pt_lead_{m['uid']}", x + w - 64, cy + 12, 48, 8, T.PARTY_PROMOTE, size=6):
                        self.send("promote", uid=m["uid"])
                cy += 24
            if ui.button("pt_leave", x + 12, cy + 2, 70, 14, T.PARTY_LEAVE):
                self.send("leave")
            cy += 20
        invites = [i for i in g.party_invites if i["until"] > g.now]
        if invites:
            ui.text(T.PARTY_PENDING, x + 12, cy, 7, "#8B5A2B")
            cy += 10
            for inv in invites[:2]:
                ui.text(inv["name"], x + 14, cy + 3, 8)
                if ui.button(f"pt_acc_{inv['uid']}", x + w - 120, cy, 52, 13, T.PARTY_ACCEPT, style="green"):
                    g.answer_invite(inv["uid"], True)
                if ui.button(f"pt_dec_{inv['uid']}", x + w - 64, cy, 52, 13, T.PARTY_DECLINE):
                    g.answer_invite(inv["uid"], False)
                cy += 16
        if not party or party["leader"] == me:
            name = ui.input_box("pt_name", x + 12, y + h - 50, w - 84, 14, T.PARTY_INVITE_PH, max_len=20)
            if (ui.button("pt_invite", x + w - 66, y + h - 50, 54, 14, T.PARTY_INVITE_BTN, style="primary")
                    or ui.submitted("pt_name")) and name.strip():
                self.send("invite", name=name.strip())
                ui.set_value("pt_name", "")
        ui.text(T.PARTY_HINT, x + 12, y + h - 32, 6, "#5A5A5A", max_w=w - 24)
        if ui.button("pt_close", x + w / 2 - 30, y + h - 17, 60, 13, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def send(self, op: str, **kw) -> None:
        if self.game.net is not None:
            self.game.net.send({"t": "party", "op": op, **kw})


def draw_party_frames(ui, game, x: float, y: float) -> None:
    """Small health bars of the other members under the player card (spec 15.3)."""
    party = game.state.party
    if not party:
        return
    me = game.state.me.get("id")
    for m in party["members"]:
        if m["uid"] == me:
            continue
        ui.fill(x, y, 96, 11, (20, 18, 15, 150))
        col = "#F4EBD9" if m["online"] else "#8E877A"
        if m["uid"] == party["leader"]:
            ui.fill(x + 2, y + 4, 3, 3, "#E9C46A")
        ui.text(m["name"][:14], x + 7, y + 5.5, 6, col, anchor="midleft")
        if m.get("hp") is not None:
            ui.progress(x + 60, y + 3, 33, 4, m["hp"] / 100, "#8C8C8C" if m.get("ghost") else "#BC4749")
        y += 12


# ------------------------------------------------------------------ the gate
class RealmGateScene(Scene):
    def __init__(self, game, rift: dict | None = None):
        super().__init__(game)
        self.rift = rift          # {"id", "realm", "n", "left"} when opened at a Khe Nứt Mực
        self.data: dict | None = None
        self.tab = "realms"
        self.next_fetch = 0.0
        self.busy = False

    def on_enter(self) -> None:
        self.fetch()

    def fetch(self) -> None:
        self.next_fetch = self.game.now + 3.0
        self.game.api.get("/realms", self._got, lambda e: None)

    def _got(self, d: dict) -> None:
        self.data = d
        self.game.state.party = d.get("party") if d.get("party") is not None else self.game.state.party
        self.game.state.realm_queue = d.get("queue")

    def update(self, dt, top):
        if self.game.now >= self.next_fetch:
            self.fetch()

    def send(self, msg: dict) -> None:
        if self.game.net is not None:
            self.game.net.send(msg)

    def draw_ui(self, ui):
        g = self.game
        ui.dim(110)
        x, y, w, h = 40, 18, 400, 234
        ui.panel(x, y, w, h, T.REALM_RIFT_TITLE if self.rift else T.REALM_GATE_TITLE)
        if not self.rift:
            tx = x + 10
            for key, label in (("realms", T.REALM_TAB_REALMS), ("puzzles", T.REALM_TAB_PUZZLES),
                               ("forge", T.REALM_TAB_FORGE)):
                bw = ui.text_size(label, 8)[0] + 14
                if ui.button(f"rg_tab_{key}", tx, y + 8, bw, 13, label, selected=self.tab == key):
                    self.tab = key
                tx += bw + 4
        body_y = y + 26 if not self.rift else y + 12
        if self.data is None:
            ui.text("...", x + w / 2, y + h / 2, 9, anchor="center")
        elif self.tab == "realms":
            self.draw_realms(ui, x, body_y, w)
        elif self.tab == "puzzles":
            self.draw_puzzles(ui, x, body_y, w)
        else:
            self.draw_forge(ui, x, body_y, w)
        if ui.button("rg_party", x + 12, y + h - 18, 70, 13, f"{T.PARTY_TITLE} (Y)", key=pygame.K_y):
            g.push(PartyScene(g))
        if ui.button("rg_close", x + w - 72, y + h - 18, 60, 13, T.CLOSE, key=pygame.K_ESCAPE):
            self.close()

    def draw_realms(self, ui, x, y, w):
        g = self.game
        party = g.state.party
        me = g.state.me.get("id")
        queue = g.state.realm_queue
        realms = self.data["realms"]
        if self.rift:
            realms = [r for r in realms if r["id"] == self.rift["realm"]]
        for r in realms:
            ui.fill(x + 10, y, w - 20, 74, "#EFE6D2")
            ui.text(r["hanzi"], x + 16, y + 4, 16, "#2B2B2B", kind="han")
            ui.text(r["name_vi"], x + 70, y + 4, 10, "#2B2B2B")
            ui.text(r["desc_vi"], x + 70, y + 17, 7, "#5A5A5A", max_w=w - 92)
            ui.text(T.REALM_INFO.format(realm=r["min_realm_vi"], p=r["puzzles"], m=r["time_limit_minutes"],
                                        tier=r["tier"]), x + 16, y + 38, 7, "#6A994E" if r["realm_ok"] else "#BC4749")
            ui.text(T.REALM_ENTRIES.format(n=r["entries_left"], d=r["daily"]), x + w - 18, y + 38, 7,
                    "#2B2B2B", anchor="topright")
            is_rift = r["kind"] == "rift"
            if is_rift and not self.rift:
                ui.text(T.REALM_RIFT_ONLY, x + 16, y + 50, 7, "#8E5AC8", max_w=w - 40)
            else:
                if is_rift:
                    left = self.rift.get("left", 0) - (g.now - self.rift.get("seen", g.now))
                    status, col = T.REALM_RIFT_LEFT.format(t=fmt_time(left)), "#8E5AC8"
                    is_open = left > 0
                elif r.get("open"):
                    status = T.REALM_OPEN.format(m=(r["closes_in"] or 0) // 60) if r.get("closes_in") else T.REALM_OPEN_ALWAYS
                    col, is_open = "#6A994E", True
                else:
                    status, col, is_open = T.REALM_CLOSED.format(t=fmt_wait(r.get("opens_in") or 0)), "#BC4749", False
                ui.text(status, x + 16, y + 50, 7, col)
                target = {"rift": self.rift["id"]} if is_rift else {"realm": r["id"]}
                ok = is_open and r["realm_ok"] and r["entries_left"] > 0
                bx = x + w - 18
                if party:
                    leader = party["leader"] == me
                    bw = 110
                    if ui.button(f"rg_enter_{r['id']}", bx - bw, y + 56, bw, 14,
                                 T.REALM_RIFT_ENTER if is_rift else T.REALM_ENTER, style="primary",
                                 enabled=ok and leader and len(party["members"]) >= 2,
                                 tooltip=None if leader else T.REALM_NEED_LEADER):
                        self.send({"t": "realm", "op": "enter", **target})
                        g.toast(T.REALM_ENTERING.format(name=r["name_vi"]), "#4A7CC8")
                else:
                    in_q = queue is not None and queue.get("realm") == r["id"]
                    bw = 110
                    if in_q:
                        ui.text(T.REALM_QUEUED.format(n=queue.get("waiting", 1)), bx - bw - 6, y + 63, 7, "#4A7CC8",
                                anchor="midright")
                        if ui.button(f"rg_unq_{r['id']}", bx - bw, y + 56, bw, 14, T.REALM_UNQUEUE):
                            self.send({"t": "realm", "op": "unqueue"})
                            g.state.realm_queue = None
                    elif ui.button(f"rg_q_{r['id']}", bx - bw, y + 56, bw, 14,
                                   T.REALM_RIFT_QUEUE if is_rift else T.REALM_QUEUE, style="gold", enabled=ok,
                                   tooltip=T.REALM_NEED_PARTY):
                        self.send({"t": "realm", "op": "queue", **target})
            y += 80
        if party:
            names = ", ".join(m["name"] for m in party["members"])
            ui.text(T.REALM_PARTY.format(names=names), x + 14, y + 2, 7, "#2B2B2B", max_w=w - 28)

    def draw_puzzles(self, ui, x, y, w):
        puzzles = self.data.get("puzzles", {})
        for kind in ROOM_ORDER + ("boss",):
            p = puzzles.get(kind)
            if not p:
                continue
            ui.text(p.get("hanzi", ""), x + 14, y + 1, 10, "#BC4749", kind="han")
            ui.text(p["name_vi"], x + 70, y, 8, "#2B2B2B")
            r = ui.text(p["how_vi"], x + 70, y + 10, 6.5, "#5A5A5A", max_w=w - 84)
            y = max(y + 22, r.bottom + 4)

    def draw_forge(self, ui, x, y, w):
        f = self.data["forge"]
        ui.text(T.REALM_FORGE_HINT.format(set=f["set_vi"], rarity=f["rarity_vi"]), x + 14, y + 2, 8, max_w=w - 28)
        ui.text(T.REALM_FORGE_HAVE.format(have=f["have"], need=f["fragments"], stones=f["stones"]), x + 14, y + 18, 8,
                "#6A994E" if f["have"] >= f["fragments"] else "#BC4749")
        ui.text(T.REALM_FORGE_BONUS.format(b2=f["bonus_vi"].get("2", ""), b4=f["bonus_vi"].get("4", "")),
                x + 14, y + 30, 7, "#8E5AC8")
        cy = y + 46
        for p in f["pieces"]:
            ui.fill(x + 14, cy, w - 28, 20, "#EFE6D2")
            ui.text(f"{p['name_vi']} · {p['slot_vi']}", x + 20, cy + 10, 8, anchor="midleft")
            if ui.button(f"rg_forge_{p['id']}", x + w - 84, cy + 3, 64, 14, T.REALM_FORGE_BTN, style="gold",
                         enabled=f["have"] >= f["fragments"] and not self.busy):
                self.forge(p)
            cy += 24

    def forge(self, piece: dict) -> None:
        g = self.game
        self.busy = True

        def ok(r):
            self.busy = False
            e = r["equipment"]
            g.state.me["spirit_stones"] = r.get("spirit_stones", g.state.me.get("spirit_stones"))
            g.toast(T.REALM_FORGE_DONE.format(name=e["name_vi"], rarity=e["rarity_vi"]), e.get("color", "#C99A3A"))
            g.refresh_inv()
            self.fetch()

        def err(e):
            self.busy = False
            g.api_error(e)
        g.api.post("/realm/forge", {"piece": piece["id"]}, ok, err)


# ------------------------------------------------------------------ inside a bí cảnh
class RealmView:
    MARKS = ("!", "→", "?", "OK")

    def __init__(self, scene):
        self.scene = scene
        self.game = scene.game
        self.run: dict | None = None
        self.room: dict | None = None
        self.puzzle: dict | None = None
        self.mine: dict | None = None
        self.ended: dict | None = None
        self.loot: list[dict] = []
        self.left = 0.0                 # seconds left in the run, counted down locally
        self.left_at = 0.0
        self.room_shown = 0.0           # when the room started (for the "how to" banner)
        self.cleared_at: float | None = None
        self.cleared_in = 0.0
        self.end_at = 0.0
        self.notes: list[tuple[str, str, float]] = []
        self.marks: list[list] = []     # [x, y, icon, until]
        self.objs = [o for o in scene.map.objects if o.type == "realm_obj"]
        self.puzzle_at = 0.0

    # ------------------------------------------------------------ messages
    def note(self, text: str, color: str = "#F4EBD9") -> None:
        self.notes.append((text, color, self.game.now + 5.0))
        self.notes = self.notes[-4:]

    def on_net(self, m: dict) -> None:
        g = self.game
        ev = m.get("event")
        if ev == "start":
            self.run = m["run"]
            self.left, self.left_at = float(self.run.get("left", 0)), g.now
        elif ev == "room":
            self.room, self.puzzle, self.mine = m, m.get("puzzle"), m.get("mine")
            self.left, self.left_at = float(m.get("left", self.left)), g.now
            self.room_shown, self.cleared_at, self.puzzle_at = g.now, None, g.now
        elif ev == "puzzle" and self.room and m.get("i") == self.room.get("i"):
            self.puzzle, self.puzzle_at = m.get("puzzle"), g.now
        elif ev == "mine" and self.room and m.get("i") == self.room.get("i"):
            self.mine = m.get("mine")
        elif ev == "cleared":
            self.cleared_at, self.cleared_in = g.now, float(m.get("next_in", 4))
            g.audio.play("coin")
            if m.get("flawless"):
                self.note(T.REALM_CLEARED_FLAWLESS, "#E9C46A")
        elif ev == "end":
            self.ended = m
            self.end_at = g.now + float(m.get("exit_in", 30))
            g.refresh_inv()
            g.refresh_me()
        elif ev == "loot":
            lt = m["loot"]
            self.loot.append(lt)
            g.on_xp(lt.get("xp"))
            if "spirit_stones" in lt:
                g.state.me["spirit_stones"] = lt["spirit_stones"]
            if lt.get("stage", "").startswith("room"):
                self.note(T.REALM_ROOM_LOOT.format(i=int(lt["stage"][4:]) + 1, n=lt.get("stones", 0)), "#E9C46A")
            g.refresh_inv()
        elif ev == "tone":
            if m.get("ok"):
                self.note(T.REALM_TONE_OK.format(hz=m["hanzi"], py=m["pinyin"], t=m["tone"]), "#B5D67A")
            else:
                self.note(T.REALM_TONE_BAD.format(hz=m["hanzi"], py=m["pinyin"], t=m["tone"]), "#F08A8C")
        elif ev == "mirror":
            text = (T.REALM_MIRROR_OK if m.get("ok") else T.REALM_MIRROR_BAD).format(
                by=m.get("by", ""), hz=m["hanzi"], py=m.get("pinyin", ""), m=m.get("meaning", ""))
            self.note(text, "#B5D67A" if m.get("ok") else "#F08A8C")
        elif ev == "hint":
            self.note(m.get("text_vi", ""), "#E3D5BA")
        elif ev == "member_left":
            self.note(T.REALM_MEMBER_LEFT.get(m.get("reason"), "{name}").format(name=m.get("name", "")), "#F08A8C")
        elif ev == "revived":
            self.scene.ghost = False
            g.toast(T.REALM_REVIVED.format(hp=m.get("hp", 0)), "#6A994E")

    def on_fx(self, ev: dict) -> None:
        k = ev.get("k")
        fx = self.scene.fx
        x, y = ev.get("x", 0.0), ev.get("y", 0.0)
        if k == "mark":
            self.marks.append([x, y, self.MARKS[int(ev.get("i", 0)) % 4], self.game.now + 3.0])
        elif k == "pz":
            e = ev.get("e")
            if e in ("solve", "open"):
                fx.ink_to_light(x, y - 8)
            elif e == "fail":
                fx.burst(x, y - 8, "r", 16, 30)
                fx.shake = 0.3
            elif e == "step":
                fx.burst(x, y - 4, "o", 10, 20)
                if ev.get("t"):
                    self.scene.big_chars.append([ev["t"], x, y - 34, 1.0])
            elif e == "strike":
                fx.burst(x, y, "o", 8, 18)
            elif e == "wave":
                r = ev.get("r", 40)
                for i in range(18):
                    a = i / 18 * 6.283
                    fx.burst(x + math.cos(a) * r, y + math.sin(a) * r * 0.6, "K", 2, 16)
        elif k == "gshield":
            fx.float_text(f"{ev.get('n')}/{ev.get('need')}", x, y - 50, "#8CB8DA")

    # ------------------------------------------------------------ helpers
    @property
    def kind(self) -> str | None:
        return self.room.get("kind") if self.room else None

    def room_objs(self, kind: str | None = None) -> list:
        return [o for o in self.objs if o.props.get("room") == self.kind and (kind is None or o.props.get("kind") == kind)]

    def room_rect(self) -> pygame.Rect | None:
        """The current room with its walls, in world pixels."""
        if not self.kind:
            return None
        o = next((o for o in self.scene.map.objects if o.type == "realm_room" and o.props.get("kind") == self.kind), None)
        return pygame.Rect(int(o.x) - 16, int(o.y) - 16, int(o.w) + 32, int(o.h) + 32) if o else None

    def outside(self, surf, cx: int, cy: int) -> None:
        """Only the room the party stands in exists: the rest of the map is black."""
        r = self.room_rect()
        if r is None:
            return
        r = r.move(-cx, -cy)
        w, h = surf.get_size()
        black = (10, 9, 12)
        for rect in ((0, 0, w, max(0, r.top)), (0, r.bottom, w, max(0, h - r.bottom)),
                     (0, r.top, max(0, r.left), r.height), (r.right, r.top, max(0, w - r.right), r.height)):
            if rect[2] > 0 and rect[3] > 0:
                surf.fill(black, rect)

    def time_left(self) -> float:
        return self.left - (self.game.now - self.left_at)

    def puzzle_left(self, key: str) -> float | None:
        v = (self.puzzle or {}).get(key)
        if v is None:
            return None
        return max(0.0, float(v) - (self.game.now - self.puzzle_at))

    def standing_on(self, o) -> bool:
        p = self.scene.player
        return o.x - 3 <= p.x <= o.x + o.w + 3 and o.y - 3 <= p.y <= o.y + o.h + 3

    def target(self, fx: float, fy: float):
        """A pillar in reach for the E key (only the tone room has things to strike)."""
        best, bd = None, 30.0
        for o in self.room_objs("pillar"):
            d = math.hypot(o.x + o.w / 2 - fx, o.y + o.h - fy)
            if d < bd:
                best, bd = o, d
        return best

    def act(self, obj) -> None:
        if self.game.net is not None:
            self.scene.flush_inputs()
            self.game.net.send({"t": "ract", "obj": obj.name})

    def mark(self, wx: float, wy: float, icon: int = 0) -> None:
        if self.game.net is not None:
            self.game.net.send({"t": "mark", "x": max(0.0, wx), "y": max(0.0, wy), "i": icon})

    def leave(self) -> None:
        g = self.game

        def go():
            if g.net is not None:
                g.net.send({"t": "realm", "op": "leave"})
        if self.ended:
            go()
        else:
            g.message(T.REALM_LEAVE_CONFIRM, T.REALM_LEAVE, ok=T.REALM_LEAVE, cancel=T.CANCEL, on_ok=go)

    # ------------------------------------------------------------ drawing in the world
    def floor(self, surf, cx: int, cy: int, frame: int) -> None:
        """Props lying on the floor, drawn under everyone."""
        pz = self.puzzle or {}
        kind = self.kind
        for o in self.room_objs():
            k = o.props.get("kind")
            x, y = int(o.x) - cx, int(o.y) - cy
            if k == "pedestal":
                active = o.props.get("slot") in (pz.get("slots") or [])
                surf.blit(sprites.realm("pedestal", active, active and self._someone_on(o)), (x, y))
            elif k == "tile":
                n = int(o.props.get("n", 0))
                total, done = pz.get("n", 0), pz.get("k", 0)
                state = "off" if n > total else ("done" if n <= done else ("next" if n == done + 1 else "idle"))
                surf.blit(sprites.realm("rune_tile", state), (x, y))
            elif k == "mirror":
                surf.blit(sprites.realm("mirror", frame % 4), (x - 0, y - 24))
            elif k == "chest" and kind == "boss" and self.ended and self.ended.get("result") == "won":
                surf.blit(sprites.realm("chest", True), (x, y))
            elif k == "exit":
                opened = self.cleared_at is not None or (kind == "maze" and pz.get("solved"))
                surf.blit(sprites.realm("realm_exit", opened, frame % 2), (x, y - 8))
            elif k == "maze_exit":
                pygame.draw.rect(surf, (233, 196, 106), (x, y, int(o.w), int(o.h)), 1)

    def _someone_on(self, o) -> bool:
        if self.standing_on(o):
            return True
        return any(o.x - 3 <= e.pos[0] <= o.x + o.w + 3 and o.y - 3 <= e.pos[1] <= o.y + o.h + 3
                   for e in self.scene.entities.values() if e.kind == "p")

    def drawables(self, cx: int, cy: int, frame: int) -> list:
        """Standing props, sorted with the characters by their feet."""
        out = []
        for o in self.room_objs():
            k = o.props.get("kind")
            if k == "pillar":
                tone = int(o.props.get("tone", 1))
                out.append((o.y + o.h, sprites.realm("pillar", tone, False), (int(o.x) - cx, int(o.y) - cy)))
            elif k == "statue":
                out.append((o.y + o.h, sprites.realm("statue", frame % 2), (int(o.x) - cx, int(o.y) - cy)))
        return out

    def dark(self, surf, cx: int, cy: int) -> None:
        """Mê Cung Mực: black ink everywhere except around those who shed light."""
        pz = self.puzzle or {}
        if self.kind != "maze" or pz.get("solved"):
            return
        scene = self.scene
        me = scene.game.state.me.get("id")
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((8, 8, 14, 238))
        lights = []
        carriers = set(pz.get("carriers") or [])
        r = int(pz.get("radius", 64))
        if me in carriers:
            lights.append((scene.player.x, scene.player.y, r))
        for e in scene.entities.values():
            if e.kind == "p" and e.uid in carriers:
                lights.append((e.pos[0], e.pos[1], r))
        lights.append((scene.player.x, scene.player.y, int(pz.get("self_radius", 18))))
        for lx, ly, lr in lights:
            for k, a in ((1.0, 150), (0.8, 70), (0.6, 0)):
                pygame.draw.circle(shade, (8, 8, 14, a), (int(lx - cx), int(ly - 10 - cy)), int(lr * k))
        surf.blit(shade, (0, 0))

    # ------------------------------------------------------------ the HUD
    def draw_ui(self, ui, top: bool) -> None:
        g = self.game
        cx, cy = self.scene.cam
        now = g.now
        # floor labels: tile numbers, pedestal slots, pillar tones (sharp, at window resolution)
        pz = self.puzzle or {}
        for o in self.room_objs():
            k = o.props.get("kind")
            ox, oy = o.x + o.w / 2 - cx, o.y + o.h / 2 - cy
            if k == "tile" and int(o.props["n"]) <= pz.get("n", 0):
                ui.text(o.props["n"], ox, oy, 8, "#2B2B2B", anchor="center")
            elif k == "pedestal" and o.props.get("slot") in (pz.get("slots") or []):
                ui.text(T.REALM_SLOTS.get(o.props["slot"], ""), ox, oy + 13, 6, "#E9C46A", anchor="center")
            elif k == "pillar":
                ui.text(f"{o.props['tone']}", ox, o.y - cy - 6, 7, "#E9C46A", anchor="center")
        for mk in list(self.marks):
            if mk[3] < now:
                self.marks.remove(mk)
                continue
            bob = math.sin(now * 8) * 2
            ui.text(mk[2], mk[0] - cx, mk[1] - cy - 30 + bob, 12, "#E9C46A", anchor="center")
        if self.run:
            name = self.run.get("name_vi", "")
            if self.room:
                label = T.REALM_ROOM.format(name=name, i=self.room["i"] + 1, n=self.room["n"], room=self.room["name_vi"])
            else:
                label = name
            label += "   " + fmt_time(self.time_left())
            w = ui.text_size(label, 8)[0] + 14
            ui.fill(240 - w / 2, 4, w, 13, (20, 18, 15, 200))
            ui.text(label, 240, 10.5, 8, "#F4EBD9" if self.time_left() > 60 else "#F08A8C", anchor="center")
        if self.room and now - self.room_shown < 8 and not self.ended:   # how this room works, for a while
            how = self.room.get("how_vi", "")
            ui.fill(100, 176, 280, 30, (20, 18, 15, 200))
            ui.text(how, 106, 179, 7, "#F4EBD9", max_w=268)
        y = 20
        for text, col, until in self.notes:
            if until > now:
                tw = ui.text_size(text, 7)[0] + 10
                ui.fill(240 - tw / 2, y, tw, 10, (20, 18, 15, 170))
                ui.text(text, 240, y + 5, 7, col, anchor="center")
                y += 11
        if self.cleared_at is not None and not self.ended:
            n = max(0, int(self.cleared_in - (now - self.cleared_at)) + 1)
            ui.text(T.REALM_CLEARED.format(n=n), 240, 110, 10, "#E9C46A", anchor="center")
        self.draw_card(ui)
        if self.ended:
            self.draw_result(ui, top)
        elif top and ui.button("realm_leave", 400, 238, 76, 12, T.REALM_LEAVE, size=7, style="dark"):
            self.leave()

    def draw_card(self, ui) -> None:
        """The puzzle card, top right: what everyone sees, and this player's own part."""
        if not self.room or self.ended:
            return
        pz = self.puzzle or {}
        mine = self.mine or {}
        x, y, w = 346, 22, 130
        lines: list[tuple] = []          # (text, size, color, kind)
        kind = self.kind
        if kind == "compose":
            lines.append((T.REALM_COMPOSE_DOOR.format(m=pz.get("meaning", "")), 7, "#F4EBD9", "ui"))
            lines.append((T.REALM_COMPOSE_STONES.format(slots=" + ".join(T.REALM_SLOTS.get(s, s) for s in pz.get("slots", []))),
                          7, "#8CB8DA", "ui"))
            if pz.get("answer"):
                lines.append((T.REALM_COMPOSE_ANSWER.format(hz=pz["answer"]), 8, "#E9C46A", "ui"))
            else:
                lines.append((T.REALM_COMPOSE_PIECE if mine.get("piece") else T.REALM_COMPOSE_NOPIECE, 7, "#E3D5BA", "ui"))
                if mine.get("piece"):
                    lines.append((mine["piece"], 20, "#E9C46A", "han"))
                left = self.puzzle_left("window")
                if left is not None:
                    lines.append((T.REALM_COMPOSE_WINDOW.format(t=int(left) + 1), 7, "#F08A8C", "ui"))
        elif kind == "sentence":
            lines.append((T.REALM_SENTENCE_VI.format(vi=pz.get("vi", "")), 7, "#F4EBD9", "ui"))
            done = " ".join(t["t"] for t in pz.get("done", []))
            if done:
                lines.append((T.REALM_SENTENCE_DONE.format(text=done), 8, "#E9C46A", "han"))
            if not pz.get("solved"):
                lines.append((T.REALM_SENTENCE_NEXT.format(n=pz.get("k", 0) + 1, total=pz.get("n", 0)), 7, "#8CB8DA", "ui"))
                toks = mine.get("tokens") or []
                if toks:
                    lines.append((T.REALM_SENTENCE_MINE, 7, "#E3D5BA", "ui"))
                    lines.append(("  ".join(t["t"] for t in toks), 12, "#E9C46A", "han"))
                    lines.append(("  ".join(t["py"] for t in toks), 7, "#B5D67A", "ui"))
        elif kind == "tone":
            lines.append((T.REALM_TONE_STREAK.format(s=pz.get("streak", 0), n=pz.get("need", 8)), 8, "#E9C46A", "ui"))
            r = pz.get("round")
            if r:
                lines.append((T.REALM_TONE_READ, 7, "#E3D5BA", "ui"))
                lines.append((f"{r['hanzi']}  {r['syllable']}", 18, "#F4EBD9", "han"))
                left = max(0.0, r.get("left", 0) - (self.game.now - self.puzzle_at))
                lines.append((f"{left:.1f}s", 8, "#F08A8C" if left < 2 else "#F4EBD9", "ui"))
            elif not pz.get("solved"):
                lines.append((T.REALM_TONE_WAIT, 7, "#8E877A", "ui"))
        elif kind == "mirror":
            if pz.get("meaning"):
                lines.append((T.REALM_MIRROR_SHOWS.format(m=pz["meaning"]), 7, "#F4EBD9", "ui"))
            lines.append((T.REALM_MIRROR_COUNT.format(c=pz.get("correct", 0), n=pz.get("need", 3)), 7, "#8CB8DA", "ui"))
            if mine.get("hanzi"):
                lines.append((T.REALM_MIRROR_MINE, 7, "#E3D5BA", "ui"))
                lines.append((mine["hanzi"], 18, "#E9C46A", "han"))
                lines.append((mine.get("pinyin", ""), 7, "#B5D67A", "ui"))
        elif kind == "maze":
            names = self._names(pz.get("carriers") or [])
            if pz.get("lantern"):
                lines.append((T.REALM_MAZE_LANTERN.format(name=names), 7, "#E9C46A", "ui"))
            else:
                lines.append((T.REALM_MAZE_LIGHT.format(names=names), 7, "#E9C46A", "ui"))
            lines.append((T.REALM_MAZE_EXIT.format(n=pz.get("in_exit", 0), need=pz.get("need", 0)), 7, "#8CB8DA", "ui"))
        elif kind == "boss":
            lines.append((T.REALM_BOSS_PHASE.format(p=min(4, pz.get("phase", 1))), 8, "#F08A8C", "ui"))
            if pz.get("shield"):
                lines.append((T.REALM_BOSS_SHIELD.format(n=pz.get("hits", 0), need=pz.get("need", 1)), 7, "#8CB8DA", "ui"))
            elif "hp" in pz:
                lines.append((T.REALM_BOSS_OPEN, 7, "#E9C46A", "ui"))
        if pz.get("fails"):
            lines.append((T.REALM_FAILS.format(n=pz["fails"]), 6, "#F08A8C", "ui"))
        def height(text: str, size: float, kind_: str) -> float:
            if kind_ == "han" or size >= 12:
                return 28 if size >= 18 else 19 if size >= 12 else 13
            n = len(ui.f.wrap(text, size, int((w - 12) * ui.s), ui.s)) or 1
            return n * size * 1.4 + 1
        h = 20 + sum(height(t, size, k) for t, size, _, k in lines) + (8 if kind == "boss" and "hp" in pz else 0)
        ui.fill(x, y, w, h, (20, 18, 15, 200))
        ui.border(x, y, w, h, "#8B5A2B")
        ui.text(self.room.get("name_vi", ""), x + 6, y + 4, 8, "#E9C46A")
        ui.text(self.room.get("hanzi", ""), x + w - 6, y + 4, 8, "#BC4749", kind="han", anchor="topright")
        cy = y + 16
        for text, size, col, kind_ in lines:
            r = ui.text(text, x + 6, cy, size, col, kind=kind_, max_w=w - 12)
            cy += max(height(text, size, kind_), r.h + 1)
        if kind == "boss" and "hp" in pz:
            ui.progress(x + 6, y + h - 9, w - 12, 4, pz["hp"] / 100, "#BC4749")

    def _names(self, uids: list[int]) -> str:
        me = self.game.state.me.get("id")
        names = []
        for uid in uids:
            if uid == me:
                names.append(T.REALM_YOUR)
            else:
                m = next((x for x in (self.run or {}).get("members", []) if x["uid"] == uid), None)
                names.append(m["name"] if m else "?")
        return ", ".join(names)

    def draw_result(self, ui, top: bool) -> None:
        g = self.game
        e = self.ended
        ui.dim(120)
        x, y, w, h = 110, 30, 260, 206
        won = e.get("result") == "won"
        ui.panel(x, y, w, h, T.REALM_RESULT.get(e.get("result"), ""))
        secs = int(e.get("time", 0))
        ui.text(T.REALM_RESULT_INFO.format(m=secs // 60, s=secs % 60, f=e.get("flawless", 0), p=e.get("puzzles", 0)),
                x + w / 2, y + 8, 8, anchor="midtop")
        cy = y + 22
        if won and e.get("fast"):
            ui.text(T.REALM_FAST, x + w / 2, cy, 7, "#6A994E", anchor="midtop")
            cy += 11
        if won:
            ui.text(T.REALM_FRAGMENTS.format(n=e.get("fragments", 0)), x + w / 2, cy, 8, "#8E5AC8", anchor="midtop")
            cy += 13
        ui.text(T.REALM_YOUR_LOOT, x + 12, cy, 8, "#8B5A2B")
        cy += 12
        stones = sum(lt.get("stones", 0) for lt in self.loot)
        jade = sum(lt.get("jade", 0) for lt in self.loot)
        items: dict[str, int] = {}
        for lt in self.loot:
            for it in lt.get("items", []):
                items[it["name_vi"]] = items.get(it["name_vi"], 0) + it["qty"]
        parts = [T.REALM_LOOT_STONES.format(n=stones)] + ([T.REALM_LOOT_JADE.format(n=jade)] if jade else [])
        parts += [f"{k} ×{v}" for k, v in items.items()]
        ui.text(" · ".join(parts), x + 12, cy, 7, "#2B2B2B", max_w=w - 24)
        cy += 30
        for lt in self.loot:
            for eq in lt.get("equipment", []):
                ui.text(f"{eq['name_vi']} · {eq.get('rarity_vi', '')}", x + 12, cy, 8, eq.get("color", "#6A994E"))
                cy += 11
        left = max(0, int(self.end_at - g.now))
        if ui.button("realm_back", x + w / 2 - 60, y + h - 20, 120, 14, T.REALM_BACK.format(n=left), style="primary",
                     enabled=top, key=pygame.K_RETURN if top else None):
            self.leave()
