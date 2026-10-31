"""Spec 5.4: the vocabulary data must be complete and traceable to its sources."""
import json
import warnings

import pytest

from app.config import DATA_DIR
from app.learning import pinyin as py
from app.learning.wordbank import PUNCT, bank

REQUIRED = ["id", "hanzi", "pinyin", "pinyin_numeric", "tier", "rarity", "topic", "meaning_en",
            "meaning_vi", "meaning_vi_reviewed", "source", "chars", "measure_words", "readings_all"]


def raw_words():
    out = []
    for p in sorted((DATA_DIR / "words").glob("words_hsk*.json")):
        out += json.loads(p.read_text("utf-8"))["words"]
    return out


WORDS = raw_words()


def test_counts_match_spec():
    t1 = [w for w in WORDS if w["tier"] == 1 and w["gacha"]]
    t2 = [w for w in WORDS if w["tier"] == 2]
    assert 75 <= len([w for w in t1 if w["rarity"] != "legendary"]) <= 90
    assert len([w for w in t1 if w["rarity"] == "legendary"]) == 3
    assert 75 <= len(t2) <= 90
    for ch in "木火水日月女子人口山大小马妈买卖问":  # spec 5.2 step 3
        assert ch in bank().by_hanzi


@pytest.mark.parametrize("w", WORDS, ids=[w["hanzi"] for w in WORDS])
def test_word_complete(w):
    for k in REQUIRED:
        assert k in w, k
    assert w["pinyin"].strip() and w["pinyin_numeric"].strip()
    assert w["meaning_en"] and all(m.strip() for m in w["meaning_en"])
    assert w["meaning_vi"].strip()
    assert w["rarity"] in ("common", "rare", "epic", "legendary")


@pytest.mark.parametrize("w", WORDS, ids=[w["hanzi"] for w in WORDS])
def test_pinyin_forms_agree(w):
    # marked and numeric pinyin convert into each other
    assert py.numeric_to_marked(w["pinyin_numeric"]) == w["pinyin"]
    spaced = py.numeric_to_marked(w["pinyin_numeric"], joined=False)
    assert py.canonical(py.marked_to_numeric(spaced)) == py.canonical(w["pinyin_numeric"])
    # one syllable per character
    assert len(py.split_numeric(w["pinyin_numeric"])) == len(w["hanzi"])
    # the chosen reading is one CC-CEDICT knows
    assert py.canonical(w["pinyin_numeric"]) in w["readings_all"]


@pytest.mark.parametrize("w", WORDS, ids=[w["hanzi"] for w in WORDS])
def test_traceable_source(w):
    src = w["source"]
    assert src["list"] in ("hsk3.0", "cc-cedict")
    assert src["cedict"].startswith("CC-CEDICT")
    if src["list"] == "hsk3.0":
        assert w["hsk_level"] in (1, 2, 3)
        assert any(py.same_reading(w["hanzi"], w["pinyin_numeric"], r) for r in src["hsk_pinyin"])


def test_examples_and_sentences_use_known_words():
    b = bank()
    for w in b.words.values():
        if w.example:
            for t in w.example["tokens"]:
                assert t["t"] in PUNCT or t["word_id"] in b.words
    for s in b.sentences.values():
        assert s.word_ids and all(wid in b.words for wid in s.word_ids)
        assert s.vi.strip()


def test_unreviewed_content_warning():
    n = sum(1 for w in WORDS if not w["meaning_vi_reviewed"])
    if n:
        warnings.warn(f"{n} Vietnamese meanings are not reviewed yet (tools/apply_review.py)")


def test_combos_checked_against_makemeahanzi():
    combos = json.loads((DATA_DIR / "combos.json").read_text("utf-8"))["combos"]
    unlocks = [c for c in combos if c["kind"] == "unlock"]
    assert unlocks and all("etymology_verified" in c for c in unlocks)


def test_mishaps_reference_real_words():
    for m in bank().mishaps:
        assert m["target_id"] in bank().words
        assert m["wrong_pinyin_marked"]
