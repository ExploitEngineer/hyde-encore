"""Single-instance helpers for the overlay, built on flock.

The pidfile carries an exclusive BSD lock for the owner's lifetime, so two
racing claims can never both win, and a stale file from a crash is simply
a file nobody holds locked.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO

_held: dict[str, IO[str]] = {}


def read_pid(path: Path) -> int | None:
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def pid_alive(pid: int, marker: str = "encore") -> bool:
    """True when `pid` is a live process whose command line mentions `marker`.

    The marker guards against a recycled pid belonging to something else.
    """
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError):
        return False
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
    except OSError:
        return False
    return marker.encode() in cmdline


def claim(path: Path) -> bool:
    """Take the pidfile lock for this process; False when someone holds it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")  # noqa: SIM115 (held for process lifetime)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    _held[str(path)] = handle
    return True


def release(path: Path) -> None:
    handle = _held.pop(str(path), None)
    if handle is None:
        return
    Path(path).unlink(missing_ok=True)
    handle.close()  # closing drops the lock after the file is gone
