"""Ải Thủ Vườn (spec 9): the tower-defense simulation, shared by server and client
(client/engine/td_sim.py is a byte-for-byte copy; tests check they agree).

Mặc Quái walk a path of grid cells from the ink gate to the Linh Mạch; plants placed beside
the path (Mộc ones on it) hold them back. Time runs in fixed steps of STEP_MS, but only
during a wave: between waves (and while a question card is open, which the client handles
by not stepping) nothing moves.

The server sends `params` (the level, every number from balance/td.json and the power of
each plant the player brought). The client plays live and records its actions as events
`{"s": step, "k": kind, ...}`; the server replays the same events with the same code and
must reach the same end (`replay`). Question results come from the server's own records
(`answers`), so a client cannot claim a right answer it did not give. Only + - * / and
random.Random.random() are used, so both sides compute exactly the same floats.
"""
from __future__ import annotations

import random

STEP_MS = 50
DT = STEP_MS / 1000

BUILD, WAVE, WON, LOST = "build", "wave", "won", "lost"
BLOCK_GAP = 0.6       # a blocked monster waits this far (in cells) before the Mộc plant


class LogError(Exception):
    """An event the rules do not allow (the log is fake or broken)."""


class Plant:
    def __init__(self, x: int, y: int, word: str, role: str, spent: float):
        self.x, self.y, self.word, self.role = x, y, word, role
        self.level = 1
        self.spent = spent
        self.cd = 0.0
        self.hp = 0.0
        self.max_hp = 0.0
        self.buff = 1.0       # combo power (好)
        self.light = 1.0      # combo light radius (明)
        self.hp_mult = 1.0    # combo max hp (森)
        self.regen = 0.0      # combo regen per second (休)
        self.haste = 0.0      # attack speed from Hỗ Trợ neighbours
        self.heal = 0.0       # hp per second from Hỗ Trợ neighbours
        self.reach: set[int] = set()   # path indices in range


class Monster:
    def __init__(self, mid: int, kind: str, hp: float):
        self.id, self.kind = mid, kind
        self.hp = self.max_hp = hp
        self.d = 0.0                 # distance walked along the path, in cells
        self.slow = 1.0
        self.slow_until = 0
        self.stun_until = 0
        self.blocked = -1            # path index of the Mộc plant holding it, or -1
        self.dead = False


def endless_wave(n: int, e: dict, rng: random.Random) -> list[dict]:
    """Wave n (0-based) of the Vô Tận Trận: more and tougher monsters every wave, a boss every
    `boss_every` waves. Kinds come from the seeded rng, so a week's endless run is the same
    for everybody (a fair leaderboard)."""
    kinds = [k for k, first in e["kinds"] if first <= n]
    count = int(e["base_count"] + n * e["count_per_wave"])
    gap = e["gap_ms"] - n * e["gap_per_wave_ms"]
    if gap < e["gap_min_ms"]:
        gap = e["gap_min_ms"]
    hpx = 1 + n * e["hp_growth"]
    groups = []
    left, at = count, 0
    while left > 0:
        kind = kinds[int(rng.random() * len(kinds))]
        k = 3 if left > 3 else left
        groups.append({"m": kind, "n": k, "gap": gap, "at": at, "x": hpx})
        at += k * gap + 400
        left -= k
    if (n + 1) % e["boss_every"] == 0:
        groups.append({"m": "mac_vuong", "n": 1, "gap": gap, "at": at + 600, "x": hpx})
    return groups


class Sim:
    def __init__(self, params: dict, answers: dict | None = None):
        p = self.p = params
        self.cols, self.rows = int(p["cols"]), int(p["rows"])
        self.path = [(int(c[0]), int(c[1])) for c in p["path"]]
        self.path_at = {c: i for i, c in enumerate(self.path)}
        self.end_d = float(len(self.path) - 1)
        self.rocks = set((int(c[0]), int(c[1])) for c in p.get("rocks", []))
        self.roles = p["roles"]
        self.kinds = p["monsters"]
        self.defs = p["plants"]               # word_id -> {role, hanzi, power, skill?}
        self.answers = answers if answers is not None else {}
        self.rng = random.Random(p["seed"])
        q = p["qi"]
        self.qi = float(q["start"])
        self.hp = int(p["core_hp"])
        self.step_n = 0
        self.wave = 0                          # waves started so far
        self.total = len(p["waves"]) if p.get("waves") else int(p["endless"]["max_waves"])
        self.phase = BUILD
        self.plants: dict[tuple[int, int], Plant] = {}
        self.order: list[tuple[int, int]] = []  # plant cells in a fixed order (row, column)
        self.monsters: list[Monster] = []
        self.spawns: list[list] = []           # [step, kind, hp multiplier], in spawn order
        self.next_id = 1
        self.wave_start = 0
        self.break_q = 0
        self.last_tu_khi = -10 ** 9
        self.used_q: set[str] = set()
        self.skills_used: list[str] = []
        self.combos: list[str] = []            # combo ids active now (for display)
        self.lit: set[int] = set()             # path indices inside light
        self.moc_at: dict[int, Plant] = {}     # path index -> Mộc plant standing there
        self.kills = 0
        self.leaked = 0
        self.killed: dict[str, int] = {}
        self.met: dict[str, int] = {}
        self.record_fx = False
        self.fx: list[tuple] = []

    # ------------------------------------------------------------ helpers
    def role(self, word: str) -> dict:
        return self.roles[self.defs[word]["role"]]

    def level_mult(self, pl: Plant) -> float:
        return self.p["upgrade"]["level_mult"][pl.level - 1]

    def strength(self, pl: Plant) -> float:
        return self.defs[pl.word]["power"] * self.level_mult(pl) * pl.buff

    def cost_to_place(self, word: str) -> float:
        return float(self.role(word)["cost"])

    def cost_to_upgrade(self, pl: Plant) -> float | None:
        ups = self.p["upgrade"]["cost"]
        if pl.level - 1 >= len(ups):
            return None
        return self.role(pl.word)["cost"] * ups[pl.level - 1]

    def cell_of(self, m: Monster) -> int:
        return int(m.d + 0.5)

    def pos(self, m: Monster) -> tuple[float, float]:
        """Where a monster stands, in cells (for drawing)."""
        i = int(m.d)
        if i >= len(self.path) - 1:
            x, y = self.path[-1]
            return float(x), float(y)
        f = m.d - i
        (x0, y0), (x1, y1) = self.path[i], self.path[i + 1]
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f

    def visible(self, m: Monster) -> bool:
        return not self.kinds[m.kind].get("hidden") or self.cell_of(m) in self.lit

    def can_place(self, x: int, y: int, word: str) -> str | None:
        """None if a plant of `word` may go on (x, y) now, else the reason."""
        if self.phase in (WON, LOST):
            return "over"
        if word not in self.defs:
            return "not_in_loadout"
        r = self.role(word)
        if r.get("skill_only"):
            return "skill_only"
        if not (0 <= x < self.cols and 0 <= y < self.rows) or (x, y) in self.rocks:
            return "bad_cell"
        if (x, y) in self.plants:
            return "occupied"
        i = self.path_at.get((x, y))
        if r.get("on_path"):
            if i is None or i == 0 or i == len(self.path) - 1:
                return "needs_path"
        elif i is not None:
            return "off_path"
        if self.qi < self.cost_to_place(word):
            return "no_qi"
        return None

    # ------------------------------------------------------------ plants and combos
    def _refresh(self) -> None:
        """Recompute everything that depends on where plants stand: ranges, light, combos,
        Hỗ Trợ bonuses, the Mộc blockers. Called after every change of the board."""
        self.order = sorted(self.plants, key=lambda c: (c[1], c[0]))
        hz = {c: self.defs[self.plants[c].word]["hanzi"] for c in self.order}
        for c in self.order:
            pl = self.plants[c]
            pl.buff, pl.light, pl.hp_mult, pl.regen, pl.haste, pl.heal = 1.0, 1.0, 1.0, 0.0, 0.0, 0.0
        active: list[str] = []
        for cb in self.p["combos"]:
            hit = False
            if cb["kind"] == "pair":
                for c in self.order:
                    if hz[c] not in cb["a"]:
                        continue
                    for nb in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                        if nb in self.plants and hz[nb] in cb["b"]:
                            hit = True
                            self._combo(self.plants[c], cb)
                            if cb["effect"] == "power":
                                self._combo(self.plants[nb], cb)
            else:   # cluster: connected cells of the listed characters
                seen: set[tuple[int, int]] = set()
                for c in self.order:
                    if c in seen or hz[c] not in cb["a"]:
                        continue
                    group, stack = [], [c]
                    seen.add(c)
                    while stack:
                        cur = stack.pop()
                        group.append(cur)
                        for nb in ((cur[0] + 1, cur[1]), (cur[0] - 1, cur[1]), (cur[0], cur[1] + 1), (cur[0], cur[1] - 1)):
                            if nb in self.plants and nb not in seen and hz[nb] in cb["a"]:
                                seen.add(nb)
                                stack.append(nb)
                    if len(group) >= cb["size"]:
                        hit = True
                        for g in group:
                            self._combo(self.plants[g], cb)
            if hit:
                active.append(cb["id"])
        self.combos = active
        for c in self.order:   # Hỗ Trợ neighbours
            pl = self.plants[c]
            if pl.role != "ho_tro":
                continue
            r = self.roles["ho_tro"]
            k = self.strength(pl)
            for nb in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                if nb in self.plants:
                    self.plants[nb].haste += r["haste"] * k
                    self.plants[nb].heal += r["heal"] * k
        self.lit = set()
        self.moc_at = {}
        for c in self.order:
            pl = self.plants[c]
            r = self.roles[pl.role]
            if pl.role == "moc":
                self.moc_at[self.path_at[c]] = pl
                new_max = r["hp"] * self.strength(pl) * pl.hp_mult
                if pl.max_hp > 0:
                    pl.hp = pl.hp * new_max / pl.max_hp
                else:
                    pl.hp = new_max
                pl.max_hp = new_max
            rng = r.get("range", 0) * (pl.light if pl.role == "quang" else 1.0)
            rr = rng * rng
            pl.reach = set()
            for i, (px, py) in enumerate(self.path):
                dx, dy = px - c[0], py - c[1]
                if dx * dx + dy * dy <= rr:
                    pl.reach.add(i)
            if pl.role == "quang":
                self.lit |= pl.reach

    def _combo(self, pl: Plant, cb: dict) -> None:
        e = cb["effect"]
        if e == "power" and pl.buff == 1.0:
            pl.buff = cb["value"]
        elif e == "light" and pl.light == 1.0:
            pl.light = cb["value"]
        elif e == "hp":
            pl.hp_mult = cb["value"]
        elif e == "regen":
            pl.regen = cb["value"]

    # ------------------------------------------------------------ events
    def apply(self, ev: dict) -> None:
        """Apply one player action at the current step. Raises LogError when not allowed."""
        k = ev.get("k")
        if k == "place":
            x, y, word = ev.get("x"), ev.get("y"), ev.get("w")
            if not isinstance(x, int) or not isinstance(y, int) or not isinstance(word, str):
                raise LogError("bad_event")
            why = self.can_place(x, y, word)
            if why:
                raise LogError(why)
            cost = self.cost_to_place(word)
            self.qi -= cost
            self.plants[(x, y)] = Plant(x, y, word, self.defs[word]["role"], cost)
            self._refresh()
        elif k == "sell":
            pl = self.plants.get((ev.get("x"), ev.get("y")))
            if pl is None or self.phase in (WON, LOST):
                raise LogError("no_plant")
            self.qi += pl.spent * self.p["sell_refund"]
            del self.plants[(pl.x, pl.y)]
            self._refresh()
        elif k == "up":
            pl = self.plants.get((ev.get("x"), ev.get("y")))
            if pl is None or self.phase in (WON, LOST):
                raise LogError("no_plant")
            a = self._answer(ev.get("q"), "upgrade")
            if a["word"] != pl.word:
                raise LogError("wrong_word")
            cost = self.cost_to_upgrade(pl)
            if cost is None:
                raise LogError("max_level")
            if self.qi < cost:
                raise LogError("no_qi")
            self.qi -= cost
            pl.spent += cost
            if a["ok"]:
                pl.level += 1
                self._refresh()
        elif k == "qi":
            a = self._answer(ev.get("q"), None)
            q = self.p["qi"]
            if a["kind"] == "break":
                if self.phase != BUILD or self.break_q >= q["break_questions"]:
                    raise LogError("no_break")
                self.break_q += 1
                if a["ok"]:
                    self.qi += q["break_qi"]
            elif a["kind"] == "tu_khi":
                if self.phase != WAVE or self.step_n - self.last_tu_khi < self.tu_khi_cd():
                    raise LogError("cooldown")
                self.last_tu_khi = self.step_n
                if a["ok"]:
                    self.qi += q["tu_khi_qi"]
                else:
                    self.qi -= q["tu_khi_wrong_loss"]
                    if self.qi < 0:
                        self.qi = 0.0
            else:
                raise LogError("wrong_kind")
        elif k == "skill":
            word = ev.get("w")
            if self.phase != WAVE or word not in self.defs or word in self.skills_used \
                    or not self.defs[word].get("skill"):
                raise LogError("no_skill")
            self.skills_used.append(word)
            self._skill(self.defs[word]["skill"])
        elif k == "wave":
            if self.phase != BUILD or self.wave >= self.total:
                raise LogError("no_wave")
            self._start_wave()
        else:
            raise LogError("bad_event")

    def tu_khi_cd(self) -> int:
        return int(self.p["qi"]["tu_khi_cooldown_s"] * 1000) // STEP_MS

    def _answer(self, sid, kind: str | None) -> dict:
        if not isinstance(sid, str) or sid in self.used_q or sid not in self.answers:
            raise LogError("bad_question")
        a = self.answers[sid]
        if kind is not None and a["kind"] != kind:
            raise LogError("wrong_kind")
        self.used_q.add(sid)
        return a

    def _skill(self, s: dict) -> None:
        live = [m for m in self.monsters if not m.dead]
        if s["type"] == "strike_strongest":
            live.sort(key=lambda m: (-m.hp, m.id))
            for m in live[:s["targets"]]:
                self._hurt(m, s["dmg"], None)
                if self.record_fx:
                    self.fx.append(("skill", self.pos(m)))
        elif s["type"] == "slow_all":
            until = self.step_n + int(s["seconds"] * 1000) // STEP_MS
            for m in live:
                m.slow, m.slow_until = s["mult"], until
        elif s["type"] == "stun_all":
            until = self.step_n + int(s["seconds"] * 1000) // STEP_MS
            for m in live:
                if m.stun_until < until:
                    m.stun_until = until
        self._bury()

    def _start_wave(self) -> None:
        if self.p.get("waves"):
            groups = self.p["waves"][self.wave]
        else:
            groups = endless_wave(self.wave, self.p["endless"], self.rng)
        hpx = self.p.get("hp_mult", 1.0)
        out = []
        for g in groups:
            for i in range(int(g["n"])):
                ms = int(g["at"]) + i * int(g["gap"])
                out.append([self.step_n + ms // STEP_MS, g["m"], g.get("x", 1.0) * hpx])
        out.sort(key=lambda s: s[0])
        self.spawns = out
        self.wave += 1
        self.wave_start = self.step_n
        self.phase = WAVE
        self.break_q = 0

    # ------------------------------------------------------------ time
    def step(self) -> None:
        if self.phase != WAVE:
            return
        self.step_n += 1
        while self.spawns and self.spawns[0][0] <= self.step_n:
            _, kind, hpx = self.spawns.pop(0)
            m = Monster(self.next_id, kind, self.kinds[kind]["hp"] * hpx)
            self.next_id += 1
            self.monsters.append(m)
            self.met[kind] = self.met.get(kind, 0) + 1
        self.qi += self.p["qi"]["regen_per_s"] * DT
        for c in self.order:
            pl = self.plants.get(c)
            if pl is not None:
                self._act(pl)
        self._bury()
        self._walk()
        self._bury()
        if not self.spawns and not self.monsters and self.phase == WAVE:
            self.qi += self.p["qi"]["wave_bonus"]
            self.phase = WON if self.wave >= self.total else BUILD
        elif self.phase == WAVE and self.step_n - self.wave_start > \
                int(self.p["wave_max_seconds"] * 1000) // STEP_MS:
            self.hp = 0          # a wave that never ends (should not happen): the garden falls
            self.phase = LOST

    def _act(self, pl: Plant) -> None:
        r = self.roles[pl.role]
        role = pl.role
        if role == "moc":
            if pl.hp < pl.max_hp:
                pl.hp += (pl.regen + pl.heal) * DT
                if pl.hp > pl.max_hp:
                    pl.hp = pl.max_hp
            return
        if role in ("ho_tro", "thanh_ngu"):
            return
        if pl.cd > 0:
            pl.cd -= DT * (1 + pl.haste)
            if pl.cd > 0:
                return
        if role == "sinh_khi":
            self.qi += r["qi"] * self.strength(pl)
            pl.cd = r["cd"]
            if self.record_fx:
                self.fx.append(("qi", (pl.x, pl.y)))
            return
        targets = [m for m in self.monsters if not m.dead and self.cell_of(m) in pl.reach and self.visible(m)]
        if not targets:
            return
        k = self.strength(pl)
        if role == "son":
            for m in targets:
                self._hurt(m, r["dmg"] * k, r["elem"])
                res = self.kinds[m.kind]["resist"].get("son", 1.0)
                if self.kinds[m.kind].get("boss"):
                    res = res * self.p["boss_stun_mult"]
                until = self.step_n + int(r["stun_s"] * res * 1000) // STEP_MS
                if m.stun_until < until:
                    m.stun_until = until
            pl.cd = r["cd"]
            if self.record_fx:
                self.fx.append(("quake", (pl.x, pl.y), r["range"]))
            return
        if role == "kim":
            tgt = max(targets, key=lambda m: (m.hp, -m.id))
        else:
            tgt = max(targets, key=lambda m: (m.d, -m.id))
        if role == "hoa":
            for m in self.monsters:
                if not m.dead and self.visible(m) and -r["splash"] <= m.d - tgt.d <= r["splash"]:
                    self._hurt(m, r["dmg"] * k, r["elem"])
        else:
            self._hurt(tgt, r["dmg"] * k, r["elem"])
            if role == "thuy":
                res = self.kinds[tgt.kind]["resist"].get("thuy", 1.0)
                mult = 1 - (1 - r["slow"]) * (res if res < 1 else 1.0)
                until = self.step_n + int(r["slow_s"] * 1000) // STEP_MS
                if tgt.slow_until <= self.step_n or mult <= tgt.slow:
                    tgt.slow = mult
                    if tgt.slow_until < until:
                        tgt.slow_until = until
        pl.cd = r["cd"]
        if self.record_fx:
            self.fx.append(("shot", role, (pl.x, pl.y), self.pos(tgt)))

    def _hurt(self, m: Monster, dmg: float, elem: str | None) -> None:
        if m.dead:
            return
        if elem is not None:
            dmg = dmg * self.kinds[m.kind]["resist"].get(elem, 1.0)
        m.hp -= dmg
        if m.hp <= 0:
            m.dead = True
            self.kills += 1
            self.killed[m.kind] = self.killed.get(m.kind, 0) + 1
            self.qi += self.kinds[m.kind]["qi"]

    def _bury(self) -> None:
        if any(m.dead for m in self.monsters):
            if self.record_fx:
                for m in self.monsters:
                    if m.dead:
                        self.fx.append(("die", self.pos(m), m.kind))
            self.monsters = [m for m in self.monsters if not m.dead]

    def _walk(self) -> None:
        broken = False
        for m in self.monsters:
            kd = self.kinds[m.kind]
            if m.blocked >= 0:
                pl = self.moc_at.get(m.blocked)
                if pl is None or pl.hp <= 0:
                    m.blocked = -1
                else:
                    pl.hp -= kd["atk"] * DT
                    self._hurt(m, self.roles["moc"]["thorns"] * self.strength(pl) * DT, None)
                    if pl.hp <= 0:
                        broken = True
                    continue
            if m.stun_until > self.step_n:
                continue
            speed = kd["speed"]
            if m.slow_until > self.step_n:
                speed = speed * m.slow
            nd = m.d + speed * DT
            i = int(nd + BLOCK_GAP)
            bp = i - BLOCK_GAP
            if i in self.moc_at and self.moc_at[i].hp > 0 and m.d <= bp:
                nd = bp
                m.blocked = i
            m.d = nd
            if m.d >= self.end_d:
                m.dead = True     # reached the Linh Mạch: no kill reward
                self.leaked += 1
                self.hp -= kd["leak"]
                if self.record_fx:
                    self.fx.append(("leak", kd["leak"]))
        if broken:
            for idx, pl in list(self.moc_at.items()):
                if pl.hp <= 0:
                    del self.plants[(pl.x, pl.y)]
                    if self.record_fx:
                        self.fx.append(("fell", (pl.x, pl.y)))
            self._refresh()
        if self.hp <= 0:
            self.hp = 0
            self.phase = LOST
        # leaked monsters are flagged dead; they gave no Linh Khí (see _hurt)

    # ------------------------------------------------------------ results
    def summary(self) -> dict:
        return {"result": self.phase, "core_hp": self.hp, "wave": self.wave, "steps": self.step_n,
                "waves_cleared": self.wave if self.phase in (BUILD, WON) else self.wave - 1}


def replay(params: dict, answers: dict, events: list, max_events: int = 6000, finish: bool = True) -> Sim:
    """Play a whole log: every event at its step, then the wave in progress to its end.
    Raises LogError for an event the rules refuse (wrong order, too little Linh Khí, a
    question that was not answered...). With finish=False it stops right after the last
    event: that is how the client continues a run left unfinished."""
    if not isinstance(events, list) or len(events) > max_events:
        raise LogError("bad_log")
    sim = Sim(params, answers)
    for ev in events:
        if not isinstance(ev, dict):
            raise LogError("bad_event")
        s = ev.get("s")
        if not isinstance(s, int) or isinstance(s, bool) or s < sim.step_n:
            raise LogError("bad_step")
        while sim.step_n < s and sim.phase == WAVE:
            sim.step()
        if sim.step_n != s:
            raise LogError("bad_step")     # time does not pass between waves
        try:
            sim.apply(ev)
        except (TypeError, KeyError, ValueError, IndexError):
            raise LogError("bad_event")     # fields of the wrong type (a hand-made log)
    while finish and sim.phase == WAVE:
        sim.step()
    return sim
