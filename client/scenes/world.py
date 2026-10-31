"""The shared world (spec 7.1, 15.1, 18): Trúc Lâm Thôn, Rừng Mực Loang...

The own character is predicted: every frame's held keys become a movement step that is
applied at once and sent to the server in small batches. Snapshots bring the
authoritative position plus the last batch the server applied; unapplied batches are
replayed on top, so normally nothing visible happens. Everyone else is interpolated 100 ms
in the past between snapshots.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

import pygame

from .. import strings_vi as T
from ..art.palette import rgb
from ..engine import movement as mv
from ..engine import sprites
from ..engine.beeflock import Flock
from ..engine.effects import Effects
from ..engine.tilemap import load_map
from ..net.interpolation import Interpolator
from ..ui.dialog import DialogScene
from .abode import Player
from .base import Scene

FACING = ("down", "up", "left", "right")
SPEED = 74.0
SEND_EVERY = 0.05          # 20 input messages a second at most
BUBBLE_SECONDS = 5.0


@dataclass
class Ent:
    id: str
    kind: str                      # "p" player, "m" monster
    name: str
    uid: int | None = None
    appearance: dict = field(default_factory=dict)
    mtype: str = ""
    realm: str = "pham_nhan"
    walk_t: float = 0.0
    pos: tuple = (0.0, 0.0, 0, 0)  # last drawn (x, y, facing, moving)
    hp: int = 100                  # percent
    shield: int = 0
    alive: int = 1
    rank: str = "normal"
    weapon: str | None = None
    hurt_t: float = 0.0            # flashes white when hit
    swing_t: float = 0.0           # attack animation
    bees: list = field(default_factory=list)   # guard bees: [species, hp %, target id, down]
    pet: str | None = None                     # worn Linh Thú (stage 8)
    ghost: bool = False                        # out of health in a bí cảnh (stage 9)
    realm_id: str = ""                         # a Khe Nứt Mực rift ("r"): where it leads
    left: float = 0.0                          # rift: seconds until it closes, when first seen
    seen: float = 0.0


_GHOST: dict = {}


def ghostly(img: pygame.Surface) -> pygame.Surface:
    """A bí cảnh ghost: the same sprite, pale and see-through."""
    key = id(img)
    if key not in _GHOST:
        g = img.copy()
        g.fill((170, 190, 220, 0), special_flags=pygame.BLEND_RGBA_MAX)
        g.set_alpha(120)
        _GHOST[key] = g
    return _GHOST[key]


def map_collider(tmap) -> mv.Collider:
    solids = [(r.x, r.y, r.w, r.h) for r in tmap.solids]
    return mv.Collider(tmap.px_w, tmap.px_h, solids)


def darkness(phase: float) -> float:
    """0 by day, 1 at night (spec 7.1: one game day = two real hours)."""
    h = (phase % 1.0) * 24
    if 6 <= h < 18:
        return 0.0
    if 18 <= h < 20:
        return (h - 18) / 2
    if 4 <= h < 6:
        return 1 - (h - 4) / 2
    return 1.0


_WHITE: dict = {}
_FLIP: dict = {}


def white(img: pygame.Surface) -> pygame.Surface:
    """The hit flash: the same sprite painted white."""
    key = id(img)
    if key not in _WHITE:
        w = img.copy()
        w.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
        _WHITE[key] = w
    return _WHITE[key]


def flipped(img: pygame.Surface) -> pygame.Surface:
    key = id(img)
    if key not in _FLIP:
        _FLIP[key] = pygame.transform.flip(img, True, False)
    return _FLIP[key]


_RINGS: dict = {}


def shield_ring(w: int, frame: int) -> pygame.Surface:
    """Mặc Thuẫn: a dark, slowly turning ring of ink around the monster."""
    key = (w, frame)
    if key not in _RINGS:
        s = pygame.Surface((w, w), pygame.SRCALPHA)
        r = w // 2 - 1
        for i in range(16):
            if (i + frame) % 4 == 0:
                continue
            a0 = i / 16 * 6.283
            pygame.draw.arc(s, (26, 26, 26, 200), s.get_rect().inflate(-2, -2), a0, a0 + 0.35, 2)
        pygame.draw.circle(s, (90, 90, 90, 40), (w // 2, w // 2), r)
        _RINGS[key] = s
    return _RINGS[key]


_WEAPONS: dict = {}


def weapon_img(kind: str, facing: str, swing: float) -> pygame.Surface:
    """A small weapon drawn over the hand (spec 7.2: gear changes the look)."""
    key = (kind, facing, swing > 0.12)
    if key not in _WEAPONS:
        s = pygame.Surface((12, 12), pygame.SRCALPHA)
        shaft = {"brush": "b", "sword": "t", "fan": "w", "staff": "V"}.get(kind, "b")
        tip = {"brush": "K", "sword": "W", "fan": "r", "staff": "n"}.get(kind, "K")
        length = {"brush": 8, "sword": 9, "fan": 5, "staff": 11}.get(kind, 8)
        if kind == "fan":
            pygame.draw.polygon(s, rgb("w"), [(6, 10), (1, 3), (11, 3)])
            pygame.draw.polygon(s, rgb("k"), [(6, 10), (1, 3), (11, 3)], 1)
            pygame.draw.line(s, rgb("r"), (2, 4), (10, 4))
        else:
            pygame.draw.line(s, rgb(shaft), (6, 11), (6, 11 - length), 2 if kind != "sword" else 1)
            pygame.draw.rect(s, rgb(tip), (5, 11 - length - 1, 3, 3 if kind == "brush" else 2))
            if kind == "sword":
                pygame.draw.line(s, rgb("o"), (4, 9), (8, 9))
        angle = {"down": 160, "up": -20, "left": 70, "right": -70}[facing] + (-60 if swing > 0.12 else 0)
        _WEAPONS[key] = pygame.transform.rotate(s, angle)
    return _WEAPONS[key]


def weapon_pos(x: float, y: float, facing: str, cx: int, cy: int) -> tuple[int, int]:
    ox, oy = {"down": (2, -16), "up": (-10, -18), "left": (-14, -16), "right": (2, -16)}[facing]
    return int(x + ox) - cx, int(y + oy) - cy


class WorldScene(Scene):
    draws_world = True
    modal = False

    @property
    def toast_y(self) -> int:
        """Toasts sit under the HUD card; over the bí cảnh result panel they move to the very top."""
        return 4 if (self.realm is not None and self.realm.ended) else 70

    def __init__(self, game, zone_id: str, via: str = "resume", zone_msg: dict | None = None):
        super().__init__(game)
        self.zone_id = zone_id
        self.via = via
        self.map = load_map(zone_id)
        self.col = map_collider(self.map)
        ch = game.state.character
        sx, sy = self.map.find("spawn")[0].x, self.map.find("spawn")[0].y
        self.player = Player(float(sx), float(sy), ch.get("facing", "down"), ch.get("appearance", {}))
        self.joined = False
        self.join_sent_at: float | None = None
        self.waiting_zone: float | None = None
        self.portal_cool = 0.0
        self.seq = 0
        self.batch: list[list[int]] = []
        self.batch_t = 0.0
        self.ms_rem = 0.0
        self.pending: deque = deque()
        self.corrections = 0
        self.entities: dict[str, Ent] = {}
        self.interp = Interpolator()
        self.bubbles: dict[str, tuple[str, float]] = {}
        self.channel = 1
        self.channels: list[dict] = []
        self.zone_name = T.ZONE_NAMES.get(zone_id, zone_id)
        self.cam = [0, 0]
        self.t = 0.0
        self.fx = Effects()
        self.target = None
        self.minimap = self._build_minimap()
        self.teles: list[list] = []          # [x, y, r, time_left, total]
        self.big_chars: list[list] = []      # [hanzi, x, y, life]
        self.hurt_flash = 0.0
        self.swing_t = 0.0
        self.dead = False
        self.skill_ready: dict[str, float] = {}
        self.attack_ready = 0.0
        self.flock = Flock()                 # guard bees (stage 5), drawn flying around their owner
        self.pet_follow: dict = {}           # Linh Thú trotting after their owners (stage 8): eid -> PetFollower
        self.my_bees: list = []              # [id, species, hp, max hp, seconds resting, target]
        self.bee_hits = 0
        self.fishing = None                  # the FishingScene casting from here (stage 6)
        from .fishing import WeatherWatch
        self.weather = WeatherWatch(zone_id)
        self.ghost = False                   # stage 9: a ghost following the party in a bí cảnh
        from .realm import RealmView
        self.realm = RealmView(self) if zone_id == "bi_canh" else None
        if zone_msg:
            self.apply_zone(zone_msg)

    # ------------------------------------------------------------ network
    @property
    def net(self):
        return self.game.net

    def request_join(self) -> None:
        if self.net is not None and self.net.online:
            self.net.send({"t": "join", "zone": self.zone_id, "via": self.via})
            self.join_sent_at = self.game.now

    def on_net(self, m: dict) -> None:
        t = m.get("t")
        if t == "welcome":  # (re)connected: ask for our place back
            self.joined = False
            if not (m.get("zone") == "abode" and self.via == "abode"):
                self.via = "resume"   # the server still has us here (or saved us here)
            self.join_sent_at = None
            self.pending.clear()
            self.batch = []
        elif t == "zone":
            z = m.get("zone")
            if z == "abode":
                self.game.enter_abode(m.get("x"), m.get("y"), m.get("f", "up"))
            elif z != self.zone_id:
                self.game.replace_all(WorldScene(self.game, z, zone_msg=m))
            else:
                self.apply_zone(m)
        elif t == "snap" and self.joined:
            self.apply_snapshot(m)
        elif t == "error":
            code = m.get("code")
            if code in ("not_at_portal", "realm_too_low", "zone_full", "not_in_zone"):
                self.waiting_zone = None
                self.portal_cool = 2.0
            if not self.joined and m.get("zone") == "abode":  # cannot return to where we were
                self.game.enter_abode(None, None, "down")
                return
            self.game.toast(m.get("message_vi", ""), "#BC4749")
        elif t == "chat":
            eid = (m.get("from") or {}).get("id")
            if m.get("ch") in ("zone", "world") and eid:
                self.bubbles[eid] = (m.get("text", ""), self.game.now + BUBBLE_SECONDS)
        elif t == "q":  # a Vấn Đạo question: Hộ Thể until answered (spec 8.1)
            from .rpg import CombatQuizScene
            self.flush_inputs()
            self.player.moving = False
            for sc in self.game.scenes:
                if isinstance(sc, CombatQuizScene):
                    return
            while self.game.top is not None and self.game.top is not self and self in self.game.scenes:
                self.game.pop()      # the fight comes first: close bag/menus so the card sits over the world
            if m.get("first_meet"):
                self.game.toast(T.COMBAT_INTRO, "#4A7CC8")
            self.game.push(CombatQuizScene(self.game, m["q"], m.get("mid", ""), on_result=self.on_combat_result))
        elif t == "q_end":
            from .rpg import CombatQuizScene
            for sc in list(self.game.scenes):
                if isinstance(sc, CombatQuizScene) and sc.q.get("session_id") == m.get("sid") and not sc.result:
                    self.game.pop(sc)
        elif t == "dead":
            from .rpg import CombatQuizScene, DeathOverlay
            for sc in list(self.game.scenes):
                if isinstance(sc, CombatQuizScene):
                    self.game.pop(sc)
            if m.get("ghost"):   # stage 9: in a bí cảnh you follow the party as a ghost
                self.ghost = True
                self.game.toast(T.REALM_GHOST, "#8C8C8C")
                return
            self.dead = True
            self.game.push(DeathOverlay(self.game, m.get("respawn_in", 3)))
        elif t == "realm":
            if self.realm is not None:
                self.realm.on_net(m)
        elif t == "loot":
            p = self.player
            y = p.y - 30
            if m.get("stones"):
                self.fx.float_text(T.LOOT_STONES.format(n=m["stones"]), p.x, y, "#E9C46A")
                y -= 9
            xp = (m.get("xp") or {}).get("gained")
            if xp:
                self.fx.float_text(T.LOOT_XP.format(n=xp), p.x, y, "#B5D67A")
        elif t == "act_fail":
            if m.get("code") == "too_far":
                self.fx.float_text(T.SKILL_FAIL["too_far"], self.player.x, self.player.y - 30, "#F4EBD9")
        elif t == "cast":
            if m.get("ok"):
                self.skill_ready[m["k"]] = self.game.now + float(m.get("ready_in", 0))
            else:
                self.fx.float_text(T.SKILL_FAIL.get(m.get("code"), m.get("code") or ""), self.player.x,
                                   self.player.y - 30, "#F4EBD9")

    def on_combat_result(self, res: dict) -> None:
        pass  # effects arrive with the next snapshot; Tu Vi is shown by the quiz card

    def apply_zone(self, m: dict) -> None:
        p = self.player
        p.x, p.y = float(m["x"]), float(m["y"])
        p.facing = m.get("f", p.facing) if m.get("f") in FACING else p.facing
        self.pending.clear()
        self.batch = []
        self.seq = max(self.seq, int(m.get("ack", -1)) + 1)
        self.entities.clear()
        self.interp.clear()
        self.channel = m.get("channel", 1)
        self.channels = m.get("channels", [])
        self.zone_name = m.get("name_vi") or self.zone_name
        self.joined = True
        self.waiting_zone = None
        ch = self.game.state.character
        ch.update({"zone_id": self.zone_id, "x": p.x, "y": p.y, "facing": p.facing})
        if m.get("day") is not None:
            self.game.set_day(m["day"])

    def apply_snapshot(self, m: dict) -> None:
        st = m["st"]
        now = self.game.now
        self.interp.clock_sample(st, now)
        ack = m.get("ack", -1)
        while self.pending and self.pending[0][0] <= ack:
            self.pending.popleft()
        x, y = float(m["me"][0]), float(m["me"][1])
        for _, steps in self.pending:
            for dx, dy, ms in steps:
                x, y = mv.step(x, y, dx, dy, ms, SPEED, self.col)
        for dx, dy, ms in self.batch:
            x, y = mv.step(x, y, dx, dy, ms, SPEED, self.col)
        p = self.player
        if abs(x - p.x) > 0.01 or abs(y - p.y) > 0.01:
            self.corrections += 1   # the server disagreed (blocked or too fast): follow it
            p.x, p.y = x, y
        me = m["me"]
        if len(me) >= 7:
            ch = self.game.state.character
            ch["hp"], ch["max_hp"], ch["qi"], ch["max_qi"] = int(round(me[3])), int(me[4]), int(round(me[5])), int(me[6])
            if me[3] > 0:
                self.dead = False
        if len(me) >= 8:
            self.my_bees = me[7]
        if len(me) >= 9:
            self.ghost = bool(me[8])
        seen = set()
        for e in m.get("add", []):
            ent = Ent(e["id"], e["k"], e.get("n", ""), e.get("uid"), e.get("ap") or {}, e.get("type", ""),
                      e.get("realm", "pham_nhan"))
            ent.hp, ent.shield, ent.alive = e.get("hp", 100), e.get("sh", 0), e.get("alive", 1)
            ent.rank, ent.weapon = e.get("rank", "normal"), e.get("wp")
            ent.bees = e.get("bees") or []
            ent.pet = e.get("pet")
            ent.ghost = bool(e.get("gh"))
            if e["k"] == "r":
                ent.realm_id, ent.left, ent.seen = e.get("realm", ""), float(e.get("left", 0)), self.game.now
            self.entities[e["id"]] = ent
            self.interp.push(e["id"], st, e["x"], e["y"], e.get("f", 0), e.get("m", 0))
            seen.add(e["id"])
        for row in m.get("e", []):
            eid, ex, ey, f, mvng = row[:5]
            ent = self.entities.get(eid)
            if ent is not None:
                if len(row) >= 6:
                    ent.hp = row[5]
                if len(row) >= 8:
                    ent.shield, ent.alive = row[6], row[7]
                elif len(row) == 7 and ent.kind == "p":
                    ent.bees = row[6] or []
                self.interp.push(eid, st, ex, ey, f, mvng)
                seen.add(eid)
        for ev in m.get("fx", []):
            self.on_fx(ev)
        for eid in m.get("rm", []):
            self.entities.pop(eid, None)
            self.interp.forget(eid)
        for eid in self.entities:  # unchanged ones keep a sample so interpolation stays continuous
            if eid not in seen:
                last = self.interp.last(eid)
                if last:
                    self.interp.push(eid, st, last[1], last[2], last[3], 0)

    def on_fx(self, ev: dict) -> None:
        """Combat effects from the server (spec 18: sparks, shake, red flash, ink to light)."""
        k = ev.get("k")
        x, y = ev.get("x", 0.0), ev.get("y", 0.0)
        me = f"p{self.game.state.me.get('id')}"
        if k in ("mark", "pz", "gshield"):    # stage 9: pings and puzzle effects
            if self.realm is not None:
                self.realm.on_fx(ev)
            return
        if k == "hit" and ev.get("b"):                  # a guard bee stung a monster (spec 10.2.3)
            self.bee_hits += 1
            ent = self.entities.get(ev.get("id"))
            if ent is not None:
                ent.hurt_t = 0.08
            self.fx.float_text(str(ev.get("v", "")), x + random.uniform(-6, 6), y - 18, "#F2D58A")
            return
        if k == "ink":                                   # Ong Thư Pháp: a brush stroke writes its character
            sp = (self.game.state.bee_species.get(ev.get("s")) or {}).get("hanzi", "笔蜂")
            self.big_chars.append([sp[:-1] or sp, x, y - 30, 1.0])
            self.fx.burst(x, y - 8, "K", 12, 30)
            return
        if k == "bee_down":
            if ev.get("id") == me:
                name = (self.game.state.bee_species.get(ev.get("s")) or {}).get("name_vi", "Ong")
                self.game.toast(T.BEE_DOWN.format(name=name), "#BC4749")
            self.fx.burst(x, y - 12, "o", 6, 20)
            return
        if k == "stun":
            self.fx.float_text(T.BEE_STUN, x, y - 30, "#B5A0E0")
            return
        if k in ("hit", "mk") and ev.get("id") == me:   # we were hit
            self.fx.shake = 0.6 if k == "mk" else 0.3
            self.hurt_flash = 0.45 if k == "mk" else 0.2
            self.fx.float_text(f"-{ev.get('v', '')}", x, y - 30, "#F08A8C")
            if k == "mk":
                self.fx.float_text(T.MAC_KICH, x, y - 40, "#BC4749")
        elif k in ("hit", "mk"):
            ent = self.entities.get(ev.get("id"))
            if ent is not None:
                ent.hurt_t = 0.15
            col = "#9A9A9A" if ev.get("sh") else ("#E9C46A" if ev.get("c") else "#FFFFFF")
            if k == "mk" or (ent is not None and ent.kind == "p"):
                col = "#F08A8C"
            self.fx.float_text(str(ev.get("v", "")), x + random.uniform(-4, 4), y - 22, col)
        elif k == "tele":
            self.teles.append([x, y, ev.get("r", 20), ev.get("d", 0.8), ev.get("d", 0.8)])
        elif k == "shield":
            if ev.get("on"):
                self.fx.burst(x, y - 8, "K", 16, 25)
                self.fx.float_text(T.SHIELD_BACK, x, y - 34, "#5A5A5A")
            else:  # "mực tan thành hạt sáng khi phá khiên"
                self.fx.ink_to_light(x, y - 8)
                self.fx.float_text(T.SHIELD_BROKEN, x, y - 34, "#E9C46A")
        elif k == "die":
            self.fx.burst(x, y - 8, "K", 22, 40)
            self.fx.burst(x, y - 8, "W", 10, 30)
        elif k == "atk":
            ent = self.entities.get(ev.get("by"))
            if ent is not None:
                ent.swing_t = 0.25
        elif k == "skill":
            sid = ev.get("s")
            if sid == "hoa":
                tx, ty = ev.get("tx", x), ev.get("ty", y)
                for i in range(8):
                    f = i / 8
                    self.fx.burst(x + (tx - x) * f, y + (ty - y) * f, "r" if i % 2 else "o", 3, 12)
                self.fx.burst(tx, ty, "r", 18, 40)
            elif sid == "thuy":
                r = ev.get("r", 60)
                for i in range(16):
                    a = i / 16 * 6.283
                    self.fx.burst(x + math.cos(a) * r * 0.8, y + math.sin(a) * r * 0.5, "a", 2, 15)
            elif sid == "moc":
                self.fx.burst(x, y, "l", 14, 25)
            elif sid == "son":
                self.fx.burst(x, y + 8, "T", 16, 20)
            caster = self.entities.get(ev.get("by"))
            hz = {"hoa": "火", "thuy": "水", "moc": "木", "son": "山"}.get(sid, "")
            if hz:  # spec 18: the skill's character shows big above the caster
                cx, cy = (self.player.x, self.player.y) if ev.get("by") == me else (
                    (caster.pos[0], caster.pos[1]) if caster else (x, y))
                self.big_chars.append([hz, cx, cy - 40, 1.0])
        elif k == "heal":
            self.fx.float_text(f"+{ev.get('v', '')}", x, y - 30, "#4A7CC8" if ev.get("q") else "#B5D67A")
            self.fx.burst(x, y - 10, "l", 8, 15)

    # ------------------------------------------------------------ guard bees (stage 5)
    def update_bees(self, dt: float) -> None:
        now = self.game.now
        me = f"p{self.game.state.me.get('id')}"
        owners = [(me, self.player.x, self.player.y, [[b[1], 100, b[5], int(b[4] > 0)] for b in self.my_bees])]
        for e in self.entities.values():
            if e.kind == "p" and e.bees and e.alive:
                owners.append((e.id, e.pos[0], e.pos[1], e.bees))
        for eid, ox, oy, bees in owners:
            for i, b in enumerate(bees):
                sp, _hp, tgt, down = b[0], b[1], b[2], b[3]
                if down:
                    continue                      # resting in the hive
                fb = self.flock.get(f"{eid}:{i}", sp, ox, oy, now)
                target = self.entities.get(tgt) if tgt else None
                if target is not None and target.alive:
                    fb.update(dt, target.pos[0], target.pos[1] - 4, 6, 120, 12)    # stinging
                else:
                    side = -1 if i % 2 == 0 else 1
                    fb.update(dt, ox + side * (9 + i * 3), oy - 2, 6, 95, 18)      # following the owner
        self.flock.prune(now)

    def update_pets(self, dt: float) -> None:
        from ..engine.petfollow import PetFollower
        me = f"p{self.game.state.me.get('id')}"
        owners = []
        mine = self.game.worn_pet()
        if mine and not self.dead:
            owners.append((me, mine, self.player.x, self.player.y, self.player.facing))
        for e in self.entities.values():
            if e.kind == "p" and e.pet and e.alive:
                owners.append((e.id, e.pet, e.pos[0], e.pos[1], FACING[e.pos[2] % 4] if len(e.pos) > 2 else "down"))
        alive = set()
        for eid, kind, ox, oy, facing in owners:
            f = self.pet_follow.get(eid)
            if f is None or f.kind != kind:
                f = self.pet_follow[eid] = PetFollower(ox, oy)
                f.kind = kind
            f.update(dt, ox, oy, facing)
            alive.add(eid)
        for eid in list(self.pet_follow):
            if eid not in alive:
                del self.pet_follow[eid]

    # ------------------------------------------------------------ movement
    def _typing(self) -> bool:
        return self.game.chatbox.typing

    def update(self, dt, top):
        self.t += dt
        self.fx.update(dt)
        self.update_bees(dt)
        self.update_pets(dt)
        self.weather.update(dt, self.game.api)
        self.portal_cool = max(0.0, self.portal_cool - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        for tl in self.teles:
            tl[3] -= dt
        self.teles = [tl for tl in self.teles if tl[3] > -0.15]
        for b in self.big_chars:
            b[3] -= dt
        self.big_chars = [b for b in self.big_chars if b[3] > 0]
        self.swing_t = max(0.0, self.swing_t - dt)
        for e in self.entities.values():
            e.hurt_t = max(0.0, e.hurt_t - dt)
            e.swing_t = max(0.0, e.swing_t - dt)
        net = self.net
        if not self.joined:
            if net is not None and net.online and (self.join_sent_at is None or self.game.now - self.join_sent_at > 6):
                self.request_join()
            return
        if self.waiting_zone is not None and self.game.now - self.waiting_zone > 4:
            self.waiting_zone = None
        p = self.player
        dx = dy = 0
        if top and not self._typing() and self.waiting_zone is None and net is not None and net.online \
                and not self.dead:
            keys = pygame.key.get_pressed()
            dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        p.moving = bool(dx or dy)
        if p.moving:
            total = dt * 1000.0 + self.ms_rem
            ms = int(total)
            self.ms_rem = total - ms
            p.facing = mv.facing_for(dx, dy, p.facing)
            while ms > 0:
                part = min(ms, 100)
                ms -= part
                p.x, p.y = mv.step(p.x, p.y, dx, dy, part, SPEED, self.col)
                # sent exactly as applied (never merged): the server must repeat the same steps
                self.batch.append([dx, dy, part])
            p.walk_t += dt
        else:
            self.ms_rem = 0.0
        self.batch_t += dt
        if self.batch and (self.batch_t >= SEND_EVERY or len(self.batch) >= 12):
            self.flush_inputs()
        if self.batch_t >= SEND_EVERY:
            self.batch_t = 0.0
        self._check_portals()
        for e in self.entities.values():
            if e.pos[3]:
                e.walk_t += dt
        self.target = self.find_target() if top else None

    def flush_inputs(self) -> None:
        if not self.batch or self.net is None:
            return
        steps = [list(s) for s in self.batch]
        if self.net.send({"t": "in", "s": self.seq, "k": steps}):
            self.pending.append((self.seq, steps))
            self.seq += 1
        self.batch = []
        self.batch_t = 0.0
        if len(self.pending) > 80:  # the server stopped answering: stop predicting that far ahead
            self.pending.popleft()

    def _check_portals(self) -> None:
        if self.waiting_zone is not None or self.portal_cool > 0:
            return
        p = self.player
        for o in self.map.objects:
            if o.type == "portal" and o.x <= p.x <= o.x + o.w and o.y <= p.y <= o.y + o.h:
                target = o.props.get("target")
                if not target:
                    continue
                self.flush_inputs()
                self.net.send({"t": "join", "zone": target, "via": "portal"})
                self.waiting_zone = self.game.now
                self.game.toast(T.ENTERING.format(zone=T.ZONE_NAMES.get(target, target)))
                return

    # ------------------------------------------------------------ interaction
    def find_target(self):
        p = self.player
        off = {"up": (0, -10), "down": (0, 6), "left": (-10, -3), "right": (10, -3)}[p.facing]
        fx, fy = p.x + off[0], p.y + off[1]
        best, best_d = None, 22.0
        for o in self.map.objects:
            if o.type in ("npc", "interact", "sign"):
                cx, cy = o.x + o.w / 2, o.y + o.h
                d = math.hypot(cx - fx, cy - fy)
                if d < best_d:
                    best, best_d = ("object", o), d
        for e in self.entities.values():
            if not e.alive:
                continue
            x, y = e.pos[0], e.pos[1]
            d = math.hypot(x - fx, y - fy)
            if d < min(best_d, 26 if e.kind == "r" else 18):
                best, best_d = ("ent", e), d
        if self.realm is not None and not self.ghost:   # a tone pillar to strike
            o = self.realm.target(fx, fy)
            if o is not None:
                best = ("object", o)
        return best

    # ------------------------------------------------------------ fighting (stage 4)
    def weapon_range(self) -> float:
        kinds = {"brush": 40, "sword": 26, "fan": 32, "staff": 46}
        return kinds.get((self.game.state.cult or {}).get("stats", {}).get("weapon"), 22)

    def nearest_monster(self, max_d: float) -> Ent | None:
        p = self.player
        best, bd = None, max_d
        for e in self.entities.values():
            if e.kind == "m" and e.alive:
                d = math.hypot(e.pos[0] - p.x, e.pos[1] - p.y)
                if d < bd:
                    best, bd = e, d
        return best

    def attack(self, ent: Ent | None) -> None:
        if ent is None or self.net is None or self.dead or self.game.now < self.attack_ready:
            return
        self.flush_inputs()
        self.net.send({"t": "atk", "id": ent.id})
        self.attack_ready = self.game.now + 0.45
        self.swing_t = 0.25
        dx, dy = ent.pos[0] - self.player.x, ent.pos[1] - self.player.y
        self.player.facing = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")

    def learned_skills(self) -> list[dict]:
        return [k for k in (self.game.state.cult or {}).get("skills", []) if k.get("learned")]

    def cast(self, slot: int, hovered: Ent | None) -> None:
        sk = self.learned_skills()
        if slot >= len(sk) or self.net is None or self.dead:
            if slot >= len(sk):
                self.game.toast(T.SKILL_EMPTY, "#5A5A5A")
            return
        s = sk[slot]
        target = hovered if (hovered is not None and hovered.kind == "m" and hovered.alive) else \
            self.nearest_monster(140)
        self.flush_inputs()
        self.net.send({"t": "skill", "k": s["id"], "id": target.id if target else None})

    def use_pill(self) -> None:
        g = self.game

        def ok(r):
            g.refresh_inv()
        g.api.post("/inventory/use", {"item_id": "hoi_huyet_dan"}, ok, g.api_error)

    def start_fishing(self, bob) -> None:
        from .fishing import FishingScene
        self.flush_inputs()
        self.player.moving = False
        self.game.push(FishingScene(self.game, self, "world", bob))

    def action_of(self, target) -> str:
        kind, obj = target
        if kind == "ent":
            return "player" if obj.kind == "p" else ("rift" if obj.kind == "r" else "monster")
        if obj.type == "sign":
            return "sign"
        if obj.type == "realm_obj":
            return "pillar"
        return obj.props.get("action") or ("talk_master" if obj.props.get("npc") == "truc_lao" else "talk_guide")

    def interact(self, target) -> None:
        kind, obj = target
        action = self.action_of(target)
        g = self.game
        if kind == "ent":
            if obj.kind == "p":
                g.open_player_menu(obj.uid, obj.name, obj.realm)
            elif obj.kind == "r":   # stage 9: a Khe Nứt Mực
                from .realm import RealmGateScene
                g.push(RealmGateScene(g, rift={"id": obj.id, "realm": obj.realm_id, "n": obj.name,
                                               "left": obj.left, "seen": obj.seen}))
            else:
                self.attack(obj)
            return
        if action == "pillar":
            if self.realm is not None:
                self.realm.act(obj)
            return
        if action == "realm":
            from .realm import RealmGateScene
            g.push(RealmGateScene(g))
            return
        if action == "talk_master":
            npc = obj.props.get("npc", "truc_lao")

            def talked(r):
                if r.get("finished"):
                    g.push(DialogScene(g, T.MASTER_QUEST_LINES))
                    g.refresh_quests()
                else:
                    g.push(DialogScene(g, [random.choice(T.MASTER_VILLAGE)]))
            g.api.post("/quests/talk", {"npc": npc}, talked,
                       lambda e: g.push(DialogScene(g, [random.choice(T.MASTER_VILLAGE)])))
        elif action == "forge":
            from .rpg import ForgeScene
            g.push(ForgeScene(g))
        elif action == "quests":
            g.open_quests()
        elif action == "talk_guide":
            g.push(DialogScene(g, T.GUIDE_LINES, speaker=T.GUIDE_NAME, portrait=sprites.npc("guide")[("down", 0)]))
        elif action == "library":
            first = not g.state.me.get("met_librarian")
            g.state.me["met_librarian"] = True
            g.push(DialogScene(g, T.LIBRARIAN_LINES if first else [random.choice(T.LIBRARIAN_IDLE)],
                               speaker=T.LIBRARIAN_NAME, portrait=sprites.npc("librarian")[("down", 0)],
                               on_done=g.open_library))
        elif action == "td":
            from .td import TdMapScene
            first = not g.state.me.get("met_td")
            g.state.me["met_td"] = True
            g.push(TdMapScene(g))
            if first:
                g.push(DialogScene(g, T.TD_GATE_LINES))
        elif action == "gacha":
            from .gacha import GachaScene
            g.push(GachaScene(g, on_close=g.refresh_me))
        elif action == "fisher":
            from .fishing import FishShopScene

            def talked(r):
                first = r.get("finished") or not g.state.me.get("met_fisher")
                g.state.me["met_fisher"] = True
                if r.get("finished"):
                    g.refresh_quests()
                g.push(DialogScene(g, T.FISHER_LINES if first else [random.choice(T.FISHER_IDLE)],
                                   speaker=T.FISHER_NAME, portrait=sprites.npc("fisher")[("down", 0)],
                                   on_done=lambda: g.push(FishShopScene(g))))
            g.api.post("/quests/talk", {"npc": "fisher"}, talked, lambda e: g.push(FishShopScene(g)))
        elif action == "fish_book":
            from .fishing import FishBookScene
            g.push(FishBookScene(g))
        elif action == "alchemy":       # stage 8: the Đan Sư and his public furnace
            def talked(r):
                first = r.get("finished") or not g.state.me.get("met_alchemist")
                g.state.me["met_alchemist"] = True
                if r.get("finished"):
                    g.refresh_quests()
                g.push(DialogScene(g, T.ALCHEMIST_LINES if first else [random.choice(T.ALCHEMIST_IDLE)],
                                   speaker=T.ALCHEMIST_NAME, portrait=sprites.npc("alchemist")[("down", 0)],
                                   on_done=g.open_alchemy))
            g.api.post("/quests/talk", {"npc": "alchemist"}, talked, lambda e: g.open_alchemy())
        elif action == "shop":
            from .shop import ShopScene
            first = not g.state.me.get("met_shopkeeper")
            g.state.me["met_shopkeeper"] = True
            if first:
                g.push(DialogScene(g, T.SHOP_LINES, speaker=T.SHOP_NAME, portrait=sprites.npc("shopkeeper")[("down", 0)],
                                   on_done=lambda: g.push(ShopScene(g))))
            else:
                g.push(ShopScene(g))
        elif action == "sign":
            g.message(obj.props.get("text", ""), T.SIGN_READ)
        elif action in T.COMING:
            g.message(T.COMING[action], T.WORLD_ACTIONS.get(action, obj.name))

    # ------------------------------------------------------------ drawing
    def _build_minimap(self) -> pygame.Surface:
        k = min(100 / self.map.px_w, 64 / self.map.px_h)
        w, h = max(1, int(self.map.px_w * k)), max(1, int(self.map.px_h * k))
        self.mm_k = k
        base = pygame.Surface((self.map.px_w, self.map.px_h))
        self.map.draw_ground(base, (0, 0), 0)
        for r in self.map.solids:
            pygame.draw.rect(base, rgb("n"), r)
        return pygame.transform.smoothscale(base, (w, h))

    def _cam(self, surf) -> tuple[int, int]:
        w, h = surf.get_size()
        cx = int(self.player.x - w / 2)
        cy = int(self.player.y - 12 - h / 2)
        cx = max(0, min(self.map.px_w - w, cx))
        cy = max(0, min(self.map.px_h - h, cy))
        room = self.realm.room_rect() if self.realm is not None else None
        if room is not None:   # a bí cảnh room fits the screen: keep it still and centred
            cx, cy = int(room.centerx - w / 2), int(room.centery - h / 2)
        if self.fx.shake:
            cx += random.randint(-2, 2)
            cy += random.randint(-2, 2)
        self.cam = [cx, cy]
        return cx, cy

    def _ent_frame(self, e: Ent, facing: int, moving: int) -> pygame.Surface:
        if e.kind == "r":
            return sprites.realm("rift", int(self.t * 6) % 8)
        if e.kind == "m":
            kind = e.mtype if e.mtype in ("ink_slime", "tone_wisp", "ink_fox", "muc_anh", "but_yeu", "nghien_ma") else "ink_slime"
            frames = sprites.monster(kind)
            img = frames[int(self.t * (5 if moving else 2) + hash(e.id) % 7) % len(frames)]
            if kind == "ink_fox" and FACING[facing % 4] == "right":
                img = flipped(img)
            return white(img) if e.hurt_t > 0 else img
        frames = sprites.character(e.appearance)
        f = (0, 1, 0, 2)[int(e.walk_t * 8) % 4] if moving else 0
        img = frames[(FACING[facing % 4], f)]
        return white(img) if e.hurt_t > 0 else img

    def draw_world(self, surf):
        cx, cy = self._cam(surf)
        self.map.draw_ground(surf, (cx, cy), self.t)
        frame = int(self.t * 3) % 4
        drawables = []
        if self.realm is not None:   # stage 9: puzzle stones, tiles, pillars
            self.realm.floor(surf, cx, cy, frame)
            drawables += self.realm.drawables(cx, cy, frame)
        sw, sh = surf.get_size()
        # telegraphed monster attacks: a red zone that fills up before it lands (spec 8.1)
        for tx, ty, r, left, total in self.teles:
            k = 1 - max(0.0, left) / max(0.01, total)
            zone = pygame.Surface((int(r * 2 + 4), int(r * 1.3 + 4)), pygame.SRCALPHA)
            rect = zone.get_rect()
            pygame.draw.ellipse(zone, (188, 71, 73, 50), rect)
            inner = rect.inflate(-rect.w * (1 - k), -rect.h * (1 - k))
            pygame.draw.ellipse(zone, (188, 71, 73, 110), inner)
            pygame.draw.ellipse(zone, (142, 53, 55, 200), rect, 1)
            surf.blit(zone, (int(tx - r - 2) - cx, int(ty - r * 0.65 - 2) - cy))
        for o in self.map.objects:
            if o.x + o.w < cx - 8 or o.x > cx + sw + 8 or o.y + o.h < cy - 8 or o.y > cy + sh + 40:
                continue
            name = o.props.get("sprite")
            if name:
                img = sprites.prop(name, int(o.props.get("variant", 0) or 0),
                                   frame if name in sprites.ANIMATED_PROPS else 0)
                drawables.append((o.foot_y, img, (int(o.x) - cx, int(o.y) - cy)))
            elif o.type == "npc":
                look = o.props.get("npc", "guide")
                if look == "truc_lao":
                    img = sprites.truc_lao()[1 if int(self.t * 10) % 37 == 0 else 0]
                else:
                    img = sprites.npc(look)[("down", 0)]
                drawables.append((o.foot_y, img, (int(o.x) - cx, int(o.y) - cy)))
        now = self.game.now
        bars = []
        for e in self.entities.values():
            s = self.interp.sample(e.id, now)
            if s is None:
                continue
            e.pos = s
            x, y, f, m = s
            if not e.alive:
                continue
            img = self._ent_frame(e, f, m)
            if e.kind == "r":
                drawables.append((y, img, (int(x - 12) - cx, int(y - 32) - cy)))
            elif e.kind == "m":
                bob = int(abs(math.sin(self.t * 3 + hash(e.id) % 5)) * 2) if e.mtype == "tone_wisp" else 0
                w, ih = img.get_width(), img.get_height()
                drawables.append((y, img, (int(x - w / 2) - cx, int(y - ih - bob) - cy)))
                if e.shield:
                    ring = w + 8
                    drawables.append((y - 0.1, shield_ring(ring, int(self.t * 6) % 4),
                                      (int(x - ring / 2) - cx, int(y - ih / 2 - ring / 2 - bob) - cy)))
                if e.hp < 100:
                    bars.append((x, y - ih - 4 - bob, w, e.hp, "#BC4749"))
            else:
                if e.ghost:
                    img = ghostly(img)
                drawables.append((y, img, (int(x - 8) - cx, int(y - 24) - cy)))
                if e.weapon:
                    drawables.append((y + 0.1, weapon_img(e.weapon, FACING[f % 4], e.swing_t),
                                      weapon_pos(x, y, FACING[f % 4], cx, cy)))
                if e.hp < 100:
                    bars.append((x, y - 27, 14, e.hp, "#6A994E"))
        p = self.player
        if not self.dead:
            drawables.append((p.y, ghostly(p.frame()) if self.ghost else p.frame(), (int(p.x - 8) - cx, int(p.y - 24) - cy)))
            wp = (self.game.state.cult or {}).get("stats", {}).get("weapon")
            if wp:
                drawables.append((p.y + 0.1, weapon_img(wp, p.facing, self.swing_t),
                                  weapon_pos(p.x, p.y, p.facing, cx, cy)))
        for pf in self.pet_follow.values():
            pygame.draw.ellipse(surf, (30, 36, 26), (int(pf.x - 5) - cx, int(pf.y - 1) - cy, 10, 3))
            drawables.append((pf.y, sprites.pet(pf.kind, pf.frame, pf.left), (int(pf.x - 8) - cx, int(pf.y - 13) - cy)))
        species = self.game.state.bee_species
        for fb in self.flock.bees.values():
            look = (species.get(fb.sp) or {}).get("look")
            pygame.draw.ellipse(surf, (30, 36, 26), (int(fb.x - 2) - cx, int(fb.y) - cy, 4, 2))
            drawables.append((fb.y + 6, sprites.bee(look, fb.frame(), fb.left),
                              (int(fb.x - 4) - cx, int(fb.y - fb.z - 4) - cy)))
        for _, img, pos in sorted(drawables, key=lambda d: d[0]):
            surf.blit(img, pos)
        if self.fishing is not None:
            from .fishing import draw_rod
            draw_rod(surf, self.fishing, cx, cy, self.t)
        for x, y, w, hp, col in bars:  # small health bars over the hurt ones
            bx, by = int(x - w / 2) - cx, int(y - 4) - cy
            pygame.draw.rect(surf, rgb("K"), (bx - 1, by - 1, w + 2, 4))
            pygame.draw.rect(surf, pygame.Color(col), (bx, by, max(1, int(w * hp / 100)), 2))
        if self.target and self.game.top is self:
            kind, obj = self.target
            if kind == "object":
                tx, ty = obj.x + obj.w / 2, obj.y
            else:
                tx, ty = obj.pos[0], obj.pos[1] - 26
            bob = int(math.sin(self.t * 6) * 2)
            pygame.draw.polygon(surf, rgb("o"), [(int(tx) - cx - 3, int(ty) - cy - 8 + bob),
                                                 (int(tx) - cx + 3, int(ty) - cy - 8 + bob),
                                                 (int(tx) - cx, int(ty) - cy - 4 + bob)])
        self.fx.draw(surf, (cx, cy), lambda t, c: self.game.fonts.render(t, 7, c, 1), self.t)
        if self.realm is not None:   # underground: no sky, but the maze is dark, other rooms unseen
            self.realm.dark(surf, cx, cy)
            self.realm.outside(surf, cx, cy)
        d = darkness(self.game.day_phase()) if self.realm is None else 0.0
        if d > 0:
            night = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            night.fill((18, 22, 58, int(110 * d)))
            surf.blit(night, (0, 0))
        if self.weather.rain:
            from .fishing import draw_rain
            draw_rain(surf, self.t)
        if self.hurt_flash > 0:  # "chớp đỏ khi trúng Mặc Kích" (spec 18)
            red = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            red.fill((188, 40, 40, int(160 * min(1.0, self.hurt_flash * 2))))
            surf.blit(red, (0, 0))

    # ------------------------------------------------------------ HUD
    def draw_ui(self, ui):
        top = self.game.top is self
        g = self.game
        cx, cy = self.cam
        now = g.now
        # names and chat bubbles over heads (window resolution, so text stays sharp)
        heads = [(self.player.x, self.player.y, g.state.character.get("display_name", ""), "#FFFFFF",
                  f"p{g.state.me.get('id')}", 25)]
        for e in self.entities.values():
            if not e.alive:
                continue
            col = "#F4EBD9" if e.kind == "p" else ("#E9C46A" if e.rank == "elite" else "#F08A8C")
            name = e.name if e.rank == "normal" or e.kind == "p" else f"{e.name} · {T.MONSTER_RANK.get(e.rank, '')}"
            heads.append((e.pos[0], e.pos[1], name, col, e.id, 25 if e.kind == "p" else 22))
        for o in self.map.objects:
            if o.type == "npc":
                heads.append((o.x + o.w / 2, o.y + o.h, o.name, "#E9C46A", None, 25))
        for x, y, name, col, eid, lift in heads:
            bx, by = x - cx, y - cy - lift
            if not (-40 < bx < 520 and -20 < by < 290):
                continue
            ui.text(name, bx + 0.5, by + 0.5, 7, "#1A1A1A", anchor="midbottom")
            ui.text(name, bx, by, 7, col, anchor="midbottom")
            b = self.bubbles.get(eid) if eid else None
            if b and b[1] > now:
                self._bubble(ui, b[0], bx, by - 9)
        for hz, bx_, by_, life in self.big_chars:  # spec 18: the skill's character, big, above the caster
            ui.text(hz, bx_ - cx, by_ - cy - (1 - life) * 8, 18, "#E9C46A", kind="han", anchor="center")
        # player card: portrait, realm, Sinh Lực / Linh Lực / Tu Vi
        ch, me = g.state.character, g.state.me
        cult = g.state.cult or {}
        ui.fill(4, 4, 136, 50, (244, 235, 217, 235))
        ui.border(4, 4, 136, 50, "#8B5A2B")
        head = sprites.character(self.player.appearance)[("down", 0)].subsurface(pygame.Rect(2, 1, 12, 11))
        ui.fill(7, 7, 28, 28, "#E3D5BA")
        ui.image(head, 21, 21, zoom=2, anchor="center")
        from .library import portrait_frame, title_after
        portrait_frame(ui, me.get("frame"), 7, 7, 28, 28)
        title_after(ui, me.get("title"), ui.text(ch.get("display_name", ""), 39, 6, 8), 7.5)
        ui.text(cult.get("label") or T.REALMS.get(ch.get("realm", "pham_nhan"), ""), 39, 15, 7, "#6A994E")
        hp, mhp = ch.get("hp", 100), ch.get("max_hp", 100) or 100
        qi, mqi = ch.get("qi", 50), ch.get("max_qi", 50) or 50
        ui.progress(39, 25, 96, 5, hp / mhp, "#BC4749")
        ui.progress(39, 33, 96, 5, qi / mqi, "#4A7CC8")
        ui.text(f"{T.HP} {hp}/{mhp}", 41, 27.5, 6, "#FFFFFF", anchor="midleft")
        ui.text(f"{T.QI} {qi}/{mqi}", 41, 35.5, 6, "#FFFFFF", anchor="midleft")
        need = cult.get("need") or 0
        ui.progress(39, 41, 96, 5, (cult.get("xp", 0) / need) if need else 1.0, "#B8862E")
        ui.text(f"{T.TU_VI} {cult.get('xp', 0)}/{need or '—'}", 41, 43.5, 6, "#FFFFFF", anchor="midleft")
        ui.image(sprites.icon("stone"), 7, 57, zoom=1)
        stones = f"{me.get('spirit_stones', 0):,}".replace(",", ".")
        ui.text(stones, 18, 60.5, 8, "#FFFFFF", anchor="midleft")
        self.draw_bee_hud(ui, 64, 56)
        from .realm import draw_party_frames
        draw_party_frames(ui, g, 4, 72)
        if self.realm is not None:   # stage 9: the room banner and the puzzle card instead of channel/minimap
            ended = self.realm.ended is not None
            self.draw_hotbar(ui, top and not g.chatbox.typing and not ended)
            g.chatbox.draw(ui, in_zone=self.joined, enabled=top)
            self._hud_buttons(ui, top)
            self.realm.draw_ui(ui, top)
            if not ended:
                self._hud_input(ui, top)
            return
        # zone and channel
        label = f"{self.zone_name} · {T.CHANNEL.format(n=self.channel)}"
        w = ui.text_size(label, 8)[0] + 14
        if ui.button("w_channel", 240 - w / 2, 4, w, 13, label, style="dark", enabled=top and self.joined,
                     tooltip=T.CHANNEL_HINT):
            g.push(ChannelPicker(g, self))
        # minimap (top right)
        mw, mh = self.minimap.get_size()
        mx, my = 476 - mw, 4
        ui.fill(mx - 2, my - 2, mw + 4, mh + 4, "#3A342C")
        ui.image(self.minimap, mx, my)
        k = self.mm_k
        for o in self.map.objects:
            if o.type == "portal":
                ui.fill(mx + o.x * k, my + o.y * k, max(2, o.w * k), max(2, o.h * k), "#8CB8DA")
        for e in self.entities.values():
            if e.kind == "p":
                ui.fill(mx + e.pos[0] * k - 1, my + e.pos[1] * k - 1, 2, 2, "#FFFFFF")
            elif e.kind == "r":
                ui.fill(mx + e.pos[0] * k - 1.5, my + e.pos[1] * k - 1.5, 3, 3, "#8E5AC8")
        ui.fill(mx + self.player.x * k - 1.5, my + self.player.y * k - 1.5, 3, 3, "#E9C46A")
        ui.border(mx - 2, my - 2, mw + 4, mh + 4, "#8B5A2B")
        # quest tracker under the minimap
        quests = [q for q in (g.state.quests or {}).get("quests", []) if q["state"] in ("active", "done")]
        if quests:
            q = quests[0]
            o = q["objective"]
            line = f"{q['title_vi']}  {q['progress']}/{o['count']}"
            col = "#B5D67A" if q["state"] == "done" else "#F4EBD9"
            tw = ui.text_size(line, 7)[0] + 8
            ui.fill(476 - tw, my + mh + 4, tw, 11, (20, 18, 15, 150))
            ui.text(line, 472, my + mh + 9.5, 7, col, anchor="midright")
        # hotbar: Pháp Chữ 1-4 and the healing pill (spec 18)
        self.draw_hotbar(ui, top and not g.chatbox.typing)
        # chat (before hotkeys, so typing never triggers them)
        g.chatbox.draw(ui, in_zone=self.joined, enabled=top)
        self._hud_buttons(ui, top)
        self._hud_input(ui, top)

    def _hud_buttons(self, ui, top: bool) -> None:
        g = self.game
        typing = g.chatbox.typing
        # buttons, bottom right
        bx = 480 - 4
        for wid, lbl, key, action in [("hud_menu", T.HUD_MENU, pygame.K_ESCAPE, g.open_settings),
                                      ("hud_friends", T.HUD_FRIENDS, pygame.K_p, g.open_friends),
                                      ("hud_quests", T.HUD_QUESTS, pygame.K_j, g.open_quests),
                                      ("hud_char", T.HUD_CHAR, pygame.K_k, g.open_char),
                                      ("hud_book", T.HUD_BOOK, pygame.K_b, g.open_book),
                                      ("hud_pets", T.HUD_PETS, pygame.K_o, g.open_pets),
                                      ("hud_bag", T.HUD_BAG, pygame.K_TAB, g.open_bag),
                                      ("hud_party", T.HUD_PARTY, pygame.K_y, g.open_party)]:
            w = ui.text_size(lbl, 8)[0] + 10
            bx -= w + 3
            if ui.button(wid, bx, 252, w, 14, lbl, key=key if (top and not typing) else None, enabled=top):
                action()
        if top and not typing and ui.key(pygame.K_l):
            g.open_library()

    def _hud_input(self, ui, top: bool) -> None:
        g = self.game
        typing = g.chatbox.typing
        cx, cy = self.cam
        if not self.joined:
            msg = T.ENTERING.format(zone=self.zone_name) if (self.net and self.net.online) else T.CONNECTING_WORLD
            ui.fill(160, 120, 160, 24, (20, 18, 15, 200))
            ui.text(msg, 240, 132, 9, "#FFFFFF", anchor="center")
        if not top or typing:
            return
        # hover tooltips on entities
        mxw, myw = ui.inp.mouse
        wx, wy = mxw + cx, myw + cy
        hovered = None
        for e in self.entities.values():
            if e.alive and abs(e.pos[0] - wx) < (12 if e.kind == "m" else 8) and e.pos[1] - 24 < wy < e.pos[1] + 2:
                hovered = e
        if hovered is not None and ui.hover(0, 60, 480, 180):
            tip = hovered.name
            if hovered.kind == "p":
                tip += "\n" + T.PLAYER_REALM.format(realm=T.REALMS.get(hovered.realm, hovered.realm))
            elif hovered.kind == "r":
                tip += "\n" + T.REALM_RIFT_LEFT.format(t=int(max(0, hovered.left - (g.now - hovered.seen))))
            ui.set_tooltip(tip)
        if self.realm is not None and ui.inp.right_clicked and 20 < myw < 222:   # a ping for the party
            self.realm.mark(wx, wy, 1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 0)
        # fighting keys: Space attacks the nearest monster, 1-4 cast, Q drinks a pill
        if ui.key(pygame.K_SPACE):
            self.attack(hovered if hovered is not None and hovered.kind == "m" else
                        self.nearest_monster(self.weapon_range() + 14))
        for i, key in enumerate((pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4)):
            if ui.key(key):
                self.cast(i, hovered)
        if ui.key(pygame.K_q):
            self.use_pill()
        if self.target:
            label = T.WORLD_ACTIONS.get(self.action_of(self.target), T.SIGN_READ)
            ui.text(T.PRESS_E.format(action=label), 240, 216, 9, "#FFFFFF", anchor="center")
            if ui.key(pygame.K_e):
                self.interact(self.target)
                return
        from .fishing import water_near   # stage 6: F at the water (spec 11.1)
        spot = water_near(self.map, self.player.x, self.player.y, self.player.facing) if not self.dead else None
        if spot:
            ui.text(T.PRESS_F, 240, 206 if self.target else 216, 9, "#FFFFFF", anchor="center")
            if ui.key(pygame.K_f):
                self.start_fishing(spot[1])
                return
        if ui.inp.clicked and 20 < myw < 222 and not ui.hover(0, 150, 214, 100):
            if hovered is not None:
                ui.consume_click()
                self.interact(("ent", hovered))   # a monster: attack (spec 7.2: left click)
                return
            for o in self.map.objects:
                if o.type in ("npc", "interact", "sign") and o.rect.collidepoint(wx, wy):
                    ui.consume_click()
                    self.interact(("object", o))
                    return

    def draw_bee_hud(self, ui, x: float, y: float) -> None:
        """Own guard bees: portrait, health, resting countdown (spec 10.2.3)."""
        species = self.game.state.bee_species
        for i, b in enumerate(self.my_bees):
            bid, sp, hp, mhp, rest, _tgt = b[:6]
            bx = x + i * 16
            ui.fill(bx, y, 14, 14, (20, 18, 15, 170))
            info = species.get(sp) or {}
            ui.image(sprites.bee(info.get("look"), int(ui.time * 10 + i) % 2), bx + 7, y + 6, zoom=1, anchor="center")
            if rest > 0:
                ui.fill(bx, y, 14, 14, (0, 0, 0, 150))
                ui.text(f"{int(rest)}", bx + 7, y + 7, 6, "#FFFFFF", anchor="center")
            ui.fill(bx + 1, y + 12, 12, 2, "#3A342C")
            ui.fill(bx + 1, y + 12, 12 * hp / max(1, mhp), 2, "#E9C46A")
            if ui.hover(bx, y, 14, 14) and self.game.top is self:
                name = info.get("name_vi", sp)
                ui.set_tooltip(T.BEE_HUD_DOWN.format(name=name, t=int(rest)) if rest > 0 else
                               T.BEE_HUD_TIP.format(name=name, hp=hp, mx=mhp))

    def draw_hotbar(self, ui, active: bool) -> None:
        skills = self.learned_skills()
        x0, y0 = 252, 226
        now = self.game.now
        for i in range(4):
            x = x0 + i * 24
            ui.fill(x, y0, 22, 22, (20, 18, 15, 180))
            ui.border(x, y0, 22, 22, "#8B5A2B")
            ui.text(str(i + 1), x + 2, y0 + 1, 6, "#8E877A")
            if i < len(skills):
                sk = skills[i]
                ui.text(sk["hanzi"], x + 11, y0 + 12, 13, "#E9C46A", kind="han", anchor="center")
                left = self.skill_ready.get(sk["id"], 0) - now
                if left > 0:
                    frac = min(1.0, left / max(0.1, sk.get("cooldown", 1)))
                    ui.fill(x, y0 + 22 * (1 - frac), 22, 22 * frac, (0, 0, 0, 150))
                    ui.text(f"{left:.0f}", x + 11, y0 + 11, 8, "#FFFFFF", anchor="center")
                qi = (self.game.state.character or {}).get("qi", 0)
                if qi < sk.get("qi", 0):
                    ui.fill(x, y0, 22, 22, (40, 60, 120, 90))
                if active and ui.hover(x, y0, 22, 22):
                    ui.set_tooltip(f"{sk['name_vi']} ({sk['hanzi']}) · cấp {sk['level']}\n{sk['desc_vi']}\n"
                                   f"Linh Lực {sk['qi']} · hồi {sk['cooldown']} giây")
            elif active and ui.hover(x, y0, 22, 22):
                ui.set_tooltip(T.SKILL_EMPTY)
        # pill slot
        x = x0 + 4 * 24 + 4
        ui.fill(x, y0, 22, 22, (20, 18, 15, 180))
        ui.border(x, y0, 22, 22, "#BC4749")
        ui.text("Q", x + 2, y0 + 1, 6, "#8E877A")
        n = sum(i["qty"] for i in (self.game.state.inv or {}).get("items", []) if i["item_id"] == "hoi_huyet_dan")
        pygame.draw.circle(ui.win, pygame.Color("#BC4749"), ui.d.to_window(x + 11, y0 + 12), int(4 * ui.s))
        ui.text(f"{n}", x + 20, y0 + 20, 7, "#FFFFFF", anchor="bottomright")
        if active and ui.hover(x, y0, 22, 22):
            ui.set_tooltip("Hồi Huyết Đan (Q): hồi 35% Sinh Lực, hồi chung 15 giây")
        if active and ui.click_in(x, y0, 22, 22):
            self.use_pill()

    def _bubble(self, ui, text: str, x: float, y: float) -> None:
        lines = ui.f.wrap(text, 7, int(110 * ui.s), ui.s)[:3]
        w = max(ui.text_size(line, 7)[0] for line in lines) + 6
        h = len(lines) * 8 + 4
        ui.fill(x - w / 2, y - h, w, h, "#FFFFFF")
        ui.border(x - w / 2, y - h, w, h, "#2B2B2B")
        for i, line in enumerate(lines):
            ui.text(line, x, y - h + 2 + i * 8, 7, "#2B2B2B", anchor="midtop")


class ChannelPicker(Scene):
    def __init__(self, game, world: WorldScene):
        super().__init__(game)
        self.world = world

    def draw_ui(self, ui):
        ui.dim(110)
        chans = self.world.channels or [{"n": self.world.channel, "players": 1, "cap": 40}]
        h = 50 + 15 * (len(chans) + 1)
        x, y, w = 160, 40, 160
        ui.panel(x, y, w, h, T.CHANNELS_TITLE)
        ui.text(T.CHANNEL_HINT, x + 10, y + 10, 7, "#5A5A5A", max_w=w - 20)
        cy = y + 30
        for c in chans:
            label = T.CHANNEL_ROW.format(n=c["n"], p=c["players"], cap=c["cap"])
            full = c["players"] >= c["cap"] and c["n"] != self.world.channel
            if ui.button(f"chan_{c['n']}", x + 12, cy, w - 24, 13, label, selected=c["n"] == self.world.channel,
                         enabled=not full):
                self.pick(c["n"])
                return
            cy += 15
        nxt = max(c["n"] for c in chans) + 1
        if ui.button("chan_new", x + 12, cy, w - 24, 13, T.CHANNEL_NEW, style="gold"):
            self.pick(nxt)
            return
        if ui.key(pygame.K_ESCAPE) or (ui.inp.clicked and not ui.hover(x, y, w, h)):
            self.close()

    def pick(self, n: int) -> None:
        self.close()
        if self.game.net is not None and n != self.world.channel:
            self.world.flush_inputs()
            self.game.net.send({"t": "channel", "n": n})
