"""WebSocket client for the shared world (spec 2, 15.1, 15.5).

Runs an asyncio loop on its own thread; the game loop talks to it only through
thread-safe queues: `send()` queues a message, `poll()` returns what arrived. It sends a
heartbeat every 15 s, reconnects with exponential backoff and stops for good when the
server says the login is invalid, the version is old, or the account logged in elsewhere.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time

CONNECTING, ONLINE, OFFLINE, STOPPED = "connecting", "online", "offline", "stopped"
FATAL_ERRORS = {"bad_token", "token_expired", "no_token", "version", "no_character", "banned"}


def ws_url(http_url: str) -> str:
    u = http_url.rstrip("/")
    if u.startswith("https://"):
        return "wss://" + u[len("https://"):] + "/ws"
    if u.startswith("http://"):
        return "ws://" + u[len("http://"):] + "/ws"
    return "ws://" + u + "/ws"


class WsClient:
    def __init__(self, http_url: str, token: str, version: int, heartbeat: float = 15.0,
                 start: bool = True):
        self.url = ws_url(http_url)
        self.token, self.version, self.heartbeat = token, version, heartbeat
        self.inbox: queue.Queue = queue.Queue()
        self.state = CONNECTING
        self.stop_reason: str | None = None
        self.connected_once = False
        self.rtt: float | None = None
        self.sent = 0
        self._out: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="ws")
        if start:
            self.thread.start()

    # ------------------------------------------------------------ game thread
    @property
    def online(self) -> bool:
        return self.state == ONLINE

    def send(self, msg: dict) -> bool:
        """Queue a message; returns False (dropped) while not connected."""
        loop = self._loop
        if self.state != ONLINE or loop is None or self._out is None:
            return False
        try:
            loop.call_soon_threadsafe(self._put, msg)
        except RuntimeError:  # loop already closed
            return False
        return True

    def poll(self) -> list[dict]:
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ network thread
    def _put(self, msg: dict) -> None:
        if self._out is not None:
            try:
                self._out.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        finally:
            self.state = STOPPED

    async def _main(self) -> None:
        from websockets.asyncio.client import connect
        self._loop = asyncio.get_running_loop()
        backoff = 1.0
        while not self._stop.is_set():
            self.state = CONNECTING
            try:
                async with connect(self.url, open_timeout=10, ping_interval=20, ping_timeout=20,
                                   close_timeout=2, max_size=1 << 20) as ws:
                    self._out = asyncio.Queue(maxsize=512)
                    await ws.send(json.dumps({"t": "hello", "v": self.version, "token": self.token}))
                    tasks = {asyncio.create_task(self._reader(ws)), asyncio.create_task(self._writer(ws)),
                             asyncio.create_task(self._watch_stop())}
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                    for t in done:  # a closed socket ends the reader with an error: that is expected
                        if not t.cancelled():
                            t.exception()
                    if self.connected_once:
                        backoff = 1.0
            except asyncio.CancelledError:
                break
            except Exception:  # refused, DNS, TLS, closed... all mean: try again later
                pass
            self._out = None
            if self._stop.is_set() or self.stop_reason:
                break
            self.state = OFFLINE
            self.inbox.put({"t": "_offline"})
            end = time.monotonic() + backoff
            while time.monotonic() < end and not self._stop.is_set():
                await asyncio.sleep(0.1)
            backoff = min(30.0, backoff * 2)
        self.state = STOPPED

    async def _watch_stop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(0.1)

    async def _reader(self, ws) -> None:
        async for raw in ws:
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            t = m.get("t")
            if t == "welcome":
                self.state = ONLINE
                self.connected_once = True
            elif t == "pong" and isinstance(m.get("c"), (int, float)):
                self.rtt = time.monotonic() - m["c"]
            elif t == "kicked":
                self.stop_reason = m.get("reason") or "kicked"
                if self.stop_reason == "timeout":  # our side stalled: just reconnect
                    self.stop_reason = None
            elif t == "error" and m.get("code") in FATAL_ERRORS:
                self.stop_reason = m["code"]
            self.inbox.put(m)

    async def _writer(self, ws) -> None:
        while True:
            try:
                msg = await asyncio.wait_for(self._out.get(), self.heartbeat)
            except asyncio.TimeoutError:
                msg = {"t": "ping", "c": time.monotonic()}
            await ws.send(json.dumps(msg, ensure_ascii=False, separators=(",", ":")))
            self.sent += 1
