"""Screen-edge glow that breathes with the music.

One click-through layer-shell window covers the whole output; each tick
paints all four edges into a 1/DOWNSCALE texture that GSK stretches on
the GPU. Two comets circle the frame in the album colors. While music
plays the intensity rides a beat envelope fed by HyDE's cava socket when
it exists, else a slow breathe. Paused shows a faint static glow;
stopped hides entirely.
"""

from __future__ import annotations

import logging
import math
import os
import time

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

from encoregui.outputs import place_on
from encorelib.colors import scheme as color_scheme
from encorelib.config import EncoreConfig
from encorelib.glowfield import comet_strength, edge_mix, falloff_stops, perimeter_u
from encorelib.look import read_look
from encorelib.palette import wallpaper_palette
from encorelib.stream import LineDecoder

THICKNESS = 130
DOWNSCALE = 4
FRAME_MS = (
    80  # slow comets and breathing read smooth at 12 fps; 4 windows x 20 fps cost 12% of a core
)
BASE_ALPHA = 0.30
BEAT_ALPHA = 0.55
RELEASE = 0.90
EDGES = (
    ("top", LayerShell.Edge.TOP, (LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT)),
    ("bottom", LayerShell.Edge.BOTTOM, (LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT)),
    ("left", LayerShell.Edge.LEFT, (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM)),
    ("right", LayerShell.Edge.RIGHT, (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM)),
)


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
        self.album_accent = (1.0, 1.0, 1.0)
        self.album_accent2 = (1.0, 1.0, 1.0)
        self.palette: dict | None = None
        self.look_path = os.path.join(runtime_dir, "encore.look")
        self.look: dict = {}
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
        # ONE click-through window over the whole output: a single GL frame
        # per tick (four strip windows cost 4x the per-frame GTK overhead)
        window = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(window)
        LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(window, "encore-glow")
        LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.NONE)
        for _name, edge, _sides in EDGES:
            LayerShell.set_anchor(window, edge, True)
        # cover the true screen edge, waybar and corners included
        LayerShell.set_exclusive_zone(window, -1)
        place_on(window, cfg.glow_monitor)
        self.placed_monitor = cfg.glow_monitor
        display = window.get_display()
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        # a small texture stretched by the GPU: the CPU only rasterises
        # 1/DOWNSCALE of the frame, GSK scales it with linear filtering
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.FILL)
        picture.set_can_shrink(True)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        window.set_child(picture)

        def claim(win):
            surface = win.get_surface()
            if surface is not None:
                surface.set_input_region(cairo.Region())

        window.connect("realize", claim)
        window.connect("map", claim)
        window.present()
        window.set_visible(False)  # nothing shows until the daemon speaks
        self.windows.append(("frame", window, picture))

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
        self._load_look()
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
        elif name == "encore.look":
            self._load_look()

    def _load_look(self) -> None:
        """Glow settings from the player's popover, applied live."""
        self.look = read_look(self.look_path)
        self._resolve_colors()
        self._place()
        self._queue()

    def _place(self) -> None:
        """Pin the glow to the chosen display; a layer surface moves by remapping."""
        wanted = self.look.get("glow_monitor") or self.cfg.glow_monitor
        if wanted == self.placed_monitor:
            return
        self.placed_monitor = wanted
        _, window, _picture = self.windows[0]
        shown = window.get_visible()
        if shown:
            window.set_visible(False)
        place_on(window, wanted)
        if shown:
            window.set_visible(True)

    def _resolve_colors(self) -> None:
        look = self.look
        if look.get("glow_override"):
            primary = _hex_rgb(look.get("glow_primary", "#6B7CE8").lstrip("#"))
            secondary = _hex_rgb(look.get("glow_secondary", "#C86BE8").lstrip("#"))
        else:
            primary, secondary = self.album_accent, self.album_accent2
        self.accent = primary
        self.accent2 = secondary if look.get("glow_colors", 2) == 2 else primary

    @property
    def thickness(self) -> int:
        return self.look.get("glow_thickness", THICKNESS)

    @property
    def intensity(self) -> float:
        return self.look.get("glow_intensity", 85) / 85.0

    def _on_state_line(self, line: bytes) -> None:
        for state in self.decoder.feed(line + b"\n"):
            self.status = state.get("status") or "stopped"
            palette = state.get("palette") or {}
            if palette != self.palette:
                # same scheme as the lyrics: grey covers fall back to the theme
                self.palette = palette
                colors = color_scheme(palette, wallpaper_palette())
                self.album_accent = _hex_rgb(colors.accent)
                self.album_accent2 = _hex_rgb(colors.accent2)
                self._resolve_colors()
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
            alpha = BASE_ALPHA + BEAT_ALPHA * self.envelope
        else:
            alpha = 0.28  # paused: a calm, even frame, still clearly there
        return min(1.0, alpha * self.intensity)

    def _tick(self) -> bool:
        now = time.monotonic()
        dt, self.last_tick = now - self.last_tick, now
        animation = self.look.get("glow_animation", "music")
        if animation == "static":
            self.envelope = 0.55
        elif animation == "breathe" or self.cava_feed.connection is None:
            self.envelope = 0.5 + 0.5 * math.sin(now * 1.6)
        else:
            self.envelope *= RELEASE
        # the gradient flows along the edges, faster on the beat
        # comets lap the frame every ~10 s, faster on the beat
        self.phase = (self.phase + dt * (0.09 + 0.25 * self.envelope)) % 1.0
        self._queue()
        return True

    def _queue(self) -> None:
        for _name, window, picture in self.windows:
            if not window.get_visible():
                continue
            full_w = window.get_width() or 1920
            full_h = window.get_height() or 1080
            picture.set_paintable(self._frame_texture(full_w, full_h))

    def _frame_texture(self, full_w: int, full_h: int) -> Gdk.Texture:
        small_w = max(1, -(-full_w // DOWNSCALE))
        small_h = max(1, -(-full_h // DOWNSCALE))
        band = max(2, -(-self.thickness // DOWNSCALE))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, small_w, small_h)
        cr = cairo.Context(surface)
        cr.set_operator(cairo.OPERATOR_ADD)  # overlapping corners glow brighter
        for name, (x, y, w, h) in (
            ("top", (0, 0, small_w, band)),
            ("bottom", (0, small_h - band, small_w, band)),
            ("left", (0, 0, band, small_h)),
            ("right", (small_w - band, 0, band, small_h)),
        ):
            cr.save()
            cr.rectangle(x, y, w, h)
            cr.clip()
            cr.translate(x, y)
            self._paint_strip(cr, w, h, name, small_w, small_h)
            cr.restore()
        surface.flush()
        data = GLib.Bytes.new(bytes(surface.get_data()))
        return Gdk.MemoryTexture.new(
            small_w, small_h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, data, surface.get_stride()
        )

    def _paint_strip(self, cr, width, height, name, frame_w, frame_h) -> None:
        alpha = self._alpha()
        self.drawn_alpha = alpha
        horizontal = name in ("top", "bottom")
        along = (
            cairo.LinearGradient(0, 0, width, 0)
            if horizontal
            else cairo.LinearGradient(0, 0, 0, height)
        )
        stops = 25
        playing = self.status == "playing"
        for i in range(stops):
            t = i / (stops - 1)
            u = perimeter_u(name, t, frame_w, frame_h)
            mix = edge_mix(u, self.phase * 0.5)
            r = self.accent[0] * mix + self.accent2[0] * (1 - mix)
            g = self.accent[1] * mix + self.accent2[1] * (1 - mix)
            b = self.accent[2] * mix + self.accent2[2] * (1 - mix)
            # comets ride a steady base glow while playing; paused is even
            strength = 0.5 + 0.5 * comet_strength(u, self.phase) if playing else 0.8
            along.add_color_stop_rgba(t, r, g, b, strength)
        if name == "top":
            fade = cairo.LinearGradient(0, 0, 0, height)
        elif name == "bottom":
            fade = cairo.LinearGradient(0, height, 0, 0)
        elif name == "left":
            fade = cairo.LinearGradient(0, 0, width, 0)
        else:
            fade = cairo.LinearGradient(width, 0, 0, 0)
        for offset, a in falloff_stops(alpha):
            fade.add_color_stop_rgba(offset, 1, 1, 1, a)
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
