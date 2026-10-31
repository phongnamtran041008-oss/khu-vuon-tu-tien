#!/usr/bin/env python3
"""Record a human review of the Vietnamese content, then rebuild the data files.

Workflow:
  1. python tools/build_wordlist.py          -> tools/reports/review_sheet.csv
                                                tools/reports/sentences_review.csv
  2. Open the CSVs in Excel / LibreOffice. For each row either
       - put x in `meaning_ok` / `example_ok` / `ok` if it is correct, or
       - type a corrected Vietnamese text in `*_fixed` (this also counts as approved).
     Leave a row blank to keep it unreviewed.
  3. python tools/apply_review.py            -> updates tools/curation/reviews.json
                                                and rebuilds server/data/*

Reviews are stored by word id / sentence id in tools/curation/reviews.json, so they
survive later rebuilds. Clearing a mark in the CSV does not un-review a row; edit
reviews.json directly for that.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "tools" / "reports"
REVIEWS = ROOT / "tools" / "curation" / "reviews.json"
YES = {"x", "1", "y", "yes", "ok", "có", "co", "true", "✓"}


def _yes(v: str | None) -> bool:
    return (v or "").strip().lower() in YES


def main() -> int:
    ap = argparse.ArgumentParser(description="apply reviewed CSV sheets")
    ap.add_argument("--sheet", default=str(REP / "review_sheet.csv"))
    ap.add_argument("--sentences", default=str(REP / "sentences_review.csv"))
    ap.add_argument("--no-rebuild", action="store_true")
    args = ap.parse_args()

    reviews = json.loads(REVIEWS.read_text("utf-8")) if REVIEWS.exists() else {}
    reviews.setdefault("words", {})
    reviews.setdefault("sentences", {})
    n_words = n_sent = 0

    if Path(args.sheet).exists():
        with open(args.sheet, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                r = reviews["words"].setdefault(row["id"], {})
                changed = False
                if (row.get("meaning_vi_fixed") or "").strip():
                    r["meaning_vi"] = row["meaning_vi_fixed"].strip()
                    r["meaning_ok"] = changed = True
                elif _yes(row.get("meaning_ok")):
                    r["meaning_ok"] = changed = True
                if (row.get("example_vi_fixed") or "").strip():
                    r["example_vi"] = row["example_vi_fixed"].strip()
                    r["example_ok"] = changed = True
                elif _yes(row.get("example_ok")):
                    r["example_ok"] = changed = True
                if not r:
                    del reviews["words"][row["id"]]
                n_words += changed

    if Path(args.sentences).exists():
        with open(args.sentences, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                r = reviews["sentences"].setdefault(row["id"], {})
                if (row.get("vi_fixed") or "").strip():
                    r["vi"], r["ok"] = row["vi_fixed"].strip(), True
                    n_sent += 1
                elif _yes(row.get("ok")):
                    r["ok"] = True
                    n_sent += 1
                if not r:
                    del reviews["sentences"][row["id"]]

    REVIEWS.write_text(json.dumps(reviews, ensure_ascii=False, indent=1), "utf-8")
    print(f"recorded reviews: {n_words} word rows, {n_sent} sentences -> {REVIEWS.relative_to(ROOT)}")
    if args.no_rebuild:
        return 0
    return subprocess.call([sys.executable, str(ROOT / "tools" / "build_wordlist.py")])


if __name__ == "__main__":
    sys.exit(main())
