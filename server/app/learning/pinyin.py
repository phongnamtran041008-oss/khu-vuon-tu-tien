"""Pinyin helpers shared by the data tools and the server.

Numeric pinyin ("ma1 ma5", "nü3") is the canonical stored form; tone-marked
pinyin ("māma", "nǚ") is derived from it, never typed by hand.
"""
from __future__ import annotations

import re
import unicodedata

TONE_MARKS = {
    "a": "āáǎàa",
    "e": "ēéěèe",
    "i": "īíǐìi",
    "o": "ōóǒòo",
    "u": "ūúǔùu",
    "ü": "ǖǘǚǜü",
}
VOWELS = set(TONE_MARKS)
_MARKED_TO_BASE = {}
for _base, _marks in TONE_MARKS.items():
    for _i, _ch in enumerate(_marks[:4]):
        _MARKED_TO_BASE[_ch] = (_base, _i + 1)
        _MARKED_TO_BASE[_ch.upper()] = (_base.upper(), _i + 1)

_SYLLABLE_RE = re.compile(r"^([A-Za-zü]+)([1-5]?)$")


def normalize_u(s: str) -> str:
    """CC-CEDICT writes ü as 'u:'; some inputs use 'v'."""
    return s.replace("u:", "ü").replace("U:", "Ü").replace("v", "ü").replace("V", "Ü")


def split_numeric(pinyin_numeric: str) -> list[str]:
    """'Zhong1 guo2' -> ['Zhong1', 'guo2'] with explicit tone 5 for neutral syllables."""
    out = []
    for raw in normalize_u(pinyin_numeric.strip()).split():
        m = _SYLLABLE_RE.match(raw)
        if not m:
            raise ValueError(f"bad pinyin syllable: {raw!r} in {pinyin_numeric!r}")
        out.append(m.group(1) + (m.group(2) or "5"))
    return out


def syllable_tone(syl: str) -> int:
    return int(syl[-1]) if syl and syl[-1].isdigit() else 5


def syllable_base(syl: str) -> str:
    return syl[:-1] if syl and syl[-1].isdigit() else syl


def _mark_syllable(syl: str) -> str:
    base, tone = syllable_base(syl), syllable_tone(syl)
    if tone == 5 or base.lower() == "r":
        return base
    low = base.lower()
    if "a" in low:
        idx = low.index("a")
    elif "e" in low:
        idx = low.index("e")
    elif "ou" in low:
        idx = low.index("o")
    else:
        idx = max(i for i, ch in enumerate(low) if ch in VOWELS)
    ch = base[idx]
    marked = TONE_MARKS[ch.lower()][tone - 1]
    if ch.isupper():
        marked = marked.upper()
    return base[:idx] + marked + base[idx + 1:]


def numeric_to_marked(pinyin_numeric: str, joined: bool = True) -> str:
    """'ma1 ma5' -> 'māma'; 'tian1 an1' -> "tiān'ān". joined=False keeps spaces."""
    syls = [_mark_syllable(s) for s in split_numeric(pinyin_numeric)]
    if not joined:
        return " ".join(syls)
    out = ""
    for i, s in enumerate(syls):
        if i and s[:1].lower() in "aeoāáǎàēéěèōóǒò":
            out += "'"
        out += s
    return out


def marked_to_numeric(pinyin_marked: str) -> str:
    """Space-separated tone-marked syllables -> numeric ('ài hào' -> 'ai4 hao4')."""
    out = []
    for syl in pinyin_marked.split():
        tone = 5
        base = ""
        for ch in unicodedata.normalize("NFC", syl):
            if ch in _MARKED_TO_BASE:
                b, tone = _MARKED_TO_BASE[ch]
                base += b
            else:
                base += ch
        out.append(base + str(tone))
    return " ".join(out)


def canonical(pinyin_numeric: str) -> str:
    """Lower-case, ü-normalised, explicit tone 5: used for equality checks."""
    return " ".join(s.lower() for s in split_numeric(pinyin_numeric))


def strip_tones(pinyin_numeric: str) -> str:
    return " ".join(syllable_base(s).lower() for s in split_numeric(pinyin_numeric))


def tones(pinyin_numeric: str) -> list[int]:
    return [syllable_tone(s) for s in split_numeric(pinyin_numeric)]


def with_tones(pinyin_numeric: str, new_tones: list[int]) -> str:
    syls = split_numeric(pinyin_numeric)
    return " ".join(syllable_base(s) + str(t) for s, t in zip(syls, new_tones))


SANDHI_CHARS = {"一", "不"}


def same_reading(hanzi: str, a: str, b: str) -> bool:
    """Equality that ignores tone-sandhi on 一/不 and letter case (spec 5.2 step 2)."""
    sa, sb = canonical(a).split(), canonical(b).split()
    if len(sa) != len(sb):
        return False
    for i, (x, y) in enumerate(zip(sa, sb)):
        if x == y:
            continue
        ch = hanzi[i] if i < len(hanzi) else ""
        if ch in SANDHI_CHARS and syllable_base(x) == syllable_base(y):
            continue
        return False
    return True


def _typed_key(s: str) -> str:
    s = normalize_u(s.strip().lower())
    s = re.sub(r"[\s'’\-]", "", s)
    return s.replace("5", "")


def typed_matches(expected_numeric: str, typed: str) -> bool:
    """Accepts 'ma1ma5', 'ma1 ma', 'MA1MA', 'nv3' / 'nu:3' for 'nü3'."""
    if not typed or len(typed) > 64:
        return False
    return _typed_key(typed) == _typed_key(" ".join(split_numeric(expected_numeric)))
