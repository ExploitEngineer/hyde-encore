from encorelib.glyphs import glyph_for


def test_known_words_map():
    assert glyph_for("city,") == "󰅆"
    assert glyph_for("Left") == "←"
    assert glyph_for("started") == "▶"


def test_unknown_word_none():
    assert glyph_for("strangers") is None
    assert glyph_for("") is None


def test_punctuation_and_case_ignored():
    assert glyph_for("FIRE!!") == glyph_for("fire")
    assert glyph_for("Money,") is not None
