from encorelib.codeview import CodeRow, code_rows, typed_text
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
