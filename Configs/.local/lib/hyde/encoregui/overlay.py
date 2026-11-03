"""GTK4 layer-shell lyrics overlay.

A click-through surface on the OVERLAY layer that renders the daemon's
current line with a smooth per-word fill. Each line is rasterised once
into a dim and a bright cairo surface (shadow and glow baked in); a frame
then costs two clipped blits, so the steady cost stays tiny.

Scheduling: a tick callback runs only while a word is actively filling or
a line transition plays; between words a single one-shot timeout sleeps
until the next word; paused, hidden or lyric-less states run nothing.
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import ClassVar

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo
from gi.repository import Gtk4LayerShell as LayerShell

from encorelib.config import EncoreConfig
from encorelib.constellation import chain_words
from encorelib.glyphs import glyph_for
from encorelib.look import effective, read_look
from encorelib.lyricview import (
    HIDDEN,
    View,
    build_view,
    current_word_index,
    live_position,
    next_word_boundary,
    should_transition,
)
from encorelib.palette import pick_accent
from encorelib.stream import LineDecoder, should_connect
from encorelib.wordrects import word_byte_ranges

TRANSITION_SECONDS = 0.22
ANIMATE_MS = 33
SLIDE_PX = 26
FEATHER_PX = 26
CREDIT_SECONDS = 10.0
POP_SECONDS = 0.16
SLIDE_SECONDS = 0.2
EXIT_SECONDS = 0.26
COLUMN_ROWS = 3
CONSTELLATION_SCALE = 1.2
PAST_SCALE = 0.55
RASTER_CACHE = 6
WIDTH_FRACTION = 0.8


def _hex_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    if len(color) < 6:
        return (1.0, 1.0, 1.0)
    try:
        return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (1.0, 1.0, 1.0)


class LineRaster:
    """Dim and bright surfaces for one line, plus per-word pixel rects."""

    def __init__(
        self,
        text: str,
        words: list[str],
        font: str,
        size: int,
        width: int,
        accent: tuple[float, float, float],
        scale: int,
    ):
        self.scale = scale
        layout_width = width * Pango.SCALE
        measure = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        context = cairo.Context(measure)
        layout = PangoCairo.create_layout(context)
        desc = Pango.FontDescription.from_string(f"{font} Bold")
        desc.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(desc)
        layout.set_width(layout_width)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_text(text, -1)
        _, logical = layout.get_pixel_extents()
        self.height = logical.height + 10  # room for the baked shadow
        self.width = width
        self.rects = self._word_rects(layout, text, words)
        self.dim = self._render(layout, (1, 1, 1), 0.42, glow=None)
        self.bright = self._render(layout, accent, 1.0, glow=accent)

    @staticmethod
    def _char_box(layout, index: int) -> tuple[float, float, float, float]:
        r = layout.index_to_pos(index)
        x, w = (r.x + r.width, -r.width) if r.width < 0 else (r.x, r.width)
        return (x / Pango.SCALE, r.y / Pango.SCALE, w / Pango.SCALE, r.height / Pango.SCALE)

    def _word_rects(
        self, layout, text: str, words: list[str]
    ) -> list[list[tuple[float, float, float, float]]]:
        """One pixel rect per word (two when a word wraps across rows).

        Built from the first and last character boxes via index_to_pos: the
        PyGI binding of pango_layout_line_get_x_ranges truncates its result
        to half its length, so it cannot be used.
        """
        out = []
        for word, (a, b) in zip(words, word_byte_ranges(text, words)):
            if b <= a:
                out.append([])
                continue
            last_start = b - len(word[-1].encode("utf-8"))
            xa, ya, wa, ha = self._char_box(layout, a)
            xz, yz, wz, hz = self._char_box(layout, last_start)
            if abs(ya - yz) < ha / 2:
                left = min(xa, xz)
                right = max(xa + wa, xz + wz)
                out.append([(left, ya, right - left, ha)])
            else:
                # word wrapped across rows: overshoot is harmless, the
                # bright surface is transparent outside the glyphs
                out.append(
                    [
                        (xa, ya, max(0.0, self.width - xa), ha),
                        (0.0, yz, xz + wz, hz),
                    ]
                )
        return out

    def _render(self, layout, rgb, alpha: float, glow) -> cairo.ImageSurface:
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self.width * self.scale, self.height * self.scale
        )
        surface.set_device_scale(self.scale, self.scale)
        cr = cairo.Context(surface)
        # shadow: a soft dark copy under everything, so text reads on light windows
        cr.save()
        cr.translate(0, 2)
        PangoCairo.layout_path(cr, layout)
        cr.set_source_rgba(0, 0, 0, 0.30)
        cr.set_line_width(3.0)
        cr.stroke_preserve()
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.fill()
        cr.restore()
        if glow is not None:
            cr.save()
            PangoCairo.layout_path(cr, layout)
            cr.set_source_rgba(*glow, 0.16)
            cr.set_line_width(7.0)
            cr.stroke_preserve()
            cr.set_source_rgba(*glow, 0.28)
            cr.set_line_width(3.5)
            cr.stroke()
            cr.restore()
        cr.set_source_rgba(*rgb, alpha)
        cr.move_to(0, 0)
        PangoCairo.show_layout(cr, layout)
        return surface


class Overlay:
    def __init__(self, app: Gtk.Application, cfg: EncoreConfig, runtime_dir: str):
        self.cfg = cfg
        self.runtime_dir = runtime_dir
        self.socket_path = os.path.join(runtime_dir, "encore.sock")
        self.state: dict | None = None
        self.view: View = HIDDEN
        self.prev_draw: tuple[LineRaster, View] | None = None
        self.transition_from: float | None = None
        self.anim_id = 0
        self.timeout_id = 0
        self.rasters: dict[tuple, LineRaster] = {}
        self.small: dict[tuple, LineRaster] = {}
        self.word_cache: dict[tuple, tuple[cairo.ImageSurface, float, float]] = {}
        self.look_path = os.path.join(runtime_dir, "encore.look")
        (
            self.style,
            self.font,
            self.size,
            self.color_override,
            self.show_next,
            self.motion,
        ) = effective(cfg, read_look(self.look_path))
        self.look_cache = read_look(self.look_path)
        self.fade_from = 0.0
        self.slide_from = 0.0
        self.exit_from = 0.0
        self.exit_snapshot: tuple | None = None
        self.last_word_ix: int | None = None
        self._last_fade_key = ""
        self.places: dict[tuple, list[tuple[float, float]]] = {}
        self.decoder = LineDecoder()
        self.accent_rgb: tuple[float, float, float] = (1.0, 1.0, 1.0)
        self._accent_palette: dict | None = None
        self.credit_track = ""
        self.credit_until = 0.0
        self.credit_timer = 0
        self.connection: Gio.SocketConnection | None = None
        self.connecting = False
        self.cancel = Gio.Cancellable()

        self.window = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(self.window)
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(self.window, "encore")
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.NONE)
        self._apply_style_geometry()
        if cfg.overlay_monitor:
            display = self.window.get_display()
            monitors = display.get_monitors()
            for i in range(monitors.get_n_items()):
                monitor = monitors.get_item(i)
                if monitor.get_connector() == cfg.overlay_monitor:
                    LayerShell.set_monitor(self.window, monitor)
                    break

        css = Gtk.CssProvider()
        css.load_from_string("window, window.background { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        # stage: a static background layer (visual style's album art,
        # pre-scaled once per cover) under the word canvas; for stack and
        # visual the canvas is a centered region, so frames repaint less
        self.stage = Gtk.Overlay()
        self.stage.set_child(Gtk.Box())
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self.on_draw)
        self.stage.add_overlay(self.area)
        self.window.set_child(self.stage)
        # visual style's album art lives in its own window one layer lower:
        # the compositor stacks the two on the GPU and the art never redraws
        self.bg_window = Gtk.Window(application=app)
        LayerShell.init_for_window(self.bg_window)
        LayerShell.set_layer(self.bg_window, LayerShell.Layer.TOP)
        LayerShell.set_namespace(self.bg_window, "encore-visual")
        LayerShell.set_keyboard_mode(self.bg_window, LayerShell.KeyboardMode.NONE)
        for edge in (
            LayerShell.Edge.TOP,
            LayerShell.Edge.BOTTOM,
            LayerShell.Edge.LEFT,
            LayerShell.Edge.RIGHT,
        ):
            LayerShell.set_anchor(self.bg_window, edge, True)
        LayerShell.set_exclusive_zone(self.bg_window, -1)
        self.bg = Gtk.Picture()
        self.bg.set_content_fit(Gtk.ContentFit.FILL)
        self.bg.set_can_shrink(True)
        self.bg_art = ""
        self.bg_window.set_child(self.bg)
        self.bg_window.connect("realize", self._claim_input_shape)
        self.bg_window.connect("map", self._claim_input_shape)
        self._layout_stage()

        self.window.connect("realize", self._claim_input_shape)
        self.window.connect("map", self._claim_input_shape)
        self._size_window()
        self.window.present()
        self.window.set_visible(False)

        self._watch_runtime_dir()
        self.try_connect()

    # window ----------------------------------------------------------------

    def _apply_style_geometry(self) -> None:
        """A bottom/top strip for the line style; the whole output for
        stack and constellation."""
        full = self.style != "line"
        edges = (
            LayerShell.Edge.TOP,
            LayerShell.Edge.BOTTOM,
            LayerShell.Edge.LEFT,
            LayerShell.Edge.RIGHT,
        )
        for edge in edges:
            LayerShell.set_anchor(self.window, edge, full)
            LayerShell.set_margin(self.window, edge, 0)
        if not full:
            edge = {
                "top": LayerShell.Edge.TOP,
                "center": None,
                "bottom": LayerShell.Edge.BOTTOM,
            }[self.cfg.overlay_position]
            if edge is not None:
                LayerShell.set_anchor(self.window, edge, True)
                LayerShell.set_margin(self.window, edge, self.cfg.overlay_margin)
        self._size_window()

    def _size_window(self) -> None:
        display = self.window.get_display()
        monitor = None
        monitors = display.get_monitors()
        for i in range(monitors.get_n_items()):
            m = monitors.get_item(i)
            if not self.cfg.overlay_monitor or m.get_connector() == self.cfg.overlay_monitor:
                monitor = m
                break
        screen_w = monitor.get_geometry().width if monitor else 1920
        screen_h = monitor.get_geometry().height if monitor else 1080
        self.screen_w, self.screen_h = screen_w, screen_h
        self.content_width = int(screen_w * WIDTH_FRACTION)
        self._layout_stage()
        # room for two wrapped rows of the main and next lines plus the
        # credit; the surface is transparent, so the slack is invisible
        small = max(12, int(self.size * 0.55))
        height = int(self.size * 4.6 + small * 5.6 + 56)
        self.window.set_default_size(self.content_width, height)

    def _layout_stage(self) -> None:
        """Canvas region and background visibility for the current style."""
        if not hasattr(self, "bg"):  # geometry runs once before the stage exists
            return
        visual = self.style == "visual"
        column = self.style in ("stack", "visual")
        self._sync_bg_window()
        if column:
            self.area.set_halign(Gtk.Align.CENTER)
            self.area.set_valign(Gtk.Align.CENTER)
            self.area.set_size_request(int(self.screen_w * 0.8), int(self.screen_h * 0.8))
        else:
            self.area.set_halign(Gtk.Align.FILL)
            self.area.set_valign(Gtk.Align.FILL)
            self.area.set_size_request(-1, -1)
        if visual:
            self._update_background()

    def _sync_bg_window(self) -> None:
        want = self.style == "visual" and self.window.get_visible() and self.bg_art != ""
        if want != self.bg_window.get_visible():
            self.bg_window.set_visible(want)

    def _update_background(self) -> None:
        art = ((self.state or {}).get("track") or {}).get("art") or ""
        if art == self.bg_art:
            return
        self.bg_art = art
        if not art:
            self.bg.set_paintable(None)
            return
        try:
            src = cairo.ImageSurface.create_from_png(art)
        except (cairo.Error, OSError):
            self.bg.set_paintable(None)
            return
        w, h = self.screen_w, self.screen_h
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(out)
        iw, ih = src.get_width(), src.get_height()
        zoom = max(w / max(1, iw), h / max(1, ih))
        cr.translate((w - iw * zoom) / 2, (h - ih * zoom) / 2)
        cr.scale(zoom, zoom)
        cr.set_source_surface(src, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        cr.identity_matrix()
        # dim + vignette baked in once, so frames never recompute a gradient
        cr.set_source_rgba(0, 0, 0, 0.30)
        cr.paint()
        vignette = cairo.RadialGradient(w / 2, h / 2, h * 0.32, w / 2, h / 2, h * 0.95)
        vignette.add_color_stop_rgba(0, 0, 0, 0, 0)
        vignette.add_color_stop_rgba(1, 0, 0, 0, 0.62)
        cr.set_source(vignette)
        cr.paint()
        out.flush()
        data = GLib.Bytes.new(bytes(out.get_data()))
        texture = Gdk.MemoryTexture.new(
            w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, data, out.get_stride()
        )
        self.bg.set_paintable(texture)
        self._sync_bg_window()

    def _claim_input_shape(self, window) -> None:
        surface = window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())

    # socket ----------------------------------------------------------------

    def _watch_runtime_dir(self) -> None:
        gfile = Gio.File.new_for_path(self.runtime_dir)
        self.monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._on_dir_event)

    def _on_dir_event(self, _monitor, child, _other, event) -> None:
        if event not in (Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.CHANGED):
            return
        path = child.get_path() or ""
        if should_connect(path):
            self.try_connect()
        if os.path.basename(path) == "encore.look":
            self._reload_look()

    def _reload_look(self) -> None:
        self.look_cache = read_look(self.look_path)
        self.word_cache.clear()  # colors may have changed even if nothing else did
        self.area.queue_draw()
        new = effective(self.cfg, self.look_cache)
        old = (self.style, self.font, self.size, self.color_override, self.show_next, self.motion)
        if new == old:
            return
        style_changed = new[0] != self.style
        size_changed = new[2] != self.size
        (
            self.style,
            self.font,
            self.size,
            self.color_override,
            self.show_next,
            self.motion,
        ) = new
        for cache in (self.rasters, self.small, self.word_cache, self.places):
            cache.clear()
        self._accent_palette = None  # force accent recompute (color override)
        self.transition_from = None
        self.prev_draw = None
        self.last_word_ix = None
        self.fade_from = 0.0
        if style_changed:
            self._apply_style_geometry()
        elif size_changed:
            self._size_window()  # the line strip's height depends on the size
        self.apply()

    def try_connect(self) -> None:
        if self.connection is not None or self.connecting:
            return
        if not os.path.exists(self.socket_path):
            return
        self.connecting = True
        client = Gio.SocketClient()
        address = Gio.UnixSocketAddress.new(self.socket_path)
        client.connect_async(address, self.cancel, self._on_connected)

    def _on_connected(self, client, result) -> None:
        self.connecting = False
        try:
            self.connection = client.connect_finish(result)
        except GLib.Error:
            # the daemon may be between bind() and listen(); retry shortly
            self.connection = None
            GLib.timeout_add(300, self._late_retry)
            return
        self.decoder.reset()
        self._read_more()

    def _read_more(self) -> None:
        stream = self.connection.get_input_stream()
        stream.read_bytes_async(8192, GLib.PRIORITY_DEFAULT, self.cancel, self._on_read)

    def _on_read(self, stream, result) -> None:
        try:
            data = stream.read_bytes_finish(result)
        except GLib.Error:
            data = None
        if data is None or data.get_size() == 0:
            self._disconnect()
            return
        for obj in self.decoder.feed(data.get_data()):
            self.state = obj
        try:
            self.apply()
        except Exception:
            import logging

            logging.getLogger("encore").exception("overlay apply failed")
        self._read_more()

    def _disconnect(self) -> None:
        if self.connection is not None:
            self.connection.close(None)
            self.connection = None
        self.state = None
        self.apply()
        GLib.timeout_add(500, self._late_retry)

    def _late_retry(self) -> bool:
        self.try_connect()
        return False

    # scheduling ------------------------------------------------------------

    def apply(self) -> None:
        now = time.monotonic()
        palette = (self.state or {}).get("palette") or {}
        if palette != self._accent_palette:
            # pick_accent scans the palette; run it only when the palette changes
            self._accent_palette = palette
            if self.color_override:
                self.accent_rgb = _hex_rgb(self.color_override)
            else:
                self.accent_rgb = _hex_rgb(pick_accent(palette))
        view = build_view(self.state, now)
        if should_transition(self.view.line_key, view.line_key) and self.view.visible:
            raster = self._raster_for(self.view)
            if raster is not None and view.visible:
                self.prev_draw = (raster, self.view)
                self.transition_from = now
        if not view.visible:
            self.transition_from = None
            self.prev_draw = None
        self.view = view
        if view.visible:
            track = view.line_key.rsplit(":", 1)[0]
            if track != self.credit_track:
                self.credit_track = track
                self.credit_until = now + CREDIT_SECONDS
                if self.credit_timer:
                    GLib.source_remove(self.credit_timer)
                self.credit_timer = GLib.timeout_add(
                    int(CREDIT_SECONDS * 1000) + 80, self._credit_expired
                )
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = 0
        if self.style == "visual":
            self._update_background()
        show_window = view.visible or self._card_active()
        if show_window != self.window.get_visible():
            self.window.set_visible(show_window)
        self._sync_bg_window()
        if show_window and not view.visible:
            self.area.queue_draw()  # the card is state-driven, no timers
        if self.style == "line":
            in_transition = self.transition_from is not None
            active = view.visible and (view.animating or in_transition)
            wake = view.wake_in
        else:
            self.transition_from = None
            self.prev_draw = None
            ix = current_word_index(view) if view.visible else None
            if view.visible and (ix, view.line_key) != (self.last_word_ix, self._last_fade_key):
                if view.line_key != self._last_fade_key and self.view.visible and self.view.words:
                    # line change: let the old cluster fade out as a whole
                    old_ix = current_word_index(self.view)
                    self.exit_snapshot = (
                        self._last_fade_key,
                        [t for t, _ in self.view.words],
                        old_ix,
                    )
                    self.exit_from = now
                elif ix is not None and self.last_word_ix is not None and ix > self.last_word_ix:
                    self.slide_from = now
                self.last_word_ix = ix
                self._last_fade_key = view.line_key
                if ix is not None and ix >= 0:
                    self.fade_from = now
            playing = (self.state or {}).get("status") == "playing"
            drifting = self.motion and view.visible and playing
            in_motion = (
                (now - self.fade_from) < POP_SECONDS
                or (now - self.slide_from) < SLIDE_SECONDS
                or self.exit_snapshot is not None
            )
            active = view.visible and (in_motion or drifting)
            wake = next_word_boundary(self.state, now) if view.visible else None
            if wake is None:
                wake = view.wake_in
        if active:
            self._ensure_anim()
        else:
            self._drop_anim()
            if view.visible and wake is not None:
                self.timeout_id = GLib.timeout_add(max(16, int(wake * 1000) + 8), self._wake)
        self.area.queue_draw()

    def _wake(self) -> bool:
        self.timeout_id = 0
        self.apply()
        return False

    def _ensure_anim(self) -> None:
        # A plain 30 fps timer, not a frame-clock tick callback: an active
        # tick callback makes GTK run its whole frame cycle at the monitor
        # rate, which alone costs more than the drawing does. The feathered
        # edge keeps the half-rate sweep looking continuous.
        if not self.anim_id:
            self.anim_id = GLib.timeout_add(ANIMATE_MS, self._animate)

    def _drop_anim(self) -> None:
        if self.anim_id:
            GLib.source_remove(self.anim_id)
            self.anim_id = 0

    def _animate(self) -> bool:
        now = time.monotonic()
        if self.transition_from is not None and now - self.transition_from > TRANSITION_SECONDS:
            self.transition_from = None
            self.prev_draw = None
        view = build_view(self.state, now)
        changed_key = view.line_key != self.view.line_key
        self.view = view
        if self.style == "line":
            still = view.animating or self.transition_from
        else:
            ix = current_word_index(view) if view.visible else None
            if view.visible and (ix, view.line_key) != (self.last_word_ix, self._last_fade_key):
                # a fast word started inside the previous pop: restart the pop
                if (
                    view.line_key == self._last_fade_key
                    and ix is not None
                    and self.last_word_ix is not None
                    and ix > self.last_word_ix
                ):
                    self.slide_from = now
                self.last_word_ix = ix
                self._last_fade_key = view.line_key
                if ix is not None and ix >= 0:
                    self.fade_from = now
            playing = (self.state or {}).get("status") == "playing"
            if self.exit_snapshot is not None and now - self.exit_from >= EXIT_SECONDS:
                self.exit_snapshot = None
            still = (
                (now - self.fade_from) < POP_SECONDS
                or (now - self.slide_from) < SLIDE_SECONDS
                or self.exit_snapshot is not None
                or (self.motion and view.visible and playing)
            )
        if changed_key or not view.visible or not still:
            self.anim_id = 0
            GLib.idle_add(self.apply)
            return False
        self.area.queue_draw()
        return True

    # rendering -------------------------------------------------------------

    def _accent(self) -> tuple[float, float, float]:
        return self.accent_rgb

    def _raster_for(self, view: View) -> LineRaster | None:
        if not view.visible:
            return None
        key = (view.line_key, self.size, self._accent())
        raster = self.rasters.get(key)
        if raster is None:
            raster = LineRaster(
                view.text,
                [w for w, _ in view.words],
                self.font,
                self.size,
                self.content_width,
                self._accent(),
                self.area.get_scale_factor() or 1,
            )
            self.rasters[key] = raster
            while len(self.rasters) > RASTER_CACHE:
                self.rasters.pop(next(iter(self.rasters)))
        return raster

    def _small_raster(self, text: str, alpha_key: str) -> LineRaster | None:
        if not text:
            return None
        size = max(12, int(self.size * 0.55))
        key = (text, size, alpha_key)
        raster = self.small.get(key)
        if raster is None:
            raster = LineRaster(
                text,
                [],
                self.font,
                size,
                self.content_width,
                (1, 1, 1),
                self.area.get_scale_factor() or 1,
            )
            self.small[key] = raster
            while len(self.small) > RASTER_CACHE:
                self.small.pop(next(iter(self.small)))
        return raster

    def _paint_line(self, cr, raster: LineRaster, view: View, y: float, alpha: float) -> None:
        cr.save()
        cr.translate(0, y)
        grouped = alpha < 1.0
        if grouped:  # only transitions need an offscreen composite
            cr.push_group()
        cr.set_source_surface(raster.dim, 0, 0)
        cr.paint()
        full = []
        partial = None
        for rects, (_, fill) in zip(raster.rects, view.words):
            if fill >= 1.0:
                full.extend(rects)
            elif fill > 0.0 and partial is None:
                partial = (rects, fill)
        if full:
            cr.save()
            for x, ry, rw, rh in full:
                cr.rectangle(x - 2, ry - 4, rw + 4, rh + 8)
            cr.clip()
            cr.set_source_surface(raster.bright, 0, 0)
            cr.paint()
            cr.restore()
        if partial is not None:
            rects, fill = partial
            feather = FEATHER_PX
            spans = [
                rw + (feather if i == len(rects) - 1 else 0)
                for i, (_, _, rw, _) in enumerate(rects)
            ]
            revealed = sum(spans) * fill
            for (x, ry, rw, rh), span in zip(rects, spans):
                take = min(span, revealed)
                revealed -= take
                if take <= 0:
                    continue
                # the ramp trails the edge, so a word rises from nothing and
                # is fully lit once the edge has passed its end
                edge = x + take
                cr.save()
                cr.rectangle(x - 2, ry - 4, min(take, rw) + 4, rh + 8)
                cr.clip()
                gradient = cairo.LinearGradient(edge - feather, 0, edge, 0)
                gradient.add_color_stop_rgba(0, 1, 1, 1, 1)
                gradient.add_color_stop_rgba(1, 1, 1, 1, 0)
                cr.set_source_surface(raster.bright, 0, 0)
                cr.mask(gradient)
                cr.restore()
        if grouped:
            cr.pop_group_to_source()
            cr.paint_with_alpha(alpha)
        cr.restore()

    def _word_surface(
        self, text: str, size: int, rgb, dim: bool, style: str = "bold", shear: float = 0.0
    ):
        """A rendered word with baked shadow (and glow when bright).

        style: "bold" (our font), "serif" (italic serif) or "medium".
        shear bakes a horizontal skew in, so frames can blit 1:1.
        """
        key = (text, size, rgb, dim, style, round(shear, 3))
        hit = self.word_cache.get(key)
        if hit is not None:
            return hit
        scale = self.area.get_scale_factor() or 1
        measure = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        layout = PangoCairo.create_layout(cairo.Context(measure))
        if style == "serif":
            desc = Pango.FontDescription.from_string("Serif Italic")
        elif style == "medium":
            desc = Pango.FontDescription.from_string(self.font + " Medium")
        else:
            desc = Pango.FontDescription.from_string(self.font + " Bold")
        desc.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        _, logical = layout.get_pixel_extents()
        lean = abs(shear) * logical.height
        w, h = logical.width + 16.0 + lean, logical.height + 16.0
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w * scale), int(h * scale))
        surface.set_device_scale(scale, scale)
        cr2 = cairo.Context(surface)
        cr2.translate(8 + (lean if shear < 0 else 0), 8)
        if shear:
            # skew about the text's vertical middle
            mid = logical.height / 2
            cr2.translate(-shear * mid, 0)
            cr2.transform(cairo.Matrix(1, 0, shear, 1, 0, 0))
        cr2.save()
        cr2.translate(0, 2)
        PangoCairo.layout_path(cr2, layout)
        cr2.set_source_rgba(0, 0, 0, 0.5)
        cr2.set_line_width(3.5)
        cr2.stroke_preserve()
        cr2.fill()
        cr2.restore()
        if not dim:
            cr2.save()
            PangoCairo.layout_path(cr2, layout)
            cr2.set_source_rgba(*rgb, 0.18)
            cr2.set_line_width(7.0)
            cr2.stroke_preserve()
            cr2.set_source_rgba(*rgb, 0.3)
            cr2.set_line_width(3.0)
            cr2.stroke()
            cr2.restore()
        cr2.set_source_rgba(*rgb, 0.55 if dim else 1.0)
        cr2.move_to(0, 0)
        PangoCairo.show_layout(cr2, layout)
        out = (surface, w, h)
        self.word_cache[key] = out
        while len(self.word_cache) > 128:
            self.word_cache.pop(next(iter(self.word_cache)))
        return out

    def _paint_word(self, cr, surface, w, h, cx, cy, alpha=1.0, scale=1.0):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(scale, scale)
        cr.set_source_surface(surface, -w / 2, -h / 2)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _drift(self, now: float, index: int, boost: float = 1.0) -> tuple[float, float]:
        """A slow float so the constellation feels alive; still while paused."""
        if not self.motion or (self.state or {}).get("status") != "playing":
            return (0.0, 0.0)
        return (
            4.0 * boost * math.sin(now * 0.7 + index * 1.7),
            3.0 * boost * math.sin(now * 0.9 + index * 2.3 + 1.1),
        )

    def _pop(self, now: float) -> tuple[float, float]:
        p = min(1.0, max(0.0, (now - self.fade_from) / POP_SECONDS))
        eased = 1 - (1 - p) ** 3
        return 0.35 + 0.65 * eased, 0.9 + 0.1 * eased

    # rolling column (stack and visual styles) --------------------------------
    # Reference semantics (official hero video, 6 fps): three slots scroll up.
    # bottom = the word being sung (visual: on a sweeping Highlight marker),
    # middle = the word just sung, big; top = the word before, small.

    SLOT_SCALE: ClassVar[dict] = {-1: 1.0, 0: 1.1, 1: 2.4, 2: 0.85, 3: 0.6}
    SLOT_ALPHA: ClassVar[dict] = {-1: 0.6, 0: 1.0, 1: 1.0, 2: 0.62, 3: 0.0}

    @staticmethod
    def _word_style(line_key: str, index: int) -> str:
        return ("bold", "serif", "medium")[hash((line_key, index)) % 3]

    def _stagger(self, line_key: str, index: int, width: int) -> float:
        return (hash((line_key, "x", index)) % 1000 / 1000 - 0.5) * width * 0.05

    def _trio(self) -> tuple[tuple, tuple, tuple]:
        """(lyric, highlight, secondary) colors: look overrides, else album."""
        look = self.look_cache
        accent = self.accent_rgb

        def mix(rgb, other, t):
            return tuple(a * (1 - t) + b * t for a, b in zip(rgb, other))

        lyric = (
            _hex_rgb(look["lyric_color"]) if "lyric_color" in look else mix(accent, (1, 1, 1), 0.45)
        )
        highlight = _hex_rgb(look["highlight_color"]) if "highlight_color" in look else accent
        secondary = (
            _hex_rgb(look["secondary_color"])
            if "secondary_color" in look
            else mix(accent, (0.55, 0.55, 0.6), 0.55)
        )
        return lyric, highlight, secondary

    def _column_base(self, height: int) -> float:
        """Column font unit: ~8% of the screen height at the default size,
        so the middle word lands near the reference's ~20% of the height."""
        return getattr(self, "screen_h", height) * 0.08 * (self.size / 30.0)

    def _slot_y(self, slot: float, cy: float, base: float) -> float:
        # distance between slot centers from the two word heights involved
        def half(s):
            return self._lerp_slot(self.SLOT_SCALE, s) * base * 0.62

        gap_down = (half(1) + half(0)) * 1.02
        gap_up = (half(1) + half(2)) * 1.02
        if slot <= 1:
            return cy + (1 - slot) * gap_down
        return cy - (slot - 1) * gap_up

    @staticmethod
    def _lerp_slot(table: dict, slot: float) -> float:
        lo = math.floor(slot)
        hi = lo + 1
        t = slot - lo
        return table.get(lo, 0.0) * (1 - t) + table.get(hi, 0.0) * t

    def _draw_rolling(self, cr, width, height, view: View) -> None:
        now = time.monotonic()
        ix = current_word_index(view)
        if ix < 0:
            return
        texts = [t for t, _ in view.words]
        fill = view.words[ix][1]
        slide = 1.0
        if now - self.slide_from < SLIDE_SECONDS:
            p = (now - self.slide_from) / SLIDE_SECONDS
            slide = 1 - (1 - p) ** 3
        lyric, highlight, secondary = self._trio()
        cy = height * 0.47
        base = self._column_base(height)
        visual = self.style == "visual"
        alone = ix == 0  # first word of a line sits big in the middle
        for i in range(max(0, ix - 3), ix + 1):
            target = ix - i  # 0 current, 1 previous, 2 two back, 3 leaving
            if alone:
                target = 1
            slot = target - 1 + slide if (not alone and slide < 1.0) else target
            slot = max(-1.0, min(3.0, slot))
            alpha = self._lerp_slot(self.SLOT_ALPHA, slot)
            if alpha <= 0.01:
                continue
            scale_rel = self._lerp_slot(self.SLOT_SCALE, slot)
            # raster at the TARGET slot's size with its tilt baked in: steady
            # frames blit 1:1 (pixman fast path); only slides scale briefly
            target_slot = max(0, min(2, target))
            ref_size = max(12, int(base * self.SLOT_SCALE[target_slot]))
            zoom = max(0.05, (base * scale_rel) / ref_size)
            shear = -0.10 * (target_slot - 1)
            current = i == ix
            if current and visual:
                rgb, dim = (1, 1, 1), False
            elif current:
                rgb, dim = highlight, False
            elif slot >= 1.6:
                rgb, dim = secondary, True
            else:
                rgb, dim = lyric, False
            surface, w, h = self._word_surface(
                texts[i], ref_size, rgb, dim, self._word_style(view.line_key, i), shear
            )
            cx = width / 2 + self._stagger(view.line_key, i, width)
            y = self._slot_y(slot, cy, base)
            if self.motion and (self.state or {}).get("status") == "playing" and current:
                cx += 2.0 * math.sin(now * 1.3 + i)
            cr.save()
            steady = abs(zoom - 1.0) < 0.01
            if steady:  # integer placement keeps the blit on the fast path
                cx, y = round(cx - w / 2) + w / 2, round(y - h / 2) + h / 2
            cr.translate(cx, y)
            if not steady:
                cr.scale(zoom, zoom)
            if current and visual:
                block = min(1.0, max(0.18, fill * 1.15))
                pad_x, pad_y = 10, 4
                bw = (w - 16 + 2 * pad_x) * block
                bh = h - 16 + 2 * pad_y
                cr.save()
                cr.transform(cairo.Matrix(1, 0, -0.18, 1, 0, 0))
                cr.rectangle(-(w - 16) / 2 - pad_x, -bh / 2 + 1, bw, bh)
                cr.set_source_rgba(*highlight, 0.92 * alpha)
                cr.fill()
                cr.restore()
            cr.set_source_surface(surface, -w / 2, -h / 2)
            # bilinear, not cairo's default convolution: scaled+skewed big
            # word bitmaps through FILTER_GOOD every frame cost most of a core
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            cr.paint_with_alpha(alpha)
            if visual and slot <= 1.4:
                glyph = glyph_for(texts[i])
                if glyph:
                    gs, _gw, gh = self._word_surface(
                        glyph, max(14, int(ref_size * 0.62)), highlight, False
                    )
                    cr.set_source_surface(gs, w / 2 - 4, -gh / 2)
                    cr.get_source().set_filter(cairo.FILTER_BILINEAR)
                    cr.paint_with_alpha(alpha)
            cr.restore()

    # constellation ------------------------------------------------------------

    def _positions(self, line_key: str, words: list[str], width, height):
        key = (line_key, width, height)
        hit = self.places.get(key)
        if hit is None:
            hit = chain_words(words, width, height, seed=line_key)
            self.places[key] = hit
            while len(self.places) > 8:
                self.places.pop(next(iter(self.places)))
        return hit

    def _draw_cluster(self, cr, width, height, line_key, texts, ix, now, fade=1.0):
        positions = self._positions(line_key, texts, width, height)
        cr.set_line_width(1.0)
        cr.set_source_rgba(1, 1, 1, 0.14 * fade)
        for i in range(min(ix, len(positions) - 1)):
            cr.move_to(*positions[i])
            cr.line_to(*positions[i + 1])
            cr.stroke()
        spark, sw, sh = self._word_surface("✦", max(10, self.size // 2 - 4), (1, 1, 1), True)
        past = max(12, int(self.size * PAST_SCALE))
        for i in range(ix):
            dx, dy = self._drift(now, i)
            x, y = positions[i][0] + dx, positions[i][1] + dy
            self._paint_word(cr, spark, sw, sh, x, y - self.size * 0.7, 0.45 * fade)
            surface, w, h = self._word_surface(texts[i], past, (1, 1, 1), True)
            self._paint_word(cr, surface, w, h, x, y, 0.8 * fade)
        if 0 <= ix < len(positions):
            surface, w, h = self._word_surface(
                texts[ix], int(self.size * CONSTELLATION_SCALE), self.accent_rgb, False
            )
            alpha, zoom = self._pop(now)
            dx, dy = self._drift(now, ix, 1.6)
            self._paint_word(
                cr, surface, w, h, positions[ix][0] + dx, positions[ix][1] + dy, alpha * fade, zoom
            )

    def _draw_constellation(self, cr, width, height, view: View) -> None:
        now = time.monotonic()
        if self.exit_snapshot is not None:
            age = now - self.exit_from
            if age < EXIT_SECONDS:
                line_key, texts, ix = self.exit_snapshot
                self._draw_cluster(
                    cr, width, height, line_key, texts, ix, now, 1 - age / EXIT_SECONDS
                )
            else:
                self.exit_snapshot = None
        ix = current_word_index(view)
        if ix < 0:
            return
        self._draw_cluster(cr, width, height, view.line_key, [t for t, _ in view.words], ix, now)

    # visual background, credit, card ------------------------------------------

    def _visual_background(self, cr, width, height) -> None:
        art = ((self.state or {}).get("track") or {}).get("art") or ""
        if not art:
            return
        surface, _w, _h = self._cover_surface(art)
        if surface is None:
            return
        iw, ih = surface.get_width(), surface.get_height()
        zoom = max(width / max(1, iw), height / max(1, ih))
        cr.save()
        cr.translate((width - iw * zoom) / 2, (height - ih * zoom) / 2)
        cr.scale(zoom, zoom)
        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        cr.restore()
        cr.set_source_rgba(0, 0, 0, 0.38)
        cr.paint()
        vignette = cairo.RadialGradient(
            width / 2, height / 2, height * 0.35, width / 2, height / 2, height * 0.85
        )
        vignette.add_color_stop_rgba(0, 0, 0, 0, 0)
        vignette.add_color_stop_rgba(1, 0, 0, 0, 0.45)
        cr.set_source(vignette)
        cr.paint()

    def _draw_credit(self, cr, width, height) -> None:
        credit = self._credit_text()
        if not credit:
            return
        raster = self._small_raster(credit, "credit")
        if raster is None:
            return
        cr.save()
        cr.translate(0, height - raster.height - 14)
        cr.set_source_surface(raster.dim, 0, 0)
        cr.paint_with_alpha(0.6)
        cr.restore()

    def _card_active(self) -> bool:
        if self.style == "line":
            return False  # the strip window has no room for the card
        state = self.state or {}
        if state.get("status") not in ("playing", "paused") or not state.get("track"):
            return False
        lyrics = state.get("lyrics")
        if lyrics is not None and lyrics.get("sync") != "none":
            return False
        if lyrics is None and state.get("status") == "playing":
            # lyrics may still be on their way; don't flash the card at track start
            return live_position(state, time.monotonic()) > 2.0
        return True

    def _cover_surface(self, path: str):
        hit = self.word_cache.get(("cover", path))
        if hit is not None:
            return hit
        try:
            surface = cairo.ImageSurface.create_from_png(path)
        except (cairo.Error, OSError, TypeError):
            surface = None
        out = (surface, 0.0, 0.0)
        self.word_cache[("cover", path)] = out
        return out

    @staticmethod
    def _rounded(cr, x, y, w, h, radius) -> None:
        cr.new_sub_path()
        cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
        cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
        cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
        cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw_card(self, cr, width, height) -> None:
        state = self.state or {}
        track = state.get("track") or {}
        art = track.get("art") or ""
        size = max(240.0, height * 0.30)
        cx, cy = width / 2, height * 0.42
        x, y = cx - size / 2, cy - size / 2
        # deep soft shadow
        for grow, alpha in ((26, 0.05), (16, 0.09), (8, 0.14), (3, 0.18)):
            cr.set_source_rgba(0, 0, 0, alpha)
            self._rounded(
                cr, x - grow / 2, y - grow / 2 + 6, size + grow, size + grow, 26 + grow / 2
            )
            cr.fill()
        surface, _w, _h = self._cover_surface(art) if art else (None, 0, 0)
        if surface is not None:
            iw, ih = surface.get_width(), surface.get_height()
            cr.save()
            self._rounded(cr, x, y, size, size, 24)
            cr.clip()
            cr.translate(x, y)
            cr.scale(size / max(1, iw), size / max(1, ih))
            cr.set_source_surface(surface, 0, 0)
            cr.paint()
            cr.restore()
        else:
            cr.set_source_rgba(1, 1, 1, 0.08)
            self._rounded(cr, x, y, size, size, 24)
            cr.fill()
        y2 = cy + size / 2 + 26
        title = track.get("title") or ""
        artist = track.get("artist") or ""
        if title:
            ts, tw, th = self._word_surface(
                title[:48], max(21, int(self.size * 0.95)), (1, 1, 1), False
            )
            self._paint_word(cr, ts, tw, th, cx, y2 + th / 2)
            y2 += th + 4
        if artist:
            asf, aw, ah = self._word_surface(
                artist[:48], max(14, int(self.size * 0.58)), (1, 1, 1), True
            )
            self._paint_word(cr, asf, aw, ah, cx, y2 + ah / 2, 0.8)
            y2 += ah + 18
        # decorative pill controls (the overlay itself stays click-through)
        paused = state.get("status") == "paused"
        glyphs = ["󰒮", "󰐊" if paused else "󰏤", "󰒭"]
        radius = 21.0
        gap = 64.0
        for i, glyph in enumerate(glyphs):
            gx = cx + (i - 1) * gap
            cr.set_source_rgba(1, 1, 1, 0.10)
            cr.arc(gx, y2 + radius, radius, 0, 2 * math.pi)
            cr.fill()
            gs, gw, gh = self._word_surface(glyph, 19, (1, 1, 1), False)
            self._paint_word(cr, gs, gw, gh, gx, y2 + radius, 0.92)
        y2 += 2 * radius + 16
        ls, lw, lh = self._word_surface("󰍥  Lyrics", 15, (1, 1, 1), True)
        cr.set_source_rgba(1, 1, 1, 0.08)
        self._rounded(cr, cx - lw / 2 - 14, y2, lw + 28, lh + 10, (lh + 10) / 2)
        cr.fill()
        self._paint_word(cr, ls, lw, lh, cx, y2 + (lh + 10) / 2, 0.9)

    def on_draw(self, _area, cr, width, height, *_):
        view = self.view
        if not view.visible:
            if self._card_active():
                self._draw_card(cr, width, height)
            return
        if self.style in ("stack", "visual"):
            self._draw_rolling(cr, width, height, view)
            self._draw_credit(cr, width, height)
            return
        if self.style == "constellation":
            self._draw_constellation(cr, width, height, view)
            self._draw_credit(cr, width, height)
            return
        raster = self._raster_for(view)
        if raster is None:
            return
        now = time.monotonic()
        next_raster = self._small_raster(view.next_text, "next") if self.show_next else None
        credit = self._credit_text()
        credit_raster = self._small_raster(credit, "credit") if credit else None

        stack = raster.height
        if next_raster:
            stack += 8 + next_raster.height
        if credit_raster:
            stack += 4 + credit_raster.height
        base = {
            "top": 0.0,
            "center": (height - stack) / 2,
            "bottom": float(height - stack),
        }[self.cfg.overlay_position]

        progress = 1.0
        if self.transition_from is not None:
            progress = min(1.0, (now - self.transition_from) / TRANSITION_SECONDS)
            eased = 1 - (1 - progress) ** 3
            if self.prev_draw is not None:
                prev_raster, prev_view = self.prev_draw
                self._paint_line(cr, prev_raster, prev_view, base - eased * SLIDE_PX, 1 - eased)
            self._paint_line(cr, raster, view, base + (1 - eased) * SLIDE_PX, eased)
        else:
            self._paint_line(cr, raster, view, base, 1.0)

        y = base + raster.height
        if next_raster:
            y += 8
            cr.save()
            cr.translate(0, y)
            cr.set_source_surface(next_raster.dim, 0, 0)
            cr.paint_with_alpha(0.72)  # dim surface is 0.42 white; net ~0.30
            cr.restore()
            y += next_raster.height
        if credit_raster:
            y += 4
            cr.save()
            cr.translate(0, y)
            cr.set_source_surface(credit_raster.dim, 0, 0)
            cr.paint_with_alpha(0.6)
            cr.restore()

    def _credit_expired(self) -> bool:
        self.credit_timer = 0
        self.area.queue_draw()
        return False

    def _credit_text(self) -> str:
        """The attribution line: the first 10 s a track's lyrics are on
        screen, and whenever playback is paused."""
        state = self.state or {}
        lyrics = state.get("lyrics") or {}
        credit = lyrics.get("credit")
        if not credit:
            return ""
        paused = state.get("status") == "paused"
        return credit if (paused or time.monotonic() < self.credit_until) else ""

    def shutdown(self) -> None:
        self.cancel.cancel()
        self._drop_anim()


def run_overlay(cfg: EncoreConfig, runtime_dir: str) -> int:
    app = Gtk.Application(application_id="org.hyde.encore.overlay")
    holder: dict[str, Overlay] = {}

    def on_activate(application):
        holder["overlay"] = Overlay(application, cfg, runtime_dir)
        application.hold()

    app.connect("activate", on_activate)

    try:
        from gi.repository import GLibUnix

        signal_add = GLibUnix.signal_add
    except ImportError:  # PyGObject < 3.52
        signal_add = GLib.unix_signal_add
    import signal as signals

    for sig in (signals.SIGINT, signals.SIGTERM):
        signal_add(GLib.PRIORITY_DEFAULT, sig, lambda *_: (app.quit(), False)[1])

    code = app.run(None)
    if "overlay" in holder:
        holder["overlay"].shutdown()
    return code


if __name__ == "__main__":
    sys.exit(run_overlay(EncoreConfig(), os.environ.get("XDG_RUNTIME_DIR", "/tmp") + "/hyde"))
