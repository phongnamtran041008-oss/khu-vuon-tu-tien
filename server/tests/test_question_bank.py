"""Every question type is generated correctly: the right answer is among the options,
no option is a second right answer, and nothing in the public payload reveals it."""
import json
import random
from collections import Counter

import pytest

from app.learning import pinyin as py
from app.learning import question_bank as qb
from app.learning.wordbank import bank

B = bank()
WORDS = list(B.words.values())
ANSWER_FIELDS = {"answer", "correct", "answer_key", "is_correct", "correct_option", "solution"}


def ctx(seed=0, unreviewed=True, audio=False):
    return qb.GenContext(bank=B, rng=random.Random(seed), max_tier=2, allow_unreviewed=unreviewed,
                         has_audio=lambda _w: audio)


def all_questions(qtype, seeds=(1, 2)):
    out = []
    for s in seeds:
        c = ctx(s)
        for w in WORDS:
            try:
                out.append((w, qb.generate(qtype, w, c)))
            except qb.QuestionError:
                pass
    return out


@pytest.mark.parametrize("qtype", qb.QTYPES)
def test_each_type_generates_for_some_words(qtype):
    assert len(all_questions(qtype, seeds=(1,))) >= 20


@pytest.mark.parametrize("qtype", qb.QTYPES)
def test_answer_in_options_and_options_distinct(qtype):
    for w, q in all_questions(qtype):
        if q.input in ("choice", "tone"):
            ids = [o["id"] for o in q.options]
            texts = [o["text"] for o in q.options]
            assert q.answer_key["option"] in ids
            assert len(set(texts)) == len(texts) == 4
        assert qb.grade(qtype, q.answer_key, _right(q))
        assert not qb.grade(qtype, q.answer_key, _wrong(q))


def _right(q):
    if q.input == "text":
        return {"text": q.answer_key["pinyin_numeric"]}
    if q.input == "order":
        pool = {}
        for tid, t in q.answer_key["token_text"].items():
            pool.setdefault(t, []).append(tid)
        return {"order": [pool[t].pop() for t in q.answer_key["order_text"]]}
    return {"option": q.answer_key["option"]}


def _wrong(q):
    if q.input == "text":
        return {"text": "zz9"}
    if q.input == "order":
        r = _right(q)["order"]
        return {"order": r[1:] + r[:1]} if len(set(q.answer_key["order_text"])) > 1 else {"order": []}
    return {"option": next(o["id"] for o in q.options if o["id"] != q.answer_key["option"])}


@pytest.mark.parametrize("qtype", qb.QTYPES)
def test_public_payload_hides_answer(qtype):
    for w, q in all_questions(qtype, seeds=(3,)):
        pub = q.public()
        dumped = json.dumps({k: v for k, v in pub.items() if k != "instruction_vi"}, ensure_ascii=False)
        assert not (ANSWER_FIELDS & set(pub))
        for o in pub["options"] or []:
            assert set(o) <= {"id", "text"}
        if qtype in ("Q1", "Q3", "Q5", "Q11"):
            assert w.id not in dumped  # no word id leaks the identity of the answer
        if qtype == "Q5":
            assert w.pinyin not in dumped and w.pinyin_numeric not in dumped
        if qtype == "Q4":
            assert w.hanzi in [o["text"] for o in pub["options"]]
            assert w.id not in dumped


def test_q1_q2_no_overlapping_meanings():
    for qtype in ("Q1", "Q2"):
        for w, q in all_questions(qtype):
            for o in q.options:
                if o["id"] == q.answer_key["option"]:
                    continue
                other = B.by_hanzi[o["text"]] if qtype == "Q2" else next(
                    x for x in WORDS if x.meaning_vi == o["text"])
                assert not (other.senses & w.senses), (w.hanzi, o["text"])


def test_q3_distractors_are_not_valid_readings():
    for w, q in all_questions("Q3"):
        valid = set(w.readings_all)
        nums = q.answer_key["option_numeric"]
        for oid, num in nums.items():
            if oid != q.answer_key["option"]:
                assert py.canonical(num) not in valid, (w.hanzi, num)


def test_q4_no_homophones():
    for w, q in all_questions("Q4"):
        hanzi = [o["text"] for o in q.options]
        sounds = [py.canonical(B.by_hanzi[h].pinyin_numeric) for h in hanzi]
        assert len(set(sounds)) == 4, (w.hanzi, hanzi)


def test_q4_pinyin_fallback_only_without_audio():
    w = B.by_hanzi["妈"]
    q = qb.generate("Q4", w, ctx(audio=False))
    assert q.prompt == {"audio": False, "pinyin": w.pinyin}
    q = qb.generate("Q4", w, ctx(audio=True))
    assert q.prompt == {"audio": True}


def test_q6_only_cedict_classifiers_and_no_valid_distractor():
    for w, q in all_questions("Q6"):
        noun = B.by_hanzi[q.prompt["noun_hanzi"]]
        valid = {m["hanzi"] for m in noun.measure_words}
        right = next(o["text"] for o in q.options if o["id"] == q.answer_key["option"])
        assert right in valid
        for o in q.options:
            if o["id"] != q.answer_key["option"]:
                assert o["text"] not in valid and o["text"] != "个"


def test_q7_blank_is_the_word():
    for w, q in all_questions("Q7"):
        assert q.prompt["tokens"].count("__") == 1
        right = next(o["text"] for o in q.options if o["id"] == q.answer_key["option"])
        assert right == w.hanzi
        assert not ({o["text"] for o in q.options} - {right}) & set(q.prompt["tokens"])


def test_q8_components_from_makemeahanzi():
    for w, q in all_questions("Q8"):
        right = next(o["text"] for o in q.options if o["id"] == q.answer_key["option"])
        assert right == " + ".join(w.chars[0]["components"])
        right_set = Counter(w.chars[0]["components"])
        for o in q.options:
            if o["id"] != q.answer_key["option"]:
                assert Counter(o["text"].split(" + ")) != right_set


def test_q9_shuffled_and_gradeable():
    for w, q in all_questions("Q9"):
        shown = [o["text"] for o in q.options]
        assert sorted(shown) == sorted(q.answer_key["order_text"])
        assert shown != q.answer_key["order_text"]


def test_q11_tones():
    for w, q in all_questions("Q11"):
        assert q.answer_key["option"] == str(py.tones(w.pinyin_numeric)[0])


def test_sentences_require_review_outside_dev():
    c = ctx(unreviewed=False)
    for qtype in ("Q7", "Q9", "Q10"):
        for w in WORDS:
            with pytest.raises(qb.QuestionError):
                qb.generate(qtype, w, c)


def test_correct_option_position_is_random():
    pos = Counter()
    c = ctx(9)
    w = B.by_hanzi["水"]
    for _ in range(400):
        pos[qb.generate("Q1", w, c).answer_key["option"]] += 1
    assert all(60 < pos[k] < 140 for k in "abcd"), pos


def test_grade_rejects_garbage():
    q = qb.generate("Q1", B.by_hanzi["水"], ctx())
    for bad in (None, {}, {"option": 1}, {"option": ["a"]}, "a", {"text": "a"}):
        assert not qb.grade("Q1", q.answer_key, bad)
    q9 = next(q for _, q in all_questions("Q9", seeds=(1,)))
    assert not qb.grade("Q9", q9.answer_key, {"order": ["t1", "t1", "t1"]})
