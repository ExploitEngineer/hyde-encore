"""What the app shows for a daemon state: idle, waiting, no lyrics, plain or synced."""

from __future__ import annotations

from .lyricview import live_position

LYRICS_GRACE = 2.0  # without a lookup field: lyrics may still be on their way
KNOWN_MUSIC_APPS = ("spotify.desktop", "spotify-launcher.desktop", "com.spotify.Client.desktop")
REASON_NONE = "No synced lyrics found for this song."
REASON_ERROR = "Lyrics lookup failed. Check the connection."


def screen_state(state: dict | None, now: float) -> str:
    """One of idle, waiting, no_lyrics, plain, lyrics."""
    state = state or {}
    if state.get("status") not in ("playing", "paused") or not state.get("track"):
        return "idle"
    lyrics = state.get("lyrics")
    if lyrics is None:
        lookup = state.get("lookup")
        if lookup == "pending":
            return "waiting"
        if lookup is None and live_position(state, now) < LYRICS_GRACE:
            return "waiting"
        return "no_lyrics"
    if not any((line.get("text") or "").strip() for line in lyrics.get("lines") or []):
        return "no_lyrics"
    return "plain" if lyrics.get("sync") == "none" else "lyrics"


def lookup_reason(entries: list[dict], artist: str, title: str) -> str:
    """Why a song has no lyrics, from the newest matching lookup in the journal."""
    for entry in reversed(entries):
        if entry.get("artist") == artist and entry.get("title") == title:
            if str(entry.get("result", "")).startswith("error"):
                return REASON_ERROR
            return REASON_NONE
    return REASON_NONE


def pick_music_apps(apps: list[tuple[str, str, str]], limit: int = 3) -> list[str]:
    """Desktop ids of music apps to offer when nothing plays: known ones first."""
    ids = [app_id for app_id, _name, _cats in apps]
    chosen = [known for known in KNOWN_MUSIC_APPS if known in ids]
    for app_id, _name, categories in apps:
        cats = {c for c in categories.split(";") if c}
        if app_id in chosen or app_id.startswith("org.hyde.encore"):
            continue
        if "Player" in cats and cats & {"Audio", "AudioVideo"}:
            chosen.append(app_id)
    return chosen[:limit]


def field_shows(background: str, has_cover: bool) -> bool:
    """Whether the album field shows under Full screen: under a clear background,
    and under a cover background when the track has no cover (never a black window)."""
    return background == "clear" or not has_cover
