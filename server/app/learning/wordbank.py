"""In-memory view of the verified vocabulary data (server/data/words, sentences.json)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config import DATA_DIR

PUNCT = set("。，！？、：；")
RARITY_ORDER = ["common", "rare", "epic", "legendary"]


def senses(meaning_vi: str) -> set[str]:
    """'cây (cây cối); gỗ' -> {'cây', 'gỗ'}: used to keep two options from both being right."""
    no_paren = re.sub(r"\([^)]*\)", "", meaning_vi.lower())
    return {s.strip() for s in re.split(r"[,;/]", no_paren) if s.strip()}


@dataclass
class Word:
    id: str
    hanzi: str
    pinyin: str
    pinyin_numeric: str
    readings_all: list[str]
    tier: int
    rarity: str
    topic: str
    hidden: bool
    gacha: bool
    meaning_vi: str
    meaning_vi_reviewed: bool
    meaning_en: list[str]
    pos: list[str]
    example: dict | None
    example_reviewed: bool
    measure_words: list[dict]
    chars: list[dict]
    story_vi: str | None = None
    hsk_level: int | None = None
    senses: set[str] = field(default_factory=set)

    @property
    def single_char(self) -> bool:
        return len(self.hanzi) == 1

    def public(self) -> dict:
        """What a player may see about a word they own (intro card, codex)."""
        d = {
            "id": self.id, "hanzi": self.hanzi, "pinyin": self.pinyin,
            "pinyin_numeric": self.pinyin_numeric, "meaning_vi": self.meaning_vi,
            "meaning_vi_reviewed": self.meaning_vi_reviewed, "tier": self.tier,
            "rarity": self.rarity, "topic": self.topic, "hsk_level": self.hsk_level,
            "measure_words": [m["hanzi"] for m in self.measure_words],
        }
        if self.example:
            d["example"] = {"text": "".join(t["t"] for t in self.example["tokens"]),
                            "pinyin": " ".join(t["pinyin"] for t in self.example["tokens"]),
                            "vi": self.example["vi"], "reviewed": self.example_reviewed}
        if self.story_vi:
            d["story_vi"] = self.story_vi
        if self.single_char and self.chars and self.chars[0].get("components"):
            c = self.chars[0]
            d["components"] = c["components"]
            d["etymology_hint"] = c.get("etymology_hint")
        return d


@dataclass
class Sentence:
    id: str
    tier: int
    tokens: list[dict]
    text: str
    vi: str
    reviewed: bool

    @property
    def word_ids(self) -> list[str]:
        return [t["word_id"] for t in self.tokens if t["word_id"]]


class WordBank:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.words: dict[str, Word] = {}
        for p in sorted((data_dir / "words").glob("words_hsk*.json")):
            for raw in json.loads(p.read_text("utf-8"))["words"]:
                w = Word(**{k: raw.get(k) for k in Word.__dataclass_fields__ if k != "senses"})
                w.senses = senses(w.meaning_vi)
                self.words[w.id] = w
        self.by_hanzi = {w.hanzi: w for w in self.words.values()}
        self.sentences: dict[str, Sentence] = {}
        sp = data_dir / "sentences.json"
        if sp.exists():
            for raw in json.loads(sp.read_text("utf-8"))["sentences"]:
                s = Sentence(**raw)
                self.sentences[s.id] = s
        mp = data_dir / "tone_mishaps.json"
        self.mishaps = json.loads(mp.read_text("utf-8"))["mishaps"] if mp.exists() else []

    def get(self, word_id: str) -> Word:
        return self.words[word_id]

    def gacha_pool(self, max_tier: int, rarity: str) -> list[Word]:
        return [w for w in self.words.values()
                if w.gacha and w.tier <= max_tier and w.rarity == rarity]

    def distractor_pool(self, max_tier: int) -> list[Word]:
        """Words that may appear as wrong options: no hidden words (would spoil discoveries)
        and no idioms."""
        return [w for w in self.words.values()
                if not w.hidden and w.rarity != "legendary" and w.tier <= max_tier]

    def sentences_with(self, word_id: str, allow_unreviewed: bool, max_tier: int = 9) -> list[Sentence]:
        return [s for s in self.sentences.values()
                if word_id in s.word_ids and s.tier <= max_tier and (s.reviewed or allow_unreviewed)]


@lru_cache(maxsize=1)
def bank() -> WordBank:
    return WordBank()
