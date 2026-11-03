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


def _default_lyrics_dirs(env: Mapping[str, str]) -> tuple[Path, ...]:
    home = Path(env.get("HOME", str(Path.home())))
    data = Path(env.get("XDG_DATA_HOME") or home / ".local" / "share")
    return (data / "lyrics", home / "Music" / "Lyrics")


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
        lyrics_dirs=(
            tuple(Path(p) for p in _unquote(dirs).split(":") if p)
            if dirs
            else _default_lyrics_dirs(merged)
        ),
        spicy_key=_unquote(get("ENCORE_LYRICS_SPICY_KEY") or get("SPICY_LYRICS_SECRET_KEY") or ""),
        lrclib=_as_bool(get("ENCORE_LYRICS_LRCLIB"), True),
        hyprlock_color=_unquote(get("ENCORE_HYPRLOCK_COLOR") or ""),
        hyprlock_dim=_unquote(get("ENCORE_HYPRLOCK_DIM") or ""),
    )
