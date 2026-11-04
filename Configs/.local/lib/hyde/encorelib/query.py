"""Search variants for lyric lookups.

Players report titles the way their store or uploader wrote them:
"Stay (feat. Justin Bieber)", "Song - Remastered 2011", or, in a browser,
"The Weeknd - Blinding Lights (Official Video)" by the channel
"TheWeekndVEVO". Lyric databases index the plain song, so after the
exact query we retry with the qualifiers stripped and the primary artist,
and split an "Artist - Title" video title. A wrong match is still caught
by the caller's duration check.
"""

from __future__ import annotations

import re

MAX_SEARCHES = 3

_QUALIFIER = (
    r"(?:feat\.?|ft\.?|featuring|with|official|video|audio|lyrics?|visuali[sz]er"
    r"|remaster(?:ed)?|live|explicit|clean|hd|hq|4k|radio edit|version)"
)
# A dash suffix is stripped only when a release qualifier opens it ("- Remastered
# 2011", "- 2011 Remaster", "- Live at Wembley"). Featuring words are left out:
# "Alicia Keys - With You" is an artist and a song.
_DASH_QUALIFIER = (
    r"(?:official|video|audio|lyrics?|visuali[sz]er|remaster(?:ed)?|live|explicit|clean"
    r"|hd|hq|4k|radio edit|version)"
)
_DASH = r"\s+[-\N{EN DASH}]\s+"
_BRACKETED = re.compile(
    r"\s*[\(\[][^\)\]]*(?<!\w)" + _QUALIFIER + r"(?!\w)[^\)\]]*[\)\]]", re.IGNORECASE
)
_DASH_SUFFIX = re.compile(_DASH + r"(?:\d{4}\s+)?" + _DASH_QUALIFIER + r"(?!\w).*$", re.IGNORECASE)
_BARE_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s.*$", re.IGNORECASE)
_ARTIST_SPLIT = re.compile(
    r"\s*(?:,|;|\s&\s|\sx\s|\sfeat\.?\s|\sft\.?\s|\sfeaturing\s|\swith\s)\s*", re.IGNORECASE
)
_TOPIC = re.compile(r"\s+-\s+Topic$", re.IGNORECASE)
_ARTIST_TITLE = re.compile(r"^(.+?)" + _DASH + r"(.+)$")


def _strip_brackets(title: str) -> str:
    return " ".join(_BRACKETED.sub("", title).split())


def clean_title(title: str) -> str:
    """The title without featuring credits and release qualifiers."""
    cleaned = _DASH_SUFFIX.sub("", _strip_brackets(title))
    cleaned = _BARE_FEAT.sub("", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned or title.strip()


def primary_artist(artist: str) -> str:
    """The first credited artist, without YouTube's " - Topic" suffix."""
    first = _ARTIST_SPLIT.split(artist.strip(), maxsplit=1)[0]
    return _TOPIC.sub("", first).strip()


def search_variants(title: str, artist: str) -> list[tuple[str, str]]:
    """(title, artist) queries to try in order, most literal first."""
    variants: list[tuple[str, str]] = []

    def add(t: str, a: str) -> None:
        pair = (t.strip(), a.strip())
        if pair[0] and pair not in variants:
            variants.append(pair)

    add(title, artist)
    add(clean_title(title), primary_artist(artist))
    # split before the dash-suffix strip: "Oasis - Live Forever" is a song
    split = _ARTIST_TITLE.match(_strip_brackets(title))
    if split:
        add(clean_title(split.group(2)), primary_artist(split.group(1)))
    return variants[:MAX_SEARCHES]
