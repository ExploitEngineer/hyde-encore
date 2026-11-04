"""The lock screen switch: Encore's hyprlock layout on or off.

HyDE keeps the chosen hyprlock layout as HYPRLOCK_LAYOUT in its staterc
(hyprlock.sh --select writes it with set_conf). Turning Encore's lyrics on
selects the Encore layout after remembering the previous one in the kept
look, so turning them off restores exactly what the user had.
"""

from __future__ import annotations

import re

ENCORE_LAYOUT = "Encore"
DEFAULT_LAYOUT = "HyDE"
_LINE = re.compile(r"^HYPRLOCK_LAYOUT=(.*)$", re.MULTILINE)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_layout(staterc: str) -> str | None:
    """The hyprlock layout named in a staterc text, or None."""
    match = _LINE.search(staterc)
    return _unquote(match.group(1)) if match else None


def with_layout(staterc: str, name: str) -> str:
    """The staterc text with HYPRLOCK_LAYOUT set to name (the way set_conf writes it)."""
    line = f'HYPRLOCK_LAYOUT="{name}"'
    if _LINE.search(staterc):
        return _LINE.sub(line, staterc, count=1)
    if staterc and not staterc.endswith("\n"):
        staterc += "\n"
    return f"{staterc}{line}\n"
