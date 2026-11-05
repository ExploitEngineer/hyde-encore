from encorelib.codeview import CodeRow, code_rows, fit_scale, typed_text
from encorelib.stream import STYLES
from encorelib.typeface import role_for

SONG = ["Neon on the city floor", "", "I call your name at night", "Every light is moving left"]


def test_code_is_a_style_set_in_the_mono_partner():
    assert "code" in STYLES
    assert role_for("code", "k", 0) == "mono"


def test_typed_text_has_the_words_that_have_started():
    assert typed_text((("Every", 1.0), ("light", 0.4), ("is", 0.0))) == "Every light"
    assert typed_text((("Every", 0.0),)) == ""
    assert typed_text(()) == ""


def test_code_rows_end_on_the_line_being_typed():
    rows = code_rows(SONG, 3, "Every light", rows=3)
    assert rows[-1] == CodeRow(4, "Every light", True)
    assert [r.number for r in rows] == [2, 3, 4]


def test_past_lines_read_as_comments_and_blank_ones_stay_blank():
    rows = code_rows(SONG, 3, "Every", rows=4)
    assert rows[0] == CodeRow(1, "// Neon on the city floor", False)
    assert rows[1] == CodeRow(2, "", False)
    assert rows[2] == CodeRow(3, "// I call your name at night", False)


def test_the_first_line_has_no_past():
    assert code_rows(SONG, 0, "Neon", rows=5) == [CodeRow(1, "Neon", True)]


def test_rows_shrink_together_to_fit_the_widest():
    assert fit_scale([300.0, 900.0], 600.0) == 600.0 / 900.0
    assert fit_scale([300.0, 500.0], 600.0) == 1.0  # never grows
    assert fit_scale([], 600.0) == 1.0


def test_fit_scale_keeps_a_floor_on_a_tiny_window():
    assert fit_scale([2000.0], 10.0) == 0.25
    assert fit_scale([2000.0], -5.0) == 0.25


def test_typed_text_types_the_current_word_letter_by_letter():
    # a word types out over the first 40% of its time, then waits for the next
    words = (("Every", 1.0), ("light", 0.2), ("is", 0.0))
    assert typed_text(words) == "Every li"  # 0.2 / 0.4 of "light"
    assert typed_text((("Every", 1.0), ("light", 0.4))) == "Every light"
    assert typed_text((("Every", 0.01),)) == "E"  # a started word shows a letter at once


def test_typing_knows_when_letters_are_still_coming():
    from encorelib.codeview import typing

    assert typing((("Every", 1.0), ("light", 0.2)))
    assert not typing((("Every", 1.0), ("light", 0.5)))  # typed, waiting
    assert not typing((("Every", 0.0),))
