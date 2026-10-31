"""Tổ đội (spec 15.3, 14.1): at most 5 players who see each other's health, share Tu Vi from
monsters they fight near each other, talk on the Tổ Đội chat channel and enter bí cảnh
together. Parties live in memory only: they are gone after a server restart, like the
world itself. A member who stays offline longer than `party_offline_grace` drops out.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import balance
from . import protocol

if TYPE_CHECKING:
    from .world import Session, World


def cfg() -> dict:
    return balance.load("realm")


@dataclass
class Party:
    id: int
    leader: int
    members: list[int]                                   # user ids in the order they joined
    names: dict[int, str] = field(default_factory=dict)  # kept for members who are offline
    offline_since: dict[int, float] = field(default_factory=dict)
    last_view: dict | None = None


class PartyService:
    def __init__(self, world: "World"):
        self.world = world
        self.parties: dict[int, Party] = {}
        self.of: dict[int, int] = {}                      # user id -> party id
        self.invites: dict[int, dict[int, float]] = {}    # invitee -> {inviter: expires at}
        self._ids = itertools.count(1)
        self._next_state = 0.0

    # ------------------------------------------------------------ lookups
    def party_of(self, user_id: int) -> Party | None:
        pid = self.of.get(user_id)
        return self.parties.get(pid) if pid is not None else None

    def mates(self, user_id: int) -> list[int]:
        p = self.party_of(user_id)
        return [u for u in p.members if u != user_id] if p else []

    def view(self, party: Party) -> dict:
        w = self.world
        out = []
        for uid in party.members:
            s = w.sessions.get(uid)
            pl = w.players.get(uid)
            zone = pl.channel.zone_id if (pl is not None and pl.channel is not None) else ("abode" if s else None)
            out.append({"uid": uid, "name": s.name if s else party.names.get(uid, "?"),
                        "realm": s.realm if s else None, "online": s is not None, "zone": zone,
                        "hp": pl.hp_pct() if pl is not None else None,
                        "ghost": bool(pl is not None and getattr(pl, "ghost", False)),
                        "dead": bool(pl is not None and pl.dead)})
        return {"id": party.id, "leader": party.leader, "members": out, "max": cfg()["party_max"]}

    def view_for(self, user_id: int) -> dict | None:
        p = self.party_of(user_id)
        return self.view(p) if p else None

    # ------------------------------------------------------------ sending
    def _send(self, user_id: int, msg: dict) -> None:
        s = self.world.sessions.get(user_id)
        if s is not None:
            s.send(msg)

    def send_state(self, party: Party) -> None:
        v = self.view(party)
        party.last_view = v
        for uid in party.members:
            self._send(uid, {"t": "party", "event": "state", "party": v})

    # ------------------------------------------------------------ messages
    def handle(self, s: "Session", m: protocol.PartyCmd) -> None:
        if m.op == "invite":
            self.invite(s, m.name or "")
        elif m.op in ("accept", "decline"):
            self.answer(s, m.uid, m.op == "accept")
        elif m.op == "leave":
            if self.party_of(s.user_id) is None:
                s.send(protocol.error("no_party", "Bạn chưa ở trong tổ đội nào."))
            else:
                self.leave(s.user_id)
        elif m.op == "kick":
            p = self.party_of(s.user_id)
            if p is None or p.leader != s.user_id:
                s.send(protocol.error("not_leader", "Chỉ đội trưởng mới mời người khác rời đội."))
            elif m.uid in p.members and m.uid != s.user_id:
                self.leave(m.uid, "kicked")
        elif m.op == "promote":
            p = self.party_of(s.user_id)
            if p is None or p.leader != s.user_id:
                s.send(protocol.error("not_leader", "Chỉ đội trưởng mới nhường chức được."))
            elif m.uid in p.members:
                p.leader = m.uid
                self.send_state(p)

    def invite(self, s: "Session", name: str) -> None:
        c = cfg()
        want = name.strip().casefold()
        target = next((o for o in self.world.sessions.values() if o.name.casefold() == want), None)
        if target is None or s.user_id in target.blocks or target.user_id in s.blocks:
            s.send(protocol.error("player_offline", "Người này không online hoặc không nhận lời mời."))
            return
        if target.user_id == s.user_id:
            s.send(protocol.error("party_self", "Không thể tự mời mình."))
            return
        p = self.party_of(s.user_id)
        if p is not None and p.leader != s.user_id:
            s.send(protocol.error("not_leader", "Chỉ đội trưởng mới mời được người vào đội."))
            return
        if p is not None and len(p.members) >= c["party_max"]:
            s.send(protocol.error("party_full", f"Tổ đội đã đủ {c['party_max']} người."))
            return
        if self.party_of(target.user_id) is not None:
            s.send(protocol.error("already_in_party", f"{target.name} đã ở trong một tổ đội khác."))
            return
        self.invites.setdefault(target.user_id, {})[s.user_id] = self.world.mono() + c["invite_seconds"]
        target.send({"t": "party", "event": "invite", "from": {"uid": s.user_id, "name": s.name, "realm": s.realm}})
        s.send({"t": "party", "event": "invited", "to": {"uid": target.user_id, "name": target.name}})

    def answer(self, s: "Session", inviter: int | None, accept: bool) -> None:
        pending = self.invites.get(s.user_id, {})
        exp = pending.pop(inviter, None) if inviter is not None else None
        if exp is None or exp < self.world.mono():
            s.send(protocol.error("no_invite", "Lời mời đã hết hạn."))
            return
        other = self.world.sessions.get(inviter)
        if not accept:
            if other is not None:
                other.send({"t": "party", "event": "declined", "by": {"uid": s.user_id, "name": s.name}})
            return
        if other is None:
            s.send(protocol.error("player_offline", "Người mời đã ngoại tuyến."))
            return
        if self.party_of(s.user_id) is not None:
            s.send(protocol.error("already_in_party", "Bạn đang ở trong một tổ đội khác, hãy rời đội trước."))
            return
        p = self.party_of(inviter)
        if p is None:
            p = self._create([inviter])
        elif p.leader != inviter:
            s.send(protocol.error("no_invite", "Lời mời đã hết hạn."))
            return
        if len(p.members) >= cfg()["party_max"]:
            s.send(protocol.error("party_full", "Tổ đội đã đủ người."))
            return
        self._add(p, s.user_id)
        self.invites.pop(s.user_id, None)
        self.send_state(p)

    # ------------------------------------------------------------ membership
    def _create(self, members: list[int]) -> Party:
        p = Party(next(self._ids), members[0], [])
        self.parties[p.id] = p
        for uid in members:
            self._add(p, uid)
        return p

    def _add(self, p: Party, uid: int) -> None:
        p.members.append(uid)
        s = self.world.sessions.get(uid)
        p.names[uid] = s.name if s else p.names.get(uid, "?")
        self.of[uid] = p.id
        self.world.realms.unqueue(uid)

    def form(self, user_ids: list[int]) -> Party:
        """A party made by the matchmaking queue (spec 14.1)."""
        for uid in user_ids:
            if self.party_of(uid) is not None:
                self.leave(uid)
        p = self._create(list(user_ids))
        self.send_state(p)
        return p

    def leave(self, user_id: int, reason: str = "leave") -> None:
        p = self.party_of(user_id)
        if p is None:
            return
        p.members.remove(user_id)
        p.offline_since.pop(user_id, None)
        del self.of[user_id]
        self._send(user_id, {"t": "party", "event": "left", "reason": reason})
        if len(p.members) < 2:  # a party of one is no party
            for uid in list(p.members):
                p.members.remove(uid)
                self.of.pop(uid, None)
                self._send(uid, {"t": "party", "event": "left", "reason": "disbanded"})
            self.parties.pop(p.id, None)
            return
        if p.leader == user_id:
            p.leader = p.members[0]
        self.send_state(p)

    # ------------------------------------------------------------ chat (Tổ Đội channel)
    def chat(self, s: "Session", msg: dict) -> bool:
        p = self.party_of(s.user_id)
        if p is None:
            return False
        for uid in p.members:
            other = self.world.sessions.get(uid)
            if other is not None and s.user_id not in other.blocks:
                other.send(msg)
        return True

    # ------------------------------------------------------------ tick
    def tick(self, now: float) -> None:
        if now < self._next_state:
            return
        c = cfg()
        self._next_state = now + c["party_state_every"]
        for inv in list(self.invites):
            pending = {k: v for k, v in self.invites[inv].items() if v > now}
            if pending:
                self.invites[inv] = pending
            else:
                del self.invites[inv]
        for p in list(self.parties.values()):
            for uid in list(p.members):
                if uid in self.world.sessions or uid in self.world.players:
                    p.offline_since.pop(uid, None)
                elif now - p.offline_since.setdefault(uid, now) > c["party_offline_grace"]:
                    self.leave(uid, "offline")
            if p.id not in self.parties:
                continue
            v = self.view(p)
            if v != p.last_view:   # health bars and who is online, only when something changed
                self.send_state(p)
