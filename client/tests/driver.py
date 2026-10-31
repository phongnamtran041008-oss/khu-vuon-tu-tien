"""Headless test driver: runs the real client against a real server, clicking widgets by
id, typing text and holding keys, and saving screenshots. Used by test_flow.py and by
`python -m client.tests.driver` to produce screenshots for review."""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from client.config import Config, Session  # noqa: E402
from client.main import Game  # noqa: E402


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ServerProcess:
    def __init__(self, workdir: Path, time_scale: float = 86400, port: int | None = None, env: dict | None = None):
        self.db = workdir / "flow.db"
        self.port = port or free_port()
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{self.db}", TIME_SCALE=str(time_scale),
                   RATE_LIMIT="0", ENV="dev", ALLOW_UNREVIEWED="1", **(env or {}))
        self.log = open(workdir / "server.log", "a")
        # its own process group on Windows, so stop() can send Ctrl+Break (a graceful shutdown)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port)],
                                     cwd=ROOT / "server", env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                     creationflags=flags)
        self.url = f"http://127.0.0.1:{self.port}"
        import httpx
        for _ in range(100):
            try:
                if httpx.get(self.url + "/server/info", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError("server did not start")

    def sql(self, q: str, args=()):
        con = sqlite3.connect(self.db)
        try:
            cur = con.execute(q, args)
            rows = cur.fetchall()
            con.commit()
            return rows
        finally:
            con.close()

    def stop(self):
        """Shut the server down the way Ctrl+C does, so it saves positions like a real one.
        (On Windows terminate() kills the process outright and nothing would be saved.)"""
        if self.proc.poll() is None:
            if os.name == "nt":
                import signal
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        if not self.log.closed:
            self.log.close()


class Keys:
    def __init__(self):
        self.held: set[int] = set()

    def __getitem__(self, k):
        return k in self.held


class Driver:
    def __init__(self, server_url: str, workdir: Path, shots: Path | None = None):
        self.workdir = workdir
        self.shots = shots
        self.keys = Keys()
        pygame.key.get_pressed = lambda: self.keys  # movement reads this
        cfg = Config(server_url=server_url)
        self.session_path = workdir / "session.json"
        self.game = Game(cfg, Session(self.session_path), size=(1440, 810))
        from client.scenes.menu import MenuScene
        self.game.push(MenuScene(self.game))
        self.n_shots = 0
        self.toast_log: list[str] = []
        orig = self.game.toast
        self.game.toast = lambda text, color="#2B2B2B": (self.toast_log.append(text), orig(text, color))

    # ------------------------------------------------------------ stepping
    def step(self, frames: int = 1, events=None) -> None:
        """Advance frames using real elapsed time, like the real game loop does."""
        for i in range(frames):
            now = time.perf_counter()
            dt = min(0.1, max(1 / 240, now - getattr(self, "_last", now - 1 / 60)))
            self._last = now
            self.game.step(dt, events if (events and i == 0) else [])
            time.sleep(0.004)

    def wait(self, pred, timeout: float = 10.0, what: str = "") -> None:
        end = time.time() + timeout
        while time.time() < end:
            self.step(2)
            if pred():
                self.step(2)
                return
            time.sleep(0.01)
        toasts = self.toast_log[-5:]
        if self.shots:
            self.shot("FAILED")
        raise AssertionError(f"timed out waiting for {what or pred}; scenes={self.scene_names()}; toasts={toasts}")

    def wait_api(self, timeout: float = 10.0) -> None:
        self.wait(lambda: self.game.api.pending == 0, timeout, "api idle")

    def scene_names(self) -> list[str]:
        return [type(s).__name__ for s in self.game.scenes]

    def top_is(self, name: str) -> bool:
        return self.game.top is not None and type(self.game.top).__name__ == name

    def wait_scene(self, name: str, timeout: float = 10.0) -> None:
        self.wait(lambda: self.top_is(name), timeout, f"scene {name}")

    # ------------------------------------------------------------ input
    def click_at(self, pos) -> None:
        pygame.mouse.set_pos(pos)
        self.step(1, [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)])
        self.step(1, [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)])
        self.step(1)

    def click(self, wid: str, timeout: float = 5.0) -> None:
        self.wait(lambda: wid in self.game.ui.widgets, timeout, f"widget {wid}")
        self.click_at(self.game.ui.widgets[wid].center)

    def has(self, wid: str) -> bool:
        return wid in self.game.ui.widgets

    def press(self, key: int) -> None:
        self.step(1, [pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)])
        self.step(1)

    def type(self, text: str) -> None:
        for ch in text:
            self.step(1, [pygame.event.Event(pygame.TEXTINPUT, text=ch)])

    def hold(self, keys: list[int], seconds: float) -> None:
        """Hold keys for `seconds` of real time (movement follows real elapsed time)."""
        self.keys.held = set(keys)
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.step(1)
        self.keys.held = set()
        self.step(1)

    def shot(self, name: str) -> Path | None:
        if not self.shots:
            return None
        self.shots.mkdir(parents=True, exist_ok=True)
        self.n_shots += 1
        p = self.shots / f"{self.n_shots:02d}_{name}.png"
        self.step(2)
        pygame.image.save(self.game.display.window, str(p))
        return p

    def close(self) -> None:
        self.game.running = False
        self.game.shutdown()


def answer_current_quiz(drv: Driver, server: ServerProcess, correct: bool = True) -> dict:
    """Reads the answer key from the server database (test only) and answers through the UI."""
    q = drv.game.top.q
    key = server.sql("select answer_key from quiz_sessions where id=?", (q["session_id"],))[0][0]
    import json
    key = json.loads(key)
    inp = q["input"]
    if inp in ("choice", "tone"):
        target = key["option"] if correct else next(o["id"] for o in q["options"] if o["id"] != key["option"])
        drv.click(f"opt_{target}")
    elif inp == "text":
        drv.type(key["pinyin_numeric"].replace(" ", "") if correct else "xx9")
        drv.press(pygame.K_RETURN)
    elif inp == "order":
        pool = {}
        for tid, t in key["token_text"].items():
            pool.setdefault(t, []).append(tid)
        for t in key["order_text"]:
            drv.click(f"tok_{pool[t].pop()}")
        drv.click("ord_submit")
    drv.wait(lambda: drv.game.top is not None and getattr(drv.game.top, "result", None), 10, "quiz result")
    return drv.game.top.result


def main() -> int:
    """Run the full new-player flow and leave screenshots in ./screenshots."""
    from client.tests.test_flow import run_flow
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "screenshots"
    with tempfile.TemporaryDirectory() as tmp:
        run_flow(Path(tmp), out)
    print("screenshots in", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
