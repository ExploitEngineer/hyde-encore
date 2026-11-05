"""The stage flag: which output the app's Stage or Full screen covers, and by whom.

`$XDG_RUNTIME_DIR/hyde/encore.stage` holds the output's connector (or "*"
while unknown) and the app's pid. The desktop overlay on that output hides
while the flag names a living app, so a crash that leaves the file behind
never keeps the desktop lyrics hidden. The flag is up only while the show is
really in sight: a window on another workspace or in the tray hides nothing.
"""

from __future__ import annotations

from collections.abc import Callable

SHOW_PAGES = ("stage", "full")
MIN_STAGE = (320, 240)  # the engine never sizes its type to less than this


def render(connector: str, pid: int) -> str:
    return f"{connector}\n{pid}\n"


def covers(text: str, mine: str, alive: Callable[[int], bool]) -> bool:
    """True when the flag names this overlay's output and its app still runs.

    `mine` is the overlay's connector; empty means it may sit on any output.
    """
    lines = text.splitlines()
    if len(lines) < 2:
        return False
    connector = lines[0].strip()
    try:
        pid = int(lines[1].strip())
    except ValueError:
        return False
    if not connector or not alive(pid):
        return False
    return connector == "*" or not mine or connector == mine


def wanted(page: str, mapped: bool, suspended: bool) -> bool:
    """Whether the window should hold the flag: a show page, on screen and awake."""
    return page in SHOW_PAGES and mapped and not suspended


def stage_size(width: int, height: int) -> tuple[int, int]:
    """The size the Stage engine lays out for: the page, never under MIN_STAGE."""
    return max(MIN_STAGE[0], width), max(MIN_STAGE[1], height)
