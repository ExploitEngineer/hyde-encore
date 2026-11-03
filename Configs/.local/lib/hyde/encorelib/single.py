"""Single-instance pidfile helpers for the overlay process."""

from __future__ import annotations

import os
from pathlib import Path


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


def _write_own(path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(f"{os.getpid()}\n", encoding="utf-8")
    os.replace(tmp, path)


def claim(path: Path, marker: str = "encore") -> bool:
    """Claim the pidfile for this process; False when a live owner exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        owner = read_pid(path)
        if owner == os.getpid() or (owner is not None and pid_alive(owner, marker)):
            return False
        _write_own(path)
        return True
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{os.getpid()}\n")
    return True


def release(path: Path) -> None:
    path = Path(path)
    if read_pid(path) == os.getpid():
        path.unlink(missing_ok=True)
