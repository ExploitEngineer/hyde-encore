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


def _aged_put(cache, key, age_days):
    cache.put(key, Lyrics((Line(1.0, 2.0, key),), "line", "lrclib"))
    stamp = time.time() - age_days * 86400
    os.utime(cache.dir / f"{key}.json", (stamp, stamp))


def test_prune_keeps_recently_used(tmp_path):
    cache = LyricsCache(tmp_path)
    for i, key in enumerate("abcde"):
        _aged_put(cache, key, 10 - i)  # a is oldest, e newest
    assert cache.get("a") is not None  # a hit makes a recent again
    cache.prune(max_files=3)
    left = sorted(p.stem for p in cache.dir.glob("*.json"))
    assert left == ["a", "d", "e"]


def test_put_prunes_to_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("encorelib.cache.MAX_FILES", 2)
    cache = LyricsCache(tmp_path)
    for i, key in enumerate("abc"):
        _aged_put(cache, key, 10 - i)
    cache.put("d", None)
    assert sorted(p.stem for p in cache.dir.glob("*.json")) == ["c", "d"]


def test_miss_hit_does_not_extend_miss_ttl(tmp_path):
    cache = LyricsCache(tmp_path)
    cache.put("k", None)
    old = time.time() - 6 * 86400
    os.utime(cache.dir / "k.json", (old, old))
    assert cache.get("k") is not None
    assert (cache.dir / "k.json").stat().st_mtime == old
