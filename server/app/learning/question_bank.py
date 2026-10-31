"""Generates and grades every question type (spec 8.2, Q1-Q11).

Pure functions: no database, no context. A Question has a public part (sent to the
client) and an answer_key (kept on the server). The garden, combat, tower defense and
secret realms all ask for questions through this module.

Rules enforced here:
  * wrong options come from real data, and never another correct answer
    (meaning overlap, homophones, other readings of a polyphone, other valid classifiers)
  * measure words only from CC-CEDICT CL: lists, components only from makemeahanzi
  * sentences only from sentences.json / word examples, and only reviewed ones unless
    allow_unreviewed (dev) is on
"""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from .. import balance
from . import pinyin as py
from .wordbank import PUNCT, Sentence, Word, WordBank

QTYPES = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10", "Q11"]
OPTION_IDS = "abcd"

INSTRUCTIONS_VI = {
    "Q1": "Chữ này nghĩa là gì?",
    "Q2": "Chữ Hán nào mang nghĩa này?",
    "Q3": "Chọn pinyin đúng",
    "Q4": "Nghe và chọn chữ Hán đúng",
    "Q5": "Gõ pinyin dạng số (vd: ma1). Gõ v thay cho ü",
    "Q6": "Chọn lượng từ đúng",
    "Q7": "Chọn từ điền vào chỗ trống",
    "Q8": "Chữ này gồm những thành phần nào?",
    "Q9": "Sắp xếp các từ thành câu đúng",
    "Q10": "Câu này nghĩa là gì?",
    "Q11": "Chữ này mang thanh mấy?",
}


class QuestionError(Exception):
    """This question type cannot be generated for this word."""


@dataclass
class Question:
    qtype: str
    word_id: str
    prompt: dict
    input: str                      # choice | text | order | tone
    options: list[dict] | None
    answer_key: dict
    time_limit: float
    meta: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {"qtype": self.qtype, "instruction_vi": INSTRUCTIONS_VI[self.qtype],
                "prompt": self.prompt, "input": self.input, "options": self.options,
                "time_limit": self.time_limit}


@dataclass
class GenContext:
    bank: WordBank
    rng: random.Random
    max_tier: int = 1                       # vocabulary tier allowed for options
    allow_unreviewed: bool = False
    has_audio: Callable[[str], bool] = lambda _wid: False


# ------------------------------------------------------------------ helpers
def _time_limit(qtype: str) -> float:
    return float(balance.quiz()["types"][qtype]["time_limit"])


def _pick(cands: list, score: Callable, rng: random.Random, n: int = 3) -> list:
    keyed = [(-score(c), rng.random(), i) for i, c in enumerate(cands)]
    keyed.sort()
    return [cands[i] for _, _, i in keyed[:n]]


def _choice_options(correct: str, wrong: list[str], rng: random.Random,
                    extra: dict | None = None) -> tuple[list[dict], str]:
    texts = [correct] + wrong
    if len(set(texts)) != len(texts) or len(texts) != 4:
        raise QuestionError("options not distinct")
    order = list(range(4))
    rng.shuffle(order)
    options, correct_id = [], ""
    for slot, idx in enumerate(order):
        oid = OPTION_IDS[slot]
        opt = {"id": oid, "text": texts[idx]}
        if extra and texts[idx] in extra:
            opt.update(extra[texts[idx]])
        options.append(opt)
        if idx == 0:
            correct_id = oid
    return options, correct_id


def _reveal(w: Word, text: str) -> dict:
    return {"hanzi": w.hanzi, "pinyin": w.pinyin, "meaning_vi": w.meaning_vi, "answer_text": text}


def _pos1(w: Word) -> str:
    return (w.pos[0][:1] if w.pos else "")


def _homophone(a: Word, b: Word) -> bool:
    ca, cb = py.canonical(a.pinyin_numeric), py.canonical(b.pinyin_numeric)
    return ca == cb or ca in b.readings_all or cb in a.readings_all


def _usable_sentences(ctx: GenContext, w: Word) -> list[Sentence]:
    out = list(ctx.bank.sentences_with(w.id, ctx.allow_unreviewed, max(ctx.max_tier, w.tier)))
    for other in ctx.bank.words.values():  # word examples count as sentences too
        ex = other.example
        if not ex or not (other.example_reviewed or ctx.allow_unreviewed):
            continue
        if w.id in [t["word_id"] for t in ex["tokens"]] and other.tier <= max(ctx.max_tier, w.tier):
            out.append(Sentence(id=f"ex:{other.id}", tier=other.tier, tokens=ex["tokens"],
                                text="".join(t["t"] for t in ex["tokens"]), vi=ex["vi"],
                                reviewed=other.example_reviewed))
    seen, uniq = set(), []
    for s in out:
        if s.text not in seen:
            seen.add(s.text)
            uniq.append(s)
    return uniq


# ------------------------------------------------------------------ generators
def gen_q1(w: Word, ctx: GenContext) -> Question:
    cands = [o for o in ctx.bank.distractor_pool(max(ctx.max_tier, w.tier))
             if o.id != w.id and o.hanzi != w.hanzi and not (o.senses & w.senses)
             and o.meaning_vi != w.meaning_vi]
    wrong = _pick(cands, lambda o: 2 * (o.topic == w.topic) + (o.tier == w.tier), ctx.rng)
    wrong_texts = []
    for o in wrong:
        if o.meaning_vi not in wrong_texts:
            wrong_texts.append(o.meaning_vi)
    if len(wrong_texts) < 3:
        raise QuestionError("not enough meanings")
    opts, cid = _choice_options(w.meaning_vi, wrong_texts, ctx.rng)
    return Question("Q1", w.id, {"hanzi": w.hanzi}, "choice", opts,
                    {"option": cid, "reveal": _reveal(w, w.meaning_vi)}, _time_limit("Q1"))


def gen_q2(w: Word, ctx: GenContext) -> Question:
    comps = {c for ch in w.chars for c in (ch.get("components") or [])} | set(w.hanzi)
    base = py.strip_tones(w.pinyin_numeric)

    def score(o: Word) -> float:
        o_comps = {c for ch in o.chars for c in (ch.get("components") or [])} | set(o.hanzi)
        return (2 * bool(comps & o_comps) + 2 * (py.strip_tones(o.pinyin_numeric) == base)
                + (len(o.hanzi) == len(w.hanzi)) + (o.topic == w.topic))

    cands = [o for o in ctx.bank.distractor_pool(max(ctx.max_tier, w.tier))
             if o.id != w.id and o.hanzi != w.hanzi and not (o.senses & w.senses)]
    wrong = _pick(cands, score, ctx.rng)
    if len(wrong) < 3:
        raise QuestionError("not enough words")
    opts, cid = _choice_options(w.hanzi, [o.hanzi for o in wrong], ctx.rng)
    return Question("Q2", w.id, {"meaning_vi": w.meaning_vi}, "choice", opts,
                    {"option": cid, "reveal": _reveal(w, w.hanzi)}, _time_limit("Q2"))


def _tone_variants(w: Word) -> list[str]:
    syls = py.split_numeric(w.pinyin_numeric)
    cur = [py.syllable_tone(s) for s in syls]
    invalid = set(w.readings_all) | {py.canonical(w.pinyin_numeric)}
    out: list[str] = []
    # change one syllable first, then two
    for i in range(len(syls)):
        for t in (1, 2, 3, 4):
            if t != cur[i]:
                nt = cur.copy()
                nt[i] = t
                out.append(py.with_tones(w.pinyin_numeric, nt))
    if len(syls) > 1:
        for i in range(len(syls)):
            for j in range(i + 1, len(syls)):
                for t1 in (1, 2, 3, 4):
                    for t2 in (1, 2, 3, 4):
                        if t1 != cur[i] and t2 != cur[j]:
                            nt = cur.copy()
                            nt[i], nt[j] = t1, t2
                            out.append(py.with_tones(w.pinyin_numeric, nt))
    # neutral-tone variants only as a last resort (single syllables with several readings)
    for i in range(len(syls)):
        if cur[i] != 5:
            nt = cur.copy()
            nt[i] = 5
            out.append(py.with_tones(w.pinyin_numeric, nt))
    seen, uniq = set(), []
    for v in out:
        c = py.canonical(v)
        if c not in invalid and c not in seen:
            seen.add(c)
            uniq.append(v)
    return uniq


def gen_q3(w: Word, ctx: GenContext) -> Question:
    variants = _tone_variants(w)
    real = {py.canonical(o.pinyin_numeric) for o in ctx.bank.words.values()}
    mishap_wrong = {py.canonical(m["wrong_pinyin"]) for m in ctx.bank.mishaps if m["target_id"] == w.id}
    nsyl_changed = lambda v: sum(a != b for a, b in zip(py.tones(v), py.tones(w.pinyin_numeric)))  # noqa: E731
    wrong = _pick(variants, lambda v: 3 * (py.canonical(v) in mishap_wrong)
                  + 2 * (py.canonical(v) in real) - nsyl_changed(v)
                  - 5 * (5 in py.tones(v) and 5 not in py.tones(w.pinyin_numeric)), ctx.rng)
    if len(wrong) < 3:
        raise QuestionError("not enough tone variants")
    marked = {v: py.numeric_to_marked(v) for v in wrong}
    opts, cid = _choice_options(w.pinyin, [marked[v] for v in wrong], ctx.rng)
    numeric_by_text = {w.pinyin: w.pinyin_numeric, **{marked[v]: py.canonical(v) for v in wrong}}
    return Question("Q3", w.id, {"hanzi": w.hanzi}, "choice", opts,
                    {"option": cid, "reveal": _reveal(w, w.pinyin),
                     "option_numeric": {o["id"]: numeric_by_text[o["text"]] for o in opts}},
                    _time_limit("Q3"))


def gen_q4(w: Word, ctx: GenContext) -> Question:
    base = py.strip_tones(w.pinyin_numeric)
    cands = [o for o in ctx.bank.distractor_pool(max(ctx.max_tier, w.tier))
             if o.id != w.id and o.hanzi != w.hanzi and not _homophone(o, w)]
    wrong = _pick(cands, lambda o: 3 * (py.strip_tones(o.pinyin_numeric) == base)
                  + (len(o.hanzi) == len(w.hanzi)) + (o.topic == w.topic), ctx.rng)
    # two wrong options must not sound the same either, or the listener cannot tell them apart
    if len(wrong) < 3 or any(_homophone(a, b) for i, a in enumerate(wrong) for b in wrong[i + 1:]):
        alt = []
        for o in sorted(cands, key=lambda o: -(3 * (py.strip_tones(o.pinyin_numeric) == base))):
            if all(not _homophone(o, x) for x in alt):
                alt.append(o)
            if len(alt) == 3:
                break
        wrong = alt
    if len(wrong) < 3:
        raise QuestionError("not enough words")
    audio = ctx.has_audio(w.id)
    prompt = {"audio": audio}
    if not audio:  # spec 2: without audio the listening question shows pinyin instead
        prompt["pinyin"] = w.pinyin
    opts, cid = _choice_options(w.hanzi, [o.hanzi for o in wrong], ctx.rng)
    return Question("Q4", w.id, prompt, "choice", opts,
                    {"option": cid, "reveal": _reveal(w, w.hanzi)}, _time_limit("Q4"))


def gen_q5(w: Word, ctx: GenContext) -> Question:
    prompt = {"hanzi": w.hanzi}
    if len(w.readings_all) > 1:  # polyphone: say which meaning is meant
        prompt["meaning_vi"] = w.meaning_vi
    return Question("Q5", w.id, prompt, "text", None,
                    {"pinyin_numeric": w.pinyin_numeric,
                     "reveal": _reveal(w, f"{w.pinyin} ({' '.join(py.split_numeric(w.pinyin_numeric)).lower()})")},
                    _time_limit("Q5"))


def _classifier_pool(bank: WordBank) -> Counter:
    c = Counter()
    for o in bank.words.values():
        for m in o.measure_words:
            c[m["hanzi"]] += 1
    for o in bank.words.values():
        if o.topic == "measure" and o.single_char:
            c[o.hanzi] += 1
    return c


def gen_q6(w: Word, ctx: GenContext) -> Question:
    generic = balance.quiz()["generic_classifier"]
    if w.topic == "measure":  # the word is a classifier: find a noun that takes it
        nouns = [o for o in ctx.bank.words.values() if not o.hidden and o.tier <= max(ctx.max_tier, w.tier)
                 and any(m["hanzi"] == w.hanzi for m in o.measure_words)]
        if not nouns:
            raise QuestionError("no noun uses this classifier")
        noun = ctx.rng.choice(nouns)
        answer = w.hanzi
    else:
        noun = w
        specific = [m["hanzi"] for m in w.measure_words if m["hanzi"] != generic]
        if not specific:
            raise QuestionError("no specific classifier")
        answer = specific[0]
    valid = {m["hanzi"] for m in noun.measure_words} | {answer, generic}
    pool = _classifier_pool(ctx.bank)
    cands = [c for c in pool if c not in valid]
    wrong = _pick(cands, lambda c: pool[c], ctx.rng)
    if len(wrong) < 3:
        raise QuestionError("not enough classifiers")
    opts, cid = _choice_options(answer, wrong, ctx.rng)
    target = ctx.bank.by_hanzi.get(answer) if w.topic == "measure" else w
    return Question("Q6", w.id,
                    {"phrase": ["一", "__", noun.hanzi], "noun_hanzi": noun.hanzi,
                     "noun_meaning_vi": noun.meaning_vi}, "choice", opts,
                    {"option": cid, "reveal": {**_reveal(target or w, answer),
                                               "phrase": f"一{answer}{noun.hanzi}"}},
                    _time_limit("Q6"), {"noun_id": noun.id})


def gen_q7(w: Word, ctx: GenContext) -> Question:
    sents = [s for s in _usable_sentences(ctx, w)
             if [t["word_id"] for t in s.tokens].count(w.id) == 1]
    if not sents:
        raise QuestionError("no sentence")
    s = ctx.rng.choice(sents)
    in_sentence = {t["t"] for t in s.tokens}
    cands = [o for o in ctx.bank.distractor_pool(max(ctx.max_tier, w.tier))
             if o.id != w.id and o.hanzi not in in_sentence and not (o.senses & w.senses)
             and (not _pos1(o) or not _pos1(w) or _pos1(o) != _pos1(w))]
    wrong = _pick(cands, lambda o: (o.tier <= w.tier) + (len(o.hanzi) == len(w.hanzi)), ctx.rng)
    if len(wrong) < 3:
        raise QuestionError("not enough words")
    tokens = [("__" if t["word_id"] == w.id else t["t"]) for t in s.tokens]
    opts, cid = _choice_options(w.hanzi, [o.hanzi for o in wrong], ctx.rng)
    return Question("Q7", w.id, {"tokens": tokens, "vi": s.vi}, "choice", opts,
                    {"option": cid, "reveal": {**_reveal(w, w.hanzi), "sentence": s.text}},
                    _time_limit("Q7"), {"sentence_id": s.id})


def _components(w: Word) -> list[str] | None:
    if not w.single_char or not w.chars:
        return None
    c = w.chars[0]
    comps = c.get("components") or []
    if c.get("etymology_type") not in ("ideographic", "pictophonetic") or not 2 <= len(comps) <= 3:
        return None
    return comps


def gen_q8(w: Word, ctx: GenContext) -> Question:
    comps = _components(w)
    if not comps:
        raise QuestionError("no meaningful decomposition")
    right = Counter(comps)
    others = [cs for o in ctx.bank.words.values() if o.id != w.id
              and (cs := (o.chars[0].get("components") if o.single_char and o.chars else None))
              and 2 <= len(cs) <= 3]
    all_parts = sorted({p for cs in others for p in cs} | set(comps))
    cands: list[list[str]] = []
    for cs in others:
        if len(cs) == len(comps):
            cands.append(list(cs))
    for i in range(len(comps)):  # one part swapped: the classic near-miss
        for p in all_parts:
            if p != comps[i]:
                cands.append(comps[:i] + [p] + comps[i + 1:])
    uniq, seen = [], {" + ".join(comps)}
    for cs in cands:
        txt = " + ".join(cs)
        if txt not in seen and Counter(cs) != right:
            seen.add(txt)
            uniq.append(cs)
    wrong = _pick(uniq, lambda cs: 2 * len(set(cs) & set(comps)) + ctx.rng.random(), ctx.rng)
    if len(wrong) < 3:
        raise QuestionError("not enough component sets")
    opts, cid = _choice_options(" + ".join(comps), [" + ".join(cs) for cs in wrong], ctx.rng)
    rv = _reveal(w, " + ".join(comps))
    rv["hint"] = w.chars[0].get("etymology_hint")
    return Question("Q8", w.id, {"hanzi": w.hanzi}, "choice", opts,
                    {"option": cid, "reveal": rv}, _time_limit("Q8"))


def gen_q9(w: Word, ctx: GenContext) -> Question:
    sents = []
    for s in _usable_sentences(ctx, w):
        words = [t for t in s.tokens if t["t"] not in PUNCT]
        inner_punct = any(t["t"] in PUNCT for t in s.tokens[:-1])
        if len(words) >= 3 and not inner_punct and len({t["t"] for t in words}) >= 2:
            sents.append(s)
    if not sents:
        raise QuestionError("no sentence")
    s = ctx.rng.choice(sents)
    words = [t["t"] for t in s.tokens if t["t"] not in PUNCT]
    end = s.tokens[-1]["t"] if s.tokens[-1]["t"] in PUNCT else ""
    order = list(range(len(words)))
    for _ in range(20):
        ctx.rng.shuffle(order)
        if [words[i] for i in order] != words:
            break
    else:
        raise QuestionError("cannot shuffle")
    ids = [f"t{k + 1}" for k in range(len(words))]
    options = [{"id": ids[k], "text": words[i]} for k, i in enumerate(order)]
    return Question("Q9", w.id, {"end_punct": end, "vi": s.vi}, "order", options,
                    {"order_text": words, "token_text": {o["id"]: o["text"] for o in options},
                     "reveal": {**_reveal(w, s.text), "sentence": s.text}},
                    _time_limit("Q9"), {"sentence_id": s.id})


def gen_q10(w: Word, ctx: GenContext) -> Question:
    sents = _usable_sentences(ctx, w)
    if not sents:
        raise QuestionError("no sentence")
    s = ctx.rng.choice(sents)
    pool = [o for o in ctx.bank.sentences.values()
            if o.text != s.text and o.vi != s.vi and o.tier <= max(ctx.max_tier, w.tier)
            and (o.reviewed or ctx.allow_unreviewed)]
    shared = set(s.word_ids)
    wrong = _pick(pool, lambda o: len(shared & set(o.word_ids)), ctx.rng)
    if len(wrong) < 3:
        raise QuestionError("not enough sentences")
    opts, cid = _choice_options(s.vi, [o.vi for o in wrong], ctx.rng)
    return Question("Q10", w.id, {"text": s.text}, "choice", opts,
                    {"option": cid, "reveal": {**_reveal(w, s.vi), "sentence": s.text}},
                    _time_limit("Q10"), {"sentence_id": s.id})


def gen_q11(w: Word, ctx: GenContext) -> Question:
    syls = py.split_numeric(w.pinyin_numeric)
    if len(syls) != 1:
        raise QuestionError("not a single syllable")
    tone = py.syllable_tone(syls[0])
    base = py.syllable_base(syls[0]).lower()
    if tone == 5:
        raise QuestionError("neutral tone")
    if any(py.syllable_base(r).lower() == base and py.syllable_tone(r) != tone for r in w.readings_all):
        raise QuestionError("polyphone with another tone")
    options = [{"id": str(t), "text": str(t)} for t in (1, 2, 3, 4)]
    return Question("Q11", w.id, {"hanzi": w.hanzi, "pinyin_toneless": base}, "tone", options,
                    {"option": str(tone), "reveal": _reveal(w, f"thanh {tone}")}, _time_limit("Q11"))


GENERATORS = {"Q1": gen_q1, "Q2": gen_q2, "Q3": gen_q3, "Q4": gen_q4, "Q5": gen_q5, "Q6": gen_q6,
              "Q7": gen_q7, "Q8": gen_q8, "Q9": gen_q9, "Q10": gen_q10, "Q11": gen_q11}


def generate(qtype: str, w: Word, ctx: GenContext) -> Question:
    if qtype not in GENERATORS:
        raise QuestionError(f"unknown question type {qtype}")
    return GENERATORS[qtype](w, ctx)


def generate_any(qtypes: list[str], w: Word, ctx: GenContext) -> Question:
    """Try the allowed types in random order; Q1 is always possible as a last resort."""
    order = list(qtypes)
    ctx.rng.shuffle(order)
    for qt in order + (["Q1"] if "Q1" not in order else []):
        try:
            return generate(qt, w, ctx)
        except QuestionError:
            continue
    raise QuestionError(f"no question type works for {w.hanzi}")


def generate_first(qtypes: list[str], w: Word, ctx: GenContext) -> Question:
    """Try the types in the given order (used where the spec fixes the question type)."""
    for qt in qtypes:
        try:
            return generate(qt, w, ctx)
        except QuestionError:
            continue
    raise QuestionError(f"none of {qtypes} works for {w.hanzi}")


def can_generate(qtype: str, w: Word, ctx: GenContext) -> bool:
    try:
        generate(qtype, w, ctx)
        return True
    except QuestionError:
        return False


# ------------------------------------------------------------------ grading
def grade(qtype: str, answer_key: dict, answer: dict | None) -> bool:
    if not isinstance(answer, dict):
        return False
    if qtype in ("Q5",):
        text = answer.get("text")
        return isinstance(text, str) and py.typed_matches(answer_key["pinyin_numeric"], text)
    if qtype == "Q9":
        ids = answer.get("order")
        mapping = answer_key["token_text"]
        if not isinstance(ids, list) or sorted(map(str, ids)) != sorted(mapping):
            return False
        return [mapping[str(i)] for i in ids] == answer_key["order_text"]
    opt = answer.get("option")
    return isinstance(opt, str) and opt == answer_key["option"]
