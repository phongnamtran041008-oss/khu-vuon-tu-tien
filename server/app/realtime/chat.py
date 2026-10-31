"""Chat (spec 15.3): channels Thế Giới (world), Khu Vực (zone channel), Bạn Bè (private,
friends only) and Tổ Đội (the party, stage 9). Basic Vietnamese profanity filter, at most
one message every 2 seconds, 200 characters, blocked players are never delivered."""
from __future__ import annotations

import re
import unicodedata
from collections import deque
from typing import TYPE_CHECKING

from .. import admin, balance, clock
from ..moderation import contains_banned, mask
from . import protocol

if TYPE_CHECKING:
    from .world import Session, World

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")


def cfg() -> dict:
    return balance.load("social")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = CONTROL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def filter_text(text: str) -> str:
    masked = mask(text)
    if contains_banned(masked):  # a banned phrase spread over several words
        return "***"
    return masked


class ChatService:
    def __init__(self, world: "World"):
        self.world = world
        self.world_history: deque = deque(maxlen=cfg()["chat_world_history"])
        self.zone_history: dict[str, deque] = {}

    def _deliver(self, to: "Session", msg: dict) -> None:
        if msg["from"]["uid"] in to.blocks:
            return
        to.send(msg)

    def handle(self, s: "Session", m: protocol.Chat) -> None:
        c = cfg()
        if admin.is_admin_command(m.text):   # stage 10: never shown in any channel
            self.world.spawn(admin.handle_chat(self.world, s, m.text))
            return
        if s.chat_banned_until and s.chat_banned_until > clock.now():
            s.send(protocol.error("chat_banned", f"Bạn bị cấm chat đến {s.chat_banned_until:%d/%m %H:%M} (UTC)."))
            return
        text = clean(m.text)
        if not text:
            return
        if len(text) > c["chat_max_len"]:
            s.send(protocol.error("chat_too_long", f"Tin nhắn dài tối đa {c['chat_max_len']} ký tự."))
            return
        now = self.world.mono()
        wait = c["chat_min_interval_seconds"] - (now - s.last_chat)
        if wait > 0:
            s.send(protocol.error("chat_too_fast", "Chậm lại một chút, mỗi 2 giây một tin nhé.",
                                  wait=round(wait, 1)))
            return
        msg = {"t": "chat", "ch": m.ch, "from": {"uid": s.user_id, "id": f"p{s.user_id}", "name": s.name},
               "text": filter_text(text), "ts": clock.now().isoformat() + "Z"}
        if m.ch == "party":   # stage 9: the Tổ Đội channel
            if not self.world.parties.chat(s, msg):
                s.send(protocol.error("no_party", "Bạn chưa ở trong tổ đội nào."))
                return
            s.last_chat = now
        elif m.ch == "world":
            s.last_chat = now
            self.world_history.append(msg)
            for other in list(self.world.sessions.values()):
                self._deliver(other, msg)
        elif m.ch == "zone":
            p = s.player
            if p is None or p.channel is None:
                s.send(protocol.error("not_in_zone", "Kênh khu vực chỉ dùng được ngoài thế giới."))
                return
            s.last_chat = now
            msg["zone"] = p.channel.zone_id
            msg["channel"] = p.channel.number
            self.zone_history.setdefault(p.channel.key, deque(maxlen=cfg()["chat_zone_history"])).append(msg)
            for other in list(p.channel.players.values()):
                if other.session is not None:
                    self._deliver(other.session, msg)
        else:  # friend: a private message to one friend, by display name
            target = None
            want = (m.to or "").strip().casefold()
            for fid in s.friends:
                other = self.world.sessions.get(fid)
                if other is not None and other.name.casefold() == want:
                    target = other
            if target is None:
                s.send(protocol.error("friend_unreachable",
                                      "Người này không trong danh sách bạn bè hoặc đang ngoại tuyến."))
                return
            s.last_chat = now
            msg["to"] = {"uid": target.user_id, "name": target.name}
            self._deliver(target, msg)
            s.send(msg)  # echo, so the sender sees it in the Bạn Bè tab

    def send_history(self, s: "Session", which: str) -> None:
        if which == "world":
            items = list(self.world_history)
        else:
            p = s.player
            items = list(self.zone_history.get(p.channel.key, ())) if p and p.channel else []
        items = [m for m in items if m["from"]["uid"] not in s.blocks]
        if items:
            s.send({"t": "chat_history", "ch": which, "items": items})
