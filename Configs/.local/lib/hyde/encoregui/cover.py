"""Album covers drawn by the GPU, so HD covers stay crisp at any size.

CoverView is the Home and Lyrics cover: rounded, a thin light ring, a soft
drop shadow. The texture is decoded off the main thread and scaled with
mipmaps (trilinear), so a 1500 px cover shrinks to 236 px without shimmer
and a new cover crossfades in.
"""

from __future__ import annotations

import threading
import time

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

from encoregui.scene import Image, Scene, rounded
from encorelib.coverfit import fit_cover

CROSSFADE_SECONDS = 0.3


def load_texture(path: str, done) -> None:
    """Decode an image file on a worker thread; `done(path, texture | None)` runs on
    the main loop."""

    def work():
        try:
            texture = Gdk.Texture.new_from_filename(path)
        except GLib.Error:
            texture = None
        GLib.idle_add(lambda: (done(path, texture), False)[1])

    threading.Thread(target=work, name="encore-cover", daemon=True).start()


def _fit(texture: Gdk.Texture, x: float, y: float, side: float) -> tuple:
    """Cover-fit a texture into a square: the rect it is drawn into."""
    tw, th = texture.get_width(), texture.get_height()
    zoom = max(side / max(1, tw), side / max(1, th))
    w, h = tw * zoom, th * zoom
    return x + (side - w) / 2, y + (side - h) / 2, w, h


class CoverView(Gtk.Widget):
    PAD = 26  # room for the shadow around the cover

    def __init__(self, side: int):
        super().__init__()
        self.side = side
        self.path = ""
        self.texture: Gdk.Texture | None = None
        self.previous: Gdk.Texture | None = None
        self.fade_from = 0.0
        self.tick_id = 0
        self.alpha = 1.0
        self._apply_size()
        # a tick callback keeps the window's frame clock running at the monitor
        # rate; a hidden cover (the other page) must never hold one
        self.connect("unmap", lambda *_: self._stop_fade())

    def _apply_size(self) -> None:
        total = self.side + 2 * self.PAD
        self.set_size_request(total, total)

    def set_side(self, side: int) -> None:
        if side != self.side:
            self.side = side
            self._apply_size()
            self.queue_draw()

    def set_alpha(self, alpha: float) -> None:
        """Paused covers dim slightly."""
        if abs(alpha - self.alpha) > 1e-3:
            self.alpha = alpha
            self.queue_draw()

    def set_path(self, path: str) -> None:
        if path == self.path:
            return
        self.path = path
        if not path:
            self._loaded("", None)
            return
        load_texture(path, self._loaded)

    def _loaded(self, path: str, texture: Gdk.Texture | None) -> None:
        if path != self.path:
            return  # a newer cover was asked for meanwhile
        self.previous, self.texture = self.texture, texture
        self.fade_from = time.monotonic()
        if self.previous is not None and self.get_mapped():
            if not self.tick_id:
                self.tick_id = self.add_tick_callback(self._tick)
        else:
            self.previous = None  # unseen: no crossfade to show
        self.queue_draw()

    def _stop_fade(self) -> None:
        if self.tick_id:
            self.remove_tick_callback(self.tick_id)
            self.tick_id = 0
        self.previous = None

    def _tick(self, _widget, _clock) -> bool:
        self.queue_draw()
        if time.monotonic() - self.fade_from >= CROSSFADE_SECONDS:
            self.previous = None
            self.tick_id = 0
            return False
        return True

    def do_snapshot(self, snapshot) -> None:
        sc = Scene(snapshot)
        side = self.side
        x = (self.get_width() - side) / 2
        y = (self.get_height() - side) / 2
        radius = side * 0.085
        ring = 6
        sc.shadow(x, y, side, side, radius, 0.55, dy=10, blur=34)
        sc.rounded_rect(
            x - ring, y - ring, side + 2 * ring, side + 2 * ring, radius + ring, (1, 1, 1), 0.07
        )
        with sc.rounded_clip(x, y, side, side, radius):
            if self.texture is None and self.previous is None:
                sc.rect(x, y, side, side, (1, 1, 1), 0.06)
            t = min(1.0, (time.monotonic() - self.fade_from) / CROSSFADE_SECONDS)
            for texture, alpha in ((self.previous, 1.0), (self.texture, t if self.previous else 1)):
                if texture is None:
                    continue
                img = Image(texture, texture.get_width(), texture.get_height())
                fx, fy, fw, fh = _fit(texture, x, y, side)
                if alpha * self.alpha < 0.999:
                    snapshot.push_opacity(alpha * self.alpha)
                    sc.cover(img, fx, fy, fw, fh)
                    snapshot.pop()
                else:
                    sc.cover(img, fx, fy, fw, fh)
        # the hairline edge of the ring
        edge = rounded(x - ring, y - ring, side + 2 * ring, side + 2 * ring, radius + ring)
        line = Gdk.RGBA()
        line.red = line.green = line.blue = 1.0
        line.alpha = 0.12
        snapshot.append_border(edge, [1.0] * 4, [line] * 4)


class CoverBackdrop(Gtk.Widget):
    """The full-screen background: the cover, or clear black.

    A cover that fills the screen within coverfit.FILL_MAX is drawn edge to
    edge with scrims behind the bars; a smaller one is framed sharp over a
    blurred, darkened copy of itself (blurred once per cover by the GPU
    renderer and kept as a texture, so frames pay nothing for the blur). A
    new cover crossfades in.
    """

    FADE_SECONDS = 0.4
    FRAME_RADIUS = 18
    BLUR = 60

    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.path = ""
        self.mode = "art"
        self.texture: Gdk.Texture | None = None
        self.previous: Gdk.Texture | None = None
        self.fade_from = 0.0
        self.tick_id = 0
        self.blurred: tuple[tuple, Gdk.Texture] | None = None  # ((texture, w, h), blurred)
        self.connect("unmap", lambda *_: self._stop_fade())

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.mode = mode
            self.queue_draw()

    def set_path(self, path: str) -> None:
        if path == self.path:
            return
        self.path = path
        if not path:
            self._loaded("", None)
            return
        load_texture(path, self._loaded)

    def _loaded(self, path: str, texture: Gdk.Texture | None) -> None:
        if path != self.path:
            return
        self.previous, self.texture = self.texture, texture
        self.fade_from = time.monotonic()
        if self.previous is not None and self.get_mapped():
            if not self.tick_id:
                self.tick_id = self.add_tick_callback(self._tick)
        else:
            self.previous = None
        self.queue_draw()

    def _stop_fade(self) -> None:
        if self.tick_id:
            self.remove_tick_callback(self.tick_id)
            self.tick_id = 0
        self.previous = None

    def _tick(self, _widget, _clock) -> bool:
        self.queue_draw()
        if time.monotonic() - self.fade_from >= self.FADE_SECONDS:
            self.previous = None
            self.tick_id = 0
            return False
        return True

    def _blurred_backdrop(self, texture: Gdk.Texture, w: float, h: float) -> Gdk.Texture | None:
        """The cover blurred and darkened to fill the view, rendered once."""
        key = (texture, int(w), int(h))
        if self.blurred is not None and self.blurred[0] == key:
            return self.blurred[1]
        native = self.get_native()
        renderer = native.get_renderer() if native is not None else None
        if renderer is None:
            return None
        snapshot = Gtk.Snapshot()
        sc = Scene(snapshot)
        tw, th = texture.get_width(), texture.get_height()
        zoom = max(w / max(1, tw), h / max(1, th))
        bw, bh = tw * zoom, th * zoom
        snapshot.push_blur(self.BLUR)
        sc.cover(Image(texture, tw, th), (w - bw) / 2, (h - bh) / 2, bw, bh)
        snapshot.pop()
        sc.rect(0, 0, w, h, (0, 0, 0), 0.35)
        node = snapshot.to_node()
        if node is None:
            return None
        blurred = renderer.render_texture(node, Graphene.Rect().init(0, 0, w, h))
        self.blurred = (key, blurred)
        return blurred

    def _draw_cover(self, snapshot, sc: Scene, texture: Gdk.Texture, alpha: float, w, h) -> None:
        fit = fit_cover(
            texture.get_width(), texture.get_height(), w, h, self.get_scale_factor() or 1
        )
        img = Image(texture, texture.get_width(), texture.get_height())
        if alpha < 0.999:
            snapshot.push_opacity(alpha)
        if fit.mode == "fill":
            sc.cover(img, fit.x, fit.y, fit.w, fit.h)
        else:
            blurred = self._blurred_backdrop(texture, w, h)
            if blurred is not None:
                sc.cover(Image(blurred, w, h), 0, 0, w, h)
            sc.shadow(fit.x, fit.y, fit.w, fit.h, self.FRAME_RADIUS, 0.6, dy=16, blur=48)
            with sc.rounded_clip(fit.x, fit.y, fit.w, fit.h, self.FRAME_RADIUS):
                sc.cover(img, fit.x, fit.y, fit.w, fit.h)
        if alpha < 0.999:
            snapshot.pop()

    def do_snapshot(self, snapshot) -> None:
        w, h = self.get_width(), self.get_height()
        sc = Scene(snapshot)
        sc.rect(0, 0, w, h, (0, 0, 0), 1.0)
        if self.mode != "art":
            return
        t = min(1.0, (time.monotonic() - self.fade_from) / self.FADE_SECONDS)
        for texture, alpha in ((self.previous, 1.0), (self.texture, t if self.previous else 1.0)):
            if texture is not None:
                self._draw_cover(snapshot, sc, texture, alpha, w, h)
        if self.texture is None and self.previous is None:
            return
        # scrims where the bars sit, so their text reads on any cover
        for y0, y1, a0, a1 in ((0, 160, 0.45, 0.0), (h - 220, h, 0.0, 0.55)):
            stops = []
            for offset, a in ((0.0, a0), (1.0, a1)):
                stop = Gsk.ColorStop()
                stop.offset = offset
                color = Gdk.RGBA()
                color.red = color.green = color.blue = 0.0
                color.alpha = a
                stop.color = color
                stops.append(stop)
            snapshot.append_linear_gradient(
                Graphene.Rect().init(0, y0, w, y1 - y0),
                Graphene.Point().init(0, y0),
                Graphene.Point().init(0, y1),
                stops,
            )
