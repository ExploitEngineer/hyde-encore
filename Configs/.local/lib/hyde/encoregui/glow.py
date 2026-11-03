"""Screen-edge glow that breathes with the music.

Four thin layer-shell strips (one per edge) fade from the album accent
to transparent. While music plays the intensity rides a beat envelope
fed by HyDE's cava socket when it exists, else a slow breathe. Paused
shows a faint static glow; stopped hides entirely.
"""

from __future__ import annotations

import colorsys
import logging
import math
import os
import time

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gio, GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

from encorelib.config import EncoreConfig
from encorelib.palette import pick_accent
from encorelib.stream import LineDecoder

THICKNESS = 110
FRAME_MS = 50  # breathing is slow; beat attacks land on the next frame anyway
BASE_ALPHA = 0.30
BEAT_ALPHA = 0.55
RELEASE = 0.90
EDGES = (
    ("top", LayerShell.Edge.TOP, (LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT)),
    ("bottom", LayerShell.Edge.BOTTOM, (LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT)),
    ("left", LayerShell.Edge.LEFT, (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM)),
    ("right", LayerShell.Edge.RIGHT, (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM)),
)


def _shift_hue(rgb: tuple[float, float, float], amount: float) -> tuple[float, float, float]:
    h, lightness, sat = colorsys.rgb_to_hls(*rgb)
    return colorsys.hls_to_rgb((h + amount) % 1.0, lightness, sat)


def _hex_rgb(color: str) -> tuple[float, float, float]:
    try:
        return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (1.0, 1.0, 1.0)


class _SocketFeed:
    """Line-based reader with reconnect, for encore.sock and cava.sock."""

    def __init__(self, path: str, on_line, cancel: Gio.Cancellable, on_close=None):
        self.path = path
        self.on_line = on_line
        self.on_close = on_close
        self.cancel = cancel
        self.decoder_tail = b""
        self.connection: Gio.SocketConnection | None = None
        self.connecting = False

    def try_connect(self) -> None:
        if self.connection is not None or self.connecting or not os.path.exists(self.path):
            return
        self.connecting = True
        client = Gio.SocketClient()
        client.connect_async(Gio.UnixSocketAddress.new(self.path), self.cancel, self._on_connected)

    def _on_connected(self, client, result) -> None:
        self.connecting = False
        try:
            self.connection = client.connect_finish(result)
        except GLib.Error:
            self.connection = None
            GLib.timeout_add(500, lambda: (self.try_connect(), False)[1])
            return
        self.decoder_tail = b""
        self._read_more()

    def _read_more(self) -> None:
        stream = self.connection.get_input_stream()
        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, self.cancel, self._on_read)

    def _on_read(self, stream, result) -> None:
        try:
            data = stream.read_bytes_finish(result)
        except GLib.Error:
            data = None
        if data is None or data.get_size() == 0:
            if self.connection is not None:
                self.connection.close(None)
                self.connection = None
            if self.on_close is not None:
                self.on_close()
            GLib.timeout_add(500, lambda: (self.try_connect(), False)[1])
            return
        self.decoder_tail += data.get_data()
        *lines, self.decoder_tail = self.decoder_tail.split(b"\n")
        if len(self.decoder_tail) > 65536:
            self.decoder_tail = b""
        for line in lines:
            try:
                self.on_line(line)
            except Exception:
                logging.getLogger("encore").exception("glow feed line failed")
        self._read_more()


class Glow:
    def __init__(self, app: Gtk.Application, cfg: EncoreConfig, runtime_dir: str):
        self.cfg = cfg
        self.accent = (1.0, 1.0, 1.0)
        self.accent2 = (1.0, 1.0, 1.0)
        self.status = "stopped"
        self.phase = 0.0
        self.last_tick = time.monotonic()
        self.envelope = 0.0
        self.cava_max = 8.0
        self.timer = 0
        self.drawn_alpha = -1.0
        self.decoder = LineDecoder()
        self.cancel = Gio.Cancellable()
        self.windows: list[tuple[str, Gtk.ApplicationWindow, Gtk.DrawingArea]] = []

        css = Gtk.CssProvider()
        css.load_from_string("window, window.background { background: transparent; }")
        display = None
        for name, edge, sides in EDGES:
            window = Gtk.ApplicationWindow(application=app)
            LayerShell.init_for_window(window)
            LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(window, f"encore-glow-{name}")
            LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.NONE)
            LayerShell.set_anchor(window, edge, True)
            for side in sides:
                LayerShell.set_anchor(window, side, True)
            # cover the true screen edge, waybar and corners included
            LayerShell.set_exclusive_zone(window, -1)
            if name in ("top", "bottom"):
                window.set_default_size(-1, THICKNESS)
            else:
                window.set_default_size(THICKNESS, -1)
            if display is None:
                display = window.get_display()
                Gtk.StyleContext.add_provider_for_display(
                    display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER
                )
            area = Gtk.DrawingArea()
            area.set_draw_func(self._draw, name)
            window.set_child(area)

            def claim(win):
                surface = win.get_surface()
                if surface is not None:
                    surface.set_input_region(cairo.Region())

            window.connect("realize", claim)
            window.connect("map", claim)
            window.present()
            window.set_visible(False)  # nothing shows until the daemon speaks
            self.windows.append((name, window, area))

        self.state_feed = _SocketFeed(
            os.path.join(runtime_dir, "encore.sock"),
            self._on_state_line,
            self.cancel,
            on_close=self._on_state_gone,
        )
        self.cava_feed = _SocketFeed(
            os.path.join(runtime_dir, "cava.sock"), self._on_cava_line, self.cancel
        )
        gfile = Gio.File.new_for_path(runtime_dir)
        self.monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._on_dir_event)
        self.state_feed.try_connect()
        self.cava_feed.try_connect()
        self._schedule()

    def _on_state_gone(self) -> None:
        self.status = "stopped"
        self._schedule()

    # feeds ------------------------------------------------------------------

    def _on_dir_event(self, _monitor, child, _other, event) -> None:
        if event not in (Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.CHANGED):
            return
        name = os.path.basename(child.get_path() or "")
        if name == "encore.sock":
            self.state_feed.try_connect()
        elif name == "cava.sock":
            self.cava_feed.try_connect()

    def _on_state_line(self, line: bytes) -> None:
        for state in self.decoder.feed(line + b"\n"):
            self.status = state.get("status") or "stopped"
            palette = state.get("palette") or {}
            self.accent = _hex_rgb(pick_accent(palette))
            second = palette.get("3xa8") or palette.get("2xa8") or ""
            self.accent2 = _hex_rgb(second) if second else _shift_hue(self.accent, 0.12)
        self._schedule()

    def _on_cava_line(self, line: bytes) -> None:
        try:
            bars = [int(v) for v in line.decode().strip().strip(";").split(";") if v]
        except ValueError:
            return
        if not bars:
            return
        peak = max(bars)
        self.cava_max = max(self.cava_max * 0.995, float(peak), 8.0)
        energy = (sum(bars) / len(bars)) / self.cava_max
        self.envelope = max(self.envelope, min(1.0, energy * 1.6))

    # animation ----------------------------------------------------------------

    def _schedule(self) -> None:
        playing = self.status == "playing"
        if playing and not self.timer:
            self.timer = GLib.timeout_add(FRAME_MS, self._tick)
        if not playing and self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        visible = self.status in ("playing", "paused")
        for _, window, _area in self.windows:
            if window.get_visible() != visible:
                window.set_visible(visible)
        self._queue()

    def _alpha(self) -> float:
        if self.status == "playing":
            return BASE_ALPHA + BEAT_ALPHA * self.envelope
        return 0.18

    def _tick(self) -> bool:
        now = time.monotonic()
        dt, self.last_tick = now - self.last_tick, now
        if self.cava_feed.connection is None:
            self.envelope = 0.5 + 0.5 * math.sin(now * 1.6)
        else:
            self.envelope *= RELEASE
        # the gradient flows along the edges, faster on the beat
        self.phase = (self.phase + dt * (0.05 + 0.22 * self.envelope)) % 1.0
        self._queue()
        return True

    def _queue(self) -> None:
        for _, _window, area in self.windows:
            area.queue_draw()

    def _draw(self, _area, cr, width, height, name) -> None:
        alpha = self._alpha()
        self.drawn_alpha = alpha
        # color flowing along the edge between the two album accents
        if name in ("top", "bottom"):
            along = cairo.LinearGradient(0, 0, width, 0)
        else:
            along = cairo.LinearGradient(0, 0, 0, height)
        for i in range(7):
            t = i / 6
            mix = 0.5 + 0.5 * math.sin(2 * math.pi * (t * 1.5 - self.phase))
            r = self.accent[0] * mix + self.accent2[0] * (1 - mix)
            g = self.accent[1] * mix + self.accent2[1] * (1 - mix)
            b = self.accent[2] * mix + self.accent2[2] * (1 - mix)
            along.add_color_stop_rgba(t, r, g, b, 1.0)
        if name == "top":
            fade = cairo.LinearGradient(0, 0, 0, height)
        elif name == "bottom":
            fade = cairo.LinearGradient(0, height, 0, 0)
        elif name == "left":
            fade = cairo.LinearGradient(0, 0, width, 0)
        else:
            fade = cairo.LinearGradient(width, 0, 0, 0)
        fade.add_color_stop_rgba(0.0, 1, 1, 1, alpha)
        fade.add_color_stop_rgba(0.55, 1, 1, 1, alpha * 0.25)
        fade.add_color_stop_rgba(1.0, 1, 1, 1, 0.0)
        cr.set_source(along)
        cr.mask(fade)

    def shutdown(self) -> None:
        self.cancel.cancel()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0


def run_glow(cfg: EncoreConfig, runtime_dir: str) -> int:
    app = Gtk.Application(application_id="org.hyde.encore.glow")
    holder: dict[str, Glow] = {}

    def on_activate(application):
        holder["glow"] = Glow(application, cfg, runtime_dir)
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
    if "glow" in holder:
        holder["glow"].shutdown()
    return code
