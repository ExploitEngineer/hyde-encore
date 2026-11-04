"""Find and start the encore service.

Every surface (overlay, glow, player, hyprlock line) is empty without the
daemon, so the commands that open one start it on demand. It runs as the
same systemd unit HyDE's autostart would create, so a later login start
or a second click finds it already running.
"""

from __future__ import annotations

import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

CONNECT_TIMEOUT = 0.5
START_TIMEOUT = 10.0


def daemon_unit(desktop: str) -> str:
    """The unit name HyDE's `hyde-shell app -u hyde-$XDG_SESSION_DESKTOP-...` uses."""
    return f"hyde-{desktop or 'Hyprland'}-encore.service"


def daemon_start_command(desktop: str) -> list[str]:
    """Start the daemon as a HyDE service unit (not gated on [encore] enable)."""
    return [
        "hyde-shell",
        "app",
        "-u",
        daemon_unit(desktop),
        "-t",
        "service",
        "--",
        "encore.sh",
        "daemon",
    ]


def daemon_alive(socket_path: Path) -> bool:
    """True when a daemon accepts connections on its state socket."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT)
    try:
        sock.connect(str(socket_path))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def ensure_daemon(
    socket_path: Path,
    desktop: str,
    run: Callable = subprocess.run,
    fallback: Callable[[], None] | None = None,
) -> str:
    """Start the daemon unless one is answering; returns running, started or fallback.

    The HyDE unit comes first; when hyde-shell is missing, hangs or the unit
    cannot start (e.g. a failed unit of that name is still loaded), fallback
    runs the daemon some other way.
    """
    if daemon_alive(socket_path):
        return "running"
    # HyDE's app2unit starts units with --same-dir; a working directory that
    # later disappears makes every restart fail, so always start from home
    quiet = {
        "check": False,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "timeout": START_TIMEOUT,
        "cwd": Path.home(),
    }
    try:
        # a failed unit of the same name blocks a new transient one
        run(["systemctl", "--user", "reset-failed", daemon_unit(desktop)], **quiet)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        if run(daemon_start_command(desktop), **quiet).returncode == 0:
            return "started"
    except (OSError, subprocess.TimeoutExpired):
        pass
    if fallback is not None:
        fallback()
    return "fallback"
