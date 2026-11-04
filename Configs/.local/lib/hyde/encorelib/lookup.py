"""Lyrics lookup with caching rules the daemon relies on."""

from __future__ import annotations

import logging

from .cache import CACHED_MISS, LyricsCache
from .config import EncoreConfig
from .model import Lyrics
from .providers import Fetch, TrackInfo, find_lyrics, http_get, local_lrc, track_key

log = logging.getLogger("encore")


# Bump when parsing or lookup changes what a cached answer would hold, so
# old entries are refetched once (v2: search variants, CJK-aware lines).
LOOKUP_VERSION = 2


def cache_key(t: TrackInfo, cfg: EncoreConfig) -> str:
    """Track key, enabled online sources and lookup version."""
    sources = ("l" if cfg.lrclib else "") + ("s" if cfg.spicy_key else "")
    return f"{track_key(t)}-{sources or 'none'}-v{LOOKUP_VERSION}"


def lookup_lyrics(
    t: TrackInfo, cfg: EncoreConfig, cache: LyricsCache, fetch: Fetch = http_get
) -> Lyrics | None:
    """Lyrics for a track.

    Local .lrc files always win and are never cached, so edits show up at once.
    Online results are cached, including a definitive "no lyrics" answer, but
    nothing is cached when a provider failed, so being offline once does not
    hide a song's lyrics later.
    """
    local = local_lrc(t, cfg.lyrics_dirs)
    if local is not None:
        return local
    key = cache_key(t, cfg)
    cached = cache.get(key)
    if cached is not None:
        return None if cached == CACHED_MISS else cached
    errors: list[Exception] = []
    found = find_lyrics(t, cfg, fetch, errors=errors, use_local=False)
    if not errors:
        try:
            cache.put(key, found)
        except OSError as e:
            log.warning("could not cache lyrics: %s", e)
    return found
