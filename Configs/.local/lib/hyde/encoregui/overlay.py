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

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gio, GLib, Gtk, Pango, PangoCairo
from gi.repository import Gtk4LayerShell as LayerShell

from encorelib.config import EncoreConfig
from encorelib.constellation import place_words, sparkles
from encorelib.look import effective, read_look
from encorelib.lyricview import (
    HIDDEN,
    View,
    build_view,
    current_word_index,
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
STACK_SCALE = 2.1
CONSTELLATION_SCALE = 1.5
PAST_SCALE = 0.78
SPARKS = 6
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
        self.style, self.font, self.size, self.color_override, self.show_next = effective(
            cfg, read_look(self.look_path)
        )
        self.fade_from = 0.0
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
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self.on_draw)
        self.window.set_child(self.area)
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
        self.content_width = int(screen_w * WIDTH_FRACTION)
        # room for two wrapped rows of the main and next lines plus the
        # credit; the surface is transparent, so the slack is invisible
        small = max(12, int(self.size * 0.55))
        height = int(self.size * 4.6 + small * 5.6 + 56)
        self.window.set_default_size(self.content_width, height)

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
        new = effective(self.cfg, read_look(self.look_path))
        old = (self.style, self.font, self.size, self.color_override, self.show_next)
        if new == old:
            return
        style_changed = new[0] != self.style
        self.style, self.font, self.size, self.color_override, self.show_next = new
        for cache in (self.rasters, self.small, self.word_cache, self.places):
            cache.clear()
        self._accent_palette = None  # force accent recompute (color override)
        self.transition_from = None
        self.prev_draw = None
        self.last_word_ix = None
        self.fade_from = 0.0
        if style_changed:
            self._apply_style_geometry()
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
        show_window = view.visible or self._card_active()
        if show_window != self.window.get_visible():
            self.window.set_visible(show_window)
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
                self.last_word_ix = ix
                self._last_fade_key = view.line_key
                if ix is not None and ix >= 0:
                    self.fade_from = now
            active = view.visible and (now - self.fade_from) < POP_SECONDS
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
                self.last_word_ix = ix
                self._last_fade_key = view.line_key
                if ix is not None and ix >= 0:
                    self.fade_from = now
            still = (now - self.fade_from) < POP_SECONDS
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

    def _word_surface(self, text: str, size: int, rgb, dim: bool, italic: bool = False):
        key = (text, size, rgb, dim, italic)
        hit = self.word_cache.get(key)
        if hit is not None:
            return hit
        scale = self.area.get_scale_factor() or 1
        measure = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        layout = PangoCairo.create_layout(cairo.Context(measure))
        family = "Serif" if italic else self.font
        desc = Pango.FontDescription.from_string(family + (" Italic" if italic else " Bold"))
        desc.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        _, logical = layout.get_pixel_extents()
        w, h = logical.width + 14.0, logical.height + 14.0
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w * scale), int(h * scale))
        surface.set_device_scale(scale, scale)
        cr2 = cairo.Context(surface)
        cr2.translate(7, 7)
        cr2.save()
        cr2.translate(0, 2)
        PangoCairo.layout_path(cr2, layout)
        cr2.set_source_rgba(0, 0, 0, 0.5)
        cr2.set_line_width(3.0)
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
        while len(self.word_cache) > 96:
            self.word_cache.pop(next(iter(self.word_cache)))
        return out

    def _paint_word(self, cr, surface, w, h, cx, cy, alpha=1.0, scale=1.0):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(scale, scale)
        cr.set_source_surface(surface, -w / 2, -h / 2)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _pop(self, now: float) -> tuple[float, float]:
        p = min(1.0, max(0.0, (now - self.fade_from) / POP_SECONDS))
        eased = 1 - (1 - p) ** 3
        return 0.35 + 0.65 * eased, 0.9 + 0.1 * eased

    def _draw_stack(self, cr, width, height, view: View) -> None:
        now = time.monotonic()
        ix = current_word_index(view)
        texts = [t for t, _ in view.words]
        cy = height * 0.46
        if 0 <= ix < len(texts):
            surface, w, h = self._word_surface(
                texts[ix], int(self.size * STACK_SCALE), self.accent_rgb, False
            )
            alpha, zoom = self._pop(now)
            self._paint_word(cr, surface, w, h, width / 2, cy, alpha, zoom)
            top, bottom = cy - h / 2, cy + h / 2
        else:
            top = bottom = cy
        small = max(13, int(self.size * 0.85))
        if ix > 0:
            surface, w, h = self._word_surface(texts[ix - 1], small, (1, 1, 1), True, italic=True)
            self._paint_word(cr, surface, w, h, width / 2, top - 18 - h / 2, 0.8)
        if 0 <= ix + 1 < len(texts):
            surface, w, h = self._word_surface(texts[ix + 1], small, (1, 1, 1), True, italic=True)
            self._paint_word(cr, surface, w, h, width / 2, bottom + 18 + h / 2, 0.8)

    def _positions(self, view: View, width, height):
        key = (view.line_key, width, height)
        hit = self.places.get(key)
        if hit is None:
            hit = place_words([t for t, _ in view.words], width, height, seed=view.line_key)
            self.places[key] = hit
            while len(self.places) > 8:
                self.places.pop(next(iter(self.places)))
        return hit

    def _draw_constellation(self, cr, width, height, view: View) -> None:
        now = time.monotonic()
        ix = current_word_index(view)
        if ix < 0:
            return
        texts = [t for t, _ in view.words]
        positions = self._positions(view, width, height)
        cr.set_line_width(1.0)
        cr.set_source_rgba(1, 1, 1, 0.14)
        for i in range(min(ix, len(positions) - 1)):
            cr.move_to(*positions[i])
            cr.line_to(*positions[i + 1])
            cr.stroke()
        spark, sw, sh = self._word_surface("✦", max(11, self.size // 2), (1, 1, 1), True)
        for sx, sy in sparkles(view.line_key, width, height, SPARKS):
            self._paint_word(cr, spark, sw, sh, sx, sy, 0.5)
        past = max(13, int(self.size * PAST_SCALE))
        for i in range(ix):
            surface, w, h = self._word_surface(texts[i], past, (1, 1, 1), True)
            self._paint_word(cr, surface, w, h, *positions[i], 0.85)
        surface, w, h = self._word_surface(
            texts[ix], int(self.size * CONSTELLATION_SCALE), self.accent_rgb, False
        )
        alpha, zoom = self._pop(now)
        self._paint_word(cr, surface, w, h, *positions[ix], alpha, zoom)

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
        return lyrics is None or lyrics.get("sync") == "none"

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

    def _draw_card(self, cr, width, height) -> None:
        track = (self.state or {}).get("track") or {}
        art = track.get("art") or ""
        size = 280.0
        cx, cy = width / 2, height * 0.44
        surface, _w, _h = self._cover_surface(art) if art else (None, 0, 0)
        if surface is not None:
            iw, ih = surface.get_width(), surface.get_height()
            cr.save()
            x, y = cx - size / 2, cy - size / 2
            radius = 22
            cr.new_sub_path()
            cr.arc(x + size - radius, y + radius, radius, -math.pi / 2, 0)
            cr.arc(x + size - radius, y + size - radius, radius, 0, math.pi / 2)
            cr.arc(x + radius, y + size - radius, radius, math.pi / 2, math.pi)
            cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()
            cr.clip()
            cr.translate(x, y)
            cr.scale(size / max(1, iw), size / max(1, ih))
            cr.set_source_surface(surface, 0, 0)
            cr.paint()
            cr.restore()
        title = track.get("title") or ""
        artist = track.get("artist") or ""
        y = cy + size / 2 + 18
        if title:
            ts, tw, th = self._word_surface(
                title[:60], max(20, int(self.size * 0.85)), (1, 1, 1), False
            )
            self._paint_word(cr, ts, tw, th, cx, y + th / 2)
            y += th + 2
        if artist:
            asf, aw, ah = self._word_surface(
                artist[:60], max(14, int(self.size * 0.55)), (1, 1, 1), True
            )
            self._paint_word(cr, asf, aw, ah, cx, y + ah / 2, 0.85)

    def on_draw(self, _area, cr, width, height, *_):
        view = self.view
        if not view.visible:
            if self._card_active():
                self._draw_card(cr, width, height)
            return
        if self.style == "stack":
            self._draw_stack(cr, width, height, view)
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
