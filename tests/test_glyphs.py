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


def test_more_lyric_words_get_icons_like_the_reference():
    # the reference's hero: a person by "you", a speech bubble by "telling",
    # wind by "blew", a heart by "need"
    assert glyph_for("you") == glyph_for("your") == chr(0xF0004)
    assert glyph_for("Telling") == glyph_for("say") == chr(0xF0361)
    assert glyph_for("blew") == glyph_for("wind") == chr(0xF059D)
    assert glyph_for("need") == glyph_for("love")
    for word in ("light", "dream", "tears", "goodbye", "ocean", "sky", "smile", "rose", "storm"):
        assert glyph_for(word) is not None, word
