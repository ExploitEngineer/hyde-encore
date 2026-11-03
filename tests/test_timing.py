import itertools

import pytest

from encorelib.model import Line, Lyrics, Word
from encorelib.timing import Cursor, estimate_words, locate, with_words


def _words_contiguous(words):
    return all(a.end == pytest.approx(b.start) for a, b in itertools.pairwise(words))


def test_estimate_spans_line():
    out = estimate_words(Line(10.0, 12.0, "a bb ccc"))
    assert [w.text for w in out.words] == ["a", "bb", "ccc"]
    assert out.words[0].start == 10.0
    assert _words_contiguous(out.words)
    assert out.words[-1].end <= 12.0
    # longer words get more time
    assert (out.words[2].end - out.words[2].start) > (out.words[0].end - out.words[0].start)


def test_estimate_caps_long_gap():
    out = estimate_words(Line(10.0, 40.0, "hi"))
    assert out.words[-1].end == pytest.approx(10.0 + 0.45 * 2)


def test_estimate_empty_text():
    assert estimate_words(Line(1.0, 2.0, "")).words == ()


def test_with_words_fills_only_missing():
    timed = Line(0.0, 1.0, "x", (Word("x", 0.0, 0.5),))
    lyr = Lyrics((timed, Line(1.0, 3.0, "a b")), "line", "t")
    out = with_words(lyr)
    assert out.lines[0] is timed
    assert len(out.lines[1].words) == 2
    assert out.sync == "line"


def test_with_words_leaves_unsynced_alone():
    lyr = Lyrics((Line(0.0, 0.0, "a b"),), "none", "t")
    assert with_words(lyr) == lyr


LYR = Lyrics(
    (
        Line(10.0, 14.0, "one two", (Word("one", 10.0, 11.0), Word("two", 12.0, 13.0))),
        Line(14.0, 20.0, ""),
        Line(20.0, 22.0, "three", (Word("three", 20.0, 21.0),)),
    ),
    "word",
    "t",
)


def test_locate_before_first_line():
    assert locate(LYR, 3.0) == Cursor(-1, -1, 0.0)


def test_locate_in_word():
    c = locate(LYR, 10.5)
    assert (c.line, c.word) == (0, 0)
    assert c.progress == pytest.approx(0.5)


def test_locate_between_words():
    assert locate(LYR, 11.5) == Cursor(0, 0, 1.0)


def test_locate_gap_line():
    assert locate(LYR, 16.0) == Cursor(1, -1, 0.0)


def test_locate_after_end():
    assert locate(LYR, 30.0) == Cursor(2, -1, 0.0)


def test_locate_seek_back():
    locate(LYR, 21.5)
    assert locate(LYR, 10.5).line == 0


def test_locate_empty_lyrics():
    assert locate(Lyrics((), "none", "t"), 5.0) == Cursor(-1, -1, 0.0)


def test_locate_unsynced_never_highlights():
    lyr = Lyrics((Line(0.0, 0.0, "a"), Line(0.0, 0.0, "b")), "none", "t")
    assert locate(lyr, 50.0) == Cursor(-1, -1, 0.0)
