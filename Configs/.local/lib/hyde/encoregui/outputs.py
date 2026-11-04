"""Put encore's layer-shell windows on a chosen output."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gtk
from gi.repository import Gtk4LayerShell as LayerShell


def find_monitor(display: Gdk.Display, connector: str) -> Gdk.Monitor | None:
    """The monitor whose connector (e.g. "eDP-1") matches, or None."""
    if not connector:
        return None
    monitors = display.get_monitors()
    for i in range(monitors.get_n_items()):
        monitor = monitors.get_item(i)
        if monitor.get_connector() == connector:
            return monitor
    return None


def place_on(window: Gtk.Window, connector: str) -> Gdk.Monitor | None:
    """Pin a layer-shell window to the named output; empty leaves the compositor's choice."""
    monitor = find_monitor(window.get_display(), connector)
    if monitor is not None:
        LayerShell.set_monitor(window, monitor)
    return monitor
