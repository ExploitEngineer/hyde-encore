from encorelib.screen import field_shows, lookup_reason, pick_music_apps, screen_state

BASE = {"status": "playing", "track": {"key": "k"}, "position": 9, "ts": 0, "rate": 1}


def test_idle_when_player_gone():
    assert screen_state(None, 0) == "idle"
    assert screen_state({}, 0) == "idle"
    assert screen_state({"status": "stopped", "track": None}, 0) == "idle"
    assert screen_state({**BASE, "track": None}, 0) == "idle"


def test_waiting_then_no_lyrics_by_time_without_lookup_field():
    s = {**BASE, "lyrics": None, "position": 0.5}
    assert screen_state(s, 1.0) == "waiting"
    assert screen_state(s, 3.0) == "no_lyrics"


def test_lookup_field_decides_when_present():
    assert screen_state({**BASE, "lyrics": None, "lookup": "pending"}, 30) == "waiting"
    s = {**BASE, "lyrics": None, "lookup": "done", "position": 0.1}
    assert screen_state(s, 0.2) == "no_lyrics"


def test_plain_and_synced():
    lines = [{"start": 0, "text": "a"}]
    assert screen_state({**BASE, "lyrics": {"sync": "none", "lines": lines}}, 9) == "plain"
    assert screen_state({**BASE, "lyrics": {"sync": "line", "lines": lines}}, 9) == "lyrics"
    assert screen_state({**BASE, "lyrics": {"sync": "word", "lines": lines}}, 9) == "lyrics"


def test_empty_plain_lyrics_count_as_none():
    s = {**BASE, "lyrics": {"sync": "none", "lines": [{"start": 0, "text": " "}]}}
    assert screen_state(s, 9) == "no_lyrics"


def test_paused_keeps_its_state():
    s = {
        **BASE,
        "status": "paused",
        "lyrics": {"sync": "line", "lines": [{"start": 0, "text": "a"}]},
    }
    assert screen_state(s, 9) == "lyrics"


def test_lookup_reason():
    e = [
        {"artist": "A", "title": "T", "result": "none"},
        {"artist": "B", "title": "X", "result": "none"},
        {"artist": "A", "title": "T", "result": "error: timed out"},
    ]
    assert lookup_reason(e, "A", "T") == "Lyrics lookup failed. Check the connection."
    assert lookup_reason(e[:2], "A", "T") == "No synced lyrics found for this song."
    assert lookup_reason([], "A", "T") == "No synced lyrics found for this song."


def test_music_apps_known_first():
    apps = [
        ("vlc.desktop", "VLC", "AudioVideo;Player;"),
        ("spotify.desktop", "Spotify", "Audio;Music;Player;AudioVideo;"),
        ("org.gnome.Calculator.desktop", "Calculator", "GNOME;Utility;"),
    ]
    assert pick_music_apps(apps) == ["spotify.desktop", "vlc.desktop"]


def test_music_apps_skip_encore_and_limit():
    apps = [
        ("org.hyde.encore.desktop", "Encore", "AudioVideo;Audio;Player;"),
        ("a.desktop", "A", "Audio;Player;"),
        ("b.desktop", "B", "Audio;Player;"),
        ("c.desktop", "C", "Audio;Player;"),
        ("d.desktop", "D", "Audio;Player;"),
    ]
    assert pick_music_apps(apps) == ["a.desktop", "b.desktop", "c.desktop"]
    assert pick_music_apps(apps, limit=1) == ["a.desktop"]


def test_field_palette_without_cover():
    # a coverless track (podcast, local file): the album field shows under Full
    # screen whatever the background setting, so the window is never black
    assert field_shows("art", has_cover=False)
    assert field_shows("clear", has_cover=False)
    assert field_shows("clear", has_cover=True)
    assert not field_shows("art", has_cover=True)
