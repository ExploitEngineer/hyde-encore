from encorelib.wordrects import word_byte_ranges


def spans(text, words):
    data = text.encode()
    return [data[a:b].decode() for a, b in word_byte_ranges(text, words)]


def test_ascii_words():
    text = "one two three"
    assert spans(text, ["one", "two", "three"]) == ["one", "two", "three"]


def test_repeated_words_advance():
    text = "la la la"
    ranges = word_byte_ranges(text, ["la", "la", "la"])
    assert ranges == [(0, 2), (3, 5), (6, 8)]


def test_punctuation_in_words():
    text = "Swords on my back, serpents on attack"
    assert spans(text, ["back,", "serpents"]) == ["back,", "serpents"]


def test_non_latin_multibyte():
    text = "夜に 駆ける よ"
    assert spans(text, ["夜に", "駆ける", "よ"]) == ["夜に", "駆ける", "よ"]


def test_arabic():
    text = "يا ليل يا عين"
    assert spans(text, ["يا", "ليل", "يا", "عين"]) == ["يا", "ليل", "يا", "عين"]


def test_emoji():
    text = "fire 🔥🔥 ok"
    assert spans(text, ["fire", "🔥🔥", "ok"]) == ["fire", "🔥🔥", "ok"]


def test_missing_word_gets_empty_range():
    text = "one two"
    ranges = word_byte_ranges(text, ["one", "zzz", "two"])
    assert len(ranges) == 3
    a, b = ranges[1]
    assert a == b  # empty span, draws nothing
    assert ranges[2] == (4, 7)
