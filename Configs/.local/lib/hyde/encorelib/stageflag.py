"""The full-screen flag: which output the app's Full screen covers, and by whom.

`$XDG_RUNTIME_DIR/hyde/encore.stage` holds the output's connector (or "*"
while unknown) and the app's pid. The desktop overlay on that output hides
while the flag names a living app, so a crash that leaves the file behind
never keeps the desktop lyrics hidden.
"""

from __future__ import annotations

from collections.abc import Callable


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
