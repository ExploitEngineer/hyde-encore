"""A small drawing API over Gtk.Snapshot, so the GPU composes every frame.

Text is still rasterised by cairo and Pango, once, into images; frames only
place those images with transforms, opacity, clips and masks. GSK turns that
into render nodes the GPU scales and blends, so a sliding 200 px word costs
the CPU almost nothing (DECISIONS #27).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import cairo
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk


@dataclass(frozen=True)
class Image:
    """A GPU texture plus its logical size (device pixels may be larger)."""

    texture: Gdk.Texture
    w: float
    h: float

    @classmethod
    def from_surface(cls, surface: cairo.ImageSurface, w: float, h: float) -> Image:
        surface.flush()
        data = GLib.Bytes.new(bytes(surface.get_data()))
        texture = Gdk.MemoryTexture.new(
            surface.get_width(),
            surface.get_height(),
            Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
            data,
            surface.get_stride(),
        )
        return cls(texture, w, h)

    @classmethod
    def from_file(cls, path: str) -> Image | None:
        try:
            texture = Gdk.Texture.new_from_filename(path)
        except GLib.Error:
            return None
        return cls(texture, texture.get_width(), texture.get_height())


def _rect(x: float, y: float, w: float, h: float) -> Graphene.Rect:
    return Graphene.Rect().init(x, y, w, h)


def rounded(x: float, y: float, w: float, h: float, r: float) -> Gsk.RoundedRect:
    """A rounded rect for snapshot calls.

    Initialize in place and keep the instance: PyGObject's return value of
    Gsk.RoundedRect().init_from_rect() is not the initialized struct, so
    clips built from it came out empty and shadows landed at the origin.
    """
    rect = Gsk.RoundedRect()
    rect.init_from_rect(_rect(x, y, w, h), r)
    return rect


def _rgba(rgb, alpha: float) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red, color.green, color.blue, color.alpha = rgb[0], rgb[1], rgb[2], alpha
    return color


_RAMP: Image | None = None


def _ramp() -> Image:
    """64x1 alpha ramp, opaque on the left: the feathered edge of a word fill."""
    global _RAMP
    if _RAMP is None:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 1)
        cr = cairo.Context(surface)
        gradient = cairo.LinearGradient(0, 0, 64, 0)
        gradient.add_color_stop_rgba(0, 1, 1, 1, 1)
        gradient.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(gradient)
        cr.paint()
        _RAMP = Image.from_surface(surface, 64, 1)
    return _RAMP


class Scene:
    def __init__(self, snapshot: Gtk.Snapshot):
        self.s = snapshot

    @contextmanager
    def group(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        scale: float = 1.0,
        alpha: float = 1.0,
        skew_x: float = 0.0,
    ) -> Iterator[None]:
        """Translate, then scale and skew (shear factor, as cairo's Matrix xy), then fade."""
        s = self.s
        s.save()
        if dx or dy:
            s.translate(Graphene.Point().init(dx, dy))
        if scale != 1.0:
            s.scale(scale, scale)
        if skew_x:
            s.transform(Gsk.Transform.new().skew(math.degrees(math.atan(skew_x)), 0.0))
        faded = alpha < 0.999
        if faded:
            s.push_opacity(max(0.0, alpha))
        try:
            yield
        finally:
            if faded:
                s.pop()
            s.restore()

    @contextmanager
    def clip(self, x: float, y: float, w: float, h: float) -> Iterator[None]:
        self.s.push_clip(_rect(x, y, w, h))
        try:
            yield
        finally:
            self.s.pop()

    @contextmanager
    def rounded_clip(self, x: float, y: float, w: float, h: float, r: float) -> Iterator[None]:
        self.s.push_rounded_clip(rounded(x, y, w, h, r))
        try:
            yield
        finally:
            self.s.pop()

    @contextmanager
    def fade_out_right(self, x0: float, x1: float, y: float, h: float) -> Iterator[None]:
        """Content inside is fully visible left of x0, fades to nothing at x1."""
        s = self.s
        s.push_mask(Gsk.MaskMode.ALPHA)
        try:
            if x0 > -1e6:
                s.append_color(_rgba((1, 1, 1), 1.0), _rect(-1e5, y, x0 + 1e5, h))
            ramp = _ramp()
            s.append_scaled_texture(
                ramp.texture, Gsk.ScalingFilter.LINEAR, _rect(x0, y, x1 - x0, h)
            )
        finally:
            s.pop()  # end of mask
        try:
            yield
        finally:
            s.pop()  # end of source

    def image(self, img: Image, x: float, y: float, alpha: float = 1.0) -> None:
        """Draw an image with its top-left corner at (x, y)."""
        if alpha <= 0.003:
            return
        faded = alpha < 0.999
        if faded:
            self.s.push_opacity(alpha)
        self.s.append_scaled_texture(
            img.texture, Gsk.ScalingFilter.TRILINEAR, _rect(x, y, img.w, img.h)
        )
        if faded:
            self.s.pop()

    def image_centered(
        self, img: Image, cx: float, cy: float, alpha: float = 1.0, scale: float = 1.0
    ) -> None:
        with self.group(cx, cy, scale):
            self.image(img, -img.w / 2, -img.h / 2, alpha)

    def cover(self, img: Image, x: float, y: float, w: float, h: float) -> None:
        """Draw an image stretched to a box."""
        self.s.append_scaled_texture(img.texture, Gsk.ScalingFilter.TRILINEAR, _rect(x, y, w, h))

    def rect(self, x: float, y: float, w: float, h: float, rgb, alpha: float = 1.0) -> None:
        self.s.append_color(_rgba(rgb, alpha), _rect(x, y, w, h))

    def rounded_rect(self, x, y, w, h, r, rgb, alpha: float = 1.0) -> None:
        with self.rounded_clip(x, y, w, h, r):
            self.rect(x, y, w, h, rgb, alpha)

    def line(self, x1, y1, x2, y2, width: float, rgb, alpha: float = 1.0) -> None:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.5:
            return
        s = self.s
        s.save()
        s.translate(Graphene.Point().init(x1, y1))
        s.rotate(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        s.append_color(_rgba(rgb, alpha), _rect(0, -width / 2, length, width))
        s.restore()

    def shadow(self, x, y, w, h, r, alpha: float, dy: float = 6.0, blur: float = 30.0) -> None:
        """A soft drop shadow outside a rounded box (drawn by the GPU)."""
        box = rounded(x, y, w, h, r)
        self.s.append_outset_shadow(box, _rgba((0, 0, 0), alpha), 0.0, dy, 0.0, blur)
