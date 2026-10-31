"""Bí cảnh, the live part (spec 14): matchmaking, Khe Nứt Mực rifts, and one instance per run.

An instance is a private copy of the `bi_canh` map (a ChannelZone of its own, so movement,
Vấn Đạo combat, guard bees and snapshots work exactly as in the world). A run is 3-5 puzzle
rooms in a random order and then the boss's den; the party is moved from room to room when
one is cleared (its puzzle solved and its Mặc Quái beaten). Puzzles are decided here, on
the server, from what the players do: where they stand, which pillar they strike. Each
player only receives the part of a puzzle meant for them (their piece, their words).

Like the rest of the tick, nothing here waits for the database: entering a run, paying loot
and recording what was learned run as background tasks (app/systems/secret_realm.py).
"""
from __future__ import annotations

import datetime as dt
import itertools
import logging
import math
import random
import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .. import balance, clock
from ..config import settings
from ..learning.wordbank import Word, bank
from . import ai, combat, maps, protocol
from .maps import Area
from .zone import ChannelZone, Player

if TYPE_CHECKING:
    from .world import Session, World

log = logging.getLogger("khu_vuon.realm")
MAP = "bi_canh"
VILLAGE = "truc_lam_thon"
PUZZLE_KINDS = ("compose", "sentence", "tone", "mirror", "maze")
TONE_RE = re.compile(r"^([a-z:üv]+)([1-4])$")


def cfg() -> dict:
    return balance.load("realm")


def realm_defs() -> dict:
    from ..systems import secret_realm
    return secret_realm.realms()


def puzzle_info(kind: str) -> dict:
    from ..systems import secret_realm
    return secret_realm.puzzle_info(kind)


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def anchor(a: Area) -> tuple[float, float]:
    """Where a prop stands: the middle of its bottom edge."""
    return a.x + a.w / 2, a.y + a.h


# ------------------------------------------------------------------ the schedule (spec 14.1)
def window_status(now: dt.datetime) -> dict:
    """Is the scheduled realm open? Fixed hours in UTC+7, `open_minutes` long."""
    c = cfg()
    if c.get("always_open"):
        return {"open": True, "opens_in": 0, "closes_in": None}
    sch = c["schedule"]
    local = now + clock.VN_OFFSET
    length = dt.timedelta(minutes=sch["open_minutes"])
    starts = sorted(dt.datetime.combine(local.date() + dt.timedelta(days=d), dt.time(h))
                    for d in (-1, 0, 1) for h in sch["hours_local"])
    for st in starts:
        if st <= local < st + length:
            return {"open": True, "opens_in": 0, "closes_in": int((st + length - local).total_seconds())}
    nxt = next(st for st in starts if st > local)
    return {"open": False, "opens_in": int((nxt - local).total_seconds()), "closes_in": None}


# ------------------------------------------------------------------ words for puzzles
def tone_of(w: Word) -> int | None:
    if not w.single_char:
        return None
    m = TONE_RE.match(w.pinyin_numeric.strip().lower())
    return int(m.group(2)) if m else None


def toneless(w: Word) -> str:
    """'ma1' -> 'ma', 'lu:4' -> 'lü': what the stone statue reads out (spec 14.2)."""
    return re.sub(r"[0-9]", "", w.pinyin_numeric.strip().lower()).replace("u:", "ü").replace("v", "ü")


def composable(w: Word) -> tuple[str, list[str]] | None:
    """A character made of two parts side by side (⿰) or stacked (⿱), e.g. 好 = 女 + 子."""
    if not w.single_char or not w.chars:
        return None
    c = w.chars[0]
    dec, comps = c.get("decomposition") or "", c.get("components") or []
    if len(dec) == 3 and dec[0] in "⿰⿱" and len(comps) == 2 and all(len(x) == 1 and x != "？" for x in comps):
        return dec[0], list(comps)
    return None


@dataclass
class Member:
    uid: int
    name: str
    learned: dict[str, int]          # word id -> mastery (introduced words only)
    state: str = "in"                # in | left


@dataclass
class Rift:
    """A Khe Nứt Mực: seen by whoever walks near it in a public zone for a few minutes."""
    id: str
    realm_id: str
    channel: ChannelZone
    x: float
    y: float
    expires: float
    now: float = 0.0

    def state(self) -> list:
        return [self.id, round(self.x, 1), round(self.y, 1), 0, 0]

    def full(self) -> dict:
        r = realm_defs()[self.realm_id]
        return {"id": self.id, "k": "r", "x": round(self.x, 1), "y": round(self.y, 1), "realm": self.realm_id,
                "n": r["name_vi"], "left": int(max(0.0, self.expires - self.now))}


# ------------------------------------------------------------------ puzzles
class Puzzle:
    kind = ""

    def __init__(self, inst: "RealmInstance"):
        self.inst = inst
        self.rng = inst.rng
        self.solved = False
        self.mistakes = 0

    def public(self, now: float) -> dict:
        return {"kind": self.kind, "solved": self.solved, "fails": self.mistakes}

    def private(self, uid: int) -> dict | None:
        return None

    def tick(self, dt_: float, now: float) -> None:
        pass

    def act(self, p: Player, obj: Area, now: float) -> None:
        pass

    def solve(self, now: float) -> None:
        self.solved = True
        x, y = self.inst.room_center()
        self.inst.event(k="pz", e="solve", x=x, y=y)
        self.inst.push_puzzle(now)

    def mistake(self, now: float, x: float | None = None, y: float | None = None) -> None:
        self.mistakes += 1
        cx, cy = self.inst.room_center()
        self.inst.event(k="pz", e="fail", x=cx if x is None else x, y=cy if y is None else y)


class ComposePuzzle(Puzzle):
    """Cửa Ghép Chữ: the door shows a meaning, the right holders stand on the right stones."""
    kind = "compose"

    def __init__(self, inst: "RealmInstance", now: float):
        super().__init__(inst)
        self.word = self.rng.choice(inst.compose_candidates())
        self.layout, comps = composable(self.word)
        self.slots = ["left", "right"] if self.layout == "⿰" else ["top", "bottom"]
        self.need = dict(zip(self.slots, comps))
        parts = {c for w in bank().words.values() if (x := composable(w)) for c in x[1]}
        self.decoys = sorted(parts - set(comps)) or ["口"]
        self.pieces: dict[int, str] = {}
        self.dealt: set[int] = set()
        self.required: list[str] = list(self.slots)
        self.window_end: float | None = None
        self.cool_until = 0.0
        self.deal()

    def deal(self) -> None:
        uids = [p.user_id for p in self.inst.active()]
        self.rng.shuffle(uids)
        self.required = list(self.slots) if len(uids) >= 2 else self.slots[:1]   # alone: one stone is enough
        self.pieces = {}
        for i, uid in enumerate(uids):
            self.pieces[uid] = self.need[self.required[i]] if i < len(self.required) else self.rng.choice(self.decoys)
        self.dealt = set(uids)
        self.inst.push_private(uids)

    def public(self, now: float) -> dict:
        return {**super().public(now), "meaning": self.word.meaning_vi, "layout": self.layout,
                "slots": self.required, "answer": self.word.hanzi if self.solved else None,
                "window": round(self.window_end - now, 1) if self.window_end else None}

    def private(self, uid: int) -> dict | None:
        return {"piece": self.pieces.get(uid)}

    def _fail(self, now: float, hurt: list[Player], pct: float) -> None:
        for p in hurt:
            self.inst.hurt(p, pct, now)
            self.inst.record(p.user_id, self.word.id, False)
        self.mistake(now)
        self.window_end = None
        self.cool_until = now + 2.5
        self.deal()
        self.inst.push_puzzle(now)

    def tick(self, dt_: float, now: float) -> None:
        if self.solved or now < self.cool_until:
            return
        act = {p.user_id: p for p in self.inst.active()}
        if not self.dealt <= set(act):         # a holder fell or left: the pieces are dealt again
            self.deal()
            self.window_end = None
            self.inst.push_puzzle(now)
            return
        stones = {o.props.get("slot"): o for o in self.inst.objs("pedestal")}
        occ: dict[str, Player] = {}
        anyone = False
        for slot, ped in stones.items():
            on = [p for p in act.values() if self.inst.on(p, ped)]
            anyone = anyone or bool(on)
            if on and slot in self.required:
                occ[slot] = on[0]
        if not anyone:
            if self.window_end is not None:    # everyone stepped off: no harm done, start over
                self.window_end = None
                self.inst.push_puzzle(now)
            return
        if self.window_end is None:
            self.window_end = now + cfg()["compose"]["window_seconds"]
            self.inst.push_puzzle(now)
        if len(occ) == len(self.required):
            wrong = [occ[s] for s in self.required if self.pieces.get(occ[s].user_id) != self.need[s]]
            if not wrong:
                for p in occ.values():
                    self.inst.record(p.user_id, self.word.id, True)
                self.window_end = None
                self.solve(now)
                return
            self._fail(now, wrong, cfg()["puzzle_fail_pct"])
            return
        if now >= self.window_end:              # too slow: the stones throw everyone off
            self._fail(now, list(occ.values()), cfg()["puzzle_fail_pct"] / 2)


class SentencePuzzle(Puzzle):
    """Câu Văn Đứt Đoạn: everyone holds a few words of a sentence; in turn, each steps on the
    numbered stone of the next word's place."""
    kind = "sentence"

    def __init__(self, inst: "RealmInstance", now: float):
        super().__init__(inst)
        self.sentence = self.rng.choice(inst.sentence_candidates())
        self.tokens = [t for t in self.sentence.tokens if t["word_id"]]
        self.n = len(self.tokens)
        self.k = 0
        self.owner: list[int] = [0] * self.n
        self.on_tile: dict[int, int | None] = {}
        self.assign(range(self.n))

    def assign(self, indexes) -> None:
        act = [p.user_id for p in self.inst.active()] or [m.uid for m in self.inst.members.values()
                                                           if m.state == "in"]
        counts = {u: sum(1 for i, o in enumerate(self.owner) if o == u and i >= self.k) for u in act}
        order = list(indexes)
        self.rng.shuffle(order)
        for idx in order:
            wid = self.tokens[idx]["word_id"]
            knows = [u for u in act if wid in self.inst.members[u].learned]
            u = min(knows or act, key=lambda u: (counts[u], self.rng.random()))
            self.owner[idx] = u
            counts[u] += 1
        self.inst.push_private(act)

    def public(self, now: float) -> dict:
        return {**super().public(now), "vi": self.sentence.vi, "n": self.n, "k": self.k,
                "done": [{"t": t["t"], "py": t["pinyin"]} for t in self.tokens[:self.k]]}

    def private(self, uid: int) -> dict | None:
        mine = [{"t": t["t"], "py": t["pinyin"]} for i, t in enumerate(self.tokens) if self.owner[i] == uid and i >= self.k]
        self.rng.shuffle(mine)   # the player learns the words, not their places
        return {"tokens": mine}

    def tick(self, dt_: float, now: float) -> None:
        if self.solved:
            return
        act = {p.user_id: p for p in self.inst.active()}
        gone = [i for i in range(self.k, self.n) if self.owner[i] not in act]
        if gone and act:
            self.assign(gone)
        tiles = {int(o.props.get("n", 0)): o for o in self.inst.objs("tile")}
        for uid, p in act.items():
            here = next((n for n, o in tiles.items() if n <= self.n and self.inst.on(p, o)), None)
            if here != self.on_tile.get(uid):
                self.on_tile[uid] = here
                if here:
                    self.step(p, here, now)
                    if self.solved:
                        return

    def step(self, p: Player, n: int, now: float) -> None:
        if n <= self.k:
            return
        if n > self.k + 1:
            if self.owner[n - 1] == p.user_id and p.session is not None:
                p.session.send({"t": "realm", "event": "hint", "code": "not_yet",
                                "text_vi": f"Đúng chỗ rồi, nhưng còn chờ ô {self.k + 1} trước đã."})
            return
        tok = self.tokens[self.k]
        if self.owner[self.k] == p.user_id:
            self.inst.record(p.user_id, tok["word_id"], True)
            self.k += 1
            self.inst.event(k="pz", e="step", x=p.x, y=p.y, t=tok["t"])
            if self.k >= self.n:
                self.solve(now)
            else:
                self.inst.push_puzzle(now)
                self.inst.push_private([p.user_id])
            return
        self.inst.hurt(p, cfg()["puzzle_fail_pct"], now)
        self.mistake(now, p.x, p.y)
        self.inst.push_puzzle(now)


class TonePuzzle(Puzzle):
    """Trụ Thanh Điệu: the statue reads a syllable; whoever stands nearest the pillar of its
    tone must strike it within 5 seconds. Eight right in a row open the door."""
    kind = "tone"

    def __init__(self, inst: "RealmInstance", now: float):
        super().__init__(inst)
        c = cfg()["tone"]
        self.need = c["streak"]
        self.streak = 0
        self.round: dict | None = None
        self.next_at = now + 3.0
        self.recent: deque = deque(maxlen=4)

    def pillars(self) -> dict[int, Area]:
        return {int(o.props.get("tone", 0)): o for o in self.inst.objs("pillar")}

    def _words(self, wids, tone: int) -> list[Word]:
        b = bank()
        out = [b.words[w] for w in wids if w in b.words and b.words[w].tier <= self.inst.question_tier]
        return [w for w in out if tone_of(w) == tone]

    def new_round(self, now: float) -> None:
        act = self.inst.active()
        if not act:
            return
        union = self.inst.union_learned()
        tones = [t for t in (1, 2, 3, 4) if self._words(union, t)] or [1, 2, 3, 4]
        tone = self.rng.choice(tones)
        ax, ay = anchor(self.pillars()[tone])
        resp = min(act, key=lambda p: dist(p.x, p.y, ax, ay))
        pool = (self._words(self.inst.members[resp.user_id].learned, tone) or self._words(union, tone)
                or [w for w in bank().words.values() if not w.hidden and w.tier <= self.inst.question_tier
                    and tone_of(w) == tone])
        fresh = [w for w in pool if w.id not in self.recent] or pool
        w = self.rng.choice(fresh)
        self.recent.append(w.id)
        c = cfg()["tone"]
        self.round = {"tone": tone, "word": w, "resp": resp.user_id, "asked": now,
                      "deadline": now + c["answer_seconds"] + c["grace"]}
        self.inst.push_puzzle(now)

    def public(self, now: float) -> dict:
        out = {**super().public(now), "streak": self.streak, "need": self.need, "round": None}
        r = self.round
        if r is not None:
            out["round"] = {"hanzi": r["word"].hanzi, "syllable": toneless(r["word"]),
                            "left": round(max(0.0, r["asked"] + cfg()["tone"]["answer_seconds"] - now), 1)}
        return out

    def _end_round(self, now: float, ok: bool, who: Player | None) -> None:
        r = self.round
        self.round = None
        c = cfg()["tone"]
        if who is not None:
            self.inst.record(who.user_id, r["word"].id, ok)
        if ok:
            self.streak += 1
            self.next_at = now + c["pause_seconds"]
            if self.streak >= self.need:
                self.solve(now)
                return
        else:
            self.streak = 0
            self.mistake(now, who.x if who else None, who.y if who else None)
            if who is not None:
                self.inst.hurt(who, cfg()["puzzle_fail_pct"], now)
            self.next_at = now + c["pause_seconds"] * 1.5
        self.inst.send_all({"t": "realm", "event": "tone", "ok": ok, "tone": r["tone"],
                            "pinyin": r["word"].pinyin, "hanzi": r["word"].hanzi, "by": who.name if who else None})
        self.inst.push_puzzle(now)

    def tick(self, dt_: float, now: float) -> None:
        if self.solved:
            return
        if self.round is None:
            if now >= self.next_at:
                self.new_round(now)
            return
        if now >= self.round["deadline"]:        # nobody struck in time: the one nearest pays
            resp = self.inst.players.get(self.round["resp"])
            self._end_round(now, False, resp if resp is not None and not resp.dead else None)

    def act(self, p: Player, obj: Area, now: float) -> None:
        if self.solved or self.round is None or obj.props.get("kind") != "pillar":
            return
        ax, ay = anchor(obj)
        if dist(p.x, p.y, ax, ay) > cfg()["tone"]["reach"]:
            if p.session is not None:
                p.session.send({"t": "realm", "event": "hint", "code": "too_far", "text_vi": "Đứng sát trụ hơn mới đánh được."})
            return
        tone = int(obj.props.get("tone", 0))
        self.inst.event(k="pz", e="strike", x=ax, y=ay - 20, tone=tone, by=p.eid)
        self._end_round(now, tone == self.round["tone"], p)


class MirrorPuzzle(Puzzle):
    """Gương Nghĩa: each player sees one word of their own, the mirror shows a meaning; the
    one whose word means it walks into the mirror. The wrong one costs everyone health."""
    kind = "mirror"

    def __init__(self, inst: "RealmInstance", now: float):
        super().__init__(inst)
        self.need = cfg()["mirror"]["rounds"]
        self.correct = 0
        self.assigned: dict[int, Word] = {}
        self.target: Word | None = None
        self.deadline = 0.0
        self.next_at = now + 2.0
        self.inside: set[int] = set()
        self.used: set[str] = set()

    def mirror(self) -> Area:
        return self.inst.objs("mirror")[0]

    def new_round(self, now: float) -> None:
        act = self.inst.active()
        if not act:
            return
        b = bank()
        tier = self.inst.question_tier
        union = [w for w in (b.words.get(x) for x in self.inst.union_learned()) if w and not w.hidden]
        everyone = [w for w in b.words.values() if not w.hidden and w.tier <= tier]
        self.assigned, taken = {}, set()
        order = list(act)
        self.rng.shuffle(order)
        for p in order:
            own = [b.words[x] for x in self.inst.members[p.user_id].learned if x in b.words]
            for pool in (own, union, everyone):
                ok = [w for w in pool if w.tier <= tier and not w.hidden and not (w.senses & taken)
                      and w.id not in self.used]
                ok = ok or [w for w in pool if w.tier <= tier and not w.hidden and not (w.senses & taken)]
                if ok:
                    w = self.rng.choice(ok)
                    self.assigned[p.user_id] = w
                    taken |= w.senses or {w.id}
                    break
        uid = self.rng.choice(list(self.assigned))
        self.target = self.assigned[uid]
        self.used.add(self.target.id)
        self.deadline = now + cfg()["mirror"]["round_seconds"]
        m = self.mirror()
        self.inside = {p.user_id for p in act if self.inst.on(p, m)}   # those already in must step out first
        self.inst.push_private(list(self.assigned))
        self.inst.push_puzzle(now)

    def public(self, now: float) -> dict:
        return {**super().public(now), "correct": self.correct, "need": self.need,
                "meaning": self.target.meaning_vi if self.target else None,
                "left": round(max(0.0, self.deadline - now), 1) if self.target else None}

    def private(self, uid: int) -> dict | None:
        w = self.assigned.get(uid)
        return {"hanzi": w.hanzi, "pinyin": w.pinyin} if w else {"hanzi": None}

    def tick(self, dt_: float, now: float) -> None:
        if self.solved:
            return
        if self.target is None:
            if now >= self.next_at:
                self.new_round(now)
            return
        m = self.mirror()
        act = self.inst.active()
        for p in act:
            inside = self.inst.on(p, m, pad=0)
            if inside and p.user_id not in self.inside:
                self.inside.add(p.user_id)
                self.judge(p, now)
                return
            if not inside:
                self.inside.discard(p.user_id)
        if now >= self.deadline:     # nobody dared: the mirror clouds over and everyone feels it
            for p in act:
                self.inst.hurt(p, cfg()["team_fail_pct"] / 2, now)
            self.mistake(now)
            self.target = None
            self.next_at = now + 1.5
            self.inst.push_puzzle(now)

    def judge(self, p: Player, now: float) -> None:
        mine, target = self.assigned.get(p.user_id), self.target
        ok = mine is not None and (mine.id == target.id or bool(mine.senses & target.senses))
        self.inst.send_all({"t": "realm", "event": "mirror", "ok": ok, "by": p.name, "hanzi": target.hanzi,
                            "pinyin": target.pinyin, "meaning": target.meaning_vi})
        if ok:
            self.inst.record(p.user_id, target.id, True)
            self.correct += 1
            self.target = None
            if self.correct >= self.need:
                self.solve(now)
                return
            self.next_at = now + 1.5
        else:
            if mine is not None:
                self.inst.record(p.user_id, mine.id, False)
            for q in self.inst.active():
                self.inst.hurt(q, cfg()["team_fail_pct"], now)
            self.mistake(now, p.x, p.y)
            self.target = None
            self.next_at = now + 2.0
        self.inst.push_puzzle(now)


class MazePuzzle(Puzzle):
    """Mê Cung Mực: dark corridors. Players who learned 明 (or 光) shed light; whoever stands
    in the dark loses a little health every second. Everyone at the exit opens the door."""
    kind = "maze"

    def __init__(self, inst: "RealmInstance", now: float):
        super().__init__(inst)
        c = cfg()["maze"]
        b = bank()
        self.light_ids = {b.by_hanzi[h].id for h in c["light_words"] if h in b.by_hanzi}
        self.carriers: list[int] = []
        self.lantern = False
        self.radius = c["light_radius"]
        self.dark: dict[int, float] = {}
        self.in_exit = -1
        self.pick_carriers()

    def pick_carriers(self) -> None:
        c = cfg()["maze"]
        act = self.inst.active()
        self.carriers = [p.user_id for p in act if self.light_ids & set(self.inst.members[p.user_id].learned)]
        self.lantern = not self.carriers
        if self.lantern and act:   # nobody knows 明 yet: the most learned one gets a weak lantern
            best = max(act, key=lambda p: (len(self.inst.members[p.user_id].learned), -p.user_id))
            self.carriers = [best.user_id]
        self.radius = c["lantern_radius"] if self.lantern else c["light_radius"]

    def public(self, now: float) -> dict:
        return {**super().public(now), "carriers": self.carriers, "radius": self.radius, "lantern": self.lantern,
                "self_radius": cfg()["maze"]["self_radius"], "in_exit": max(0, self.in_exit),
                "need": len(self.inst.active())}

    def tick(self, dt_: float, now: float) -> None:
        if self.solved:
            return
        act = self.inst.active()
        if not act:
            return
        lights = [p for p in act if p.user_id in self.carriers]
        if not lights:
            self.pick_carriers()
            self.inst.push_puzzle(now)
            return
        pct = cfg()["maze"]["dark_dps_pct"]
        for p in act:
            if any(dist(p.x, p.y, q.x, q.y) <= self.radius for q in lights):
                self.dark.pop(p.user_id, None)
                continue
            acc = self.dark.get(p.user_id, 0.0) + dt_
            if acc >= 1.0:   # the ink bites once a second (one hit event, not twenty)
                acc -= 1.0
                self.inst.hurt(p, pct, now, kind="hit")
            self.dark[p.user_id] = acc
        door = self.inst.objs("maze_exit")[0]
        n = sum(1 for p in act if self.inst.on(p, door, pad=6))
        if n != self.in_exit:
            self.in_exit = n
            self.inst.push_puzzle(now)
        if n >= len(act):
            self.solve(now)


class BossPuzzle(Puzzle):
    """The den: solved when the Nghiên Ma falls (its shield rules live in combat.py)."""
    kind = "boss"

    def public(self, now: float) -> dict:
        b = self.inst.boss
        out = super().public(now)
        if b is not None:
            out.update({"boss": b.eid, "hp": b.hp_pct(), "shield": int(b.shield), "phase": 4 - len(b.regen),
                        "hits": len(b.group_hits), "need": self.inst.group_need(b)})
        return out

    def tick(self, dt_: float, now: float) -> None:
        b = self.inst.boss
        if b is not None and not b.alive and not self.solved:
            self.solved = True


PUZZLES = {"compose": ComposePuzzle, "sentence": SentencePuzzle, "tone": TonePuzzle, "mirror": MirrorPuzzle,
           "maze": MazePuzzle}


# ------------------------------------------------------------------ one run
class RealmInstance(ChannelZone):
    instance = True

    def __init__(self, world: "World", run_id: int, realm_id: str, members: dict[int, Member],
                 rng: random.Random | None = None, rooms: list[str] | None = None):
        super().__init__(MAP, run_id, maps.load(MAP), rng or random.Random())
        self.monsters = []
        self.world = world
        self.run_id, self.realm_id = run_id, realm_id
        self.rdef = realm_defs()[realm_id]
        self.question_tier = int(self.rdef["tier"])
        self.members = members
        self._union: set[str] | None = None
        self.rooms = list(rooms) if rooms else self._pick_rooms()
        self.room_i = -1
        self.puzzle: Puzzle | None = None
        self.phase = "starting"            # starting | running | advancing | ended
        self.started = world.mono()
        self.deadline = self.started + self.rdef["time_limit_minutes"] * 60
        self.advance_at = 0.0
        self.end_at = 0.0
        self.flawless = 0
        self.result: str | None = None
        self.boss: ai.Monster | None = None
        self.boss_wake = 0.0
        self.next_aoe = 0.0
        self.aoes: list[tuple] = []
        self._mid = itertools.count()

    # ------------------------------------------------------------ words
    def union_learned(self) -> set[str]:
        if self._union is None:
            b = bank()
            self._union = {w for m in self.members.values() for w in m.learned
                           if w in b.words and b.words[w].tier <= self.question_tier}
        return self._union

    def compose_candidates(self) -> list[Word]:
        b = bank()
        return [b.words[w] for w in sorted(self.union_learned()) if composable(b.words[w])]

    def sentence_candidates(self) -> list:
        c = cfg()["sentence"]
        known = self.union_learned()
        tiles = len([o for o in self.map.realm_objs if o.props.get("kind") == "tile"])
        out = []
        for s in bank().sentences.values():
            words = [t["word_id"] for t in s.tokens if t["word_id"]]
            if (s.tier <= self.question_tier and (s.reviewed or settings.allow_unreviewed)
                    and c["min_tokens"] <= len(words) <= min(c["max_tokens"], tiles) and set(words) <= known):
                out.append(s)
        return out

    def _pick_rooms(self) -> list[str]:
        kinds = [k for k in PUZZLE_KINDS if (k != "compose" or self.compose_candidates())
                 and (k != "sentence" or self.sentence_candidates())]
        self.rng.shuffle(kinds)
        return kinds[:max(1, min(int(self.rdef["puzzles"]), len(kinds)))] + ["boss"]

    # ------------------------------------------------------------ places and people
    @property
    def kind(self) -> str | None:
        return self.rooms[self.room_i] if 0 <= self.room_i < len(self.rooms) else None

    def objs(self, kind: str) -> list[Area]:
        return [o for o in self.map.realm_objs if o.props.get("room") == self.kind and o.props.get("kind") == kind]

    def room_center(self) -> tuple[float, float]:
        a = self.map.rooms[self.kind]
        return a.x + a.w / 2, a.y + a.h / 2

    def on(self, p: Player, a: Area, pad: float | None = None) -> bool:
        pad = cfg()["stand_pad"] if pad is None else pad
        return a.x - pad <= p.x <= a.x + a.w + pad and a.y - pad <= p.y <= a.y + a.h + pad

    def present(self) -> list[Player]:
        return [p for p in self.players.values()
                if (m := self.members.get(p.user_id)) is not None and m.state == "in"]

    def active(self) -> list[Player]:
        """Who can play right now: connected, standing (not a ghost)."""
        return [p for p in self.present() if p.session is not None and not p.dead]

    def group_need(self, m: ai.Monster) -> int:
        """Spec 14.2: the boss's big shield needs as many right answers (from different players)
        as there are members still alive."""
        return max(1, len(self.active()))

    def exit_pos(self) -> tuple[float, float]:
        from .world import zone_defs
        return maps.load(zone_defs()[VILLAGE]["map"]).spawn("from_realm")

    # ------------------------------------------------------------ messages
    def send_all(self, msg: dict) -> None:
        for p in self.present():
            if p.session is not None:
                p.session.send(msg)

    def run_msg(self, now: float) -> dict:
        return {"t": "realm", "event": "start", "run": {
            "id": self.run_id, "realm": self.realm_id, "name_vi": self.rdef["name_vi"],
            "hanzi": self.rdef.get("hanzi", ""), "left": int(max(0, self.deadline - now)),
            "rooms": [{"kind": k, "name_vi": puzzle_info(k).get("name_vi", k)} for k in self.rooms],
            "members": [{"uid": m.uid, "name": m.name, "in": m.state == "in"} for m in self.members.values()]}}

    def room_msg(self, uid: int, now: float) -> dict:
        info = puzzle_info(self.kind)
        return {"t": "realm", "event": "room", "i": self.room_i, "n": len(self.rooms), "kind": self.kind,
                "name_vi": info.get("name_vi", self.kind), "hanzi": info.get("hanzi", ""),
                "how_vi": info.get("how_vi", ""), "left": int(max(0, self.deadline - now)), "phase": self.phase,
                "puzzle": self.puzzle.public(now) if self.puzzle else None,
                "mine": self.puzzle.private(uid) if self.puzzle else None}

    def push_puzzle(self, now: float) -> None:
        if self.puzzle is not None:
            self.send_all({"t": "realm", "event": "puzzle", "i": self.room_i, "puzzle": self.puzzle.public(now)})

    def push_private(self, uids) -> None:
        if self.puzzle is None:
            return
        for uid in uids:
            p = self.players.get(uid)
            if p is not None and p.session is not None:
                p.session.send({"t": "realm", "event": "mine", "i": self.room_i, "mine": self.puzzle.private(uid)})

    def resync(self, p: Player) -> None:
        """A player came back after losing the connection (spec 14.3): everything again."""
        now = self.world.mono()
        if p.session is None:
            return
        p.session.send(self.run_msg(now))
        if self.kind is not None:
            p.session.send(self.room_msg(p.user_id, now))
        if self.phase == "ended":
            p.session.send(self.end_msg(now))

    # ------------------------------------------------------------ effects on players
    def hurt(self, p: Player, pct: float, now: float, kind: str = "mk") -> None:
        if not p.dead:
            combat.hurt_player(self, p, p.max_hp * pct / 100, now, kind=kind, by="pz")

    def record(self, uid: int, word_id: str, correct: bool) -> None:
        m = self.members.get(uid)
        if m is not None and word_id in m.learned:
            from ..systems import secret_realm
            self.world.spawn(secret_realm.record_answer(uid, word_id, correct))

    def _ghost_changed(self, p: Player) -> None:
        for other in self.players.values():
            other.known.pop(p.eid, None)   # everyone gets this player again, drawn as a ghost (or not)

    def on_down(self, p: Player, now: float) -> None:
        """Out of health in a bí cảnh: a ghost that follows the party until the next room."""
        p.dead, p.ghost, p.hp = True, True, 0.0
        p.respawn_at = float("inf")
        for m in self.monsters:
            m.engaged.discard(p.user_id)
        if p.question:
            combat.end_question(p, "dead")
        p.next_q = None
        self.event(k="die", id=p.eid, x=p.x, y=p.y)
        self._ghost_changed(p)
        if p.session is not None:
            p.session.send({"t": "dead", "ghost": 1, "respawn_in": 0})

    def revive(self, p: Player, pct: float | None = None) -> None:
        if not p.ghost and not p.dead:
            return
        p.dead = p.ghost = False
        p.hp = max(1.0, p.max_hp * (cfg()["revive_hp_pct"] if pct is None else pct) / 100)
        p.respawn_at = 0.0
        self._ghost_changed(p)
        self.event(k="heal", id=p.eid, v=int(p.hp), x=p.x, y=p.y)
        if p.session is not None:
            p.session.send({"t": "realm", "event": "revived", "hp": int(p.hp)})

    # ------------------------------------------------------------ the run
    def begin(self, now: float) -> None:
        self.phase = "running"
        x, y = self.map.spawn(f"{self.rooms[0]}_entry")
        for i, (uid, m) in enumerate(self.members.items()):
            s = self.world.sessions.get(uid)
            if s is None:
                self._member_gone(m, "disconnected")
                continue
            self.world.put(s, self, *self._spread(x, y, i), "up")
        self.send_all(self.run_msg(now))
        self._start_room(0, now)

    def _spread(self, x: float, y: float, i: int) -> tuple[float, float]:
        dx = (0, -26, 26, -52, 52)[i % 5]
        return (x + dx, y) if not self.map.collider.blocked(x + dx, y) else (x, y)

    def _teleport(self, p: Player, x: float, y: float) -> None:
        p.x, p.y, p.facing = float(x), float(y), "up"
        p.inputs.clear()
        p.queued_ms = 0
        p.budget_ms = 0.0
        p.moving = False
        p.known = {}   # the client forgets everyone on a zone message: send them all again
        if p.session is not None:
            self.world._send_zone(p.session, p)

    def _spawn_monsters(self, now: float) -> None:
        kind = self.kind
        area = self.map.rooms[kind]
        if kind == "maze":
            return
        if kind == "boss":
            bs = self.objs("boss_spawn")[0]
            m = ai.Monster(f"m{self.run_id}_{next(self._mid)}", self.rdef["boss"], area, bs.x + 8, bs.y + 12)
            extra = max(0, len(self.present()) - 1)
            m.hp_scale = self.rdef.get("boss_hp_mult", 1.0) * (1 + cfg()["boss"]["hp_per_extra_member"] * extra)
            m.reset()
            self.boss = m
            self.monsters.append(m)
            self.boss_wake = now + 3.0
            self.next_aoe = now + cfg()["boss"]["aoe_every"]
            return
        for mkind, count in self.rdef["room_monsters"].items():
            for _ in range(int(count)):
                x, y = self._free_spot(area)
                m = ai.Monster(f"m{self.run_id}_{next(self._mid)}", mkind, area, x, y)
                m.idle = self.rng.uniform(0.5, 2.0)
                self.monsters.append(m)

    def _free_spot(self, a: Area) -> tuple[float, float]:
        for _ in range(40):   # the far half of the room, away from the entrance
            x = self.rng.uniform(a.x + 24, a.x + a.w - 24)
            y = self.rng.uniform(a.y + 20, a.y + a.h * 0.45)
            if not self.map.collider.blocked(x, y):
                return x, y
        return a.x + a.w / 2, a.y + 40

    def _start_room(self, i: int, now: float) -> None:
        self.room_i = i
        self.monsters = []
        self.boss, self.aoes = None, []
        self.puzzle = None
        x, y = self.map.spawn(f"{self.kind}_entry")
        if i > 0:   # (the first room: begin() just put everyone there)
            for n, p in enumerate(self.present()):
                self._teleport(p, *self._spread(x, y, n))
        self._spawn_monsters(now)
        self._rebuild_grid()   # the snapshot of this very tick already sees everyone in the new room
        self.puzzle = BossPuzzle(self) if self.kind == "boss" else PUZZLES[self.kind](self, now)
        self.phase = "running"
        for p in self.present():
            if p.session is not None:
                p.session.send(self.room_msg(p.user_id, now))

    def _room_cleared(self, now: float) -> None:
        i, kind = self.room_i, self.kind
        flawless = self.puzzle.mistakes == 0
        if kind != "boss" and flawless:
            self.flawless += 1
        for uid, m in self.members.items():
            if m.state == "in":
                self.world.spawn(self._pay_room(uid, i, kind))
        x, y = anchor(self.objs("exit")[0])
        self.event(k="pz", e="open", x=x, y=y)
        if kind == "boss":
            self._finish("won", now)
            return
        self.phase = "advancing"
        self.advance_at = now + cfg()["advance_seconds"]
        self.send_all({"t": "realm", "event": "cleared", "i": i, "flawless": flawless,
                       "next_in": cfg()["advance_seconds"]})

    def _advance(self, now: float) -> None:
        for p in self.present():   # spec 14.2: ghosts come back when the party moves on
            self.revive(p)
        self._start_room(self.room_i + 1, now)

    def end_msg(self, now: float) -> dict:
        elapsed = (self.end_at - cfg()["exit_seconds"]) - self.started
        return {"t": "realm", "event": "end", "result": self.result, "time": int(elapsed), "flawless": self.flawless,
                "puzzles": len(self.rooms) - 1, "fast": self._fast(), "fragments": self._fragments(),
                "exit_in": int(max(0, self.end_at - now))}

    def _fast(self) -> bool:
        took = (self.end_at - cfg()["exit_seconds"]) - self.started
        return self.result == "won" and took <= self.rdef["time_limit_minutes"] * 60 * cfg()["fast_fraction"]

    def _fragments(self) -> int:
        if self.result != "won":
            return 0
        c = cfg()
        return c["chest"][self.realm_id]["fragments"] + self.flawless * c["flawless_fragments"]

    def _finish(self, result: str, now: float) -> None:
        if self.phase == "ended":
            return
        from ..systems import secret_realm
        self.phase, self.result = "ended", result
        self.end_at = now + cfg()["exit_seconds"]
        for m in self.monsters:
            m.engaged = set()
            m.tele = None
        self.aoes = []
        for p in self.players.values():
            if p.question:
                combat.end_question(p, "realm_end")
            p.next_q = None
            self.revive(p)
        inside = [uid for uid, m in self.members.items() if m.state == "in"]
        if result == "won":
            for uid in inside:
                self.world.spawn(self._pay_chest(uid, self._fragments(), self._fast()))
        self.world.spawn(secret_realm.finish_run(self.run_id, result, inside))
        self.send_all(self.end_msg(now))

    async def _pay_room(self, uid: int, i: int, kind: str) -> None:
        from ..systems import secret_realm
        try:
            loot = await secret_realm.claim_room(self.run_id, uid, i, kind)
        except Exception:
            log.exception("room loot failed")
            return
        if loot is not None:
            self.world.notify(uid, {"t": "realm", "event": "loot", "loot": loot})

    async def _pay_chest(self, uid: int, fragments: int, fast: bool) -> None:
        from ..systems import secret_realm
        try:
            loot = await secret_realm.claim_chest(self.run_id, uid, self.realm_id, fragments, fast)
        except Exception:
            log.exception("chest loot failed")
            return
        if loot is not None:
            self.world.notify(uid, {"t": "realm", "event": "loot", "loot": loot})

    # ------------------------------------------------------------ leaving
    def _member_gone(self, m: Member, why: str) -> None:
        if m.state != "in":
            return
        from ..systems import secret_realm
        m.state = "left"
        self.world.spawn(secret_realm.member_left(self.run_id, m.uid, why))
        self.send_all({"t": "realm", "event": "member_left", "uid": m.uid, "name": m.name, "reason": why})

    def leave(self, p: Player, now: float) -> None:
        """The player walks out (keeping the loot of the rooms already cleared)."""
        m = self.members.get(p.user_id)
        if m is not None:
            self._member_gone(m, "left")
        self._exit(p)

    def member_lost(self, p: Player) -> None:
        """Called by the world when a disconnected member did not come back in time."""
        m = self.members.get(p.user_id)
        if m is not None:
            self._member_gone(m, "disconnected")
        self.revive(p)

    def _exit(self, p: Player) -> None:
        self.revive(p)
        if p.session is not None:
            x, y = self.exit_pos()
            self.world._place(p.session, VILLAGE, x, y, "down")
            p.session.send({"t": "realm", "event": "left"})
        else:
            self.world._leave_world(p)

    def act(self, p: Player, name: str, now: float) -> None:
        if self.phase != "running" or p.dead or self.puzzle is None:
            return
        obj = next((o for o in self.map.realm_objs if o.name == name and o.props.get("room") == self.kind), None)
        if obj is not None:
            self.puzzle.act(p, obj, now)

    # ------------------------------------------------------------ tick
    def _boss_tick(self, now: float) -> None:
        b = self.boss
        if b is None or not b.alive or now < self.boss_wake:
            return
        c = cfg()["boss"]
        for p in self.active():
            if p.user_id not in b.engaged:
                combat.engage(self, b, p, now)
        if b.shield and b.group_hits and len(b.group_hits) >= self.group_need(b):
            combat.break_shield(self, b, None, now)   # someone fell: the ones left already did enough
        if now >= self.next_aoe:
            self.next_aoe = now + c["aoe_every"]
            targets = self.active()
            if targets:   # Mặc Triều: a wide red circle under someone, then a wave of ink
                t = self.rng.choice(targets)
                self.aoes.append((t.x, t.y, c["aoe_radius"], now + c["aoe_delay"]))
                self.event(k="tele", id=b.eid, x=round(t.x, 1), y=round(t.y, 1), r=c["aoe_radius"],
                           d=c["aoe_delay"], big=1)
        for a in list(self.aoes):
            x, y, r, land = a
            if now < land:
                continue
            self.aoes.remove(a)
            self.event(k="pz", e="wave", x=x, y=y, r=r)
            for p in self.active():
                if dist(p.x, p.y, x, y) <= r + 5:
                    combat.hurt_player(self, p, p.max_hp * c["aoe_pct"] / 100, now, by=b.eid)
        if self.puzzle is not None and self.tick_count % 10 == 0:
            self.push_puzzle(now)   # boss health, phase and shield progress twice a second

    def tick(self, dt_: float, now: float) -> None:
        super().tick(dt_, now)
        if self.phase == "ended":
            if now >= self.end_at:
                for p in list(self.players.values()):
                    m = self.members.get(p.user_id)
                    if m is not None and m.state == "in":
                        m.state = "left"
                    self._exit(p)
            return
        if self.phase == "starting":
            return
        if not any(m.state == "in" for m in self.members.values()) or not self.players:
            self._finish("abandoned", now)
            return
        if now >= self.deadline:
            self._finish("timeout", now)
            return
        present = self.present()
        if present and all(p.dead for p in present):
            self._finish("failed", now)
            return
        if self.phase == "advancing":
            if now >= self.advance_at:
                self._advance(now)
            return
        if self.puzzle is not None:
            self.puzzle.tick(dt_, now)
        if self.kind == "boss":
            self._boss_tick(now)
        if self.puzzle is not None and self.puzzle.solved and self.phase == "running" \
                and all(not m.alive for m in self.monsters):
            self._room_cleared(now)


# ------------------------------------------------------------------ the service in the world
class RealmService:
    def __init__(self, world: "World"):
        self.world = world
        self.instances: dict[int, RealmInstance] = {}
        self.rifts: dict[str, Rift] = {}
        self.queues: dict[str, list[list]] = {}          # key (realm id or 'rift:<id>') -> [[uid, realm idx, since]]
        self.queued: dict[int, str] = {}                 # uid -> key
        self.starting: set[int] = set()                  # players whose entry is being written
        self.rng = random.Random()
        self.room_order: list[str] | None = None         # tests: a fixed room order
        self._rift_ids = itertools.count(1)
        self._next_rift = 0.0
        self._next_queue = 0.0
        self._next_announce = 0.0
        self._announced: set[tuple] = set()

    def instance_of(self, p: Player | None) -> RealmInstance | None:
        ch = p.channel if p is not None else None
        return ch if isinstance(ch, RealmInstance) else None

    # ------------------------------------------------------------ checks
    def _err(self, s: "Session", code: str, text: str) -> None:
        s.send(protocol.error(code, text))

    def check_members(self, uids: list[int], rdef: dict, starting_ok: bool = False) -> str | None:
        from ..systems import cultivation
        from .world import realm_index
        for uid in uids:
            s = self.world.sessions.get(uid)
            p = self.world.players.get(uid)
            if s is None:
                return "Có thành viên đang ngoại tuyến."
            if p is None or p.channel is None:
                return f"{s.name} đang ở động phủ, hãy ra Trúc Lâm Thôn trước."
            if self.instance_of(p) is not None:
                return f"{s.name} đang ở trong một bí cảnh khác."
            if p.dead:
                return f"{s.name} đang trọng thương."
            if uid in self.starting and not starting_ok:
                return f"{s.name} đang vào một bí cảnh khác."
            if realm_index(s.realm) < realm_index(rdef["min_realm"]):
                return f"{s.name} chưa đạt {cultivation.realm_name(rdef['min_realm'])}."
        return None

    def _near_gate(self, p: Player) -> bool:
        if p.channel is None or p.channel.zone_id != VILLAGE or self.instance_of(p):
            return False
        gate = p.channel.map.interacts.get("realm")
        return gate is not None and dist(p.x, p.y, *gate) <= 90

    def _near_rift(self, p: Player, r: Rift) -> bool:
        return p.channel is r.channel and dist(p.x, p.y, r.x, r.y) <= cfg()["rift"]["use_radius"]

    def _target(self, s: "Session", m: protocol.RealmCmd) -> tuple[str, str] | None:
        """(realm id, queue key) of what the player asks for, or None after an error."""
        p = s.player
        if m.rift:
            r = self.rifts.get(m.rift)
            if r is None or r.expires <= self.world.mono():
                self._err(s, "rift_gone", "Khe nứt đã khép lại mất rồi.")
                return None
            if p is None or not self._near_rift(p, r):
                self._err(s, "too_far", "Hãy đứng sát khe nứt.")
                return None
            return r.realm_id, f"rift:{r.id}"
        rdef = realm_defs().get(m.realm or "")
        if rdef is None or rdef["kind"] != "scheduled":
            self._err(s, "no_realm", "Không có bí cảnh này.")
            return None
        if not window_status(clock.now())["open"]:
            self._err(s, "realm_closed", "Bí cảnh chưa mở cửa. Xem giờ mở ở Cổng Bí Cảnh.")
            return None
        if p is None or not self._near_gate(p):
            self._err(s, "too_far", "Hãy tới Cổng Bí Cảnh ở Trúc Lâm Thôn.")
            return None
        return m.realm, m.realm

    # ------------------------------------------------------------ messages
    def handle(self, s: "Session", m: protocol.RealmCmd) -> None:
        now = self.world.mono()
        if m.op == "leave":
            inst = self.instance_of(s.player)
            if inst is None:
                self._err(s, "not_in_realm", "Bạn không ở trong bí cảnh.")
            else:
                inst.leave(s.player, now)
            return
        if m.op == "unqueue":
            self.unqueue(s.user_id)
            return
        target = self._target(s, m)
        if target is None:
            return
        realm_id, key = target
        rdef = realm_defs()[realm_id]
        party = self.world.parties.party_of(s.user_id)
        if m.op == "queue":
            if party is not None:
                self._err(s, "in_party", "Tổ đội thì đội trưởng bấm Vào bí cảnh; hàng chờ dành cho người đi một mình.")
                return
            err = self.check_members([s.user_id], rdef)
            if err:
                self._err(s, "cannot_enter", err)
                return
            self.unqueue(s.user_id, notify=False)
            from .world import realm_index
            self.queues.setdefault(key, []).append([s.user_id, realm_index(s.realm), now])
            self.queued[s.user_id] = key
            self._queue_news(key)
            return
        c = cfg()
        if party is None or len(party.members) < c["party_min"]:
            self._err(s, "need_party", f"Cần tổ đội {c['party_min']}-{c['party_max']} người. "
                                       "Mời bạn vào đội, hoặc vào hàng chờ ghép đội.")
            return
        if party.leader != s.user_id:
            self._err(s, "not_leader", "Chỉ đội trưởng mới dẫn đội vào bí cảnh.")
            return
        err = self.check_members(party.members, rdef)
        if err:
            self._err(s, "cannot_enter", err)
            return
        self.start(list(party.members), realm_id)

    def act(self, s: "Session", m: protocol.RealmAct) -> None:
        inst = self.instance_of(s.player)
        if inst is not None:
            inst.act(s.player, m.obj, self.world.mono())

    # ------------------------------------------------------------ entering
    def start(self, uids: list[int], realm_id: str) -> None:
        self.starting |= set(uids)
        for uid in uids:
            self.unqueue(uid, notify=False)
            self.world.notify(uid, {"t": "realm", "event": "entering", "realm": realm_id,
                                    "name_vi": realm_defs()[realm_id]["name_vi"]})
        self.world.spawn(self._start(list(uids), realm_id))

    async def _start(self, uids: list[int], realm_id: str) -> None:
        from .. import db as dbm
        from ..systems import secret_realm
        rdef = realm_defs()[realm_id]
        try:
            try:
                async with dbm.SessionLocal() as db:
                    over = await secret_realm.over_limit(db, uids, realm_id)
                    if over:
                        names = ", ".join(self.world.sessions[u].name for u in over if u in self.world.sessions)
                        for uid in uids:
                            self.world.notify(uid, protocol.error(
                                "daily_limit", f"{names} đã vào {rdef['name_vi']} {cfg()['daily_entries']} lần hôm nay rồi."))
                        return
                    run_id = await secret_realm.create_run(db, realm_id, uids)
                    learned = await secret_realm.learned_words(db, uids)
                    await db.commit()
            except Exception:
                log.exception("could not open a realm run")
                for uid in uids:
                    self.world.notify(uid, protocol.error("realm_error", "Bí cảnh chưa mở được, thử lại sau nhé."))
                return
            err = self.check_members(uids, rdef, starting_ok=True)
            if err:   # someone walked off while the gate was opening: nobody loses an entry
                await secret_realm.abort_run(run_id)
                for uid in uids:
                    self.world.notify(uid, protocol.error("cannot_enter", err))
                return
            members = {uid: Member(uid, self.world.sessions[uid].name, learned.get(uid, {})) for uid in uids}
            try:
                inst = RealmInstance(self.world, run_id, realm_id, members, random.Random(), rooms=self.room_order)
            except Exception:
                log.exception("could not build a realm run")
                await secret_realm.abort_run(run_id)
                for uid in uids:
                    self.world.notify(uid, protocol.error("realm_error", "Bí cảnh chưa mở được, thử lại sau nhé."))
                return
            self.instances[run_id] = inst
            inst.begin(self.world.mono())
        finally:
            self.starting -= set(uids)

    # ------------------------------------------------------------ the queue (spec 14.1)
    def unqueue(self, uid: int, notify: bool = True) -> None:
        key = self.queued.pop(uid, None)
        if key is None:
            return
        self.queues[key] = [e for e in self.queues.get(key, []) if e[0] != uid]
        if not self.queues[key]:
            del self.queues[key]
        if notify:
            self.world.notify(uid, {"t": "realm", "event": "unqueued"})
        if key in self.queues:
            self._queue_news(key)

    def queue_of(self, uid: int) -> dict | None:
        key = self.queued.get(uid)
        if key is None:
            return None
        realm_id = self.rifts[key[5:]].realm_id if key.startswith("rift:") and key[5:] in self.rifts else key
        return {"key": key, "realm": realm_id, "waiting": len(self.queues.get(key, []))}

    def _queue_news(self, key: str) -> None:
        for e in self.queues.get(key, []):
            self.world.notify(e[0], {"t": "realm", "event": "queued", **(self.queue_of(e[0]) or {})})

    def _queue_tick(self, now: float) -> None:
        c = cfg()
        pmin, pmax, fill = c["party_min"], c["party_max"], c["queue"]["fill_seconds"]
        for key in list(self.queues):
            rift = self.rifts.get(key[5:]) if key.startswith("rift:") else None
            realm_id = rift.realm_id if rift else key
            keep = []
            for e in self.queues[key]:
                p = self.world.players.get(e[0])
                ok = (e[0] in self.world.sessions and p is not None and p.channel is not None and not p.dead
                      and self.instance_of(p) is None and e[0] not in self.starting
                      and self.world.parties.party_of(e[0]) is None
                      and (rift is not None and self._near_rift(p, rift) if key.startswith("rift:") else True))
                if ok:
                    keep.append(e)
                else:
                    self.queued.pop(e[0], None)
                    self.world.notify(e[0], {"t": "realm", "event": "unqueued"})
            groups: dict[int, list] = {}
            for e in keep:
                groups.setdefault(e[1], []).append(e)
            ready = [g for g in groups.values() if len(g) >= pmax or (len(g) >= pmin and now - min(x[2] for x in g) >= fill)]
            if not ready and len(keep) >= pmin and now - min(x[2] for x in keep) >= fill * 2:
                ready = [keep]   # few people online: after a while, mix the realms
            taken = set()
            for g in ready:
                g = sorted(g, key=lambda x: x[2])[:pmax]
                uids = [x[0] for x in g]
                taken |= set(uids)
                for uid in uids:
                    self.queued.pop(uid, None)
                self.world.parties.form(uids)
                err = self.check_members(uids, realm_defs()[realm_id])
                if err:
                    for uid in uids:
                        self.world.notify(uid, protocol.error("cannot_enter", err))
                    continue
                self.start(uids, realm_id)
            self.queues[key] = [e for e in keep if e[0] not in taken]
            if not self.queues[key]:
                del self.queues[key]

    # ------------------------------------------------------------ rifts (spec 14.1)
    def spawn_rift(self, ch: ChannelZone, now: float, x: float | None = None, y: float | None = None) -> Rift:
        rc = cfg()["rift"]
        if x is None or y is None:
            players = list(ch.players.values())
            base = self.rng.choice(players) if players else None
            x, y = (base.x, base.y) if base else (ch.map.width_px / 2, ch.map.height_px / 2)
            for _ in range(40):
                a, d = self.rng.uniform(0, 6.283), self.rng.uniform(70, 170)
                tx, ty = x + math.cos(a) * d, y + math.sin(a) * d
                if 24 < tx < ch.map.width_px - 24 and 24 < ty < ch.map.height_px - 24 and not ch.map.collider.blocked(tx, ty):
                    x, y = tx, ty
                    break
        r = Rift(f"r{next(self._rift_ids)}", rc["realm"], ch, float(x), float(y), now + rc["life_seconds"], now)
        self.rifts[r.id] = r
        ch.extras.append(r)
        name = realm_defs()[r.realm_id]["name_vi"]
        for p in ch.players.values():
            if p.session is not None and dist(p.x, p.y, r.x, r.y) <= 420:
                p.session.send({"t": "notice", "text": f"Một {name} vừa rách ra gần đây! Rủ nhau vào trước khi nó khép lại."})
        return r

    def _rift_tick(self, now: float) -> None:
        for rid, r in list(self.rifts.items()):
            r.now = now
            if now >= r.expires:
                del self.rifts[rid]
                if r in r.channel.extras:
                    r.channel.extras.remove(r)
        if now < self._next_rift:
            return
        rc = cfg()["rift"]
        self._next_rift = now + rc["check_seconds"]
        for zone_id in rc["zones"]:
            for ch in self.world.channels.get(zone_id, []):
                if len(self.rifts) >= rc["max_open"]:
                    return
                if ch.players and not any(r.channel is ch for r in self.rifts.values()) \
                        and self.rng.random() < rc["chance"]:
                    self.spawn_rift(ch, now)

    # ------------------------------------------------------------ announcements (spec 14.1)
    def _announce_tick(self) -> None:
        c = cfg()
        if c.get("always_open"):
            return
        st = window_status(clock.now())
        names = [r["name_vi"] for r in realm_defs().values() if r["kind"] == "scheduled"]
        if not names:
            return
        if st["open"]:
            key = ("open", int(clock.now().timestamp() + st["closes_in"]) // 60)
            text = f"{', '.join(names)} đã mở cửa ở Cổng Bí Cảnh (Trúc Lâm Thôn), còn {st['closes_in'] // 60} phút!"
        elif st["opens_in"] <= c["schedule"]["announce_minutes"] * 60:
            key = ("soon", int(clock.now().timestamp() + st["opens_in"]) // 60)
            text = f"{', '.join(names)} sẽ mở cửa sau {max(1, round(st['opens_in'] / 60))} phút. Lập tổ đội đi thôi!"
        else:
            return
        if key in self._announced:
            return
        self._announced.add(key)
        for s in list(self.world.sessions.values()):
            s.send({"t": "notice", "text": text})

    # ------------------------------------------------------------ tick
    def tick(self, dt_: float, now: float, server_time: float, snap_every: int) -> None:
        for inst in list(self.instances.values()):
            inst.tick(dt_, now)
            if inst.tick_count % snap_every == 0 and inst.awake:
                for p in inst.players.values():
                    if p.session is not None:
                        p.session.send(inst.snapshot_for(p, server_time))
                inst.events = []
            elif not inst.awake:
                inst.events = []
            if inst.phase == "ended" and not inst.players:
                del self.instances[inst.run_id]
        self._rift_tick(now)
        if now >= self._next_queue:
            self._next_queue = now + cfg()["queue"]["check_seconds"]
            self._queue_tick(now)
        if now >= self._next_announce:
            self._next_announce = now + 5.0
            self._announce_tick()
