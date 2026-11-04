"""The look and app settings, shared by the CLI, the app, the overlay and glow.

`$XDG_RUNTIME_DIR/hyde/encore.look` holds a small JSON object the user
changes live (style, font, size, colors, glow, full-screen background, app
switches). It layers on top of config.toml. Every process watches it, so a
change shows at once. Writers also keep a copy in
`$XDG_STATE_HOME/hyde/encore.look`, restored when the runtime file is
missing (after a reboot), so settings survive like HyDE's own state.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .config import EncoreConfig
from .stream import STYLES

MIN_SIZE, MAX_SIZE = 14, 72
GLOW_ANIMATIONS = ("music", "breathe", "static")
STAGE_BACKGROUNDS = ("art", "clear")
MAX_PLAYERS = 16
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _valid(key: str, value) -> bool:
    if key == "style":
        return value in STYLES
    if key == "font":
        return isinstance(value, str) and 0 < len(value) <= 128
    if key == "size":
        return (
            isinstance(value, int) and not isinstance(value, bool) and MIN_SIZE <= value <= MAX_SIZE
        )
    if key in (
        "color",
        "lyric_color",
        "highlight_color",
        "secondary_color",
        "glow_primary",
        "glow_secondary",
    ):
        return isinstance(value, str) and bool(_COLOR.match(value))
    if key == "glow_colors":
        return value in (1, 2) and not isinstance(value, bool)
    if key == "glow_animation":
        return value in GLOW_ANIMATIONS
    if key == "glow_thickness":
        return isinstance(value, int) and not isinstance(value, bool) and 40 <= value <= 220
    if key == "glow_intensity":
        return isinstance(value, int) and not isinstance(value, bool) and 10 <= value <= 100
    if key in (
        "next_line",
        "motion",
        "glow_override",
        "hd_covers",
        "autostart",
        "desktop_lyrics_on",
        "glow_on",
    ):
        return isinstance(value, bool)
    if key == "stage_bg":
        return value in STAGE_BACKGROUNDS
    if key == "players":  # empty follows every player
        return (
            isinstance(value, list)
            and len(value) <= MAX_PLAYERS
            and all(isinstance(v, str) and 0 < len(v) <= 64 for v in value)
        )
    if key == "lock_previous":  # the hyprlock layout to restore
        return isinstance(value, str) and 0 < len(value) <= 128
    if key == "glow_monitor":  # a connector name, e.g. "eDP-1"
        return isinstance(value, str) and 0 < len(value) <= 64
    return False


def read_look(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if _valid(k, v)}


def _write(path: Path, look: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(look, f)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


def update_look(path: Path, persist: Path | None = None, **changes) -> dict:
    """Merge validated changes into the look file; None removes a key.

    With `persist`, the merged look is kept there too, for the next boot.
    """
    look = read_look(path)
    for key, value in changes.items():
        if value is None:
            look.pop(key, None)
        elif _valid(key, value):
            look[key] = value
    _write(path, look)
    if persist is not None:
        _write(persist, look)
    return look


def restore_look(path: Path, persist: Path) -> bool:
    """Seed a missing runtime look from the kept copy; True when it did."""
    if Path(path).exists() or not Path(persist).exists():
        return False
    _write(path, read_look(persist))
    return True


def state_look_path(env: Mapping[str, str] | None = None) -> Path:
    """Where the look is kept across reboots: $XDG_STATE_HOME/hyde/encore.look."""
    env = os.environ if env is None else env
    home = Path(env.get("HOME") or Path.home())
    state = Path(env.get("XDG_STATE_HOME") or home / ".local" / "state")
    return state / "hyde" / "encore.look"


def effective_autostart(cfg: EncoreConfig, look: dict) -> bool:
    """Start the engine at login: the app's switch when set, else config's enable."""
    return bool(look.get("autostart", cfg.enable))


def effective_players(cfg: EncoreConfig, look: dict) -> tuple[str, ...]:
    """The players to follow: the app's list when set (empty: every player), else config."""
    if "players" in look:
        return tuple(look["players"])
    return cfg.players


def effective(cfg: EncoreConfig, look: dict) -> tuple[str, str, int, str, bool, bool]:
    """(style, font, size, color, next_line, motion) after overrides."""
    return (
        look.get("style", cfg.overlay_style),
        look.get("font", cfg.overlay_font),
        look.get("size", cfg.overlay_size),
        look.get("color", cfg.overlay_color),
        look.get("next_line", cfg.overlay_next_line),
        look.get("motion", True),
    )
