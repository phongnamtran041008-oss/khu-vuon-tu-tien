#!/usr/bin/env python3
"""Download the fonts the client needs into client/assets/fonts/ (spec 2, 18).

* VT323 (SIL OFL 1.1) — pixel font for interface text; covers Vietnamese.
* Noto Sans SC (SIL OFL 1.1) — Chinese characters and pinyin tone marks.
  The 8 MB file is subset with fontTools to GB2312 + every character in the game data
  + Latin/Vietnamese/pinyin, which keeps the client small but still lets players type
  any common simplified character (chat in later stages). Pass --full to skip subsetting.

Both are downloaded from GitHub (Google Fonts repo / notofonts), the same files the
official sites distribute. Licences are copied next to the fonts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "client" / "assets" / "fonts"
SOURCES = {
    "VT323-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/vt323/VT323-Regular.ttf",
    "VT323-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/vt323/OFL.txt",
    "NotoSansSC-Regular.otf": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
    "NotoSansSC-LICENSE.txt": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "khu-vuon-tu-tien-assets/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def game_characters() -> str:
    chars = set()
    for p in (ROOT / "server" / "data").rglob("*.json"):
        chars |= set(p.read_text("utf-8"))
    for p in (ROOT / "client").rglob("*.py"):
        chars |= set(p.read_text("utf-8"))
    return "".join(sorted(chars))


def gb2312() -> str:
    out = []
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return "".join(out)


def subset(src: Path, dst: Path) -> None:
    from fontTools import subset as fts
    text = game_characters() + gb2312()
    text += "".join(chr(c) for c in range(0x20, 0x250))          # Latin + Latin Extended
    text += "".join(chr(c) for c in range(0x1E00, 0x1F00))       # Vietnamese precomposed
    text += "".join(chr(c) for c in range(0x3000, 0x3040))       # CJK punctuation
    text += "".join(chr(c) for c in range(0xFF00, 0xFFF0))       # full-width forms
    opts = fts.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = fts.load_font(str(src), opts)
    sub = fts.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    fts.save_font(font, str(dst), opts)


def main() -> int:
    ap = argparse.ArgumentParser(description="download client fonts")
    ap.add_argument("--full", action="store_true", help="keep the full Noto Sans SC (8 MB)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    FONTS.mkdir(parents=True, exist_ok=True)
    meta = {}
    for name, url in SOURCES.items():
        dst = FONTS / name
        if dst.exists() and not args.force and name != "NotoSansSC-Regular.otf":
            continue
        if name == "NotoSansSC-Regular.otf" and (FONTS / "NotoSansSC-Game.otf").exists() and not args.force:
            continue
        print(f"downloading {name} …")
        data = fetch(url)
        meta[name] = {"url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        dst.write_bytes(data)
    noto = FONTS / "NotoSansSC-Regular.otf"
    if noto.exists():
        if args.full:
            noto.replace(FONTS / "NotoSansSC-Game.otf")
        else:
            try:
                subset(noto, FONTS / "NotoSansSC-Game.otf")
                noto.unlink()
                print("subset Noto Sans SC ->", (FONTS / "NotoSansSC-Game.otf").stat().st_size // 1024, "KB")
            except ImportError:
                print("fontTools not installed; keeping the full font (pip install fonttools)")
                noto.replace(FONTS / "NotoSansSC-Game.otf")
    if meta:
        (FONTS / "SOURCES.json").write_text(json.dumps(meta, indent=2), "utf-8")
    print("fonts ready in", FONTS.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
