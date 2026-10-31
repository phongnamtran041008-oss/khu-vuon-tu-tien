#!/usr/bin/env python3
"""Build the game's vocabulary data from verified open sources (spec section 5).

Sources (downloaded into tools/raw/, never committed):
  * HSK 3.0 word lists  - drkameleon/complete-hsk-vocabulary (MIT)
  * CC-CEDICT           - MDBG export (CC BY-SA 4.0); falls back to the unmodified
                          export bundled in the PyPI package `pycccedict` if mdbg.net
                          cannot be reached
  * makemeahanzi        - skishore/makemeahanzi dictionary.txt (LGPL-3.0+)

Inputs written by people/AI (tools/curation/):
  words.json        which words, which reading, topic   (verified against sources)
  vi_content.json   Vietnamese meaning + example         (always starts unreviewed)
  sentences.json    practice sentences                   (always starts unreviewed)
  combos.json, tone_mishaps.json
  reviews.json      human review decisions (written by apply_review.py)

Outputs:
  server/data/words/words_hsk1.json, words_hsk2.json
  server/data/sentences.json, combos.json, tone_mishaps.json
  tools/reports/pinyin_conflicts.csv, review_sheet.csv, sentences_review.csv, build_report.txt

Nothing linguistic is invented here: pinyin, English meanings, measure words and
character components all come from the sources above. A word whose reading the
sources disagree on is left out and written to pinyin_conflicts.csv for a human.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from app.learning import pinyin as py  # noqa: E402

RAW = ROOT / "tools" / "raw"
CUR = ROOT / "tools" / "curation"
REP = ROOT / "tools" / "reports"
DATA = ROOT / "server" / "data"

HSK_URL = "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/wordlists/inclusive/new/{level}.json"
CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
PYPI_CEDICT_JSON = "https://pypi.org/pypi/pycccedict/json"
MMAH_URL = "https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt"

PUNCT = set("。，！？、：；")
TIER_FOR_LIST = {"tier1": 1, "hidden": 1, "idioms": 1, "tier2": 2}
# Component-variant forms used by makemeahanzi decompositions.
RADICAL_VARIANTS = {"亻": "人", "氵": "水", "扌": "手", "忄": "心", "讠": "言", "钅": "金",
                    "饣": "食", "纟": "糸", "艹": "草", "灬": "火", "礻": "示", "衤": "衣",
                    "犭": "犬", "⺮": "竹", "阝": "阜", "刂": "刀", "王": "玉"}
SKIP_DEF = re.compile(r"^(surname |variant of|old variant|used in |abbr\. |Kangxi radical|"
                      r"see |also written|erhua variant|\(old\)|archaic variant|Japanese variant|"
                      r"\(slang\)|\(dialect\)|\(Tw\)|\(loanword\))",
                      re.I)


# ---------------------------------------------------------------- downloads
def _fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "khu-vuon-tu-tien-build/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_sources(refresh: bool) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    meta_path = RAW / "sources_meta.json"
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
    today = dt.date.today().isoformat()

    def save(name: str, data: bytes, url: str, note: str = ""):
        (RAW / name).write_bytes(data)
        meta[name] = {"url": url, "downloaded": today,
                      "sha256": hashlib.sha256(data).hexdigest(), "note": note}

    for level in (1, 2, 3):
        name = f"hsk{level}.json"
        if refresh or not (RAW / name).exists():
            url = HSK_URL.format(level=level)
            save(name, _fetch(url), url)

    if refresh or not (RAW / "cedict.txt").exists():
        try:
            data = gzip.decompress(_fetch(CEDICT_URL))
            save("cedict.txt", data, CEDICT_URL, "official MDBG export")
        except Exception as e:  # mdbg blocked -> unmodified export inside pycccedict wheel
            print(f"  ! mdbg.net unreachable ({e.__class__.__name__}); using pycccedict wheel copy")
            info = json.loads(_fetch(PYPI_CEDICT_JSON))
            whl = next(u for u in info["urls"] if u["filename"].endswith(".whl"))
            z = zipfile.ZipFile(io.BytesIO(_fetch(whl["url"])))
            member = next(n for n in z.namelist() if n.endswith("cedict_1_0_ts_utf-8_mdbg.txt.gz"))
            data = gzip.decompress(z.read(member))
            save("cedict.txt", data, whl["url"],
                 f"unmodified MDBG export bundled in pycccedict {info['info']['version']} "
                 f"(mdbg.net was unreachable from the build machine)")

    if refresh or not (RAW / "mmah_dictionary.txt").exists():
        save("mmah_dictionary.txt", _fetch(MMAH_URL), MMAH_URL)

    head = (RAW / "cedict.txt").read_text("utf-8").splitlines()[:40]
    for line in head:
        if line.startswith("#! date="):
            meta["cedict.txt"]["cedict_date"] = line.split("=", 1)[1]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    write_sources_md(meta)
    return meta


def write_sources_md(meta: dict) -> None:
    lines = ["# Raw data sources", "",
             "Downloaded by `tools/build_wordlist.py`. These files are not committed.", ""]
    for name, m in sorted(meta.items()):
        lines.append(f"- **{name}**: {m['url']}  ")
        lines.append(f"  downloaded {m['downloaded']}, sha256 `{m['sha256'][:16]}…`"
                     + (f", CC-CEDICT date {m['cedict_date']}" if m.get("cedict_date") else "")
                     + (f"  \n  note: {m['note']}" if m.get("note") else ""))
    (RAW / "SOURCES.md").write_text("\n".join(lines) + "\n", "utf-8")


# ---------------------------------------------------------------- parsing
CEDICT_LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\] /(.*)/\s*$")


def load_cedict() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for line in (RAW / "cedict.txt").read_text("utf-8").splitlines():
        if line.startswith("#"):
            continue
        m = CEDICT_LINE.match(line)
        if not m:
            continue
        trad, simp, pin, defs = m.groups()
        idx.setdefault(simp, []).append({"trad": trad, "pinyin": pin, "defs": defs.split("/")})
    return idx


def load_hsk() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for level in (1, 2, 3):
        for w in json.loads((RAW / f"hsk{level}.json").read_text("utf-8")):
            if w["simplified"] not in out:  # inclusive lists: first level seen is the real one
                out[w["simplified"]] = {**w, "level": level}
    return out


def load_mmah() -> dict[str, dict]:
    out = {}
    for line in (RAW / "mmah_dictionary.txt").read_text("utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out[d["character"]] = d
    return out


INLINE_CL = re.compile(r"\s*\(?CL:([^)]*)\)?")


def parse_classifiers(defs: list[str]) -> list[dict]:
    """Collects CL: lists, both standalone ('CL:個|个[ge4]') and inline ('dish (CL:道[dao4])')."""
    out = []
    for d in defs:
        for m_cl in INLINE_CL.finditer(d):
            for item in m_cl.group(1).split(","):
                m = re.match(r"^(?:[^|\[]+\|)?([^\[]+)\[([^\]]+)\]$", item.strip())
                if m:
                    simp, pin = m.groups()
                    out.append({"hanzi": simp, "pinyin_numeric": py.canonical(pin),
                                "pinyin": py.numeric_to_marked(pin)})
    seen, uniq = set(), []
    for c in out:
        if c["hanzi"] not in seen:
            seen.add(c["hanzi"])
            uniq.append(c)
    return uniq


def clean_def(d: str) -> str:
    return INLINE_CL.sub("", d).strip()


def flatten_components(decomp: str) -> list[str]:
    """'⿱木⿰木木' -> ['木','木','木']; returns [] if any part is unknown ('？')."""
    if not decomp or "？" in decomp:
        return []
    parts = [c for c in decomp if not ("⿰" <= c <= "⿿")]
    return parts if len(parts) >= 2 else []


def char_info(ch: str, mmah: dict) -> dict:
    d = mmah.get(ch)
    if not d:
        return {"char": ch, "radical": None, "decomposition": None, "components": []}
    return {"char": ch, "radical": d.get("radical"), "decomposition": d.get("decomposition"),
            "components": flatten_components(d.get("decomposition", "")),
            "etymology_type": (d.get("etymology") or {}).get("type"),
            "etymology_hint": (d.get("etymology") or {}).get("hint")}


def word_id(hanzi: str, numeric: str) -> str:
    compact = "".join(py.split_numeric(numeric)).lower().replace("ü", "v")
    return f"{compact}_{ord(hanzi[0]):x}"


# ---------------------------------------------------------------- build
class Conflicts:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, hanzi, curated, hsk, cedict, reason):
        self.rows.append({"hanzi": hanzi, "curated_pinyin": curated, "hsk_pinyin": hsk,
                          "cedict_pinyin": cedict, "reason": reason})


def resolve_word(item: dict, hsk: dict, cedict: dict, conflicts: Conflicts) -> dict | None:
    hanzi, cur = item["hanzi"], item["pinyin"]
    try:
        cur_c = py.canonical(cur)
    except ValueError as e:
        conflicts.add(hanzi, cur, "", "", f"bad curated pinyin: {e}")
        return None
    nsyl = len(cur_c.split())
    if nsyl != len(hanzi):
        conflicts.add(hanzi, cur, "", "", "syllable count != character count")
        return None

    h = hsk.get(hanzi)
    hsk_readings = []
    if h:
        hsk_readings = [f["transcriptions"]["numeric"] for f in h["forms"]]
        if not any(py.same_reading(hanzi, cur, r) for r in hsk_readings if r and re.search(r"\d", r)):
            conflicts.add(hanzi, cur, " / ".join(hsk_readings), "", "curated reading not in HSK list")
            return None

    entries = cedict.get(hanzi, [])
    matches = [e for e in entries if py.same_reading(hanzi, cur, e["pinyin"])]
    if item.get("trad"):
        matches = [e for e in matches if e["trad"] == item["trad"]] or matches
    exact_case = [e for e in matches if e["pinyin"].replace("u:", "ü") == cur.replace("u:", "ü")]
    if exact_case:
        matches = exact_case
    if not matches:
        conflicts.add(hanzi, cur, " / ".join(hsk_readings),
                      " / ".join(e["pinyin"] for e in entries) or "(not in CC-CEDICT)",
                      "curated reading not in CC-CEDICT")
        return None
    cedict_pin = matches[0]["pinyin"]
    if h and not any(py.same_reading(hanzi, r, cedict_pin) for r in hsk_readings if re.search(r"\d", r)):
        conflicts.add(hanzi, cur, " / ".join(hsk_readings), cedict_pin, "HSK and CC-CEDICT disagree")
        return None

    defs, cls = [], []
    for e in matches:
        cls += parse_classifiers(e["defs"])
        for d in e["defs"]:
            d = clean_def(d)
            if d and not SKIP_DEF.match(d) and d not in defs:
                defs.append(d)
    if not defs:
        conflicts.add(hanzi, cur, " / ".join(hsk_readings), cedict_pin, "no usable CC-CEDICT meaning")
        return None
    seen = set()
    cls = [c for c in cls if not (c["hanzi"] in seen or seen.add(c["hanzi"]))]
    return {
        "pinyin_numeric": " ".join(py.split_numeric(cedict_pin)),
        "traditional": matches[0]["trad"],
        "meaning_en": defs[:5],
        "measure_words": cls,
        "hsk_level": h["level"] if h else None,
        "frequency": h["frequency"] if h else None,
        "pos": h["pos"] if h else [],
        "hsk_pinyin": hsk_readings,
        # every reading CC-CEDICT knows for this spelling: a question must never offer
        # one of these as a "wrong" option (e.g. 只 zhī / zhǐ)
        "readings_all": sorted({py.canonical(e["pinyin"]) for e in entries}),
    }


def load_reviews() -> dict:
    p = CUR / "reviews.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {"words": {}, "sentences": {}}


def tokenize(text: str) -> list[str]:
    return [t for t in text.split() if t]


def build(args) -> int:
    meta = download_sources(args.refresh)
    print("Loading sources …")
    cedict, hsk, mmah = load_cedict(), load_hsk(), load_mmah()
    curation = json.loads((CUR / "words.json").read_text("utf-8"))
    vi = json.loads((CUR / "vi_content.json").read_text("utf-8"))
    reviews = load_reviews()
    conflicts = Conflicts()
    errors: list[str] = []
    REP.mkdir(parents=True, exist_ok=True)

    words: list[dict] = []
    for list_name, tier in TIER_FOR_LIST.items():
        for item in curation[list_name]:
            r = resolve_word(item, hsk, cedict, conflicts)
            if r is None:
                continue
            hz = item["hanzi"]
            content = vi.get(hz)
            if not content:
                errors.append(f"missing Vietnamese content for {hz}")
                continue
            w = {
                "id": word_id(hz, r["pinyin_numeric"]),
                "hanzi": hz,
                "traditional": r["traditional"],
                "pinyin": py.numeric_to_marked(r["pinyin_numeric"]),
                "pinyin_numeric": r["pinyin_numeric"],
                "readings_all": r["readings_all"],
                "tier": tier,
                "hsk_level": r["hsk_level"],
                "frequency": r["frequency"],
                "pos": r["pos"],
                "topic": item["topic"],
                "rarity": None,
                "hidden": list_name == "hidden",
                "gacha": list_name != "hidden",
                "meaning_en": r["meaning_en"],
                "meaning_vi": content["vi"],
                "meaning_vi_reviewed": False,
                "example": None,
                "example_reviewed": False,
                "story_vi": content.get("story_vi"),
                "measure_words": r["measure_words"],
                "chars": [char_info(c, mmah) for c in hz],
                "fictional": False,
                "source": {"list": "hsk3.0" if r["hsk_level"] else "cc-cedict",
                           "hsk_pinyin": r["hsk_pinyin"],
                           "cedict": "CC-CEDICT " + meta["cedict.txt"].get("cedict_date", "")},
            }
            if list_name == "idioms":
                w["rarity"] = "legendary"
            words.append(w)
            w["_ex"] = content

    by_hanzi = {w["hanzi"]: w for w in words}
    if len(by_hanzi) != len(words):
        errors.append("duplicate hanzi in curation")
    ids = [w["id"] for w in words]
    if len(set(ids)) != len(ids):
        errors.append("duplicate word ids")

    # rarity per tier by frequency (spec 5.2 step 4: ~60 common / 15 rare / 5 epic)
    for tier in (1, 2):
        pool = [w for w in words if w["tier"] == tier and w["gacha"] and w["rarity"] is None]
        # Required core characters that are not on the HSK list (木 …) have no HSK
        # frequency; spec 5.2 step 3 makes them garden basics, so rank them as common.
        pool.sort(key=lambda w: (w["frequency"] if w["frequency"] is not None else 0, w["id"]))
        n = len(pool)
        n_epic, n_rare = max(1, round(n * 5 / 80)), max(1, round(n * 15 / 80))
        for i, w in enumerate(pool):
            w["rarity"] = "common" if i < n - n_rare - n_epic else ("rare" if i < n - n_epic else "epic")
    for w in words:
        if w["rarity"] is None:  # hidden words: rarity by tier frequency rank is meaningless
            w["rarity"] = "rare"

    def token_pinyin(tokens: list[str], max_tier: int, where: str) -> list[dict] | None:
        out = []
        for t in tokens:
            if t in PUNCT:
                out.append({"t": t, "word_id": None, "pinyin": t})
                continue
            w = by_hanzi.get(t)
            if not w:
                errors.append(f"{where}: token {t!r} is not a word in the game data")
                return None
            if w["tier"] > max_tier:
                errors.append(f"{where}: token {t!r} is above tier {max_tier}")
                return None
            out.append({"t": t, "word_id": w["id"], "pinyin": w["pinyin"]})
        return out

    for w in words:
        c = w.pop("_ex")
        if c.get("ex"):
            toks = token_pinyin(tokenize(c["ex"]), w["tier"], f"example of {w['hanzi']}")
            if toks is not None:
                if w["hanzi"] not in [t["t"] for t in toks]:
                    errors.append(f"example of {w['hanzi']} does not contain the word")
                w["example"] = {"tokens": toks, "vi": c["ex_vi"]}
        rv = reviews["words"].get(w["id"], {})
        if rv.get("meaning_vi"):
            w["meaning_vi"] = rv["meaning_vi"]
        w["meaning_vi_reviewed"] = bool(rv.get("meaning_ok"))
        if rv.get("example_vi") and w["example"]:
            w["example"]["vi"] = rv["example_vi"]
        w["example_reviewed"] = bool(rv.get("example_ok")) and w["example"] is not None

    # sentences
    sent_cur = json.loads((CUR / "sentences.json").read_text("utf-8"))["sentences"]
    sentences = []
    for i, s in enumerate(sent_cur, 1):
        toks = tokenize(s["text"])
        tiers = [by_hanzi[t]["tier"] for t in toks if t in by_hanzi]
        tier = max(tiers) if tiers else 1
        tp = token_pinyin(toks, 2, f"sentence {i}")
        if tp is None:
            continue
        sid = f"s{i:03d}"
        rv = reviews["sentences"].get(sid, {})
        sentences.append({"id": sid, "tier": tier, "tokens": tp,
                          "text": "".join(t["t"] for t in tp),
                          "vi": rv.get("vi") or s["vi"], "reviewed": bool(rv.get("ok"))})

    # combos: verify against makemeahanzi decompositions (spec 5.2 step 7)
    combos = json.loads((CUR / "combos.json").read_text("utf-8"))["combos"]
    for c in combos:
        if c["kind"] != "unlock":
            continue
        if c["result"] not in by_hanzi:
            errors.append(f"combo {c['id']}: result {c['result']} not in word data")
        for comp in c["components"]:
            if comp not in by_hanzi:
                errors.append(f"combo {c['id']}: component {comp} not in word data")
        parts = flatten_components((mmah.get(c["result"]) or {}).get("decomposition", ""))
        norm = sorted(RADICAL_VARIANTS.get(p, p) for p in parts)
        c["etymology_verified"] = norm == sorted(c["components"])
        c["decomposition"] = (mmah.get(c["result"]) or {}).get("decomposition")

    # tone mishaps: wrong reading must exist in CC-CEDICT
    mishaps = json.loads((CUR / "tone_mishaps.json").read_text("utf-8"))["mishaps"]
    good_mishaps = []
    for m in mishaps:
        if m["target"] not in by_hanzi:
            errors.append(f"mishap {m['id']}: target {m['target']} not in word data")
            continue
        ok = any(py.same_reading(m["wrong_hanzi"], m["wrong_pinyin"], e["pinyin"])
                 and py.canonical(e["pinyin"]) == py.canonical(m["wrong_pinyin"])
                 for e in cedict.get(m["wrong_hanzi"], []))
        if not ok:
            errors.append(f"mishap {m['id']}: {m['wrong_hanzi']} {m['wrong_pinyin']} not in CC-CEDICT")
            continue
        m["target_id"] = by_hanzi[m["target"]]["id"]
        m["wrong_pinyin_marked"] = py.numeric_to_marked(m["wrong_pinyin"])
        good_mishaps.append(m)

    # ---------------------------------------------------------------- write
    header = {
        "license": "CC BY-SA 4.0 — derived from CC-CEDICT (https://cc-cedict.org/wiki/) and "
                   "makemeahanzi dictionary.txt (LGPL-3.0+); HSK lists from "
                   "drkameleon/complete-hsk-vocabulary (MIT). See CREDITS.md.",
        "generated_by": "tools/build_wordlist.py",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "cedict_date": meta["cedict.txt"].get("cedict_date"),
    }
    (DATA / "words").mkdir(parents=True, exist_ok=True)
    for tier in (1, 2):
        out = {**header, "tier": tier, "words": [w for w in words if w["tier"] == tier]}
        (DATA / "words" / f"words_hsk{tier}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    (DATA / "sentences.json").write_text(
        json.dumps({**header, "sentences": sentences}, ensure_ascii=False, indent=1), "utf-8")
    (DATA / "combos.json").write_text(
        json.dumps({"combos": combos}, ensure_ascii=False, indent=1), "utf-8")
    (DATA / "tone_mishaps.json").write_text(
        json.dumps({"mishaps": good_mishaps}, ensure_ascii=False, indent=1), "utf-8")

    with open(REP / "pinyin_conflicts.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, ["hanzi", "curated_pinyin", "hsk_pinyin", "cedict_pinyin", "reason"])
        wr.writeheader()
        wr.writerows(conflicts.rows)
    with open(REP / "review_sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "hanzi", "pinyin", "meaning_en", "meaning_vi", "meaning_ok",
                     "meaning_vi_fixed", "example", "example_pinyin", "example_vi",
                     "example_ok", "example_vi_fixed"])
        for w in words:
            ex = w["example"]
            wr.writerow([w["id"], w["hanzi"], w["pinyin"], " / ".join(w["meaning_en"]),
                         w["meaning_vi"], "x" if w["meaning_vi_reviewed"] else "", "",
                         "".join(t["t"] for t in ex["tokens"]) if ex else "",
                         " ".join(t["pinyin"] for t in ex["tokens"]) if ex else "",
                         ex["vi"] if ex else "", "x" if w["example_reviewed"] else "", ""])
    with open(REP / "sentences_review.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "text", "pinyin", "vi", "ok", "vi_fixed"])
        for s in sentences:
            wr.writerow([s["id"], s["text"], " ".join(t["pinyin"] for t in s["tokens"]), s["vi"],
                         "x" if s["reviewed"] else "", ""])

    summary = [
        f"words: {len(words)} (tier1 {sum(w['tier'] == 1 for w in words)}, "
        f"tier2 {sum(w['tier'] == 2 for w in words)})",
        "rarity tier1: " + ", ".join(f"{r} {sum(1 for w in words if w['tier'] == 1 and w['gacha'] and w['rarity'] == r)}"
                                     for r in ("common", "rare", "epic", "legendary")),
        "rarity tier2: " + ", ".join(f"{r} {sum(1 for w in words if w['tier'] == 2 and w['rarity'] == r)}"
                                     for r in ("common", "rare", "epic")),
        f"sentences: {len(sentences)}",
        f"combos verified: " + ", ".join(f"{c['id']}={c.get('etymology_verified')}" for c in combos if c['kind'] == 'unlock'),
        f"tone mishaps: {len(good_mishaps)}/{len(mishaps)}",
        f"pinyin conflicts: {len(conflicts.rows)}",
        f"unreviewed meanings: {sum(not w['meaning_vi_reviewed'] for w in words)}",
        f"errors: {len(errors)}",
    ] + [f"  ERROR {e}" for e in errors] + [f"  CONFLICT {c}" for c in conflicts.rows]
    (REP / "build_report.txt").write_text("\n".join(summary) + "\n", "utf-8")
    print("\n".join(summary))
    return 1 if errors else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="re-download all sources")
    sys.exit(build(ap.parse_args()))
