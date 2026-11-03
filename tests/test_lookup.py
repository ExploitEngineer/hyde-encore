import json

from conftest import FIXTURES

from encorelib.cache import LyricsCache
from encorelib.config import EncoreConfig
from encorelib.lookup import lookup_lyrics
from encorelib.providers import NotFound, ProviderError, TrackInfo

SPOTIFY_ID = "4uLU6hMCjMI75M1A2tKUQC"
TRACK = TrackInfo(
    "Test Song", "Test Artist", "Test Album", 215.0, "", f"spotify:track:{SPOTIFY_ID}", "spotify"
)


class Fetch:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self, url, headers):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def cfg(tmp_path, **kw):
    return EncoreConfig(lyrics_dirs=(tmp_path / "lyrics",), **kw)


def test_transient_error_is_not_cached(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    offline = Fetch(ProviderError("offline"))
    assert lookup_lyrics(TRACK, cfg(tmp_path), cache, offline) is None
    online = Fetch((FIXTURES / "lrclib_get.json").read_bytes())
    assert lookup_lyrics(TRACK, cfg(tmp_path), cache, online).source == "lrclib"


def test_definitive_miss_is_cached(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    missing = Fetch(NotFound("x"))
    assert lookup_lyrics(TRACK, cfg(tmp_path), cache, missing) is None
    calls = missing.calls
    assert lookup_lyrics(TRACK, cfg(tmp_path), cache, missing) is None
    assert missing.calls == calls


def test_hit_is_cached(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    fetch = Fetch((FIXTURES / "lrclib_get.json").read_bytes())
    lookup_lyrics(TRACK, cfg(tmp_path), cache, fetch)
    lookup_lyrics(TRACK, cfg(tmp_path), cache, fetch)
    assert fetch.calls == 1


def test_local_lrc_beats_cache_and_is_not_cached(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    lookup_lyrics(TRACK, cfg(tmp_path), cache, Fetch(NotFound("x")))  # cached miss
    (tmp_path / "lyrics").mkdir()
    (tmp_path / "lyrics" / "Test Artist - Test Song.lrc").write_text("[00:01.00]mine")
    lyr = lookup_lyrics(TRACK, cfg(tmp_path), cache, Fetch(NotFound("x")))
    assert lyr.source == "local"
    assert lyr.lines[0].text == "mine"


def test_adding_spicy_key_bypasses_old_cache(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    lookup_lyrics(TRACK, cfg(tmp_path), cache, Fetch((FIXTURES / "lrclib_get.json").read_bytes()))
    spicy = Fetch((FIXTURES / "spicy_syllable.json").read_bytes())
    lyr = lookup_lyrics(TRACK, cfg(tmp_path, lrclib=False, spicy_key="k"), cache, spicy)
    assert lyr.sync == "word"


def test_malformed_payloads_are_errors_not_crashes(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    for payload in (b"[]", b'"x"', b"null", b"[1,2]", b"{not json"):
        assert lookup_lyrics(TRACK, cfg(tmp_path), cache, Fetch(payload)) is None
    # errors are never cached, so a good answer later still works
    good = Fetch((FIXTURES / "lrclib_get.json").read_bytes())
    assert lookup_lyrics(TRACK, cfg(tmp_path), cache, good) is not None


def test_malformed_spicy_is_error(tmp_path):
    cache = LyricsCache(tmp_path / "cache")
    bad = json.dumps(
        {"Body": {"Type": "Line", "source": "spotify", "Content": [{"StartTime": None}]}}
    )
    c = cfg(tmp_path, lrclib=False, spicy_key="k")
    assert lookup_lyrics(TRACK, c, cache, Fetch(bad.encode())) is None


def test_unwritable_cache_still_returns_lyrics(tmp_path):
    blocker = tmp_path / "cache"
    blocker.write_text("not a directory")
    fetch = Fetch((FIXTURES / "lrclib_get.json").read_bytes())
    assert lookup_lyrics(TRACK, cfg(tmp_path), LyricsCache(blocker), fetch).source == "lrclib"
