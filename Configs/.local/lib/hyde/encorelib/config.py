"""encore settings from HyDE's config.toml.

HyDE's config.lua flattens ~/.config/hyde/config.toml into shell exports in
$XDG_STATE_HOME/hyde/config, e.g. [encore.lyrics] spicy_key becomes
ENCORE_LYRICS_SPICY_KEY. Process env wins over that file, which wins over
the defaults below.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .stream import STYLES

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class EncoreConfig:
    enable: bool = False
    players: tuple[str, ...] = ()
    lyrics_dirs: tuple[Path, ...] = ()
    spicy_key: str = ""
    lrclib: bool = True
    hyprlock_color: str = ""
    hyprlock_dim: str = ""
    overlay_enable: bool = False
    overlay_position: str = "bottom"
    overlay_margin: int = 120
    overlay_font: str = "SF Pro Display, Inter, Cantarell, sans-serif"
    overlay_size: int = 30
    overlay_next_line: bool = True
    overlay_color: str = ""
    overlay_monitor: str = ""
    overlay_style: str = "line"


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _as_list(value: str) -> tuple[str, ...]:
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        items = shlex.split(value[1:-1])
    else:
        items = _unquote(value).split(",")
    return tuple(i.strip() for i in items if i.strip())


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    v = _unquote(value).lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(_unquote(value))
    except ValueError:
        return default


def _as_choice(value: str | None, allowed: tuple[str, ...], default: str) -> str:
    v = _unquote(value or "").lower()
    return v if v in allowed else default


def _default_lyrics_dirs(env: Mapping[str, str]) -> tuple[Path, ...]:
    home = Path(env.get("HOME", str(Path.home())))
    data = Path(env.get("XDG_DATA_HOME") or home / ".local" / "share")
    return (data / "lyrics", home / "Music" / "Lyrics")


def _lyrics_dirs(value: str | None, env: Mapping[str, str]) -> tuple[Path, ...]:
    """Configured folders (shell array or colon list) first, then the defaults."""
    value = (value or "").strip()
    if value.startswith("("):
        extra = _as_list(value)
    else:
        extra = tuple(p for p in _unquote(value).split(":") if p)
    return tuple(Path(p) for p in extra) + _default_lyrics_dirs(env)


def default_env_file(env: Mapping[str, str]) -> Path:
    home = Path(env.get("HOME", str(Path.home())))
    state = Path(env.get("XDG_STATE_HOME") or home / ".local" / "state")
    return state / "hyde" / "config"


def load_config(env: Mapping[str, str] | None = None, env_file: Path | None = None) -> EncoreConfig:
    env = os.environ if env is None else env
    merged: dict[str, str] = read_env_file(env_file or default_env_file(env))
    merged.update(env)

    def get(key: str) -> str | None:
        return merged.get(key)

    dirs = get("ENCORE_LYRICS_DIRS")
    return EncoreConfig(
        enable=_as_bool(get("ENCORE_ENABLE"), False),
        players=_as_list(get("ENCORE_PLAYERS") or ""),
        lyrics_dirs=_lyrics_dirs(dirs, merged),
        spicy_key=_unquote(get("ENCORE_LYRICS_SPICY_KEY") or get("SPICY_LYRICS_SECRET_KEY") or ""),
        lrclib=_as_bool(get("ENCORE_LYRICS_LRCLIB"), True),
        hyprlock_color=_unquote(get("ENCORE_HYPRLOCK_COLOR") or ""),
        hyprlock_dim=_unquote(get("ENCORE_HYPRLOCK_DIM") or ""),
        overlay_enable=_as_bool(get("ENCORE_OVERLAY_ENABLE"), False),
        overlay_position=_as_choice(
            get("ENCORE_OVERLAY_POSITION"), ("top", "center", "bottom"), "bottom"
        ),
        overlay_margin=_as_int(get("ENCORE_OVERLAY_MARGIN"), 120),
        overlay_font=_unquote(get("ENCORE_OVERLAY_FONT") or "")
        or "SF Pro Display, Inter, Cantarell, sans-serif",
        overlay_size=_as_int(get("ENCORE_OVERLAY_SIZE"), 30),
        overlay_next_line=_as_bool(get("ENCORE_OVERLAY_NEXT_LINE"), True),
        overlay_color=_unquote(get("ENCORE_OVERLAY_COLOR") or ""),
        overlay_monitor=_unquote(get("ENCORE_OVERLAY_MONITOR") or ""),
        overlay_style=_as_choice(get("ENCORE_OVERLAY_STYLE"), STYLES, "line"),
    )
