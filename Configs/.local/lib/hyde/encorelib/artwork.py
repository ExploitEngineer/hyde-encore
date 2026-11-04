"""HD album covers: a bigger copy of the player's cover, else Apple's catalog.

Spotify's MPRIS artUrl is the 640 px size of an image whose 1500 px size
sits behind another size code on the same CDN, so that upgrade sends
nothing new anywhere. Other players (browsers, local players) often send
small covers; Apple's public iTunes Search API has artwork in any size.
Its results are matched strictly: a wrong cover is worse than a small one.
With an album name the album must match; without one (browser videos) the
song title must, and the cover is that song's album.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode

from .palette import fetch_art
from .providers import Fetch, ProviderError, http_get
from .query import clean_title, primary_artist, search_variants

SPOTIFY_LARGE = "ab67616d000082c1"
HD_MIN_PX = 1000
APPLE_SIZE = 2000  # fills 1080p and 1440p screens; 3000 px stalls slow links
APPLE_SEARCH = "https://itunes.apple.com/search"

# album covers carry the "ab67616d" family prefix, then an 8-hex size code
_SPOTIFY = re.compile(
    r"^(https://(?:i\.scdn\.co|[a-z0-9-]+\.spotifycdn\.com)/image/)"
    r"ab67616d[0-9a-f]{8}([0-9a-f]{24})$"
)
_APPLE_KIND = re.compile(r"\s+-\s+(?:single|ep)$", re.IGNORECASE)
_APPLE_THUMB = re.compile(r"/\d+x\d+bb\.(jpg|png|webp)$")
# JPEG start-of-frame markers carry the size; C4, C8 and CC are other tables
_SOF = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def spotify_large(url: str) -> str | None:
    """The 1500 px copy of a Spotify album cover URL, else None."""
    m = _SPOTIFY.match(url or "")
    return f"{m.group(1)}{SPOTIFY_LARGE}{m.group(2)}" if m else None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a PNG or JPEG from its header bytes, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte before a marker
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xD8)):  # standalone markers carry no length
            i += 2
            continue
        if marker in _SOF:
            if i + 9 > len(data):
                return None
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return None


def _name(text: str) -> str:
    """A title or album as compared across catalogs."""
    return " ".join(clean_title(_APPLE_KIND.sub("", text)).lower().split())


def _artist(text: str) -> str:
    return " ".join(primary_artist(text).lower().split())


def apple_search_url(artist: str, album: str, title: str) -> str | None:
    """The iTunes Search query for this cover, or None without enough to match."""
    name = clean_title(album or title).strip()
    who = primary_artist(artist).strip()
    if not who or not name:
        return None
    entity = "album" if album.strip() else "song"
    query = {"term": f"{who} {name}", "entity": entity, "media": "music", "limit": 10}
    return f"{APPLE_SEARCH}?{urlencode(query)}"


def apple_pick(results: list[dict], artist: str, album: str, title: str) -> str | None:
    """The artwork URL of the result whose artist and album (or, without an
    album, song title) both match, at APPLE_SIZE."""
    want_artist, want_name = _artist(artist), _name(album or title)
    if not want_artist or not want_name:
        return None
    field = "collectionName" if album.strip() else "trackName"
    for record in results:
        if not isinstance(record, dict):
            continue
        art = record.get("artworkUrl100")
        if not isinstance(art, str) or not _APPLE_THUMB.search(art):
            continue
        if _artist(str(record.get("artistName", ""))) != want_artist:
            continue
        if _name(str(record.get(field, ""))) != want_name:
            continue
        return _APPLE_THUMB.sub(rf"/{APPLE_SIZE}x{APPLE_SIZE}bb.\1", art)
    return None


def _short_side(path: Path) -> int | None:
    try:
        with open(path, "rb") as f:
            size = image_size(f.read(65536))
    except OSError:
        return None
    return min(size) if size else None


def hd_art(
    art_url: str,
    original: Path | None,
    artist: str,
    album: str,
    title: str,
    dest_dir: Path,
    apple: bool,
    fetch: Fetch = http_get,
) -> Path | None:
    """A cover at least HD_MIN_PX wide when one can be had, else None.

    Spotify covers come from their own CDN at 1500 px. Apple is asked only
    when `apple` is on and the player's cover is missing, unreadable or
    under HD_MIN_PX; network trouble of any kind returns None.
    """
    large = spotify_large(art_url)
    if large:
        path = fetch_art(large, dest_dir, fetch)
        if path is not None:
            return path
    if not apple:
        return None
    if original is not None and (_short_side(original) or 0) >= HD_MIN_PX:
        return None
    # without an album, browser videos may hide the artist in the title
    # ("Artist - Title (Official Video)" from a channel): try the same
    # variants as the lyrics lookup, each distinct query once
    pairs = [(title, artist)] if album.strip() else search_variants(title, artist)
    asked: set[str] = set()
    for t, a in pairs:
        url = apple_search_url(a, album, t)
        if url is None or url in asked:
            continue
        asked.add(url)
        try:
            body = json.loads(fetch(url, {}))
        except (ProviderError, ValueError, UnicodeDecodeError):
            return None  # the network or Apple is in trouble: stop asking
        results = body.get("results") if isinstance(body, dict) else None
        art = apple_pick(results if isinstance(results, list) else [], a, album, t)
        if art:
            return fetch_art(art, dest_dir, fetch)
    return None
