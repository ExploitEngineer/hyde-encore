"""Frosted glass: a panel that shows a blurred crop of what sits behind it.

The backdrop renders its blur once per cover (CoverBackdrop.blurred_texture);
a panel draws the part of that texture under its own bounds, a dark tint
and a light edge on top, then its content. A paint costs one clipped
texture node, so the bars stay cheap on a driver where offscreens are not.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Graphene, Gtk

from encoregui.scene import Image, Scene, rounded

RADIUS = 22
TINT = (0.07, 0.06, 0.09)
TINT_ALPHA = 0.5
EDGE_ALPHA = 0.14


class GlassPanel(Gtk.Widget):
    """A bar on frosted glass: measures as its content, draws the glass under it.

    `set_backdrop(texture_fn, behind)` names what is behind: a function
    returning the blurred texture, and the widget it covers.
    """

    def __init__(self, child: Gtk.Widget):
        super().__init__()
        self.set_layout_manager(Gtk.BinLayout())
        self.texture_fn: Callable[[], Gdk.Texture | None] = lambda: None
        self.behind: Gtk.Widget | None = None
        self.child = child
        child.set_parent(self)
        self.add_css_class("glass")

    def do_dispose(self) -> None:
        if self.child is not None:
            self.child.unparent()
            self.child = None

    def set_backdrop(
        self, texture_fn: Callable[[], Gdk.Texture | None], behind: Gtk.Widget
    ) -> None:
        self.texture_fn = texture_fn
        self.behind = behind
        self.queue_draw()

    def refresh(self) -> None:
        self.queue_draw()

    def do_snapshot(self, snapshot) -> None:
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        sc = Scene(snapshot)
        texture, behind = self.texture_fn(), self.behind
        with sc.rounded_clip(0, 0, w, h, RADIUS):
            if texture is not None and behind is not None:
                ok, bounds = self.compute_bounds(behind)
                if ok:
                    bw, bh = behind.get_width(), behind.get_height()
                    sc.cover(Image(texture, bw, bh), -bounds.get_x(), -bounds.get_y(), bw, bh)
            sc.rect(0, 0, w, h, TINT, TINT_ALPHA)
        edge = Gdk.RGBA()
        edge.red = edge.green = edge.blue = 1.0
        edge.alpha = EDGE_ALPHA
        clear = Gdk.RGBA()
        clear.alpha = 0.0
        snapshot.append_border(
            rounded(0.5, 0.5, w - 1, h - 1, RADIUS),
            [1.0, 0.0, 0.0, 0.0],
            [edge, clear, clear, clear],
        )
        if self.child is not None:
            self.snapshot_child(self.child, snapshot)


def rect(x: float, y: float, w: float, h: float) -> Graphene.Rect:
    return Graphene.Rect().init(x, y, w, h)
