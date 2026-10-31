"""Khu Vườn Tu Tiên — game client entry point (pygame-ce).

    python -m client.main            # from the project folder
"""
from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):  # allow `python client/main.py` and the PyInstaller exe
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "client"

import pygame

from . import strings_vi as T
from .config import GAME_VERSION, PROTOCOL_VERSION, Config, Session, data_dir, normalize_url, version_tuple
from .engine.audio import Audio
from .engine.display import Display
from .engine.text import Fonts
from .net.rest import Api
from .net.ws_client import WsClient
from .scenes.base import MessageBox, Scene
from .ui.chat import ChatBox, ChatLog
from .ui.kit import UI


CHAT_ERRORS = {"chat_banned", "chat_too_long", "chat_too_fast", "no_party", "friend_unreachable"}


@dataclass
class Toast:
    text: str
    color: str
    born: float
    life: float = 2.2


@dataclass
class State:
    me: dict = field(default_factory=dict)
    character: dict = field(default_factory=dict)
    garden: dict = field(default_factory=dict)
    garden_at: float = 0.0
    seeds: list = field(default_factory=list)
    fruits: list = field(default_factory=list)
    friends: list = field(default_factory=list)
    cult: dict = field(default_factory=dict)       # /cultivation: Tu Vi, realm, stats, skills
    inv: dict = field(default_factory=dict)        # /inventory
    quests: dict = field(default_factory=dict)     # /quests
    hive: dict = field(default_factory=dict)       # /hive (stage 5)
    bee_species: dict = field(default_factory=dict)  # /bees/species: id -> name, hanzi, look
    pets: dict = field(default_factory=dict)       # /pets (stage 8): owned Linh Thú, the worn one, the book
    party: dict | None = None                      # tổ đội (stage 9), kept current by the WebSocket
    realm_queue: dict | None = None                # the bí cảnh matchmaking queue we wait in


class Game:
    def __init__(self, config: Config | None = None, session: Session | None = None,
                 size: tuple[int, int] | None = None):
        pygame.init()
        self.cfg = config or Config.load()
        self.session = session or Session()
        self.display = Display(self.cfg.window_scale, self.cfg.fullscreen, size)
        self.fonts = Fonts()
        self.audio = Audio(self.cfg.sfx_volume, self.cfg.voice_volume)
        self.ui = UI(self.display, self.fonts)
        self.ui.sfx = self.audio.play
        server = self.session.data.get("server_url") or self.cfg.server_url
        self.api = Api(server, self.session.token)
        self.api.on_unauthorized = self._unauthorized
        self.state = State()
        self.scenes: list[Scene] = []
        self.toasts: list[Toast] = []
        self.clock = pygame.time.Clock()
        self.running = True
        self.now = 0.0
        self.version_ok = True
        self.server_info: dict = {}               # last /server/info (stage 10: notices, newest exe)
        self._pending_since: float | None = None
        self._bottleneck_said = -1e9
        self.net: WsClient | None = None          # the shared world (stage 3)
        self.chat = ChatLog()
        self.chatbox = ChatBox(self)
        self._day = (0.3, 0.0)                    # (phase, game time it was measured)
        self._day_length = 7200.0
        self.party_invites: list[dict] = []       # tổ đội invitations waiting for an answer (stage 9)
        from .net.firebase import FirebaseAuth
        self.firebase = FirebaseAuth(self.api, self.session, self.cfg.firebase_api_key)   # LAN worlds
        self.host = None                          # the world this game opened (client/host.py), if any
        self.update: dict | None = None           # a newer release on GitHub (client/net/updates.py)
        self._update_check = None
        if self.cfg.update_repo:
            from .net.updates import UpdateChecker
            self._update_check = UpdateChecker(self.cfg.update_repo)
        pygame.key.set_repeat(350, 40)
        self._fetch_server_list()

    # ------------------------------------------------------------ scenes
    @property
    def top(self) -> Scene | None:
        return self.scenes[-1] if self.scenes else None

    def push(self, scene: Scene) -> Scene:
        self.scenes.append(scene)
        scene.on_enter()
        return scene

    def pop(self, scene: Scene | None = None) -> None:
        if not self.scenes:
            return
        scene = scene or self.scenes[-1]
        if scene in self.scenes:
            self.scenes.remove(scene)
            scene.on_exit()
            if self.scenes:
                self.scenes[-1].on_resume()

    def replace_all(self, scene: Scene) -> Scene:
        for s in list(self.scenes):
            s.on_exit()
        self.scenes = []
        self.ui.focus = None
        return self.push(scene)

    def message(self, text: str, title: str | None = None, **kw) -> None:
        self.push(MessageBox(self, text, title, **kw))

    def toast(self, text: str, color: str = "#2B2B2B", life: float = 2.2) -> None:
        self.toasts.append(Toast(text, color, self.now, life))

    def api_error(self, err) -> None:
        """Default error display for failed requests."""
        if err.status == 401:
            return
        self.toast(err.message_vi, "#BC4749")

    # ------------------------------------------------------------ session
    def _fetch_server_list(self) -> None:
        """Spec 2 / 19C: the list is the truth unless the player typed a server in Settings.
        A saved address that is still on the list is kept; one that dropped off it (an old
        quick-tunnel URL) is replaced by the first entry, so nobody needs a new exe."""
        if not self.cfg.server_list_url or self.session.data.get("server_manual"):
            return

        def ok(data):
            servers = data.get("servers") if isinstance(data, dict) else data
            urls = [normalize_url(x["url"] if isinstance(x, dict) else str(x)) for x in servers or []]
            urls = [u for u in urls if u]
            if not urls or self.api.base_url in urls:
                return
            self.api.set_base_url(urls[0])
            self.session.save(server_url=urls[0])
            self.check_version()
        self.api.get(self.cfg.server_list_url, ok, lambda e: None, retries=1)

    def set_token(self, token: str | None, username: str | None = None) -> None:
        self.api.token = token
        if token:
            self.session.save(token=token, username=username or self.session.data.get("username"),
                              server_url=self.api.base_url)
        else:
            self.session.clear_token()

    @property
    def lan_mode(self) -> bool:
        """Accounts are Firebase accounts and worlds live on players' PCs (Minecraft style)."""
        return bool(self.cfg.firebase_api_key)

    def join_world(self, url: str, on_fail) -> None:
        """LAN worlds: check the world's version, trade a Firebase ID token for its session
        token, then play. `on_fail(message)` on any problem."""
        url = normalize_url(url)
        self.api.set_base_url(url)
        self.api.token = None

        def info(i):
            if not isinstance(i, dict) or i.get("protocol_version") != PROTOCOL_VERSION:
                on_fail(T.WORLD_OTHER_VERSION.format(v=(i or {}).get("version", "?")))
            elif i.get("auth") != "firebase":
                on_fail(T.WORLD_NOT_LAN)
            else:
                self.server_info = i
                self.firebase.id_token(got_token, on_fail)

        def got_token(tok):
            self.api.post("/auth/firebase", {"id_token": tok}, authed,
                          lambda e: on_fail(e.message_vi), retries=1, timeout=20)

        def authed(r):
            self.set_token(r["token"], r.get("username"))
            self.enter_game()
        self.api.get("/server/info", info, lambda e: on_fail(T.WORLD_UNREACHABLE.format(url=url)),
                     retries=1, timeout=6)

    def open_world(self, world) -> None:
        """Start this PC's server for `world` (stopping another one first)."""
        from .host import Host, free_port
        if self.host is not None and (self.host.world.slug != world.slug or not self.host.alive()):
            self.stop_host()
        if self.host is None:
            name = (self.firebase.email or "").split("@")[0]
            self.host = Host(world, free_port(self.cfg.host_port), self.cfg.firebase_api_key, self.firebase.uid, name)

    def stop_host(self) -> None:
        if self.host is not None:
            self.disconnect_world()
            self.host.stop()
            self.host = None

    def _unauthorized(self) -> None:
        from .scenes.login import LoginScene
        self.disconnect_world()
        if self.lan_mode:
            from .scenes.play import PlayScene
            if not isinstance(self.scenes[0] if self.scenes else None, PlayScene):
                self.replace_all(PlayScene(self, notice=T.WORLD_SESSION_ENDED))
            return
        if not isinstance(self.scenes[0] if self.scenes else None, LoginScene):
            self.set_token(None)
            self.replace_all(LoginScene(self, notice="Phiên đăng nhập đã hết hạn, hãy đăng nhập lại."))

    def enter_game(self) -> None:
        """After login: create a character if needed, else go to the abode."""
        from .scenes.abode import AbodeScene
        from .scenes.create_char import CreateCharScene

        def got_me(me):
            self.state.me = me
            if not me.get("has_character"):
                self.replace_all(CreateCharScene(self))
                return
            self.api.get("/character", got_char, self.api_error)

        def got_char(ch):
            self.state.character = ch
            self.connect_world()
            if self.host is not None and self.api.base_url == self.host.url:
                addrs = ", ".join(self.host.lan_urls()) or f"127.0.0.1:{self.host.port}"
                self.chat.system(T.WORLD_HOSTING.format(name=self.host.world.name, addrs=addrs))
            self.refresh_friends()
            self.refresh_cult()
            self.refresh_inv()
            self.refresh_quests()
            self.refresh_bee_species()
            self.refresh_pets()
            zone = ch.get("zone_id")
            if zone in T.WORLD_ZONES:  # we logged out somewhere in the world: go back there
                from .scenes.world import WorldScene
                self.replace_all(WorldScene(self, zone, via="resume"))
            else:
                self.replace_all(AbodeScene(self))

        self.api.get("/me", got_me, self.api_error)

    # ------------------------------------------------------------ the shared world (stage 3)
    def connect_world(self) -> None:
        self.disconnect_world()
        self.chat.my_uid = self.state.me.get("id")
        self.net = WsClient(self.api.base_url, self.api.token or "", PROTOCOL_VERSION)

    def disconnect_world(self) -> None:
        if self.net is not None:
            self.net.close()
            self.net = None

    def world_scene(self):
        from .scenes.world import WorldScene
        return next((s for s in self.scenes if isinstance(s, WorldScene)), None)

    def go_village(self) -> None:
        from .scenes.world import WorldScene
        self.replace_all(WorldScene(self, "truc_lam_thon", via="abode"))

    def enter_abode(self, x=None, y=None, facing: str = "up") -> None:
        from .scenes.abode import AbodeScene
        ch = self.state.character
        ch["zone_id"] = "abode"
        if x is not None and y is not None:
            ch["x"], ch["y"], ch["facing"] = x, y, facing
        self.replace_all(AbodeScene(self))

    def set_day(self, phase: float) -> None:
        self._day = (float(phase), self.now)

    def day_phase(self) -> float:
        phase, at = self._day
        return (phase + (self.now - at) / self._day_length) % 1.0

    def refresh_me(self) -> None:
        self.api.get("/me", lambda me: self.state.me.update(me), lambda e: None)

    def refresh_cult(self) -> None:
        self.api.get("/cultivation", lambda d: setattr(self.state, "cult", d), lambda e: None)

    def refresh_inv(self) -> None:
        self.api.get("/inventory", lambda d: setattr(self.state, "inv", d), lambda e: None)

    def refresh_quests(self) -> None:
        self.api.get("/quests", lambda d: setattr(self.state, "quests", d), lambda e: None)

    def on_xp(self, info: dict | None) -> None:
        """Tu Vi news from any answer, kill or quest (spec 7.3)."""
        if not info:
            return
        c = self.state.cult
        if c:
            c.update({"xp": info["xp"], "need": info["need"], "label": info["label"],
                      "realm": info["realm"], "stage": info["stage"]})
        if info.get("stage_up"):
            self.toast(T.STAGE_UP.format(label=info["label"]), "#C99A3A")
            self.audio.play("discover")
            self.refresh_cult()
        elif info.get("bottleneck") and c and c.get("pill_name") and self.now - self._bottleneck_said > 90:
            self._bottleneck_said = self.now    # once in a while, not after every right answer
            self.toast(T.BOTTLENECK.format(pill=c["pill_name"], realm=T.REALMS.get(c.get("next_realm"), "")),
                       "#C99A3A")

    def refresh_pets(self) -> None:
        def ok(d):
            from .engine import sprites
            sprites.set_pet_looks(d.get("looks", {}))
            self.state.pets = d
        self.api.get("/pets", ok, lambda e: None)

    def worn_pet(self) -> str | None:
        """Species of the Linh Thú following the player (stage 8)."""
        pets = self.state.pets or {}
        w = next((p for p in pets.get("pets", []) if p.get("equipped")), None)
        return w["pet_type"] if w else None

    def open_pets(self) -> None:
        from .scenes.pets import PetScene
        self.push(PetScene(self))

    def open_alchemy(self) -> None:
        from .scenes.alchemy import AlchemyScene
        self.push(AlchemyScene(self))

    def refresh_bee_species(self) -> None:
        if not self.state.bee_species:
            self.api.get("/bees/species", lambda d: setattr(self.state, "bee_species", d.get("species", {})),
                         lambda e: None)

    def bee_look(self, sp: str) -> dict | None:
        return (self.state.bee_species.get(sp) or {}).get("look")

    def open_hive(self, on_close=None) -> None:
        from .scenes.hive import HiveScene
        self.push(HiveScene(self, on_close=on_close))

    def open_bee_book(self) -> None:
        from .scenes.hive import BeeBookScene
        self.push(BeeBookScene(self))

    def open_char(self) -> None:
        from .scenes.rpg import CharacterScene
        self.push(CharacterScene(self))

    def open_quests(self) -> None:
        from .scenes.rpg import QuestScene
        self.push(QuestScene(self))

    def refresh_friends(self) -> None:
        self.api.get("/friends", lambda d: setattr(self.state, "friends", d.get("friends", [])), lambda e: None)

    def open_player_menu(self, uid, name: str, realm: str | None = None) -> None:
        from .scenes.social import PlayerMenu
        if uid is None or uid == self.state.me.get("id"):
            return
        self.push(PlayerMenu(self, uid, name, realm))

    def open_party(self) -> None:
        from .scenes.realm import PartyScene
        self.push(PartyScene(self))

    def answer_invite(self, uid: int, accept: bool) -> None:
        self.party_invites = [i for i in self.party_invites if i["uid"] != uid]
        if self.net is not None:
            self.net.send({"t": "party", "op": "accept" if accept else "decline", "uid": uid})

    def _on_party(self, m: dict) -> None:
        ev = m.get("event")
        if ev == "state":
            self.state.party = m.get("party")
        elif ev == "left":
            self.state.party = None
            self.toast(T.PARTY_LEFT.get(m.get("reason"), T.PARTY_LEFT["leave"]), "#5A5A5A")
        elif ev == "invite":
            frm = m.get("from") or {}
            self.party_invites = [i for i in self.party_invites if i["uid"] != frm.get("uid")]
            self.party_invites.append({"uid": frm.get("uid"), "name": frm.get("name", "?"), "until": self.now + 60})
            text = T.PARTY_INVITE_FROM.format(name=frm.get("name", "?"), realm=T.REALMS.get(frm.get("realm"), ""))
            from .scenes.rpg import CombatQuizScene
            if any(isinstance(s, CombatQuizScene) for s in self.scenes):   # never over a fight
                self.toast(T.PARTY_INVITE_TOAST.format(name=frm.get("name", "?")), "#4A7CC8")
            else:
                uid = frm.get("uid")
                self.message(text, T.PARTY_TITLE, ok=T.PARTY_ACCEPT, cancel=T.PARTY_DECLINE,
                             on_ok=lambda: self.answer_invite(uid, True),
                             on_cancel=lambda: self.answer_invite(uid, False))
        elif ev == "invited":
            self.toast(T.PARTY_INVITED.format(name=(m.get("to") or {}).get("name", "")), "#4A7CC8")
        elif ev == "declined":
            self.toast(T.PARTY_DECLINED.format(name=(m.get("by") or {}).get("name", "")), "#5A5A5A")

    def _on_realm(self, m: dict) -> None:
        ev = m.get("event")
        if ev == "entering":
            self.state.realm_queue = None
            self.toast(T.REALM_ENTERING.format(name=m.get("name_vi", "")), "#4A7CC8")
        elif ev == "queued":
            self.state.realm_queue = {k: m.get(k) for k in ("key", "realm", "waiting")}
        elif ev == "unqueued":
            self.state.realm_queue = None
        elif ev == "start":
            self.state.realm_queue = None

    def open_friends(self) -> None:
        from .scenes.social import FriendsScene
        self.push(FriendsScene(self))

    def open_settings(self) -> None:
        from .scenes.settings import SettingsScene
        self.push(SettingsScene(self, in_game=True))

    def open_book(self) -> None:
        from .scenes.book import BookScene
        self.push(BookScene(self))

    def open_library(self) -> None:
        """Tàng Thư Các (spec 9.3): also a button in the Sổ Phát Hiện and the L key."""
        from .scenes.library import LibraryScene
        self.push(LibraryScene(self))

    def open_bag(self) -> None:
        from .scenes.bag import BagScene
        self.push(BagScene(self, None))

    def _poll_net(self) -> None:
        if self.net is None:
            return
        for m in self.net.poll():
            self._on_net(m)

    def _on_net(self, m: dict) -> None:
        t = m.get("t")
        ws = self.world_scene()
        if t == "welcome":
            self.chat.my_uid = (m.get("you") or {}).get("uid", self.chat.my_uid)
            self._day_length = float(m.get("day_length") or self._day_length)
            if m.get("day") is not None:
                self.set_day(m["day"])
        elif t == "chat":
            self.chat.add_server(m)
        elif t == "chat_history":
            for item in m.get("items", []):
                self.chat.add_server(item)
        elif t == "friend":
            self._on_friend(m)
        elif t == "party":
            self._on_party(m)
        elif t == "party_xp":
            self.on_xp(m.get("xp"))
        elif t == "notice":
            self.toast(m.get("text", ""), "#8E5AC8", 6.0 if m.get("kind") else 2.2)
            self.chat.system(T.NOTICE.format(text=m.get("text", "")))
            if m.get("kind") in ("announce", "maintenance"):
                self.server_info[{"announce": "announcement"}.get(m["kind"], "maintenance_message")] = m.get("text")
        elif t == "admin":   # replies to /admin commands (stage 10)
            for line in m.get("lines", []):
                self.chat.system(line)
        elif t == "realm":
            self._on_realm(m)
        elif t == "stats":
            ch = self.state.character
            ch.update({"realm": m.get("realm"), "realm_stage": m.get("stage")})
            if self.state.cult is not None:
                self.state.cult["stats"] = m.get("stats", {})
            self.refresh_cult()
        elif t == "skills":
            if self.state.cult is not None:
                self.state.cult["skills"] = m.get("skills", [])
        elif t == "loot":
            self.on_xp(m.get("xp"))
            if "spirit_stones" in m:
                self.state.me["spirit_stones"] = m["spirit_stones"]
            for it in m.get("items", []):
                self.toast(T.LOOT_ITEM.format(name=it["name_vi"], qty=it["qty"]), "#4A7CC8")
            for e in m.get("equipment", []):
                self.toast(T.LOOT_GEAR.format(name=e["name_vi"], rarity=e["rarity_vi"]), e.get("color", "#6A994E"))
            if m.get("items") or m.get("equipment"):
                self.refresh_inv()
            self.audio.play("coin")
        elif t == "quest" and m.get("event") == "done":
            self.toast(T.QUEST_DONE.format(title=m["quest"]["title_vi"]), "#C99A3A")
            self.refresh_quests()
        elif t == "xp_lost":
            self.toast(T.XP_LOST.format(n=m.get("lost", 0)), "#BC4749")
            self.refresh_cult()
        elif t == "kicked":
            self.disconnect_world()
            text = T.KICKED_ELSEWHERE if m.get("reason") == "elsewhere" else T.KICKED.format(msg=m.get("message_vi", ""))
            from .scenes.menu import MenuScene
            self.replace_all(MenuScene(self))
            self.message(text)
            return
        elif t == "error" and m.get("code") in ("bad_token", "token_expired", "no_token"):
            self._unauthorized()
            return
        elif t == "error" and m.get("code") in ("version", "banned", "no_character"):
            self.disconnect_world()
            self.message(T.VERSION_MISMATCH if m["code"] == "version" else m.get("message_vi", ""))
            return
        elif t == "error" and (m.get("code") in CHAT_ERRORS or ws is None):
            self.chat.system(m.get("message_vi", ""))  # chat problems show up in the chat box
            return
        if ws is not None and t in ("welcome", "zone", "snap", "error", "chat", "q", "q_end", "dead", "loot",
                                    "act_fail", "cast", "realm"):
            ws.on_net(m)

    def _on_friend(self, m: dict) -> None:
        ev, name = m.get("event"), (m.get("user") or {}).get("name", "")
        if ev == "online":
            self.toast(T.FRIEND_ONLINE.format(name=name), "#6A994E")
        elif ev == "offline":
            self.toast(T.FRIEND_LEFT.format(name=name), "#5A5A5A")
        elif ev == "request":
            self.toast(T.FRIEND_REQUEST.format(name=name), "#4A7CC8")
        elif ev == "accepted":
            self.toast(T.FRIEND_NOW.format(name=name), "#6A994E")
        elif ev == "gift":
            self.toast(T.GIFT_GOT.format(name=name, item=m.get("name_vi", ""), n=m.get("qty", 1)), "#C99A3A")
            self.audio.play("coin")
            self.refresh_inv()
        elif ev == "helped":
            n = m.get("reward", 0)
            self.state.me["spirit_stones"] = self.state.me.get("spirit_stones", 0) + n
            self.toast(T.FRIEND_HELPED.format(name=name, n=n), "#6A994E")
            self.audio.play("coin")
        if ev in ("online", "offline", "accepted"):
            self.refresh_friends()

    def leave_abode(self) -> None:
        for s in self.scenes:
            if hasattr(s, "save_position"):
                s.save_position()

    def check_version(self, on_ok=None) -> None:
        """Spec 15.5: compare the protocol with /server/info before playing."""
        def ok(info):
            self.server_info = info if isinstance(info, dict) else {}
            self.version_ok = self.server_info.get("protocol_version", PROTOCOL_VERSION) == PROTOCOL_VERSION
            if not self.version_ok:
                self.message(self.update_text())
            elif on_ok:
                on_ok(info)
        self.api.get("/server/info", ok, lambda e: None, retries=1, timeout=8)

    def newer_client(self) -> str | None:
        """The newest exe's version when it is newer than this one."""
        latest = self.server_info.get("latest_client_version")
        return latest if latest and version_tuple(latest) > version_tuple(GAME_VERSION) else None

    def update_text(self) -> str:
        url = self.server_info.get("client_download_url")
        return T.VERSION_MISMATCH + ("\n" + T.DOWNLOAD_AT.format(url=url) if url else "")

    def _poll_update(self) -> None:
        """A newer release came back from GitHub: ask once on the title screen, or just mention
        it when the player is already playing (the title screen keeps a link to it)."""
        chk = self._update_check
        if chk is None or not chk.done:
            return
        self._update_check = None
        self.update = chk.result
        if not self.update:
            return
        from .scenes.menu import MenuScene
        if isinstance(self.top, MenuScene):
            self.offer_update()
        else:
            self.toast(T.UPDATE_TOAST.format(v=self.update["version"]), "#4A7CC8", life=6)

    def offer_update(self) -> None:
        u = self.update
        text = T.UPDATE_TEXT.format(v=u["version"], cur=GAME_VERSION) + (f"\n{u['notes']}" if u["notes"] else "")
        self.message(text + "\n\n" + T.UPDATE_HOW, T.UPDATE_TITLE, ok=T.UPDATE_DOWNLOAD, cancel=T.UPDATE_LATER,
                     on_ok=self.download_update, width=320)

    def download_update(self) -> None:
        import webbrowser
        try:
            webbrowser.open(self.update["url"])
            self.toast(T.UPDATE_OPENED, "#4F7A3A", life=4)
        except Exception:      # no browser: show the address to type in
            self.message(T.DOWNLOAD_AT.format(url=self.update["page"]))

    # ------------------------------------------------------------ loop
    def run(self) -> None:
        from .scenes.menu import MenuScene
        if not self.scenes:
            self.push(MenuScene(self))
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self.step(min(dt, 0.1))
        self.shutdown()

    def step(self, dt: float, events: list | None = None) -> None:
        self.now += dt
        events = pygame.event.get() if events is None else events
        for e in events:
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type in (pygame.VIDEORESIZE, pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED):
                self.display.on_resize()
        self.api.poll()
        self._poll_net()
        self._poll_update()
        self.ui.begin(events, dt)
        top = self.top
        for s in list(self.scenes):
            s.update(dt, s is top)
        self.display.world.fill((20, 18, 15))
        # an opaque scene (e.g. visiting a friend's abode) hides everything below it
        first = max((i for i, sc in enumerate(self.scenes) if sc.opaque), default=0)
        visible = self.scenes[first:]
        for s in visible:
            if s.draws_world:
                s.draw_world(self.display.world)
        self.display.present_world()
        for s in visible:
            self.ui.enabled = s is self.top
            s.draw_ui(self.ui)
        self.ui.enabled = True
        self._draw_overlays()
        self.ui.end()
        pygame.display.flip()

    def _draw_overlays(self) -> None:
        ui = self.ui
        y = getattr(self.top, "toast_y", 4)
        for t in list(self.toasts):
            age = self.now - t.born
            if age > t.life:
                self.toasts.remove(t)
                continue
            w = ui.text_size(t.text, 9)[0] + 16
            ty = y - min(age * 4, max(0.0, y - 2))       # drifts up a little, never off screen
            ui.fill(240 - w / 2, ty, w, 14, (244, 235, 217, 235))
            ui.border(240 - w / 2, ty, w, 14, t.color)
            ui.text(t.text, 240, ty + 7, 9, t.color, anchor="center")
            y += 17
        net_down = self.net is not None and self.net.connected_once and not self.net.online
        if self.api.offline or net_down:
            ui.fill(0, 0, 480, 12, (188, 71, 73, 230))
            ui.text(T.OFFLINE, 240, 6, 8, "#FFFFFF", anchor="center")
        if self.api.pending:
            if self._pending_since is None:
                self._pending_since = self.now
            if self.now - self._pending_since > 0.35:
                a = self.now * 6
                for i in range(8):
                    ang = a + i * 0.785
                    x = 466 + 6 * math.cos(ang)
                    yy = 258 + 6 * math.sin(ang)
                    ui.fill(x - 1, yy - 1, 2, 2, (43, 43, 43, 60 + i * 24))
        else:
            self._pending_since = None

    def shutdown(self) -> None:
        self.leave_abode()
        deadline = time.time() + 2.0  # let the last position save go out
        while self.api.pending and time.time() < deadline:
            self.api.poll()
            time.sleep(0.02)
        for s in list(self.scenes):
            s.on_exit()
        self.disconnect_world()
        self.stop_host()      # saves the world before the game closes
        self.api.close()
        time.sleep(0.05)
        pygame.quit()


def _report_crash() -> None:
    """The packaged exe has no console: write the traceback next to the game and say where."""
    import traceback
    path = data_dir() / "vuonchu_loi.txt"
    try:
        path.write_text(f"Khu Vườn Tu Tiên v{GAME_VERSION}\n\n" + traceback.format_exc(), "utf-8")
    except OSError:
        return
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, T.CRASHED.format(path=path), T.TITLE, 0x10)


def smoke_test(modules: list[str]) -> int:
    """`VuonChu.exe --smoke-test <module>...`: import every listed module and load fonts and
    maps, then quit with 0. tools/build_exe.py runs it to prove nothing was left out."""
    import importlib
    from .engine.tilemap import load_map
    os.environ["SDL_VIDEODRIVER"] = os.environ["SDL_AUDIODRIVER"] = "dummy"
    for name in modules:
        importlib.import_module(name)
    pygame.init()
    pygame.display.set_mode((480, 270))
    if Fonts().missing:
        raise RuntimeError("fonts missing")
    load_map("abode")
    pygame.quit()
    return 0


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--host-server":   # a world opened from the game
        from .host import serve
        sys.exit(serve())
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke-test":
        try:
            code = smoke_test(sys.argv[2:])
        except Exception:
            import traceback
            (data_dir() / "vuonchu_smoke.txt").write_text(traceback.format_exc(), "utf-8")
            code = 1
        sys.exit(code)
    try:
        if os.environ.get("KVTT_SERVER"):
            cfg = Config.load()
            cfg.server_url = os.environ["KVTT_SERVER"]
            Game(cfg).run()
        else:
            Game().run()
    except Exception:
        if not getattr(sys, "frozen", False):
            raise
        _report_crash()


if __name__ == "__main__":
    main()
