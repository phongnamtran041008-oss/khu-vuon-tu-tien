"""Guard bees in the shared world (spec 10.2.3), simulated by the server like everything else.

Each character brings the bees whose role is "guard" (2-5, by realm). They follow their
owner and attack monsters within range whose Mặc Thuẫn is already broken — a bee can never
damage a shielded monster, so it never replaces answering. Every species has a passive
skill (burn, slow, stun, heal the owner, extra loot, quick stings, ink strokes). A monster's
attack also hits the bees stinging it; a bee at 0 HP flies home for 60 s to recover.

No database here: the tick is synchronous. Bee XP after a kill is a background task.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import balance

if TYPE_CHECKING:
    from .ai import Monster
    from .zone import ChannelZone, Player


def cfg() -> dict:
    return balance.load("bees")["guard"]


@dataclass
class GuardBee:
    id: int
    sp: str
    max_hp: float
    atk: float
    cd: float
    skill: dict = field(default_factory=dict)
    level: int = 1
    hp: float = 0.0
    ready_at: float = 0.0
    down_until: float = 0.0
    target: str | None = None
    hits: int = 0

    def __post_init__(self):
        if self.hp <= 0:
            self.hp = self.max_hp

    def is_down(self, now: float) -> bool:
        return now < self.down_until

    def hp_pct(self) -> int:
        return max(0, min(100, int(round(100 * self.hp / max(1.0, self.max_hp)))))

    def state(self, now: float) -> list:
        down = self.is_down(now)
        return [self.sp, self.hp_pct(), "" if down else (self.target or ""), int(down)]


def build(loadout: list[dict], old: list[GuardBee] | None = None) -> list[GuardBee]:
    """New guard list from systems/bees.guard_loadout; bees already out keep their HP,
    cooldown and knocked-out timer (a level-up does not heal a fallen bee)."""
    prev = {b.id: b for b in old or []}
    out = []
    for d in loadout:
        b = GuardBee(d["id"], d["sp"], float(d["hp"]), float(d["atk"]), float(d["cd"]), dict(d.get("skill") or {}),
                     int(d.get("level", 1)))
        o = prev.get(b.id)
        if o is not None:
            b.hp = min(b.max_hp, o.hp + max(0.0, b.max_hp - o.max_hp))
            b.ready_at, b.down_until, b.target, b.hits = o.ready_at, o.down_until, o.target, o.hits
        out.append(b)
    return out


def _dist(ax, ay, bx, by) -> float:
    return math.hypot(ax - bx, ay - by)


def bee_hurt(ch: "ChannelZone", m: "Monster", owner: "Player", bee: GuardBee, dmg: float, now: float) -> float:
    """The only way a bee hurts a monster: never through a Mặc Thuẫn (spec 10.2.3)."""
    from . import combat
    if not m.alive or m.shield or owner.dead:
        return 0.0
    combat.engage(ch, m, owner, now)          # shield is down, so no question: the monster turns on the owner
    m.bee_assist.setdefault(owner.user_id, set()).add(bee.id)
    return combat.hurt_monster(ch, m, owner, dmg, False, now, bee=bee.sp)


def _pick(ch: "ChannelZone", p: "Player", bee: GuardBee, rng_range: float) -> "Monster | None":
    cur = ch.monster(bee.target) if bee.target else None
    if cur is not None and cur.alive and not cur.shield and _dist(p.x, p.y, cur.x, cur.y) <= rng_range + 30:
        return cur
    cands = [m for m in ch.monsters if m.alive and not m.shield and _dist(p.x, p.y, m.x, m.y) <= rng_range]
    if not cands:
        return None
    mine = [m for m in cands if p.user_id in m.engaged]   # help with the owner's own fight first
    return min(mine or cands, key=lambda m: _dist(p.x, p.y, m.x, m.y))


def _sting(ch: "ChannelZone", p: "Player", b: GuardBee, m: "Monster", now: float, rng: random.Random) -> None:
    from . import combat
    sk = b.skill or {}
    kind = sk.get("type", "sting")
    dmg = max(1.0, b.atk - m.info.get("def", 0) * combat.cfg()["defense_factor"])
    b.hits += 1
    if kind == "ink" and b.hits % int(sk.get("every", 4)) == 0:
        dmg *= float(sk.get("mult", 3.0))
        ch.event(k="ink", by=p.eid, s=b.sp, x=m.x, y=m.y)
    dealt = bee_hurt(ch, m, p, b, dmg, now)
    if dealt <= 0 or not m.alive:
        return
    if kind == "burn":
        m.burn = (now + float(sk.get("duration", 3.0)), b.atk * float(sk.get("dps_mult", 0.5)), p.user_id, b.id)
    elif kind == "slow":
        mult = float(sk.get("slow", 0.8))
        if now >= m.slow_until or mult < m.slow_mult:
            m.slow_mult = mult
        m.slow_until = max(m.slow_until, now + float(sk.get("duration", 1.5)))
    elif kind == "stun" and rng.random() < float(sk.get("chance", 0.15)):
        m.stun_until = max(m.stun_until, now + float(sk.get("duration", 0.8)))
        m.tele = None
        m.moving = False
        ch.event(k="stun", id=m.eid, x=m.x, y=m.y, d=float(sk.get("duration", 0.8)))
    elif kind == "heal" and p.hp < p.max_hp:
        amount = p.max_hp * float(sk.get("pct", 1.5)) / 100
        p.hp = min(p.max_hp, p.hp + amount)
        ch.event(k="heal", id=p.eid, v=max(1, int(round(amount))), x=p.x, y=p.y, b=1)


def hit_bees(ch: "ChannelZone", m: "Monster", now: float) -> None:
    """A monster's telegraphed attack lands: the bees stinging it get hit too."""
    c = cfg()
    dmg = max(1.0, m.info.get("atk", 5) * c["hit_by_monster_mult"])
    for p in ch.players.values():
        for b in p.bees:
            if b.target == m.eid and not b.is_down(now):
                b.hp -= dmg
                if b.hp <= 0:  # back to the hive to recover (spec 10.2.3)
                    b.hp = b.max_hp
                    b.down_until = now + c["down_seconds"]
                    b.target = None
                    ch.event(k="bee_down", id=p.eid, s=b.sp, x=m.x, y=m.y)


def tick(ch: "ChannelZone", dt: float, now: float, rng: random.Random) -> None:
    c = cfg()
    rng_range = float(c["range"])
    for p in ch.players.values():
        if not p.bees:
            continue
        for b in p.bees:
            if b.is_down(now):
                continue
            if b.down_until:          # just came back from the hive, healed
                b.down_until = 0.0
                b.hp = b.max_hp
            m = None if p.dead else _pick(ch, p, b, rng_range)
            if m is None:
                b.target = None
                b.hp = min(b.max_hp, b.hp + b.max_hp * c["regen_pct_per_second"] / 100 * dt)
                continue
            if b.target != m.eid:
                b.target = m.eid
                b.ready_at = max(b.ready_at, now + c["first_attack_delay"])
            if now >= b.ready_at:
                b.ready_at = now + b.cd
                _sting(ch, p, b, m, now, rng)
    # burning monsters
    tick_s = float(c["burn_tick"])
    for m in ch.monsters:
        if m.burn is None:
            continue
        until, dps, uid, bid = m.burn
        if not m.alive or now >= until:
            m.burn = None
            m.burn_acc = 0.0
            continue
        m.burn_acc += dt
        if m.burn_acc >= tick_s:
            m.burn_acc -= tick_s
            p = ch.players.get(uid)
            b = next((x for x in p.bees if x.id == bid), None) if p is not None else None
            if p is None or b is None:
                m.burn = None
                continue
            bee_hurt(ch, m, p, b, dps * tick_s, now)
