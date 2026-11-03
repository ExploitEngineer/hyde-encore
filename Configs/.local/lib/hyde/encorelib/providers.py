"""Lyrics providers: local .lrc files, LRCLIB and the Spicy Lyrics API.

Only sources with clean terms are used. Musixmatch is deliberately absent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlencode, urlparse

from .config import EncoreConfig
from .lrc import parse_lrc
from .model import Line, Lyrics, Word

log = logging.getLogger("encore")

USER_AGENT = "hyde-encore (https://github.com/ExploitEngineer/hyde-encore)"
HTTP_TIMEOUT = 5.0
LRCLIB_URL = "https://lrclib.net/api"
SPICY_URL = "https://api.spicylyrics.org/v1/lyrics"
DURATION_TOLERANCE = 2.0
# LRCLIB holds junk uploads such as a single "[00:00.00]probe" line.
MIN_SYNCED_LINES = 4

Fetch = Callable[[str, dict[str, str]], bytes]

_FEAT = re.compile(r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s[^\)\]]*[\)\]]", re.IGNORECASE)
_SPOTIFY_ID = re.compile(r"(?:/com/spotify/track/|spotify:track:)([A-Za-z0-9]{22})")
_RANK = {"word": 2, "line": 1, "none": 0}


class ProviderError(Exception):
    """A provider could not answer (network, HTTP or payload error)."""


class NotFound(ProviderError):
    """The provider answered, but has no lyrics for this track."""


@dataclass(frozen=True)
class TrackInfo:
    title: str
    artist: str
    album: str
    length: float
    url: str
    trackid: str
    player: str


def _normalize(text: str) -> str:
    return " ".join(_FEAT.sub("", text).lower().split())


def track_key(t: TrackInfo) -> str:
    raw = f"{_normalize(t.artist)}|{_normalize(t.title)}|{round(t.length)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def http_get(url: str, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound(url) from e
        raise ProviderError(f"HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError(f"{url}: {e}") from e


def _json(data: bytes):
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as e:
        raise ProviderError(f"bad JSON: {e}") from e


def _read_lrc(path: Path) -> Lyrics | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_lrc(text, source="local")


def local_lrc(t: TrackInfo, search_dirs: Iterable[Path]) -> Lyrics | None:
    if t.url.startswith("file://"):
        media = Path(unquote(urlparse(t.url).path))
        sibling = media.with_suffix(".lrc")
        if sibling.is_file():
            return _read_lrc(sibling)
    name = f"{t.artist} - {t.title}.lrc".replace("/", "_")
    for folder in search_dirs:
        candidate = Path(folder) / name
        if candidate.is_file():
            return _read_lrc(candidate)
    return None


def _from_lrclib(record: dict) -> Lyrics | None:
    """Lyrics from one LRCLIB record, or None when it is missing or implausible."""
    if record.get("instrumental"):
        return Lyrics((), "none", "lrclib")
    if record.get("syncedLyrics"):
        lyr = parse_lrc(record["syncedLyrics"], source="lrclib")
        if sum(1 for ln in lyr.lines if ln.text) >= MIN_SYNCED_LINES:
            return lyr
        return None
    if record.get("plainLyrics"):
        return parse_lrc(record["plainLyrics"], source="lrclib")
    return None


def lrclib(t: TrackInfo, fetch: Fetch = http_get) -> Lyrics | None:
    if t.album and t.length > 0:
        query = urlencode(
            {
                "artist_name": t.artist,
                "track_name": t.title,
                "album_name": t.album,
                "duration": round(t.length),
            }
        )
        try:
            found = _from_lrclib(_json(fetch(f"{LRCLIB_URL}/get?{query}", {})))
        except NotFound:
            found = None
        if found is not None:
            return found
    query = urlencode({"track_name": t.title, "artist_name": t.artist})
    try:
        results = _json(fetch(f"{LRCLIB_URL}/search?{query}", {}))
    except NotFound:
        return None
    for record in results if isinstance(results, list) else []:
        duration = record.get("duration") or 0
        if t.length <= 0 or abs(duration - t.length) <= DURATION_TOLERANCE:
            found = _from_lrclib(record)
            if found is not None:
                return found
    return None


def _spicy_credit(body: dict) -> str | None:
    attribution = body.get("UploadAttribution")
    if body.get("source") != "spicy_lyrics" or not attribution:
        return None
    uploader = attribution.get("Uploader", {}).get("username", "unknown")
    maker = attribution.get("Maker", {}).get("username")
    if maker:
        return f"Lyrics by {uploader}, synced by {maker} on Spicy Lyrics"
    return f"Lyrics by {uploader} on Spicy Lyrics"


def _syllables_to_words(syllables: list[dict]) -> tuple[Word, ...]:
    words: list[Word] = []
    text, start, end, joining = "", 0.0, 0.0, False
    for s in syllables:
        if not joining:
            text, start = "", float(s.get("StartTime", 0.0))
        text += s.get("Text", "")
        end = float(s.get("EndTime", start))
        joining = bool(s.get("IsPartOfWord"))
        if not joining and text.strip():
            words.append(Word(text.strip(), start, end))
    if joining and text.strip():
        words.append(Word(text.strip(), start, end))
    return tuple(words)


def _close_lines(spans: list[tuple[float, float, str, tuple[Word, ...]]]) -> tuple[Line, ...]:
    """Each line ends where the next begins, matching LRC semantics."""
    lines = []
    for i, (start, end, text, words) in enumerate(spans):
        stop = spans[i + 1][0] if i + 1 < len(spans) else end
        lines.append(Line(start, stop, text, words))
    return tuple(lines)


def spicy(t: TrackInfo, key: str, fetch: Fetch = http_get) -> Lyrics | None:
    match = _SPOTIFY_ID.search(t.trackid or "")
    if t.player != "spotify" or not key or not match:
        return None
    try:
        data = _json(fetch(f"{SPICY_URL}/{match.group(1)}", {"Authorization": f"Bearer {key}"}))
    except NotFound:
        return None
    body = data.get("Body", data) if isinstance(data, dict) else {}
    kind = body.get("Type")
    source = body.get("source", "spicy")
    credit = _spicy_credit(body)
    if kind == "Syllable":
        spans = []
        for item in body.get("Content", []):
            lead = item.get("Lead", {})
            words = _syllables_to_words(lead.get("Syllables", []))
            start = float(lead.get("StartTime", words[0].start if words else 0.0))
            end = float(lead.get("EndTime", words[-1].end if words else start))
            spans.append((start, end, " ".join(w.text for w in words), words))
        return Lyrics(_close_lines(spans), "word", source, credit)
    if kind == "Line":
        spans = [
            (float(i.get("StartTime", 0.0)), float(i.get("EndTime", 0.0)), i.get("Text", ""), ())
            for i in body.get("Content", [])
        ]
        return Lyrics(_close_lines(spans), "line", source, credit)
    if kind == "Static":
        lines = tuple(Line(0.0, 0.0, i.get("Text", "")) for i in body.get("Lines", []))
        return Lyrics(lines, "none", source, credit)
    raise ProviderError(f"unknown Spicy lyrics type {kind!r}")


def _better(candidate: Lyrics | None, best: Lyrics | None) -> bool:
    if candidate is None:
        return False
    return best is None or _RANK[candidate.sync] > _RANK[best.sync]


def find_lyrics(t: TrackInfo, cfg: EncoreConfig, fetch: Fetch = http_get) -> Lyrics | None:
    best = local_lrc(t, cfg.lyrics_dirs)
    if best is None and cfg.lrclib:
        try:
            best = lrclib(t, fetch)
        except ProviderError as e:
            log.warning("lrclib failed: %s", e)
    if best is not None and best.sync == "word":
        return best
    if cfg.spicy_key:
        try:
            candidate = spicy(t, cfg.spicy_key, fetch)
        except ProviderError as e:
            log.warning("spicy lyrics failed: %s", e)
            candidate = None
        if _better(candidate, best):
            best = candidate
    return best
