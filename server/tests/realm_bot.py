"""A bot that plays a bí cảnh through the real protocol (stage 9 test criterion: three players
clear a realm together). It only uses what a player has: the messages its own session gets,
the map file every client has, and its knowledge of Chinese (the word list). It moves with
`in` messages, strikes pillars with `ract`, fights with `atk` and answers Vấn Đạo questions
through POST /quiz/answer like the game does.

Bots in a team share what they see on screen, like players talking in the party chat: the
`Team` object is that chat.
"""
from __future__ import annotations

import math
from collections import deque

from app.learning.wordbank import bank, senses
from app.realtime import maps
from app.realtime.realm import anchor, composable, tone_of

STEP = 4   # path grid in pixels (corridors of the maze are one tile wide)


def path(col, start, goal, avoid=()) -> list[tuple[float, float]]:
    """Breadth-first path over a 4 px grid of foot positions the collider allows."""
    def ok(x, y):
        if col.blocked(x, y):
            return False
        return not any(a.x - 2 <= x <= a.x + a.w + 2 and a.y - 2 <= y <= a.y + a.h + 2 for a in avoid)

    # cell centres sit in the middle of one-tile corridors (feet x = tile + 8, y = tile + 11)
    def cell(x, y):
        return round(x / STEP), round((y - 3) / STEP)

    def center(c):
        return c[0] * STEP + 0.0, c[1] * STEP + 3.0
    s, g = cell(*start), cell(*goal)
    if not ok(*center(g)):   # the exact goal is inside something: the nearest open cell
        best = None
        for r in range(1, 8):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    c = (g[0] + dx, g[1] + dy)
                    if ok(*center(c)) and (best is None or abs(dx) + abs(dy) < best[0]):
                        best = (abs(dx) + abs(dy), c)
            if best:
                break
        if best is None:
            return []
        g = best[1]
    prev = {s: None}
    q = deque([s])
    while q:
        c = q.popleft()
        if c == g:
            break
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + d[0], c[1] + d[1])
            if n not in prev and ok(*center(n)):
                prev[n] = c
                q.append(n)
    if g not in prev:
        return []
    out, c = [], g
    while c is not None and c != s:
        out.append(center(c))
        c = prev[c]
    return list(reversed(out))


class Team:
    def __init__(self):
        self.bots: list["Bot"] = []
        self.assign: dict[int, object] = {}


class Bot:
    def __init__(self, world, client, headers, uid, session, team: Team, answer):
        self.w, self.client, self.h, self.uid, self.s = world, client, headers, uid, session
        self.team = team
        team.bots.append(self)
        self.answer = answer          # async (session, question) -> grade result
        self.seen = 0
        self.room: dict | None = None
        self.puzzle: dict | None = None
        self.mine: dict | None = None
        self.run: dict | None = None
        self.ended: dict | None = None
        self.loot: list[dict] = []
        self.qs: list[dict] = []
        self.answered: set[str] = set()
        self.seq = 0
        self.goal = None
        self.route: list = []
        self.next_atk = 0.0
        self.log: list[str] = []

    @property
    def p(self):
        return self.w.players.get(self.uid)

    @property
    def inst(self):
        return self.w.realms.instance_of(self.p)

    def send(self, msg: dict):
        return self.w.handle(self.s, msg)

    # ------------------------------------------------------------ reading the screen
    def read(self) -> None:
        for m in self.s.sent[self.seen:]:
            t, ev = m.get("t"), m.get("event")
            if t == "q":
                self.qs.append(m)
            elif t == "realm" and ev == "start":
                self.run = m["run"]
            elif t == "realm" and ev == "room":
                self.room, self.puzzle, self.mine = m, m["puzzle"], m["mine"]
                self.goal, self.route = None, []
            elif t == "realm" and ev == "puzzle":
                self.puzzle = m["puzzle"]
            elif t == "realm" and ev == "mine":
                self.mine = m["mine"]
            elif t == "realm" and ev == "end":
                self.ended = m
            elif t == "realm" and ev == "loot":
                self.loot.append(m["loot"])
        self.seen = len(self.s.sent)

    # ------------------------------------------------------------ moving
    def go(self, x: float, y: float, avoid=()) -> None:
        p = self.p
        if p is None:
            return
        if self.goal is None or math.hypot(self.goal[0] - x, self.goal[1] - y) > 1 or not self.route:
            self.goal = (x, y)
            self.route = path(p.channel.map.collider, (p.x, p.y), (x, y), avoid)

    def stop(self) -> None:
        self.goal, self.route = None, []

    async def move(self) -> None:
        p = self.p
        if p is None or not self.route or p.protected(self.w.mono()):
            return
        while self.route and math.hypot(self.route[0][0] - p.x, self.route[0][1] - p.y) < 0.2:
            self.route.pop(0)
        if not self.route:
            return
        tx, ty = self.route[0]
        dx, dy = tx - p.x, ty - p.y
        if abs(dy) > 0.1:
            d, step = abs(dy), (0, 1 if dy > 0 else -1)
        else:
            d, step = abs(dx), (1 if dx > 0 else -1, 0)
        ms = max(1, min(50, int(round(d / 74.0 * 1000))))
        await self.send({"t": "in", "s": self.seq, "k": [[step[0], step[1], ms]]})
        self.seq += 1

    def near(self, x, y, r=3.0) -> bool:
        p = self.p
        return p is not None and math.hypot(p.x - x, p.y - y) <= r

    # ------------------------------------------------------------ fighting
    async def answer_questions(self) -> None:
        for q in self.qs:
            sid = q["q"]["session_id"]
            if sid in self.answered:
                continue
            self.answered.add(sid)
            await self.answer(self, q["q"])
        self.qs = []

    async def fight(self, monsters) -> bool:
        """Walks to the nearest living monster and hits it. False when none is left."""
        p = self.p
        alive = [m for m in monsters if m.alive]
        if not alive or p is None:
            return False
        m = min(alive, key=lambda m: math.hypot(m.x - p.x, m.y - p.y))
        if math.hypot(m.x - p.x, m.y - 6 - (p.y - 6)) > 18:
            self.goal, self.route = None, []
            self.go(m.x, m.y + 6)
        elif self.w.mono() >= self.next_atk:
            self.next_atk = self.w.mono() + 0.7
            await self.send({"t": "atk", "id": m.eid})
        return True

    # ------------------------------------------------------------ puzzles, like a player who knows Chinese
    def obj(self, kind, **props):
        inst = self.inst
        for o in inst.map.realm_objs:
            if o.props.get("room") == inst.kind and o.props.get("kind") == kind and all(
                    str(o.props.get(k)) == str(v) for k, v in props.items()):
                return o
        return None

    def standby(self):
        a = self.inst.map.rooms[self.inst.kind]
        i = self.team.bots.index(self)
        return a.x + a.w / 2 - 40 + 40 * i, a.y + a.h - 30

    async def think(self) -> None:
        self.read()
        await self.answer_questions()
        inst, p = self.inst, self.p
        if inst is None or p is None or self.room is None or inst.phase != "running" or p.dead:
            await self.move()
            return
        if await self.fight(inst.monsters) or inst.kind == "boss":
            await self.move()
            return
        kind = inst.kind
        getattr(self, f"play_{kind}")()
        if kind == "tone":
            await self.strike()
        await self.move()

    def play_compose(self) -> None:
        pz, piece = self.puzzle, (self.mine or {}).get("piece")
        # which character has this meaning and these parts? (what the team works out in chat)
        pieces = {(b.mine or {}).get("piece") for b in self.team.bots}
        word = next((w for w in bank().words.values() if composable(w) and w.meaning_vi == pz["meaning"]
                     and set(composable(w)[1]) <= pieces | {None}), None)
        if word is None:   # the others have not said what they hold yet
            return
        layout, comps = composable(word)
        slots = ["left", "right"] if layout == "⿰" else ["top", "bottom"]
        if piece in comps and len(pz["slots"]) > 1:
            slot = slots[comps.index(piece)]
            if comps[0] == comps[1]:   # 林: two of the same part, one each
                holders = [b for b in self.team.bots if (b.mine or {}).get("piece") == piece]
                slot = slots[holders.index(self)]
            ped = self.obj("pedestal", slot=slot)
            self.go(ped.x + ped.w / 2, ped.y + ped.h / 2)
        elif piece == comps[0]:
            ped = self.obj("pedestal", slot=pz["slots"][0])
            self.go(ped.x + ped.w / 2, ped.y + ped.h / 2)
        else:
            self.go(*self.standby(), avoid=self.inst.objs("pedestal"))

    def play_sentence(self) -> None:
        pz = self.puzzle
        sent = next((s for s in bank().sentences.values() if s.vi == pz["vi"]), None)
        if sent is None:
            return
        tokens = [t for t in sent.tokens if t["word_id"]]
        mine = [t["t"] for t in (self.mine or {}).get("tokens", [])]
        k = pz["k"]
        tiles = self.inst.objs("tile")
        if k < len(tokens) and tokens[k]["t"] in mine:
            tile = self.obj("tile", n=k + 1)
            self.go(tile.x + tile.w / 2, tile.y + tile.h / 2, avoid=[t for t in tiles if t is not tile])
        else:
            x, y = self.standby()
            self.go(x, y, avoid=tiles)

    def play_tone(self) -> None:
        i = self.team.bots.index(self)
        r = self.puzzle.get("round")
        target = i + 1
        if r:
            tone = tone_of(bank().by_hanzi[r["hanzi"]]) if r["hanzi"] in bank().by_hanzi else None
            pil = self.obj("pillar", tone=tone) if tone else None
            if pil is not None:
                ax, ay = anchor(pil)
                nearest = min(self.team.bots, key=lambda b: math.hypot(b.p.x - ax, b.p.y - ay))
                if nearest is self:
                    target = tone
        pil = self.obj("pillar", tone=target)
        ax, ay = anchor(pil)
        self.go(ax, ay + 8)

    async def strike(self) -> None:
        r = self.puzzle.get("round")
        if not r or r["hanzi"] not in bank().by_hanzi:
            return
        pil = self.obj("pillar", tone=tone_of(bank().by_hanzi[r["hanzi"]]))
        ax, ay = anchor(pil)
        key = (r["hanzi"], self.puzzle["streak"])
        if self.near(ax, ay + 8, 6) and getattr(self, "_struck", None) != key:
            self._struck = key
            await self.send({"t": "ract", "obj": pil.name})

    def play_mirror(self) -> None:
        pz, mine = self.puzzle, (self.mine or {}).get("hanzi")
        mir = self.inst.objs("mirror")[0]
        w = bank().by_hanzi.get(mine) if mine else None
        p = self.p
        inside = mir.x <= p.x <= mir.x + mir.w and mir.y <= p.y <= mir.y + mir.h
        match = bool(pz.get("meaning")) and w is not None and (
            w.meaning_vi == pz["meaning"] or bool(w.senses & senses(pz["meaning"])))
        if not match:
            self._walking_in = False
            self.go(*self.standby(), avoid=[mir])
        elif inside and not getattr(self, "_walking_in", False):
            self.go(*self.standby(), avoid=[mir])   # still in from before: the mirror only sees someone walk in
        else:
            self._walking_in = not inside
            self.go(mir.x + mir.w / 2, mir.y + mir.h / 2)

    def play_maze(self) -> None:
        door = self.inst.objs("maze_exit")[0]
        self.go(door.x + door.w / 2, door.y + door.h / 2)



def realm_map():
    return maps.load("bi_canh")
