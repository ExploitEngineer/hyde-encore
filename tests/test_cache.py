import os
import time

from encorelib.cache import LyricsCache
from encorelib.model import Line, Lyrics


def test_cache_roundtrip(tmp_path):
    cache = LyricsCache(tmp_path)
    lyr = Lyrics((Line(1.0, 2.0, "x"),), "line", "lrclib")
    cache.put("k", lyr)
    assert cache.get("k") == lyr
    assert (tmp_path / "lyrics" / "k.json").exists()


def test_cache_not_cached(tmp_path):
    assert LyricsCache(tmp_path).get("nope") is None


def test_cache_miss_marker(tmp_path):
    cache = LyricsCache(tmp_path)
    cache.put("k", None)
    assert cache.get("k") == Lyrics((), "none", "miss")


def test_cache_miss_marker_expires(tmp_path):
    cache = LyricsCache(tmp_path)
    cache.put("k", None)
    old = time.time() - 8 * 86400
    os.utime(tmp_path / "lyrics" / "k.json", (old, old))
    assert cache.get("k") is None


def test_cache_hit_never_expires(tmp_path):
    cache = LyricsCache(tmp_path)
    lyr = Lyrics((Line(1.0, 2.0, "x"),), "line", "lrclib")
    cache.put("k", lyr)
    old = time.time() - 30 * 86400
    os.utime(tmp_path / "lyrics" / "k.json", (old, old))
    assert cache.get("k") == lyr


def test_cache_corrupt_file_is_not_cached(tmp_path):
    cache = LyricsCache(tmp_path)
    (tmp_path / "lyrics").mkdir()
    (tmp_path / "lyrics" / "k.json").write_text("{not json")
    assert cache.get("k") is None
