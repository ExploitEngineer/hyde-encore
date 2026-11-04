"""Pure view model for the lyrics overlay.

Turns one daemon state dict (see protocol.build_state) plus the current
monotonic time into exactly what the overlay should show: per-word fill,
whether a frame clock is needed, and when the next visual change is due.
"""

from __future__ import annotations

from dataclasses import dataclass

from .timing import GAP_HOLD_SECONDS

GAP_HIDE_SECONDS = GAP_HOLD_SECONDS
FILL_FPS_HINT = 60


@dataclass(frozen=True)
class View:
    visible: bool
    line_key: str
    text: str
    words: tuple[tuple[str, float], ...]
    next_text: str
    animating: bool
    wake_in: float | None


HIDDEN = View(False, "", "", (), "", False, None)


def live_position(state: dict, now: float) -> float:
    """The playback position right now, extrapolated from the state's anchor."""
    position = state["position"]
    if state.get("status") == "playing":
        return position + (now - state["ts"]) * state.get("rate", 1.0)
    return position


def _fill(position: float, start: float, end: float) -> float:
    if end <= start:
        return 1.0 if position >= start else 0.0
    return min(1.0, max(0.0, (position - start) / (end - start)))


def build_view(state: dict | None, now: float) -> View:
    if not state or state.get("status") == "stopped":
        return HIDDEN
    lyrics, line, track = state.get("lyrics"), state.get("line"), state.get("track")
    if not lyrics or lyrics.get("sync") == "none" or not line or not track:
        return HIDDEN
    words = line.get("words") or []
    if not words:
        return HIDDEN

    position = live_position(state, now)
    rate = state.get("rate", 1.0) or 1.0
    playing = state.get("status") == "playing"

    last_end = words[-1]["end"]
    hide_at = last_end + GAP_HIDE_SECONDS
    if playing and position > hide_at:
        return HIDDEN

    fills = tuple((w["text"], _fill(position, w["start"], w["end"])) for w in words)
    animating = playing and any(w["start"] <= position < w["end"] for w in words)

    wake_in = None
    if playing and not animating:
        upcoming = [w["start"] for w in words if w["start"] > position]
        target = upcoming[0] if upcoming else hide_at
        wake_in = max(0.0, (target - position) / rate)

    return View(
        visible=True,
        line_key=f"{track['key']}:{line['index']}",
        text=line.get("text") or " ".join(w["text"] for w in words),
        words=fills,
        next_text=state.get("next") or "",
        animating=animating,
        wake_in=wake_in,
    )


def lyric_rows(lines: list[dict]) -> list[str]:
    """Texts of the whole-song list: every line that is not blank."""
    return [ln["text"] for ln in lines if (ln.get("text") or "").strip()]


def lyric_row(state: dict) -> int:
    """Row of lyric_rows() to highlight, -1 for none.

    The live line wins; in a gap the row of the line the gap follows stays
    lit, so the list keeps its place through instrumentals.
    """
    lines = (state.get("lyrics") or {}).get("lines") or []
    line = state.get("line")
    index = line["index"] if line else (state.get("gap") or {}).get("after", -1)
    if not 0 <= index < len(lines):
        return -1
    return len(lyric_rows(lines[: index + 1])) - 1


def should_transition(old_key: str, new_key: str) -> bool:
    """A slide cross-fade only makes sense between lines of the same track.

    Across tracks the colors and timing belong to different songs, so the
    overlay cuts instead of fading the old song into the new one.
    """
    if not old_key or not new_key or old_key == new_key:
        return False
    return old_key.rsplit(":", 1)[0] == new_key.rsplit(":", 1)[0]


def current_word_index(view: View) -> int:
    """Index of the word being (or last) sung, -1 before the first word."""
    index = -1
    for i, (_, fill) in enumerate(view.words):
        if fill > 0.0:
            index = i
    return index


def next_word_boundary(state: dict | None, now: float) -> float | None:
    """Wall seconds until the next word start or end, while playing."""
    if not state or state.get("status") != "playing":
        return None
    line = state.get("line") or {}
    words = line.get("words") or []
    position = live_position(state, now)
    rate = state.get("rate", 1.0) or 1.0
    # only word STARTS change what is on screen; ends inside a line do not,
    # except the LAST end, which starts the gap-hide countdown
    boundaries = [w["start"] for w in words if w["start"] > position]
    if boundaries:
        return (min(boundaries) - position) / rate
    if words:
        hide_at = words[-1]["end"] + GAP_HIDE_SECONDS
        if position < hide_at:
            return (hide_at - position) / rate
    return None
