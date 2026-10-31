"""Client configuration: config.json next to the exe (or the client folder when run from
source) and session.json for the saved login (spec 2, 15.5)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROTOCOL_VERSION = 5
GAME_VERSION = "1.1.2"


def base_dir() -> Path:
    """Folder for config.json / session.json: next to the exe when packaged."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".kvtt_write_test"
        probe.write_text("x", "utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """Where config.json / session.json are written: next to the exe, or, when that folder
    is read-only (e.g. unpacked into Program Files), %LOCALAPPDATA%/KhuVuonTuTien."""
    d = base_dir()
    if not getattr(sys, "frozen", False) or _writable(d):
        return d
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    d = Path(root) / "KhuVuonTuTien"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def normalize_url(url: str) -> str:
    """What players paste: 'abc.trycloudflare.com', 'https://x/server/info', 'http://1.2.3.4:8000/'
    all become a plain base URL."""
    url = url.strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    for tail in ("/server/info", "/healthz", "/docs"):
        if url.lower().endswith(tail):
            url = url[: -len(tail)].rstrip("/")
    return url


def version_tuple(v: str) -> tuple[int, ...]:
    out = []
    for part in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent / "assets"


@dataclass
class Config:
    server_url: str = "http://127.0.0.1:8000"
    server_list_url: str = ""          # optional JSON list of servers (spec 2)
    # LAN worlds: the Firebase project's Web API key. Set = accounts are Firebase accounts and
    # the menu offers "your worlds" (hosted on this PC) and "join on the LAN" instead of one server.
    firebase_api_key: str = ""
    host_port: int = 8000              # first port tried when opening a world to the LAN
    # "owner/repo" on GitHub: the game asks its Releases for a newer version at start ("" = never)
    update_repo: str = ""
    window_scale: int = 0              # 0 = largest that fits
    fullscreen: bool = False
    music_volume: float = 0.6
    sfx_volume: float = 0.8
    voice_volume: float = 1.0
    extra: dict = field(default_factory=dict)

    # Where save() writes. None = do not write anything (e.g. a Config built in code by
    # tests, which must never leave their throw-away server address in the game folder).
    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        if path is None:
            # a config saved by the player wins over the one shipped next to the exe
            path = data_dir() / "config.json"
            shipped = base_dir() / "config.json"
            source = path if path.exists() else shipped
            if not source.exists() and not getattr(sys, "frozen", False):
                source = base_dir() / "config.example.json"   # running from source with no config yet
        else:
            source = path
        cfg = cls()
        if source.exists():
            try:
                data = json.loads(source.read_text("utf-8"))
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "path"}
                cfg = cls(**known)
            except (ValueError, TypeError):
                pass
        cfg.path = path
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or self.path
        if path is None:
            return
        try:
            data = {k: v for k, v in asdict(self).items() if k != "path"}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except OSError:
            pass


class Session:
    """Saved token so the game logs in automatically (spec 15.5)."""

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "session.json"
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text("utf-8"))
            except ValueError:
                self.data = {}

    @property
    def token(self) -> str | None:
        return self.data.get("token")

    def save(self, **kw) -> None:
        self.data.update(kw)
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), "utf-8")
        except OSError:
            pass

    def clear_token(self) -> None:
        self.data.pop("token", None)
        self.save()
