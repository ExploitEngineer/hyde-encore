"""What closing the app window does."""

from __future__ import annotations


def close_action(desktop_on: bool, glow_on: bool) -> str:
    """ "hide" keeps Encore in the tray while desktop lyrics or glow run; else "quit"."""
    return "hide" if desktop_on or glow_on else "quit"
