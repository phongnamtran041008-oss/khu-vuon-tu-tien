from app.learning import pinyin as py


def test_marks():
    assert py.numeric_to_marked("ma1") == "mā"
    assert py.numeric_to_marked("ma1 ma5") == "māma"
    assert py.numeric_to_marked("nü3") == "nǚ"
    assert py.numeric_to_marked("nu:3") == "nǚ"
    assert py.numeric_to_marked("lü4") == "lǜ"
    assert py.numeric_to_marked("gou3") == "gǒu"
    assert py.numeric_to_marked("xue2") == "xué"
    assert py.numeric_to_marked("gui4") == "guì"
    assert py.numeric_to_marked("liu4") == "liù"
    assert py.numeric_to_marked("Zhong1 guo2") == "Zhōngguó"
    assert py.numeric_to_marked("ke3 ai4") == "kě'ài"
    assert py.numeric_to_marked("wan3 an1") == "wǎn'ān"


def test_roundtrip():
    for s in ["ma1", "ni3 hao3", "dui4 bu5 qi3", "nü3 er2", "yi1 shi2 er4 niao3"]:
        assert py.canonical(py.marked_to_numeric(py.numeric_to_marked(s, joined=False))) == py.canonical(s)


def test_typed_answers():
    assert py.typed_matches("ma1", "ma1")
    assert py.typed_matches("ma1 ma5", "ma1ma5")
    assert py.typed_matches("ma1 ma5", "ma1 ma")
    assert py.typed_matches("Zhong1 guo2", "zhong1guo2")
    assert py.typed_matches("nü3", "nv3")
    assert py.typed_matches("nü3", "nu:3")
    assert not py.typed_matches("ma1", "ma3")
    assert not py.typed_matches("ma1", "ma")
    assert not py.typed_matches("nü3", "nu3")
    assert not py.typed_matches("ma1", "")


def test_sandhi_tolerance():
    assert py.same_reading("一样", "yi1 yang4", "yi2 yang4")
    assert py.same_reading("不对", "bu4 dui4", "bu2 dui4")
    assert not py.same_reading("妈", "ma1", "ma3")
