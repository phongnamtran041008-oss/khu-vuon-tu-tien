"""Opening a world on this computer (Minecraft-style "Open to LAN").

The game starts its own server as a child process — the same exe (or `python -m
client.main`) with `--host-server` — so the world's 20 Hz tick never competes with the
game's frame loop. The child reads its settings from environment variables, stores the
world in the world's folder, listens on every network card and announces itself on the
LAN. Writing "stop" to its stdin (or the game closing) shuts it down cleanly, which saves
every character still standing in the world.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

from .worlds import World

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- the child process
def serve() -> int:
    """`--host-server`: run the world's server until told to stop."""
    world_dir = Path(os.environ["KVTT_WORLD_DIR"])
    log = open(world_dir / "server.log", "a", encoding="utf-8", buffering=1)
    # the packaged exe has no console: give logging somewhere to write
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(ROOT / "server"))
    import logging
    logging.basicConfig(level=logging.INFO, stream=log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    import uvicorn
    from app.main import app

    port = int(os.environ.get("PORT", "8000"))
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_config=None,
                                           ws_ping_interval=20, ws_ping_timeout=30))

    def watch_parent():
        try:
            for line in sys.stdin:
                if line.strip() == "stop":
                    break
        except (OSError, ValueError, TypeError):   # no stdin at all
            return
        server.should_exit = True      # "stop", or the game went away (stdin closed)
    if sys.stdin is not None:
        threading.Thread(target=watch_parent, daemon=True, name="parent-watch").start()
    logging.getLogger("khu_vuon").info("world %s on port %d", world_dir.name, port)
    server.run()
    return 0


# ---------------------------------------------------------------- the game's side
def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def free_port(first: int) -> int:
    for p in range(first, first + 50):
        if port_free(p):
            return p
    raise RuntimeError("no free port")


def lan_addresses() -> list[str]:
    """This computer's IPv4 addresses that friends on the same network can reach."""
    found: list[str] = []
    try:   # the address of the network card the default route uses (no packet is sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    from .net.lan import _rank
    return sorted((ip for ip in found if not ip.startswith(("127.", "169.254."))), key=_rank)   # stable: route card first


def child_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--host-server"]
    return [sys.executable, "-m", "client.main", "--host-server"]


class Host:
    """One world opened by this game."""

    def __init__(self, world: World, port: int, firebase_key: str, host_uid: str, host_name: str):
        self.world, self.port = world, port
        env = dict(os.environ,
                   KVTT_WORLD_DIR=str(world.path), PORT=str(port),
                   DATABASE_URL=f"sqlite+aiosqlite:///{world.db_path}",
                   JWT_SECRET=world.secret, ENV="prod", ALLOW_UNREVIEWED="1", AUTO_MIGRATE="1",
                   LOCAL_ACCOUNTS="0", FIREBASE_API_KEY=firebase_key, HOST_FIREBASE_UID=host_uid,
                   ADMIN_USERNAMES="",   # a world's usernames come from e-mail names, anyone could take one
                   LAN_BEACON="1", LAN_WORLD_NAME=world.name, LAN_HOST_NAME=host_name,
                   TIME_SCALE="1", BALANCE_PROFILE="", TRUST_PROXY_HEADERS="0", PYTHONIOENCODING="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(child_command(), cwd=str(ROOT), env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        world.touch()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def lan_urls(self) -> list[str]:
        return [f"{ip}:{self.port}" for ip in lan_addresses()]

    def alive(self) -> bool:
        return self.proc.poll() is None

    def log_tail(self, n: int = 6) -> str:
        try:
            return "\n".join((self.world.path / "server.log").read_text("utf-8", "replace").splitlines()[-n:])
        except OSError:
            return ""

    def stop(self, timeout: float = 10.0) -> None:
        if not self.alive():
            return
        try:
            self.proc.stdin.write(b"stop\n")
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(5)
