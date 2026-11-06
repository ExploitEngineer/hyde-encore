"""The tray menu as a com.canonical.dbusmenu layout: pure data, no D-Bus.

The tray (encoregui/tray.py) turns this into variants; waybar and other
StatusNotifier hosts render it. Ids are stable so a host's click maps to an
action here.
"""

from __future__ import annotations

ACTIONS = {
    1: "open",
    2: "play-pause",
    3: "next",
    4: "desktop",
    5: "glow",
    7: "quit",
}


def _toggle(label: str, on: bool) -> dict:
    return {"label": label, "toggle-type": "checkmark", "toggle-state": 1 if on else 0}


def layout(desktop_on: bool, glow_on: bool, playing: bool) -> tuple:
    """The GetLayout tree: (id, properties, children) with one level of items."""
    items = [
        (1, {"label": "Open Encore"}, []),
        (2, {"label": "Pause" if playing else "Play"}, []),
        (3, {"label": "Next"}, []),
        (4, _toggle("Desktop lyrics", desktop_on), []),
        (5, _toggle("Glow", glow_on), []),
        (6, {"type": "separator"}, []),
        (7, {"label": "Quit"}, []),
    ]
    return (0, {"children-display": "submenu"}, items)
