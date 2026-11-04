import pytest

from encorelib.lyricview import (
    GAP_HIDE_SECONDS,
    build_view,
    live_position,
    lyric_row,
    lyric_rows,
)


def state(**kw):
    base = {
        "v": 1,
        "ts": 1000.0,
        "status": "playing",
        "player": "spotify",
        "track": {
            "key": "cafe01",
            "title": "T",
            "artist": "A",
            "album": "",
            "length": 200.0,
            "art": None,
        },
        "lyrics": {"sync": "word", "source": "lrclib", "credit": None},
        "position": 10.5,
        "rate": 1.0,
        "line": {
            "index": 3,
            "start": 10.0,
            "end": 30.0,
            "words": [
                {"text": "one", "start": 10.0, "end": 11.0},
                {"text": "two", "start": 12.0, "end": 13.0},
            ],
        },
        "next": "next line text",
        "palette": {},
    }
    base.update(kw)
    return base


def test_hidden_without_state_or_lyrics():
    assert build_view(None, 1000.0).visible is False
    assert build_view(state(status="stopped"), 1000.0).visible is False
    assert build_view(state(lyrics=None), 1000.0).visible is False
    assert (
        build_view(state(lyrics={"sync": "none", "source": "x", "credit": None}), 1000.0).visible
        is False
    )
    assert build_view(state(line=None), 1000.0).visible is False


def test_hidden_on_empty_gap_line():
    s = state(line={"index": 4, "start": 10.0, "end": 20.0, "words": []})
    assert build_view(s, 1000.0).visible is False


def test_live_position_playing_and_paused():
    assert live_position(state(), 1002.5) == pytest.approx(13.0)
    assert live_position(state(status="paused"), 1002.5) == pytest.approx(10.5)


def test_fill_mid_word():
    v = build_view(state(), 1000.0)  # live pos 10.5, inside word one
    assert v.visible is True
    assert v.text == "one two"
    assert v.next_text == "next line text"
    assert v.line_key == "cafe01:3"
    assert v.words[0][0] == "one"
    assert v.words[0][1] == pytest.approx(0.5)
    assert v.words[1][1] == 0.0
    assert v.animating is True
    assert v.wake_in is None


def test_sung_and_unsung_words():
    v = build_view(state(position=11.5), 1000.0)
    assert [f for _, f in v.words] == [1.0, 0.0]
    assert v.animating is False


def test_paused_mid_word_is_frozen():
    v = build_view(state(status="paused"), 1010.0)
    assert v.visible is True
    assert v.words[0][1] == pytest.approx(0.5)
    assert v.animating is False
    assert v.wake_in is None


def test_wake_in_between_words():
    v = build_view(state(position=11.5), 1000.0)
    assert v.wake_in == pytest.approx(0.5)


def test_rate_two_halves_wake_in():
    v = build_view(state(position=11.5, rate=2.0), 1000.0)
    assert v.wake_in == pytest.approx(0.25)


def test_visible_in_short_gap():
    v = build_view(state(position=13.0 + GAP_HIDE_SECONDS - 0.1), 1000.0)
    assert v.visible is True
    assert v.animating is False
    assert v.wake_in == pytest.approx(0.1)


def test_hidden_in_long_gap_after_line():
    v = build_view(state(position=13.0 + GAP_HIDE_SECONDS + 0.1), 1000.0)
    assert v.visible is False


def test_line_key_changes_with_track():
    a = build_view(state(), 1000.0)
    other = state()
    other["track"] = dict(other["track"], key="beef02")
    b = build_view(other, 1000.0)
    assert a.line_key != b.line_key


def test_should_transition_same_track_new_line():
    from encorelib.lyricview import should_transition

    assert should_transition("cafe01:3", "cafe01:4") is True


def test_should_transition_not_across_tracks():
    from encorelib.lyricview import should_transition

    assert should_transition("cafe01:3", "beef02:0") is False


def test_should_transition_needs_both_keys():
    from encorelib.lyricview import should_transition

    assert should_transition("", "cafe01:0") is False
    assert should_transition("cafe01:0", "") is False


def test_current_word_index():
    from encorelib.lyricview import current_word_index

    v = build_view(state(position=10.5), 1000.0)
    assert current_word_index(v) == 0
    v = build_view(state(position=12.4), 1000.0)
    assert current_word_index(v) == 1
    v = build_view(
        state(
            position=9.0,
            line={
                "index": 3,
                "start": 10.0,
                "end": 30.0,
                "words": [{"text": "one", "start": 10.0, "end": 11.0}],
            },
        ),
        1000.0,
    )
    assert current_word_index(v) == -1


def test_next_word_boundary_mid_word_and_between():
    from encorelib.lyricview import next_word_boundary

    assert next_word_boundary(state(), 1000.0) == pytest.approx(1.5)  # start of "two"
    assert next_word_boundary(state(position=11.5), 1000.0) == pytest.approx(0.5)  # start of "two"
    assert next_word_boundary(state(position=11.5, rate=2.0), 1000.0) == pytest.approx(0.25)
    # after the last word: wake at the gap-hide boundary (13.0 + GAP)
    assert next_word_boundary(state(position=13.5), 1000.0) == pytest.approx(GAP_HIDE_SECONDS - 0.5)
    assert next_word_boundary(state(position=13.0 + GAP_HIDE_SECONDS + 1), 1000.0) is None
    assert next_word_boundary(state(status="paused"), 1000.0) is None
    assert next_word_boundary(None, 1000.0) is None


def test_build_view_uses_line_text():
    line = {
        "index": 0,
        "start": 10.0,
        "end": 30.0,
        "text": "夜に",
        "words": [
            {"text": "夜", "start": 10.0, "end": 11.0},
            {"text": "に", "start": 11.0, "end": 12.0},
        ],
    }
    assert build_view(state(line=line), 1000.0).text == "夜に"


SONG = [
    {"start": 1.0, "text": "a"},
    {"start": 2.0, "text": ""},
    {"start": 3.0, "text": "  "},
    {"start": 4.0, "text": "b"},
]


def test_lyric_rows_skip_blank_lines():
    assert lyric_rows(SONG) == ["a", "b"]


def row_state(line_index=None, gap=None):
    line = {"index": line_index, "words": []} if line_index is not None else None
    return {"lyrics": {"lines": SONG}, "line": line, "gap": gap}


def test_lyric_row_live_line():
    assert lyric_row(row_state(line_index=3)) == 1


def test_lyric_row_keeps_place_in_a_gap():
    assert lyric_row(row_state(gap={"after": 0, "until": 4.0})) == 0
    assert lyric_row(row_state(gap={"after": 2, "until": 4.0})) == 0


def test_lyric_row_outro_keeps_last_row():
    assert lyric_row(row_state(gap={"after": 3, "until": None})) == 1


def test_lyric_row_intro_and_no_lyrics():
    assert lyric_row(row_state(gap={"after": -1, "until": 1.0})) == -1
    assert lyric_row({}) == -1


def test_column_choices_are_stable_across_processes():
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, 'Configs/.local/lib/hyde');"
        "from encorelib.lyricview import word_style, stagger;"
        "print([word_style('k:3', i) for i in range(6)], round(stagger('k:3', 2, 1536), 3))"
    )
    outs = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin"},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2")
    }
    assert len(outs) == 1, outs


def test_word_styles_mix_and_stagger_stays_small():
    from encorelib.lyricview import stagger, word_style

    assert {word_style("line", i) for i in range(30)} == {"bold", "serif", "medium"}
    assert all(abs(stagger("line", i, 1000)) <= 25 for i in range(30))
