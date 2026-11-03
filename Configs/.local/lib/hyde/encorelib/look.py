"""Runtime look overrides, shared by the CLI, the menu and the overlay.

`$XDG_RUNTIME_DIR/hyde/encore.look` holds a small JSON object the user
changes live (style, font, size, color, next_line). It layers on top of
config.toml and resets on reboot.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .config import EncoreConfig
from .stream import STYLES

MIN_SIZE, MAX_SIZE = 14, 72
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
    if key == "color":
        return isinstance(value, str) and bool(_COLOR.match(value))
    if key in ("next_line", "motion"):
        return isinstance(value, bool)
    return False


def read_look(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if _valid(k, v)}


def update_look(path: Path, **changes) -> dict:
    """Merge validated changes into the look file; None removes a key."""
    look = read_look(path)
    for key, value in changes.items():
        if value is None:
            look.pop(key, None)
        elif _valid(key, value):
            look[key] = value
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
    return look


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
