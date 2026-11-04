"""The idle field: soft album-colored light drifting while nothing plays.

Three large radial blobs in the scheme's colors wander on slow, unrelated
orbits over the window's dark base, drawn by the GPU as gradient nodes.
It ticks at most IDLE_FPS, and only while it is mapped and its window is
not suspended (another workspace, minimized), so it costs nothing unseen.
"""

from __future__ import annotations

import math
import time

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

IDLE_FPS = 8  # the blobs move a few px/s: 8 fps reads as continuous at about 2% of a core
# per blob: hue source, radius (share of the long side), orbit radii, periods (s), phase
BLOBS = (
    ("accent", 0.55, (0.22, 0.16), (41.0, 29.0), 0.0),
    ("accent2", 0.48, (0.26, 0.18), (53.0, 37.0), 2.1),
    ("highlight", 0.40, (0.18, 0.22), (47.0, 31.0), 4.2),
)
BASE = (0.094, 0.090, 0.102)


def _rgba(color: str, alpha: float) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.parse(f"#{color}")
    rgba.alpha = alpha
    return rgba


def blob_center(t: float, orbit: tuple[float, float], period: tuple[float, float], phase: float):
    """Where a blob sits at time t, as fractions of the width and height."""
    ax, ay = orbit
    px, py = period
    return (
        0.5 + ax * math.sin(2 * math.pi * t / px + phase),
        0.5 + ay * math.cos(2 * math.pi * t / py + phase * 1.7),
    )


class IdleField(Gtk.Widget):
    def __init__(self):
        super().__init__()
        self.colors = None
        self.timer = 0
        self.start = time.monotonic()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.connect("map", lambda *_: self._sync_timer())
        self.connect("unmap", lambda *_: self._sync_timer())
        self.window_handler = 0
        self.connect("realize", self._on_realize)

    def _on_realize(self, _widget) -> None:
        window = self.get_root()
        if isinstance(window, Gtk.Window) and not self.window_handler:
            self.window_handler = window.connect("notify::suspended", lambda *_: self._sync_timer())

    def set_colors(self, colors) -> None:
        self.colors = colors
        self.queue_draw()

    def _visible(self) -> bool:
        window = self.get_root()
        suspended = isinstance(window, Gtk.Window) and window.is_suspended()
        return self.get_mapped() and not suspended

    def _sync_timer(self) -> None:
        if self._visible() and not self.timer:
            self.timer = GLib.timeout_add(1000 // IDLE_FPS, self._tick)
        elif not self._visible() and self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _tick(self) -> bool:
        if not self._visible():
            self.timer = 0
            return False
        self.queue_draw()
        return True

    def do_snapshot(self, snapshot) -> None:
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        base = Gdk.RGBA()
        base.red, base.green, base.blue, base.alpha = (*BASE, 1.0)
        snapshot.append_color(base, Graphene.Rect().init(0, 0, w, h))
        if self.colors is None:
            return
        t = time.monotonic() - self.start
        side = max(w, h)
        for key, size, orbit, period, phase in BLOBS:
            fx, fy = blob_center(t, orbit, period, phase)
            radius = side * size
            color = getattr(self.colors, key)
            stops = []
            for offset, alpha in ((0.0, 0.34), (0.45, 0.14), (1.0, 0.0)):
                stop = Gsk.ColorStop()
                stop.offset = offset
                stop.color = _rgba(color, alpha)
                stops.append(stop)
            center = Graphene.Point().init(fx * w, fy * h)
            snapshot.append_radial_gradient(
                Graphene.Rect().init(0, 0, w, h), center, radius, radius, 0.0, 1.0, stops
            )
