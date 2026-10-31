"""Basic word filter for display names (and chat in stage 3). Spec 15.3."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from .config import DATA_DIR


def fold(s: str) -> str:
    """Lower-case, strip Vietnamese diacritics (đ -> d)."""
    s = s.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def _lists() -> tuple[set[str], set[str]]:
    marked, plain = set(), set()
    for line in (DATA_DIR / "banned_words.txt").read_text("utf-8").splitlines():
        w = line.strip().lower()
        if not w or w.startswith("#"):
            continue
        (plain if fold(w) == w else marked).add(unicodedata.normalize("NFC", w))
    return marked, plain


def _squash(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)  # "dmmmm" -> "dm"


def contains_banned(text: str) -> bool:
    marked, plain = _lists()
    t = unicodedata.normalize("NFC", text.lower())
    tokens = re.findall(r"\w+", t)
    joined = " ".join(tokens)
    for w in marked:
        if (" " in w and w in joined) or w in tokens:
            return True
    for tok in tokens:
        if fold(tok) != tok:  # written with diacritics: only the marked list applies
            continue
        if tok in plain or _squash(tok) in plain:
            return True
    folded_joined = " ".join(tok for tok in tokens if fold(tok) == tok)
    return any(" " in w and w in folded_joined for w in plain)


def mask(text: str) -> str:
    """Replace banned tokens with *** (used for chat later)."""
    def rep(m: re.Match) -> str:
        return "*" * len(m.group(0)) if contains_banned(m.group(0)) else m.group(0)
    return re.sub(r"\w+", rep, text)
