"""The album field: the window's light, taken from the cover.

The cover, blurred large and darkened, under three blobs in the album's
colors that wander slowly, and a fine static grain. The blur is rendered
once per cover and size by the GPU renderer and kept as a texture; a frame
then costs one texture, three gradient nodes and a repeat node. It drifts
at a few frames a second only while mapped, not suspended, motion is on,
and either music plays or nothing is playing at all (the idle screen);
paused, it holds still.
"""

from __future__ import annotations

import time

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

from encoregui.cover import load_texture
from encoregui.scene import Image, Scene
from encorelib.motion import blob_center, grain_texture_bytes

PLAY_FPS = 1  # the blobs move a few px/s under an 80 px blur: steps are invisible at 1 fps
IDLE_FPS = 3
BLUR = 80
WASH = 0.68  # black over the blurred cover, so type reads on any art
BASE = (0.078, 0.075, 0.09)
# per blob: color key, radius (share of the long side), base center, orbit, periods (s), phase
BLOBS = (
    ("accent", 0.52, (0.5, 0.36), (0.05, 0.03), (41.0, 29.0), 0.0),
    ("accent2", 0.46, (0.2, 0.78), (0.12, 0.08), (53.0, 37.0), 2.1),
    ("highlight", 0.4, (0.82, 0.72), (0.1, 0.1), (47.0, 31.0), 4.2),
)


def _rgba(color: str, alpha: float) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.parse(f"#{color}")
    rgba.alpha = alpha
    return rgba


class AlbumField(Gtk.Widget):
    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.colors = None
        self.path = ""
        self.texture: Gdk.Texture | None = None
        self.blurred: tuple[tuple, Gdk.Texture] | None = None
        self.light: tuple[tuple, Gdk.Texture] | None = None  # the blobs, at quarter size
        self.grain: Gdk.Texture | None = None
        self.playing = False
        self.motion = True
        self.hover = 0.0  # 0..1: the cover is being hovered, the light rises
        self.strength = 1.0
        self.timer = 0
        self.start = time.monotonic()
        self.window_handler = 0
        self.connect("map", lambda *_: self._sync_timer())
        self.connect("unmap", lambda *_: self._sync_timer())
        self.connect("realize", self._on_realize)

    # inputs -----------------------------------------------------------------

    def set_colors(self, colors) -> None:
        self.colors = colors
        self.queue_draw()

    def set_cover(self, path: str) -> None:
        if path == self.path:
            return
        self.path = path
        if not path:
            self.texture = None
            self.queue_draw()
            self._sync_timer()
            return
        load_texture(path, self._loaded)

    def _loaded(self, path: str, texture: Gdk.Texture | None) -> None:
        if path != self.path:
            return
        self.texture = texture
        self.queue_draw()
        self._sync_timer()

    def set_playing(self, playing: bool) -> None:
        if playing != self.playing:
            self.playing = playing
            self._sync_timer()

    def set_motion(self, motion: bool) -> None:
        if motion != self.motion:
            self.motion = motion
            self._sync_timer()

    def set_hover(self, hover: float) -> None:
        hover = max(0.0, min(1.0, hover))
        if abs(hover - self.hover) > 1e-3:
            self.hover = hover
            self.queue_draw()

    # ticking ----------------------------------------------------------------

    def _on_realize(self, _widget) -> None:
        window = self.get_root()
        if isinstance(window, Gtk.Window) and not self.window_handler:
            self.window_handler = window.connect("notify::suspended", lambda *_: self._sync_timer())

    def _wants_motion(self) -> bool:
        window = self.get_root()
        suspended = isinstance(window, Gtk.Window) and window.is_suspended()
        alive = self.playing or self.texture is None  # playing, or the idle light
        return self.get_mapped() and not suspended and self.motion and alive

    def _sync_timer(self) -> None:
        want = self._wants_motion()
        fps = PLAY_FPS if self.texture is not None else IDLE_FPS
        if want and not self.timer:
            self.timer = GLib.timeout_add(1000 // fps, self._tick)
        elif not want and self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _tick(self) -> bool:
        if not self._wants_motion():
            self.timer = 0
            return False
        self.queue_draw()
        return True

    # drawing ----------------------------------------------------------------

    def _blurred_cover(self, w: float, h: float) -> Gdk.Texture | None:
        key = (self.texture, int(w), int(h))
        if self.blurred is not None and self.blurred[0] == key:
            return self.blurred[1]
        native = self.get_native()
        renderer = native.get_renderer() if native is not None else None
        if renderer is None or self.texture is None:
            return None
        snapshot = Gtk.Snapshot()
        sc = Scene(snapshot)
        tw, th = self.texture.get_width(), self.texture.get_height()
        zoom = max(w / max(1, tw), h / max(1, th)) * 1.15  # overscan hides the blur's edge
        bw, bh = tw * zoom, th * zoom
        snapshot.push_blur(BLUR)
        sc.cover(Image(self.texture, tw, th), (w - bw) / 2, (h - bh) / 2, bw, bh)
        snapshot.pop()
        sc.rect(0, 0, w, h, (0, 0, 0), WASH)
        node = snapshot.to_node()
        if node is None:
            return None
        blurred = renderer.render_texture(node, Graphene.Rect().init(0, 0, w, h))
        self.blurred = (key, blurred)
        return blurred

    def _light_texture(self, w: float, h: float, t: float, strength: float) -> Gdk.Texture | None:
        """The three blobs rendered at quarter size, once per drift step: a paint then
        costs one texture draw instead of three full-window gradients."""
        fps = PLAY_FPS if self.texture is not None else IDLE_FPS
        key = (int(t * fps), round(strength, 2), id(self.colors), int(w), int(h))
        if self.light is not None and self.light[0] == key:
            return self.light[1]
        native = self.get_native()
        renderer = native.get_renderer() if native is not None else None
        if renderer is None or self.colors is None:
            return None
        qw, qh = max(1, int(w / 4)), max(1, int(h / 4))
        snapshot = Gtk.Snapshot()
        side = max(qw, qh)
        for key_name, size, center, orbit, period, phase in BLOBS:
            fx, fy = blob_center(t, orbit, period, phase, center)
            radius = side * size
            color = getattr(self.colors, key_name)
            stops = []
            for offset, alpha in ((0.0, 0.34 * strength), (0.45, 0.14 * strength), (1.0, 0.0)):
                stop = Gsk.ColorStop()
                stop.offset = offset
                stop.color = _rgba(color, min(1.0, alpha))
                stops.append(stop)
            snapshot.append_radial_gradient(
                Graphene.Rect().init(0, 0, qw, qh),
                Graphene.Point().init(fx * qw, fy * qh),
                radius,
                radius,
                0.0,
                1.0,
                stops,
            )
        node = snapshot.to_node()
        if node is None:
            return None
        texture = renderer.render_texture(node, Graphene.Rect().init(0, 0, qw, qh))
        self.light = (key, texture)
        return texture

    def _grain(self) -> Gdk.Texture:
        if self.grain is None:
            data = GLib.Bytes.new(grain_texture_bytes(128))
            self.grain = Gdk.MemoryTexture.new(
                128, 128, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, data, 128 * 4
            )
        return self.grain

    def do_snapshot(self, snapshot) -> None:
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        sc = Scene(snapshot)
        sc.rect(0, 0, w, h, BASE, 1.0)
        blurred = self._blurred_cover(w, h) if self.texture is not None else None
        if blurred is not None:
            sc.cover(Image(blurred, w, h), 0, 0, w, h)
        if self.colors is not None:
            t = (time.monotonic() - self.start) if self.motion else 0.0
            # over a cover the blobs are a glow; without one they are the light itself
            strength = (0.42 if blurred is not None else 1.0) * self.strength
            strength *= 1.0 + 0.5 * self.hover
            light = self._light_texture(w, h, t, strength)
            if light is not None:
                sc.cover(Image(light, w, h), 0, 0, w, h)
        # a fine static grain, so the light never bands (its strength is baked in)
        snapshot.push_repeat(Graphene.Rect().init(0, 0, w, h), Graphene.Rect().init(0, 0, 128, 128))
        snapshot.append_texture(self._grain(), Graphene.Rect().init(0, 0, 128, 128))
        snapshot.pop()
