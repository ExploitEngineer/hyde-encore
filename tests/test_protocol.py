import socket
import threading
import time
from pathlib import Path

from encorelib.clock import PlaybackClock
from encorelib.model import Line, Lyrics, Word
from encorelib.protocol import StateServer, build_state, hyprlock_markup, read_state
from encorelib.providers import TrackInfo
from encorelib.timing import Cursor

TRACK = TrackInfo("Song", "Artist", "Album", 200.0, "", "", "spotify")
LYR = Lyrics(
    (
        Line(
            10.0,
            14.0,
            "one two three",
            (Word("one", 10, 11), Word("two", 11, 12), Word("three", 12, 13)),
        ),
        Line(14.0, 18.0, "next line"),
    ),
    "word",
    "lrclib",
)


def clock_at(position, playing=True):
    clock = PlaybackClock(lambda: 500.0)
    clock.sync(position, playing)
    return clock


def test_build_state_schema():
    state = build_state("playing", TRACK, Path("/c.png"), LYR, clock_at(11.5), {"pry1": "000000"})
    assert state["v"] == 1
    assert state["ts"] == 500.0
    assert state["status"] == "playing"
    assert state["player"] == "spotify"
    assert state["track"] == {
        "key": state["track"]["key"],
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "length": 200.0,
        "art": "/c.png",
        "cover": "/c.png",
    }
    assert len(state["track"]["key"]) == 40
    assert state["lyrics"]["sync"] == "word"
    assert state["lyrics"]["source"] == "lrclib"
    assert state["lyrics"]["credit"] is None
    assert state["lyrics"]["lines"] == [
        {"start": 10.0, "text": "one two three"},
        {"start": 14.0, "text": "next line"},
    ]
    assert state["position"] == 11.5
    assert state["rate"] == 1.0
    assert state["line"]["index"] == 0
    assert state["line"]["words"][1] == {"text": "two", "start": 11, "end": 12}
    assert state["next"] == "next line"
    assert state["palette"] == {"pry1": "000000"}


def test_state_carries_cover():
    state = build_state(
        "playing", TRACK, Path("/c/lock.png"), None, clock_at(1), {}, cover=Path("/c/full.jpg")
    )
    assert state["track"]["cover"] == "/c/full.jpg"
    assert state["track"]["art"] == "/c/lock.png"


def test_cover_falls_back_to_art():
    state = build_state("playing", TRACK, Path("/c/lock.png"), None, clock_at(1), {})
    assert state["track"]["cover"] == "/c/lock.png"


def test_build_state_no_track():
    state = build_state("stopped", None, None, None, clock_at(0, False), {})
    assert state["track"] is None
    assert state["player"] is None
    assert state["lyrics"] is None
    assert state["line"] is None
    assert state["next"] is None


def test_build_state_before_first_line():
    state = build_state("playing", TRACK, None, LYR, clock_at(2.0), {})
    assert state["line"] is None
    assert state["next"] == "one two three"
    assert state["track"]["art"] is None


def test_markup_highlights_sung_words():
    out = hyprlock_markup(LYR, Cursor(0, 1, 0.5), "#ff0000", "#888888")
    assert out == (
        '<span foreground="#ff0000">one two</span> <span foreground="#888888">three</span>'
    )


def test_markup_dim_with_alpha():
    out = hyprlock_markup(LYR, Cursor(0, -1, 0.0), "#ff0000", "#88888880")
    assert out == '<span foreground="#888888" fgalpha="50%">one two three</span>'


def test_markup_last_word_all_accent():
    out = hyprlock_markup(LYR, Cursor(0, 2, 1.0), "#ff0000", "#888888")
    assert out == '<span foreground="#ff0000">one two three</span>'


def test_markup_escapes():
    lyr = Lyrics(
        (
            Line(
                0,
                5,
                "rock & roll <3",
                (Word("rock", 0, 1), Word("&", 1, 2), Word("roll", 2, 3), Word("<3", 3, 4)),
            ),
        ),
        "word",
        "t",
    )
    out = hyprlock_markup(lyr, Cursor(0, 3, 1.0), "#ff0000", "#888888")
    assert "rock &amp; roll &lt;3" in out


def test_markup_gap_is_empty():
    lyr = Lyrics((Line(0, 5, ""),), "line", "t")
    assert hyprlock_markup(lyr, Cursor(0, -1, 0.0), "#f00000", "#888888") == ""


def test_markup_no_line_or_lyrics():
    assert hyprlock_markup(LYR, Cursor(-1, -1, 0.0), "#ff0000", "#888888") == ""
    assert hyprlock_markup(None, Cursor(0, 0, 0.0), "#ff0000", "#888888") == ""


def test_server_sends_last_state_on_connect(tmp_path):
    path = tmp_path / "hyde" / "encore.sock"
    server = StateServer(path)
    server.start()
    try:
        server.broadcast({"status": "playing"})
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(path))
        server.accept()
        assert client.makefile().readline().strip() == '{"status":"playing"}'
        client.close()
    finally:
        server.close()
    assert not path.exists()


def test_read_state_helper(tmp_path):
    path = tmp_path / "encore.sock"
    server = StateServer(path)
    server.start()
    server.broadcast({"status": "paused"})
    try:
        t = threading.Thread(target=lambda: (time.sleep(0.05), server.accept()))
        t.start()
        assert read_state(path) == {"status": "paused"}
        t.join()
    finally:
        server.close()


def test_read_state_no_server(tmp_path):
    assert read_state(tmp_path / "missing.sock") is None


def test_server_drops_dead_client(tmp_path):
    path = tmp_path / "encore.sock"
    server = StateServer(path)
    server.start()
    try:
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead.connect(str(path))
        server.accept()
        dead.close()
        alive = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        alive.connect(str(path))
        server.accept()
        for _ in range(3):
            server.broadcast({"n": 1})
        assert len(server.clients) == 1
        alive.close()
    finally:
        server.close()


def test_server_replaces_stale_socket_file(tmp_path):
    path = tmp_path / "encore.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()
    server = StateServer(path)
    server.start()
    server.close()


def test_server_refuses_second_instance(tmp_path):
    path = tmp_path / "encore.sock"
    first = StateServer(path)
    first.start()
    try:
        try:
            StateServer(path).start()
            raised = False
        except RuntimeError:
            raised = True
        assert raised
    finally:
        first.close()


def test_hyprlock_track_lines_escaped():
    from encorelib.protocol import hyprlock_track

    track = TrackInfo("Rock & Roll <3", "AC/DC", "", 0, "", "", "spotify")
    assert hyprlock_track(track) == "Rock &amp; Roll &lt;3\nAC/DC\n"
    assert hyprlock_track(None) == ""


def test_hyprlock_colors_defaults_from_palette():
    from encorelib.colors import scheme
    from encorelib.config import EncoreConfig
    from encorelib.protocol import hyprlock_colors

    palette = {"1xa8": "CAAAF0", "txt1": "09090A"}
    accent, dim = hyprlock_colors(EncoreConfig(), palette, {})
    assert accent == "#" + scheme(palette, {}).accent  # the vivid scheme accent, same hue
    assert dim == "#FFFFFF66"  # soft white at 40%, never the palette's (maybe dark) text color


def test_hyprlock_colors_config_wins_and_fallback():
    from encorelib.config import EncoreConfig
    from encorelib.protocol import hyprlock_colors

    cfg = EncoreConfig(hyprlock_color="#FF0000", hyprlock_dim="#00FF0080")
    assert hyprlock_colors(cfg, {}) == ("#FF0000", "#00FF0080")
    # no cover and no theme: the curated default accent, never the owner's wallpaper
    from encorelib.colors import DEFAULT_ACCENT

    assert hyprlock_colors(EncoreConfig(), {}, {}) == ("#" + DEFAULT_ACCENT, "#FFFFFF66")


GAPPY = Lyrics(
    (
        Line(10.0, 60.0, "one two", (Word("one", 10.0, 11.0), Word("two", 11.0, 12.0))),
        Line(60.0, 70.0, ""),
        Line(70.0, 74.0, "three", (Word("three", 70.0, 71.0),)),
    ),
    "word",
    "t",
)


def test_build_state_gap_after_hold():
    state = build_state("playing", TRACK, None, GAPPY, clock_at(30.0), {})
    assert state["line"] is None
    assert state["gap"] == {"after": 0, "until": 70.0}
    assert state["next"] == "three"


def test_build_state_intro_is_gap():
    state = build_state("playing", TRACK, None, GAPPY, clock_at(2.0), {})
    assert state["gap"] == {"after": -1, "until": 10.0}
    assert state["next"] == "one two"


def test_build_state_live_line_has_no_gap():
    state = build_state("playing", TRACK, None, GAPPY, clock_at(10.5), {})
    assert state["line"]["index"] == 0
    assert state["gap"] is None
    assert state["next"] == "three"


def test_build_state_outro_gap_has_no_until():
    state = build_state("playing", TRACK, None, GAPPY, clock_at(90.0), {})
    assert state["line"] is None
    assert state["gap"] == {"after": 2, "until": None}
    assert state["next"] is None


def test_build_state_unsynced_has_no_gap():
    lyr = Lyrics((Line(0.0, 0.0, "a"),), "none", "t")
    assert build_state("playing", TRACK, None, lyr, clock_at(5.0), {})["gap"] is None


CJK_WORDS = tuple(Word(c, i, i + 1) for i, c in enumerate("夜に駆ける"))
CJK = Lyrics((Line(0.0, 5.0, "夜に駆ける", CJK_WORDS),), "word", "t")


def test_build_state_line_text():
    state = build_state("playing", TRACK, None, CJK, clock_at(1.5), {})
    assert state["line"]["text"] == "夜に駆ける"


def test_markup_cjk_keeps_spacing():
    out = hyprlock_markup(CJK, Cursor(0, 1, 0.5, 0), "#ff0000", "#888888")
    assert out == '<span foreground="#ff0000">夜に</span><span foreground="#888888">駆ける</span>'


def test_hyprlock_colors_follow_the_scheme_for_grey_covers():
    from encorelib.colors import scheme
    from encorelib.config import EncoreConfig
    from encorelib.protocol import hyprlock_colors

    grey = {"1xa8": "D6D6D6", "2xa8": "D6D6D6", "txt1": "FFFFFF"}
    theme = {"1xa8": "4FB89A"}
    accent, _dim = hyprlock_colors(EncoreConfig(), grey, theme)
    assert accent == "#" + scheme(grey, theme).accent
    assert accent != "#D6D6D6"


def test_server_drops_hung_up_clients_without_broadcasting(tmp_path):
    # the player polls read_state every 400 ms while nothing is broadcast
    # (paused): closed clients must not pile up until the fd limit kills it
    server = StateServer(tmp_path / "s.sock")
    server.start()
    try:
        server.broadcast({"status": "paused"})
        for _ in range(60):  # connect, get the line, hang up: what read_state does
            poller = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            poller.connect(str(tmp_path / "s.sock"))
            server.accept()
            assert poller.makefile("rb").readline() == b'{"status":"paused"}\n'
            poller.close()
        live = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        live.connect(str(tmp_path / "s.sock"))
        server.accept()
        assert len(server.clients) <= 2  # the live client, maybe the last poller
        live.close()
    finally:
        server.close()
