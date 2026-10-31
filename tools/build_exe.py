#!/usr/bin/env python3
"""Package the game client as VuonChu.exe with PyInstaller (spec 2, 19, stage 10).

    python -m pip install pyinstaller
    python tools/build_exe.py --server-url https://vuon.duckdns.org \
        --server-list-url https://raw.githubusercontent.com/<you>/<repo>/main/deploy/server_list.json

Output:
    dist/VuonChu/VuonChu.exe        the game (with _internal/: Python, pygame, fonts, maps, audio)
    dist/VuonChu/config.json        server address (players can still change it in Cài đặt)
    dist/VuonChu-<version>-windows.zip   what goes on GitHub Releases

A folder build (one-dir) is the default: it starts in about a second and antivirus tools
flag it far less often than a one-file exe, which unpacks itself to a temp folder on every
start. `--onefile` builds the single exe anyway. Build on the OS you ship for (PyInstaller
does not cross-compile); .github/workflows/release.yml does it on Windows for every tag.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from client.config import GAME_VERSION  # noqa: E402

NAME = "VuonChu"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

PLAYER_README = """Khu Vườn Tu Tiên · 字园仙途 — bản {version}

Cách chơi (giống Minecraft: thế giới lưu ngay trên máy, chơi chung qua mạng LAN):
  1. Giải nén cả thư mục này ra một chỗ bạn ghi được (Desktop, Documents...).
     Lần đầu chạy, Windows SmartScreen có thể báo "Windows protected your PC" vì exe
     chưa ký số: bấm "More info" -> "Run anyway".
  2. Nháy đúp VuonChu.exe -> Bắt đầu -> Đăng ký bằng email + mật khẩu (tài khoản Firebase,
     dùng chung cho mọi thế giới; lần sau game tự đăng nhập). Cần Internet khi đăng nhập.
  3. Chơi một mình hoặc làm chủ thế giới: tab "Thế giới của tôi" -> đặt tên -> Tạo -> Mở thế giới.
     Windows hỏi tường lửa thì bấm "Allow" (cho cả mạng Private) để bạn bè vào được.
  4. Bạn bè cùng Wi-Fi/LAN: mở game -> Bắt đầu -> tab "Tham gia mạng LAN" -> chọn thế giới
     -> Tham gia. Lần đầu Windows hỏi tường lửa thì cũng bấm "Allow", không thì không thấy
     thế giới. Vẫn không thấy thì gõ địa chỉ người chủ thấy trong Cài đặt (vd 192.168.1.5:8000).

Dữ liệu thế giới (vườn, Linh Thạch, nhân vật của mọi người vào chơi) nằm trên máy người
mở thế giới, trong thư mục worlds/ cạnh VuonChu.exe (nút "Mở thư mục" trong game). Chép thư
mục của một thế giới là sao lưu / chuyển sang máy khác. Người chủ tắt game là thế giới đóng.
Cập nhật game: có bản mới thì game tự báo lúc mở. Bấm "Tải về", tắt game, rồi giải nén file vừa
tải ĐÈ lên thư mục này (Windows hỏi thì chọn Replace). Thế giới và đăng nhập vẫn giữ nguyên.

Lỗi làm game tắt đột ngột được ghi vào vuonchu_loi.txt cạnh VuonChu.exe; lỗi của máy chủ
thế giới ở worlds/<tên>/server.log.
Giấy phép font, dữ liệu từ vựng và tài nguyên: xem CREDITS.md và LICENSES.md.
"""


# ---------------------------------------------------------------- icon
def make_icon(path: Path) -> Path:
    """A ripe legendary word-plant on rice paper, drawn by the game's own sprite code and
    scaled with nearest-neighbour so it stays pixel-sharp. Saved as a PNG-in-ICO."""
    import pygame
    from client.art import build as B

    pygame.init()
    pygame.display.set_mode((1, 1))
    base = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.rect(base, (244, 235, 217), (1, 1, 30, 30), border_radius=6)
    pygame.draw.rect(base, (43, 43, 43), (1, 1, 30, 30), width=1, border_radius=6)
    base.blit(B.plant(5, "legendary", "k"), (4, 3))
    images = []
    for size in (16, 32, 48, 256):
        buf = io.BytesIO()
        pygame.image.save(pygame.transform.scale(base, (size, size)), buf, "icon.png")
        images.append((size, buf.getvalue()))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + blobs)
    return path


# ---------------------------------------------------------------- build
def entry_script() -> Path:
    """client/main.py relies on relative imports, which PyInstaller cannot follow from a
    top-level script; a two-line entry with an absolute import lets it see the package."""
    p = BUILD / "vuonchu_entry.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("from client.main import main\n\nmain()\n", "utf-8")
    return p


def pyinstaller_args(icon: Path, onefile: bool) -> list[str]:
    sep = os.pathsep
    return [
        str(entry_script()),
        "--name", NAME,
        "--noconfirm", "--clean",
        "--windowed",                         # no console window behind the game
        "--onefile" if onefile else "--onedir",
        "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        "--paths", str(ROOT),
        "--paths", str(SERVER),               # LAN worlds: the game runs the server package `app` itself
        "--add-data", f"{ROOT / 'client' / 'assets'}{sep}assets",
        # the server finds these next to its package (app/config.py: SERVER_DIR = _internal)
        "--add-data", f"{SERVER / 'data'}{sep}data",
        "--add-data", f"{SERVER / 'maps'}{sep}maps",
        "--add-data", f"{SERVER / 'alembic'}{sep}alembic",   # migrations are read as files
        "--add-data", f"{SERVER / 'alembic.ini'}{sep}.",
        "--hidden-import", "app.main",
        "--collect-submodules", "app",
        "--collect-submodules", "uvicorn",    # loops/protocols are picked by name at run time
        "--collect-submodules", "alembic",
        "--exclude-module", "alembic.testing", "--exclude-module", "sqlalchemy.testing",
        "--hidden-import", "sqlalchemy.dialects.sqlite.aiosqlite",
        "--hidden-import", "aiosqlite",
        # scenes imported inside functions are still found: PyInstaller reads every import
        # in the bytecode, and the client has no importlib/__import__ tricks
        "--exclude-module", "client.tests",
        "--exclude-module", "tkinter", "--exclude-module", "numpy", "--exclude-module", "pytest",
        # pulled in through optional imports, never used by the game (≈45 MB)
        "--exclude-module", "jedi", "--exclude-module", "parso", "--exclude-module", "IPython",
        "--exclude-module", "PIL", "--exclude-module", "cryptography", "--exclude-module", "matplotlib",
    ]


def git_repo() -> str:
    """"owner/repo" of this checkout's GitHub remote (origin), or ""."""
    import re
    import subprocess
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else ""


def write_extras(target: Path, server: str, server_list: str, update_repo: str = "") -> None:
    cfg = json.loads((ROOT / "client" / "config.example.json").read_text("utf-8"))
    cfg["server_url"] = server
    cfg["server_list_url"] = server_list
    cfg["update_repo"] = update_repo or cfg.get("update_repo", "")
    (target / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    (target / "DOC_TRUOC.txt").write_text(PLAYER_README.format(version=GAME_VERSION), "utf-8")
    shutil.copy(ROOT / "CREDITS.md", target / "CREDITS.md")
    lic = ROOT / "client" / "assets" / "LICENSES.md"
    if lic.exists():
        shutil.copy(lic, target / "LICENSES.md")


def client_modules() -> list[str]:
    out = []
    for p in sorted((ROOT / "client").rglob("*.py")):
        rel = p.relative_to(ROOT).with_suffix("")
        if "tests" in rel.parts or rel.name == "main":
            continue
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        out.append(".".join(parts))
    return out


def smoke_test(exe: Path) -> bool:
    """Start the packaged game with --smoke-test: every client module must import and the
    fonts and maps must load from inside the bundle."""
    import subprocess
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    try:
        r = subprocess.run([str(exe), "--smoke-test", *client_modules()], env=env, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Không chạy thử được exe: {e}")
        return False
    if r.returncode != 0:
        log = exe.parent / "vuonchu_smoke.txt"
        print("Chạy thử exe THẤT BẠI:\n" + (log.read_text("utf-8") if log.exists() else f"mã lỗi {r.returncode}"))
        return False
    return True


def smoke_test_host(exe: Path) -> bool:
    """Open a throw-away world with the packaged exe (`--host-server`), wait until it answers,
    stop it the way the game does, and check the world was created and closed cleanly."""
    import secrets
    import socket
    import subprocess
    import tempfile
    import time
    import urllib.request
    with tempfile.TemporaryDirectory(prefix="kvtt_world_") as tmp:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        db = Path(tmp) / "world.db"
        env = dict(os.environ, KVTT_WORLD_DIR=tmp, PORT=str(port), DATABASE_URL=f"sqlite+aiosqlite:///{db}",
                   JWT_SECRET=secrets.token_hex(32), ENV="prod", ALLOW_UNREVIEWED="1", AUTO_MIGRATE="1",
                   LOCAL_ACCOUNTS="0", FIREBASE_API_KEY="smoke", LAN_BEACON="0", TIME_SCALE="1", BALANCE_PROFILE="")
        p = subprocess.Popen([str(exe), "--host-server"], env=env, stdin=subprocess.PIPE)
        ok = False
        end = time.time() + 120
        while time.time() < end and p.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/server/info", timeout=2) as r:
                    ok = json.loads(r.read())["auth"] == "firebase"
                break
            except OSError:
                time.sleep(0.5)
        try:
            p.stdin.write(b"stop\n")
            p.stdin.close()
            p.wait(30)
        except (OSError, subprocess.TimeoutExpired):
            p.kill()
            ok = False
        log = Path(tmp) / "server.log"
        if not (ok and p.returncode == 0 and db.exists()):
            tail = log.read_text("utf-8", "replace")[-3000:] if log.exists() else f"mã lỗi {p.returncode}"
            print("Chạy thử máy chủ trong exe THẤT BẠI:\n" + tail)
            return False
    return True


def make_zip(folder: Path, out: Path) -> str:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(folder.rglob("*")):
            skip = p.name in ("session.json", "vuonchu_loi.txt", "vuonchu_smoke.txt") \
                or "worlds" in p.relative_to(folder).parts     # someone's saved worlds never ship
            if p.is_file() and not skip:
                z.write(p, Path(folder.name) / p.relative_to(folder))
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server-url", default="http://127.0.0.1:8000",
                    help="default server written into config.json")
    ap.add_argument("--server-list-url", default="",
                    help="raw URL of deploy/server_list.json in your GitHub repo (optional)")
    ap.add_argument("--update-repo", default=None,
                    help="owner/repo on GitHub whose Releases the game checks for updates "
                         "(default: the git remote 'origin')")
    ap.add_argument("--onefile", action="store_true", help="one VuonChu.exe instead of a folder")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Vietnamese on a Windows console
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("Chưa có PyInstaller. Cài bằng:  python -m pip install pyinstaller")
        return 1
    if not (ROOT / "client" / "assets" / "fonts" / "VT323-Regular.ttf").exists():
        print("Thiếu font: chạy  python tools/fetch_assets.py  trước.")
        return 1
    audio = list((ROOT / "client" / "assets" / "audio").glob("*.mp3"))
    print(f"Khu Vườn Tu Tiên v{GAME_VERSION}: {len(audio)} file âm thanh"
          + ("" if audio else " (chạy tools/generate_audio.py để có giọng đọc; game vẫn chơi được)"))

    icon = make_icon(BUILD / "vuonchu.ico")
    pyi.run(pyinstaller_args(icon, args.onefile))

    if args.onefile:
        target = DIST / f"{NAME}-onefile"
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        shutil.move(str(DIST / f"{NAME}.exe"), target / f"{NAME}.exe")
        final = DIST / NAME
        shutil.rmtree(final, ignore_errors=True)
        target.rename(final)
    target = DIST / NAME
    update_repo = git_repo() if args.update_repo is None else args.update_repo
    print(f"Báo cập nhật từ GitHub Releases của: {update_repo or '(không có — game sẽ không tự báo bản mới)'}")
    write_extras(target, args.server_url, args.server_list_url, update_repo)
    exe = target / f"{NAME}.exe"
    if not exe.exists() and not (target / NAME).exists():
        print("Không thấy file exe sau khi build, xem log PyInstaller ở trên.")
        return 1
    if exe.exists():
        if not smoke_test(exe):
            return 1
        print(f"Chạy thử exe: đủ {len(client_modules())} module, font và bản đồ.")
        if not smoke_test_host(exe):
            return 1
        print("Chạy thử exe: mở được một thế giới (máy chủ trong exe), tạo cơ sở dữ liệu, tắt êm.")
    print(f"\nXong: {exe}")
    if not args.no_zip:
        plat = "windows" if sys.platform == "win32" else sys.platform
        out = DIST / f"{NAME}-{GAME_VERSION}-{plat}.zip"
        digest = make_zip(target, out)
        print(f"Gói phát hành: {out}  ({out.stat().st_size / 1e6:.1f} MB)\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
