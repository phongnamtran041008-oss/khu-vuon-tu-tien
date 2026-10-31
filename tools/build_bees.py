#!/usr/bin/env python3
"""Build server/data/creatures/bees.json from tools/curation/bees.json (spec 10.1, 5).

Each Linh Phong species is tied to one word of the game's word list. Its Chinese name is
that word + 蜂 ("bee"). Nothing linguistic is typed by hand:
  * the word, its pinyin and meaning come from server/data/words/*.json (already
    verified against HSK 3.0 + CC-CEDICT by build_wordlist.py);
  * the reading of 蜂 is looked up in CC-CEDICT;
  * the whole compound is looked up too: a real dictionary word (黄蜂 = wasp) is marked
    `real_word` with its CC-CEDICT meaning, the others are marked as game names
    (`real_word: false`), shown as "tên sáng tác" and never used in questions.

    python tools/build_bees.py          # uses tools/raw/cedict.txt (downloads it if missing)
"""
from __future__ import annotations

import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))

from app.learning import pinyin as py  # noqa: E402
from build_wordlist import CEDICT_URL, PYPI_CEDICT_JSON, RAW, _fetch, load_cedict  # noqa: E402

CUR = ROOT / "tools" / "curation" / "bees.json"
OUT = ROOT / "server" / "data" / "creatures" / "bees.json"
WORDS = [ROOT / "server" / "data" / "words" / f"words_hsk{n}.json" for n in (1, 2)]
RARITIES = ["pham", "linh", "huyen", "dia", "thien"]
ELEMENTS = {"thuy", "hoa", "moc", "tho", "kim", "loi", "bang", "quang", "phong", "mac"}
SKILLS = {"sting", "burn", "slow", "stun", "heal", "loot", "swift", "ink"}
BEE = "蜂"


def ensure_cedict() -> None:
    if (RAW / "cedict.txt").exists():
        return
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        data = gzip.decompress(_fetch(CEDICT_URL))
    except Exception:
        info = json.loads(_fetch(PYPI_CEDICT_JSON))
        whl = next(u for u in info["urls"] if u["filename"].endswith(".whl"))
        z = zipfile.ZipFile(io.BytesIO(_fetch(whl["url"])))
        member = next(n for n in z.namelist() if n.endswith("cedict_1_0_ts_utf-8_mdbg.txt.gz"))
        data = gzip.decompress(z.read(member))
    (RAW / "cedict.txt").write_bytes(data)


def cedict_date() -> str:
    for line in (RAW / "cedict.txt").read_text("utf-8").splitlines()[:40]:
        if line.startswith("#! date="):
            return line.split("=", 1)[1]
    return "?"


def main() -> int:
    ensure_cedict()
    ced = load_cedict()
    words = {}
    for f in WORDS:
        for w in json.loads(f.read_text("utf-8"))["words"]:
            words[w["hanzi"]] = w
    bee = [e for e in ced.get(BEE, []) if "bee" in " ".join(e["defs"])]
    if not bee:
        raise SystemExit("CC-CEDICT has no entry 蜂 'bee'")
    bee_numeric = py.canonical(bee[0]["pinyin"])
    bee_marked = py.numeric_to_marked(bee_numeric)
    cur = json.loads(CUR.read_text("utf-8"))
    out, errors, ids = {}, [], set()
    for s in cur["species"]:
        sid = s["id"]
        if sid in ids:
            errors.append(f"{sid}: duplicate id")
        ids.add(sid)
        w = words.get(s["word"])
        if w is None:
            errors.append(f"{sid}: word {s['word']} is not in the game's word list")
            continue
        if w.get("hidden"):
            errors.append(f"{sid}: {s['word']} is a hidden word (would spoil a discovery)")
        if s["rarity"] not in RARITIES:
            errors.append(f"{sid}: bad rarity {s['rarity']}")
        if s["element"] not in ELEMENTS:
            errors.append(f"{sid}: bad element {s['element']}")
        if s["skill"]["type"] not in SKILLS:
            errors.append(f"{sid}: bad skill {s['skill']['type']}")
        fav = s["favorite"]
        if fav.startswith("fruit:") and fav[6:] not in words:
            errors.append(f"{sid}: favourite fruit {fav[6:]} is not a game word")
        hanzi = w["hanzi"] + BEE
        entries = ced.get(hanzi, [])
        numeric = f"{w['pinyin_numeric']} {bee_numeric}"
        real = [e for e in entries if py.canonical(e["pinyin"]) == py.canonical(numeric)]
        out[sid] = {
            "name_vi": s["name_vi"], "hanzi": hanzi,
            "pinyin": w["pinyin"] + bee_marked,
            "pinyin_numeric": numeric,
            "word_id": w["id"], "word_hanzi": w["hanzi"], "word_pinyin": w["pinyin"],
            "word_vi": w.get("meaning_vi") or "",
            "real_word": bool(real),
            "real_meaning_en": "; ".join(d for d in real[0]["defs"] if d) if real else None,
            "rarity": s["rarity"], "element": s["element"], "desc_vi": s["desc_vi"],
            "honey": s["honey"], "pollen": s["pollen"], "guard": s["guard"], "skill": s["skill"],
            "favorite": fav, "favorite_hint_vi": s["favorite_hint_vi"], "look": s["look"],
        }
    for r in RARITIES:
        if not any(v["rarity"] == r for v in out.values()):
            errors.append(f"no species of rarity {r}")
    if len(out) < 15:
        errors.append(f"only {len(out)} species (spec 10.1 asks for at least 15)")
    if errors:
        print("\n".join("  ! " + e for e in errors))
        return 1
    data = {"_comment": "Generated by tools/build_bees.py from tools/curation/bees.json. Do not edit by hand.",
            "_sources": {"cedict": f"CC-CEDICT {cedict_date()}", "bee": f"{BEE} [{bee[0]['pinyin']}]"},
            **out}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} species "
          f"({sum(v['real_word'] for v in out.values())} real dictionary words)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
