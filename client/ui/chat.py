"""Chat log and the chat box drawn in the bottom-left corner (spec 15.3, 18): tabs Tất cả /
Thế giới / Khu vực / Tổ đội / Bạn bè, Enter to type, /w Tên to whisper a friend, /d for the party."""
from __future__ import annotations

import time
from collections import deque

import pygame

from .. import strings_vi as T

COLORS = {"world": "#E9C46A", "zone": "#FFFFFF", "party": "#8CB8DA", "friend": "#E89AB0", "system": "#F08A8C"}
INPUT = "chat_input"


class ChatLog:
    def __init__(self, maxlen: int = 150):
        self.items: deque = deque(maxlen=maxlen)
        self._seen: deque = deque(maxlen=400)
        self.my_uid: int | None = None
        self.last_from: dict[int, str] = {}   # uid -> their latest text (sent with a report)

    def add_server(self, m: dict) -> dict | None:
        frm = m.get("from") or {}
        key = (m.get("ts"), frm.get("uid"), m.get("text"))
        if key in self._seen:
            return None
        self._seen.append(key)
        e = {"ch": m.get("ch", "world"), "uid": frm.get("uid"), "eid": frm.get("id"), "name": frm.get("name", "?"),
             "text": m.get("text", ""), "to": (m.get("to") or {}).get("name"),
             "mine": frm.get("uid") == self.my_uid, "t": time.monotonic()}
        self.items.append(e)
        if not e["mine"] and e["uid"] is not None:
            self.last_from[e["uid"]] = e["text"]
        return e

    def system(self, text: str) -> None:
        self.items.append({"ch": "system", "uid": None, "eid": None, "name": "", "text": text, "to": None,
                           "mine": False, "t": time.monotonic()})

    def filtered(self, tab: str) -> list[dict]:
        if tab == "all":
            return list(self.items)
        return [e for e in self.items if e["ch"] in (tab, "system")]


class ChatBox:
    X, W = 4, 206

    def __init__(self, game):
        self.g = game
        self.tab = "all"
        self.whisper_to: str | None = None

    @property
    def typing(self) -> bool:
        return self.g.ui.focus == INPUT

    def open(self, whisper_to: str | None = None) -> None:
        if whisper_to:
            self.tab, self.whisper_to = "friend", whisper_to
        self.g.ui.set_focus(INPUT)

    def close(self) -> None:
        if self.typing:
            self.g.ui.set_focus(None)

    # ------------------------------------------------------------ sending
    def _friend_target(self, rest: str) -> tuple[str | None, str]:
        """'/w Tiểu Trúc chào' -> ('Tiểu Trúc', 'chào'): names may contain spaces, so the
        longest friend name that starts the text wins."""
        names = sorted((f["display_name"] for f in self.g.state.friends), key=len, reverse=True)
        low = rest.casefold()
        for n in names:
            if low.startswith(n.casefold() + " "):
                return n, rest[len(n) + 1:]
        parts = rest.split(" ", 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (None, rest)

    def send(self, text: str, in_zone: bool) -> None:
        text = text.strip()
        net = self.g.net
        if not text:
            return
        if net is None or not net.online:
            self.g.chat.system(T.CHAT_OFFLINE)
            return
        ch, to = None, None
        low = text.lower()
        if low.startswith(("/w ", "/m ")):
            to, text = self._friend_target(text[3:].strip())
            if not to or not text.strip():
                self.g.chat.system(T.CHAT_NEED_TARGET)
                return
            ch, self.whisper_to = "friend", to
        elif low.startswith("/t "):
            ch, text = "world", text[3:]
        elif low.startswith("/k "):
            ch, text = "zone", text[3:]
        elif low.startswith("/d "):
            ch, text = "party", text[3:]
        elif self.tab == "friend":
            if not self.whisper_to:
                self.g.chat.system(T.CHAT_NEED_TARGET)
                return
            ch, to = "friend", self.whisper_to
        elif self.tab == "world":
            ch = "world"
        elif self.tab in ("zone", "party"):
            ch = self.tab
        elif self.g.state.party and self.g.state.character.get("zone_id") == "bi_canh":
            ch = "party"   # inside a bí cảnh the party is who you talk to
        else:
            ch = "zone" if in_zone else "world"
        if ch == "zone" and not in_zone:
            self.g.chat.system(T.CHAT_ZONE_ONLY)
            return
        msg = {"t": "chat", "ch": ch, "text": text[:200]}
        if to:
            msg["to"] = to
        net.send(msg)

    # ------------------------------------------------------------ drawing
    def draw(self, ui, in_zone: bool, enabled: bool = True) -> None:
        now = time.monotonic()
        if enabled and not self.typing and (ui.key(pygame.K_RETURN) or ui.key(pygame.K_KP_ENTER)):
            self.open()
        typing = self.typing and enabled
        full = typing or (enabled and ui.hover(self.X - 2, 160, self.W + 4, 90))
        items = self.g.chat.filtered(self.tab)[-(9 if full else 5):]
        if not full:
            items = [e for e in items if now - e["t"] < 25]
        top_y = 166
        if full:
            ui.fill(self.X - 2, top_y - 12, self.W + 4, 250 - top_y + 13, (20, 18, 15, 150))
            tx = self.X
            for key, label in T.CHAT_TABS.items():
                w = ui.text_size(label, 7)[0] + 8
                if ui.button(f"chat_tab_{key}", tx, top_y - 11, w, 10, label, size=7, selected=self.tab == key,
                             style="dark"):
                    self.tab = key
                    ui.set_focus(INPUT)
                tx += w + 2
        # newest at the bottom; long lines wrap
        lines: list[tuple[dict, str, bool]] = []
        for e in items:
            if e["ch"] == "system":
                head = T.CHAT_PREFIX["system"] + " "
            elif e["ch"] == "friend":
                head = f"{T.CHAT_PREFIX['friend']} " + (f"→{e['to']}: " if e["mine"] and e["to"] else f"{e['name']}: ")
            else:
                head = f"{T.CHAT_PREFIX[e['ch']]} {e['name']}: "
            wrapped = ui.f.wrap(head + e["text"], 7, int((self.W - 4) * ui.s), ui.s)
            for i, line in enumerate(wrapped):
                lines.append((e, line, i == 0))
        max_lines = 9 if full else 5
        lines = lines[-max_lines:]
        y = 236 - len(lines) * 8
        for e, line, first in lines:
            age = now - e["t"]
            col = COLORS.get(e["ch"], "#FFFFFF")
            if not full and age > 20:
                col = "#B8B0A0"
            if not full:  # a soft strip behind each line so it reads on any ground
                lw = ui.text_size(line, 7)[0]
                ui.fill(self.X - 2, y - 0.5, lw + 4, 8, (20, 18, 15, 110))
            ui.text(line, self.X + 1, y + 1, 7, "#1A1A1A")
            r = ui.text(line, self.X, y, 7, col)
            if full and first and e["uid"] is not None and not e["mine"] and \
                    ui.click_in(r.x, r.y, r.w, r.h):
                self.g.open_player_menu(e["uid"], e["name"])
            y += 8
        if typing:
            label = T.CHAT_TO.format(name=self.whisper_to) if self.tab == "friend" and self.whisper_to else ""
            lw = ui.text_size(label, 7)[0] + 4 if label else 0
            if label:
                ui.text(label, self.X, 243, 7, COLORS["friend"], anchor="midleft")
            ui.input_box(INPUT, self.X + lw, 238, self.W - lw, 11, T.CHAT_PLACEHOLDER, max_len=200)
            if ui.submitted(INPUT):
                text = ui.value(INPUT)
                ui.set_value(INPUT, "")
                self.send(text, in_zone)
                self.close()
            elif ui.key(pygame.K_ESCAPE):
                self.close()
        elif enabled:
            ui.text(T.CHAT_HINT, self.X, 243, 7, "#E3D5BA", anchor="midleft")
