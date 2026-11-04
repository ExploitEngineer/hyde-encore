from encorelib.words import is_cjk, join_words, split_words, word_spans, word_units


def test_is_cjk():
    assert is_cjk("夜") and is_cjk("に") and is_cjk("カ") and is_cjk("ー")
    assert not is_cjk("a") and not is_cjk("사") and not is_cjk(" ")


def test_split_latin_words():
    assert split_words("hello world") == ["hello", "world"]


def test_split_japanese_per_character():
    assert split_words("夜に駆ける") == ["夜", "に", "駆", "け", "る"]


def test_split_mixed_scripts():
    assert split_words("Lemon 夢ならば") == ["Lemon", "夢", "な", "ら", "ば"]


def test_split_latin_glued_to_cjk():
    assert split_words("夜にLemon") == ["夜", "に", "Lemon"]


def test_split_punctuation_attaches_to_previous():
    assert split_words("夢。ok!") == ["夢。", "ok!"]
    assert split_words("「夢」") == ["「夢」"]


def test_split_hangul_keeps_words():
    assert split_words("사랑해 너를") == ["사랑해", "너를"]


def test_split_blank():
    assert split_words("   ") == []


def test_join_words_cjk_seams():
    # no space only between two CJK characters; mixed seams keep words apart
    assert join_words(["夜", "に", "Lemon", "go"]) == "夜に Lemon go"
    assert join_words(["I", "love", "you", "君", "を"]) == "I love you 君を"
    assert join_words(["hello", "world"]) == "hello world"
    assert join_words([]) == ""


def test_join_round_trips_split():
    # mixed Latin/CJK spacing is not recoverable from tokens; pure scripts are
    for text in ("夜に駆ける", "hello world", "夢。「夜」", "사랑해 너를"):
        assert join_words(split_words(text)) == text


def test_word_units():
    assert word_units("夜") == 3
    assert word_units("hey") == 3
    assert word_units("ok!") == 2
    assert word_units("夢。") == 3


def test_word_spans_in_order():
    assert word_spans("a b a", ["a", "a"]) == [(0, 1), (4, 5)]


def test_word_spans_missing_word_is_empty():
    assert word_spans("ab", ["x", "b"]) == [(0, 0), (1, 2)]


def test_word_spans_without_spaces():
    assert word_spans("夜に駆ける", ["夜", "に", "駆"]) == [(0, 1), (1, 2), (2, 3)]
