#!/usr/bin/env python3
"""Generate pronunciation audio with edge-tts (spec 2): one MP3 per word, from the
hanzi (never spelled by hand), voice zh-CN-XiaoxiaoNeural.

Writes server/data/audio/{word_id}.mp3 (served to listening questions through the quiz
session, so the client never learns which word is playing) and copies the same files to
client/assets/audio/ (intro cards and the codex). The game runs without these files:
the speaker button hides and listening questions show pinyin instead.

    pip install edge-tts
    python tools/generate_audio.py            # only missing files
    python tools/generate_audio.py --force    # regenerate everything
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_AUDIO = ROOT / "server" / "data" / "audio"
CLIENT_AUDIO = ROOT / "client" / "assets" / "audio"
VOICE = "zh-CN-XiaoxiaoNeural"


def words() -> list[dict]:
    out = []
    for p in sorted((ROOT / "server" / "data" / "words").glob("words_hsk*.json")):
        out += json.loads(p.read_text("utf-8"))["words"]
    return out


async def synth(text: str, dst: Path, rate: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=rate).save(str(dst))


async def main_async(args) -> int:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("edge-tts is not installed: pip install edge-tts")
        return 1
    SERVER_AUDIO.mkdir(parents=True, exist_ok=True)
    CLIENT_AUDIO.mkdir(parents=True, exist_ok=True)
    ws = words()
    done = failed = 0
    for w in ws:
        dst = SERVER_AUDIO / f"{w['id']}.mp3"
        if dst.exists() and dst.stat().st_size > 0 and not args.force:
            continue
        try:
            await synth(w["hanzi"], dst, args.rate)
            done += 1
            print(f"  {w['hanzi']} -> {dst.name}")
        except Exception as e:  # network or service error: keep going, game works without
            dst.unlink(missing_ok=True)  # never leave an empty/partial file behind
            failed += 1
            print(f"  ! {w['hanzi']}: {e.__class__.__name__}: {e}")
            if failed >= 3 and done == 0:
                print("edge-tts service unreachable; stopping. The game works without audio.")
                return 1
    for f in SERVER_AUDIO.glob("*.mp3"):
        shutil.copy2(f, CLIENT_AUDIO / f.name)
    print(f"generated {done}, failed {failed}, total files {len(list(SERVER_AUDIO.glob('*.mp3')))}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="generate word audio with edge-tts")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rate", default="-10%", help="speaking rate, slower helps learners")
    sys.exit(asyncio.run(main_async(ap.parse_args())))
