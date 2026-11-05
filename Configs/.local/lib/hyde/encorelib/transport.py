"""Player controls for the app window: time labels, seek and volume steps, keys."""

from __future__ import annotations

SEEK_STEP = 5.0  # seconds for Left/Right
VOLUME_STEP = 0.05

# key name (Gdk.keyval_name) -> action, on every page unless listed below
_KEYS = {
    "space": "play-pause",
    "Left": "seek-back",
    "Right": "seek-forward",
    "Up": "volume-up",
    "Down": "volume-down",
    "n": "next",
    "p": "previous",
    "l": "lyrics",
    "f": "fullscreen",
    "w": "stage",
    "F11": "fullscreen",
    "Escape": "back",
}
# actions that make no sense on a page
_NOT_ON = {"home": {"back"}, "full": {"lyrics"}, "stage": {"lyrics"}, "lyrics": set()}


def fmt_time(seconds: float) -> str:
    """m:ss, or h:mm:ss past an hour; never negative."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def seek_to(position: float, delta: float, length: float) -> float:
    """The seek target, kept inside the track (a stream with no length only stops at 0)."""
    target = max(0.0, position + delta)
    if length > 0:
        target = min(target, max(0.0, length - 1))
    return target


def step_volume(volume: float, delta: float) -> float:
    return round(min(1.0, max(0.0, volume + delta)), 2)


def key_action(key: str, ctrl: bool, page: str) -> str | None:
    """The action a key press asks for on a page (home, lyrics, stage, full), or None."""
    if ctrl:
        return "quit" if key in ("q", "Q") else None
    action = _KEYS.get(key if len(key) > 1 else key.lower())
    if action is None or action in _NOT_ON.get(page, set()):
        return None
    return action


def page_after(action: str, page: str, came_from: str) -> str | None:
    """The page a page-switching action leads to, or None when it switches nothing.

    `came_from` is the page Full screen was entered from: F leaves Full screen
    back to the Stage when that is where it started, else to Home.
    """
    if action == "back":
        return "home"
    if action == "stage":
        return "home" if page == "stage" else "stage"
    if action == "fullscreen":
        if page == "full":
            return "stage" if came_from == "stage" else "home"
        return "full"
    return None


ONCE_PER_PRESS = {"fullscreen", "stage", "back", "lyrics", "play-pause", "next", "previous"}


class HeldKeys:
    """Key auto-repeat: page switches and player commands act once per press
    (holding F must not bounce between Full screen and the window); seeking and
    volume keep repeating while the key is held."""

    def __init__(self) -> None:
        self.down: set[object] = set()

    def press(self, key: object, action: str) -> bool:
        """Whether this key-press event should act."""
        repeat = key in self.down
        self.down.add(key)
        return not (repeat and action in ONCE_PER_PRESS)

    def release(self, key: object) -> None:
        self.down.discard(key)
