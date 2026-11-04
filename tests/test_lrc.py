from encorelib.lrc import parse_lrc
from encorelib.model import Lyrics, Word


def test_plain_lines():
    lyr = parse_lrc("[00:12.50]Hello world\n[00:15.00]Second")
    assert len(lyr.lines) == 2
    assert lyr.lines[0].start == 12.5
    assert lyr.lines[0].end == 15.0
    assert lyr.lines[0].text == "Hello world"
    assert lyr.lines[0].words == ()
    assert lyr.sync == "line"


def test_last_line_end():
    lyr = parse_lrc("[00:12.50]Hello\n[00:15.00]Second")
    assert lyr.lines[-1].end == 20.0


def test_multi_timestamp():
    lyr = parse_lrc("[00:30.00]Verse\n[00:01.00][00:40.00]Chorus")
    assert [(ln.start, ln.text) for ln in lyr.lines] == [
        (1.0, "Chorus"),
        (30.0, "Verse"),
        (40.0, "Chorus"),
    ]


def test_offset_tag_positive_shows_sooner():
    # LRC spec: positive offset (ms) makes lyrics appear sooner.
    lyr = parse_lrc("[offset:+500]\n[00:10.00]x")
    assert lyr.lines[0].start == 9.5


def test_offset_tag_negative_shows_later():
    lyr = parse_lrc("[offset:-250]\n[00:10.00]x")
    assert lyr.lines[0].start == 10.25


def test_timestamp_formats():
    lyr = parse_lrc("[01:02]a\n[01:03.5]b\n[01:04.250]c")
    assert [ln.start for ln in lyr.lines] == [62.0, 63.5, 64.25]


def test_enhanced_words():
    lyr = parse_lrc("[00:10.00]<00:10.00>Hel <00:10.40>lo <00:10.90>you<00:11.50>")
    assert lyr.sync == "word"
    words = lyr.lines[0].words
    assert len(words) == 3
    assert words[1] == Word("lo", 10.4, 10.9)
    assert words[-1].end == 11.5
    assert lyr.lines[0].text == "Hel lo you"


def test_enhanced_syllables_merge():
    lyr = parse_lrc("[00:01.00]<00:01.00>Hel<00:01.20>lo <00:01.50>world<00:02.00>")
    line = lyr.lines[0]
    assert line.text == "Hello world"
    assert line.words == (Word("Hello", 1.0, 1.5), Word("world", 1.5, 2.0))


def test_enhanced_cjk_keeps_characters():
    lyr = parse_lrc("[00:01.00]<00:01.00>夜<00:01.30>に<00:01.60>")
    line = lyr.lines[0]
    assert line.text == "夜に"
    assert [w.text for w in line.words] == ["夜", "に"]


def test_enhanced_last_word_without_closing_tag_ends_at_next_line():
    lyr = parse_lrc("[00:10.00]<00:10.00>a <00:10.50>b\n[00:12.00]<00:12.00>c")
    assert lyr.lines[0].words[-1].end == 12.0


def test_empty_lines_kept_as_gaps():
    lyr = parse_lrc("[00:05.00]a\n[00:08.00]\n[00:20.00]b")
    assert [ln.text for ln in lyr.lines] == ["a", "", "b"]
    assert lyr.lines[1].start == 8.0


def test_metadata_tags_ignored():
    lyr = parse_lrc("[ar:Someone]\n[ti:Song]\n[length:03:20]\n[00:01.00]x")
    assert [ln.text for ln in lyr.lines] == ["x"]


def test_no_timestamps():
    lyr = parse_lrc("first line\nsecond line\n")
    assert lyr.sync == "none"
    assert [ln.text for ln in lyr.lines] == ["first line", "second line"]
    assert all(ln.start == 0 for ln in lyr.lines)


def test_source_passed_through():
    assert parse_lrc("[00:01.00]x", source="lrclib").source == "lrclib"


def test_roundtrip_dict():
    lyr = parse_lrc("[00:10.00]<00:10.00>Hel <00:10.40>lo\n[00:12.00]plain")
    assert Lyrics.from_dict(lyr.to_dict()) == lyr
