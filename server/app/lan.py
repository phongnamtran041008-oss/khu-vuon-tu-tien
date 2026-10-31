"""LAN announcement (Minecraft-style "Open to LAN"): a world opened from the game shouts a
small UDP broadcast every couple of seconds; the "Tham gia" screen of every game on the
same network listens and lists it. Nothing here is needed to play: typing the address works too.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket

from .config import PROTOCOL_VERSION, settings

PORT = 47654          # UDP port the games listen on
MAGIC = "khuvuon-lan"
INTERVAL = 1.5

log = logging.getLogger("khu_vuon.lan")


def beacon(online: int) -> bytes:
    return json.dumps({"g": MAGIC, "v": PROTOCOL_VERSION, "name": settings.lan_world_name,
                       "host": settings.lan_host_name, "port": settings.lan_port, "online": online},
                      ensure_ascii=False).encode("utf-8")


def parse(data: bytes) -> dict | None:
    """What the client keeps from one packet, or None if it is not ours."""
    try:
        m = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(m, dict) or m.get("g") != MAGIC or not isinstance(m.get("port"), int):
        return None
    return {"v": m.get("v"), "name": str(m.get("name", ""))[:40], "host": str(m.get("host", ""))[:40],
            "port": m["port"], "online": int(m.get("online") or 0)}


def local_ipv4() -> list[str]:
    """This PC's IPv4 addresses on real networks (not loopback, not link-local 169.254.x)."""
    found: list[str] = []
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    try:   # the card the default route uses (no packet is sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return list(dict.fromkeys(ip for ip in found if not ip.startswith(("127.", "169.254.", "0."))))


def _udp(bind_ip: str | None = None) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setblocking(False)
    if bind_ip:
        s.bind((bind_ip, 0))
    return s


async def run() -> None:
    """A broadcast from an unbound socket leaves through ONE network card only — on Windows
    the one with the lowest metric, often a virtual card (WSL, Hyper-V, VPN), so friends on
    the real Wi-Fi never hear it. One socket bound to each address sends it out of every card."""
    from .realtime.world import world
    loop_sock = _udp()                  # loopback too: a PC with no network
    cards: dict[str, socket.socket] = {}
    n = 0
    try:
        while True:
            if n % 20 == 0:             # every 30 s: Wi-Fi joined, cable unplugged...
                ips = set(local_ipv4())
                for ip in set(cards) - ips:
                    cards.pop(ip).close()
                for ip in ips - set(cards):
                    try:
                        cards[ip] = _udp(ip)
                    except OSError:
                        pass
            n += 1
            packet = beacon(len(world.sessions))
            targets = [(s, "255.255.255.255") for s in cards.values()] or [(loop_sock, "255.255.255.255")]
            for s, addr in targets + [(loop_sock, "127.0.0.1")]:
                try:
                    s.sendto(packet, (addr, PORT))
                except OSError:   # no network right now; keep trying
                    pass
            await asyncio.sleep(INTERVAL)
    finally:
        loop_sock.close()
        for s in cards.values():
            s.close()
