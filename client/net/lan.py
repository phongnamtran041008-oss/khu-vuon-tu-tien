"""Finding worlds on the LAN: listens for the UDP announcements that opened worlds send
(server/app/lan.py) and keeps the ones heard in the last few seconds."""
from __future__ import annotations

import json
import socket
import threading
import time

PORT = 47654
MAGIC = "khuvuon-lan"
FORGET_AFTER = 5.0


def parse(data: bytes) -> dict | None:
    try:
        m = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(m, dict) or m.get("g") != MAGIC or not isinstance(m.get("port"), int):
        return None
    return {"v": m.get("v"), "name": str(m.get("name", ""))[:40], "host": str(m.get("host", ""))[:40],
            "port": m["port"], "online": int(m.get("online") or 0)}


def _rank(ip: str) -> int:
    """Home routers hand out 192.168.x / 10.x; 172.16-31.x is mostly virtual cards (WSL, Docker)."""
    return 0 if ip.startswith("192.168.") else 1 if ip.startswith("10.") else 3 if ip == "127.0.0.1" else 2


class LanScanner:
    def __init__(self, port: int = PORT):
        self.port = port
        self.error = ""
        self._found: dict[tuple[str, int], dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="lan-scan")
        self._thread.start()

    def _run(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", self.port))
            s.settimeout(0.5)
        except OSError as e:
            self.error = str(e)
            return
        self._sock = s
        while not self._stop.is_set():
            try:
                data, (ip, _) = s.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            info = parse(data)
            if info:
                if ip.startswith("127."):
                    ip = "127.0.0.1"
                with self._lock:
                    self._found[(ip, info["port"])] = {**info, "ip": ip, "seen": time.monotonic()}
        s.close()

    def servers(self) -> list[dict]:
        """Worlds heard recently, each once: a world heard on loopback and on a LAN IP, or from
        a PC on both Wi-Fi and cable, shows by one LAN address (always the same one, so the
        row the player picked stays picked)."""
        now = time.monotonic()
        with self._lock:
            items = [v for v in self._found.values() if now - v["seen"] < FORGET_AFTER]
        best: dict[tuple, dict] = {}
        for v in sorted(items, key=lambda v: (_rank(v["ip"]), socket.inet_aton(v["ip"]))):
            best.setdefault((v["name"], v["host"], v["port"]), v)
        return sorted(best.values(), key=lambda v: (v["name"].casefold(), v["ip"]))

    def close(self) -> None:
        self._stop.set()
