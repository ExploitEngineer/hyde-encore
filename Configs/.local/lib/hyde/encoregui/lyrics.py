"""The lyric renderer shared by the desktop overlay and the full-screen page.

A LyricsEngine owns everything but the window: the daemon socket client,
the live look file, the per-style drawing and its scheduling. Its `widget`
is the snapshot canvas a host places in its own window; the host learns
through callbacks when the engine wants to be shown, when the style or
size changes the window's geometry, and when a runtime file changes.

Each line is rasterised once into a dim and a bright surface (shadow and
glow baked in); a frame then costs two clipped blits, so the steady cost
stays tiny. Scheduling: a timer runs only while a word is actively filling
or a transition plays; between words a single one-shot timeout sleeps until
the next word; paused, hidden or lyric-less states run nothing.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable
from typing import ClassVar

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gio, GLib, Graphene, Gtk, Pango, PangoCairo

from encoregui.scene import Image, Scene
from encoregui.ui import trace
from encorelib.bytecache import ByteLRU
from encorelib.codeview import code_rows, fit_scale, typed_text, typing
from encorelib.colors import resolve
from encorelib.colors import scheme as color_scheme
from encorelib.config import EncoreConfig
from encorelib.constellation import chain_words
from encorelib.glyphs import glyph_for
from encorelib.look import effective, read_look
from encorelib.lyricview import (
    COLUMN_BASE,
    HIDDEN,
    SLOT_ALPHA,
    SLOT_SCALE,
    View,
    build_view,
    column_change,
    column_slot,
    current_word_index,
    fit_zoom,
    line_unit,
    line_x,
    live_position,
    next_word_boundary,
    should_transition,
    stagger,
)
from encorelib.motion import (
    POP_SETTLE,
    SLIDE_SETTLE,
    block_moving,
    block_width,
    ease_out,
    frame_interval,
    frame_source,
    ghosts,
    held_scale,
    pop_in,
    settle_curve,
    should_draw,
)
from encorelib.palette import wallpaper_palette
from encorelib.stream import LineDecoder, should_connect
from encorelib.typeface import (
    DISPLAY_FONTS,
    PARTNER_FAMILIES,
    Faces,
    face_for,
    pango_string,
    primary_family,
    role_for,
)
from encorelib.wordrects import word_byte_ranges

TRANSITION_SECONDS = 0.22
WORD_CACHE_BYTES = 48 * 1024 * 1024
SLIDE_PX = 26
FEATHER_PX = 26
CREDIT_SECONDS = 10.0
PULSE_GAP_SECONDS = 4.0  # full screen: a soft note pulses through gaps longer than this
PULSE_MS = 50
EXIT_SECONDS = 0.3
EXIT_RISE = 0.3  # share of the height a finished column rises as it leaves
GHOST_MIN_PX = 6.0  # a ghost closer than this to its word is not drawn
COLUMN_CY = 0.42  # the big word's center: the column's larger sung word stays clear of the bar
TIMER_MS = 33  # slow motion's timer: about 30 fps
SPRING_FAST = 0.2  # a spring's first 0.2 s hold nearly all its travel: 60 fps there
FAST_SECONDS = 0.16  # ghosts trail through the first, fast part of a slide
CODE_ROWS = 6  # the code style: five past lines and the one being typed
COLUMN_ROWS = 3
CONSTELLATION_SCALE = 1.2
PAST_SCALE = 0.55
RASTER_CACHE = 6
WIDTH_FRACTION = 0.8
GLYPH_POP_SECONDS = 0.15
NEXT_LINE_BLUR = 1.5
_FAMILIES: dict | None = None
_FACES: Faces = {}
_FACE_STRINGS: dict[tuple[str, str], str] = {}


def installed_faces(wanted: tuple[str, ...] = ()) -> Faces:
    """The families this system has, with the (weight, italic) faces each ships.

    Every installed name is a key; only the display fonts, the partners and
    the `wanted` families are described (listing every face of every family
    costs about 0.2 s here, these few about a hundredth of that).
    """
    global _FAMILIES
    if _FAMILIES is None:
        _FAMILIES = {f.get_name(): f for f in PangoCairo.FontMap.get_default().list_families()}
        for name in _FAMILIES:
            _FACES.setdefault(name, set())
    for name in (*DISPLAY_FONTS, *PARTNER_FAMILIES, *wanted):
        family = _FAMILIES.get(name)
        if family is None or _FACES[name]:
            continue
        for face in family.list_faces():
            if face.is_synthesized():
                continue
            desc = face.describe()
            italic = desc.get_style() != Pango.Style.NORMAL
            _FACES[name].add((int(desc.get_weight()), italic))
    return _FACES


def face_string(font: str, role: str) -> str:
    """The Pango description a word in `role` is set in, for the look's font."""
    key = (font, role)
    hit = _FACE_STRINGS.get(key)
    if hit is None:
        have = installed_faces(tuple(name.strip() for name in font.split(",")))
        hit = _FACE_STRINGS[key] = pango_string(face_for(role, primary_family(font, have), have))
    return hit


def _hex_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    if len(color) < 6:
        return (1.0, 1.0, 1.0)
    try:
        return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (1.0, 1.0, 1.0)


def line_layout(
    text: str, font: str, size: int, width: int, align: Pango.Alignment = Pango.Alignment.CENTER
) -> Pango.Layout:
    """The layout every line raster is built from: the font's heavy face (the
    boldest it really ships up to Bold), set a little tighter than text type,
    word-wrapped at width."""
    layout = PangoCairo.create_layout(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)))
    desc = Pango.FontDescription.from_string(face_string(font, "heavy"))
    desc.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(desc)
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_letter_spacing_new(int(-0.012 * size * Pango.SCALE)))
    layout.set_attributes(attrs)
    layout.set_width(width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD)
    layout.set_alignment(align)
    layout.set_text(text, -1)
    return layout


def line_pad(size: int) -> int:
    return max(6, size // 5)  # room for the baked shadow and bloom


def line_height(layout: Pango.Layout, size: int) -> int:
    _, logical = layout.get_pixel_extents()
    return logical.height + 2 * line_pad(size)


def measure_line_height(text: str, font: str, size: int, width: int) -> int:
    """The height a LineRaster of this line would have, without rasterising it:
    a layout costs a fraction of a raster, so a long song lays out at once."""
    return line_height(line_layout(text, font, size, width), size)


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
        rest: tuple[float, float, float] = (1.0, 1.0, 1.0),
        rest_alpha: float = 0.42,
        align: Pango.Alignment = Pango.Alignment.CENTER,
    ):
        self.scale = scale
        self.key: tuple | None = None  # set by a cache that owns the raster
        layout = line_layout(text, font, size, width, align)
        self.pad = line_pad(size)
        self.height = line_height(layout, size)
        self.width = width
        self.rects = self._word_rects(layout, text, words)
        self._shadow_layer = self._shadow(layout)
        self.dim = self._render(layout, rest, rest_alpha, glow=None)
        # the lit copy is only needed by lines that fill word by word; small
        # rasters (next line, credit, card) never show it, so build it lazily
        self._layout, self._accent = layout, accent
        self._bright: cairo.ImageSurface | None = None
        self._dim_img: Image | None = None
        self._bright_img: Image | None = None

    @property
    def bright(self) -> cairo.ImageSurface:
        if self._bright is None:
            self._bright = self._render(self._layout, self._accent, 1.0, glow=self._accent)
        return self._bright

    @property
    def dim_img(self) -> Image:
        if self._dim_img is None:
            self._dim_img = Image.from_surface(self.dim, self.width, self.height)
        return self._dim_img

    @property
    def bright_img(self) -> Image:
        if self._bright_img is None:
            self._bright_img = Image.from_surface(self.bright, self.width, self.height)
        return self._bright_img

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
        pad = self.pad  # the text is drawn this far down (room for shadow and bloom)
        for word, (a, b) in zip(words, word_byte_ranges(text, words)):
            if b <= a:
                out.append([])
                continue
            last_start = b - len(word[-1].encode("utf-8"))
            xa, ya, wa, ha = self._char_box(layout, a)
            xz, yz, wz, hz = self._char_box(layout, last_start)
            ya, yz = ya + pad, yz + pad
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

    def _shadow(self, layout) -> cairo.ImageSurface:
        """A soft drop shadow, built once per line and shared by dim and bright.

        The glyph shape is filled once into an alpha mask; the blur comes from
        shifted blits of that mask (cheap pixman copies), not repeated path
        fills, which made every line change cost tens of milliseconds.
        """
        sw, sh = self.width * self.scale, self.height * self.scale
        mask = cairo.ImageSurface(cairo.FORMAT_A8, sw, sh)
        mask.set_device_scale(self.scale, self.scale)
        mc = cairo.Context(mask)
        mc.translate(0, self.pad)
        PangoCairo.layout_path(mc, layout)
        mc.fill()
        shadow = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
        shadow.set_device_scale(self.scale, self.scale)
        cr = cairo.Context(shadow)
        cr.set_source_rgba(0, 0, 0, 0.14)
        cr.mask_surface(mask, 0, 2.2)
        for radius, a in ((3.6, 0.06), (1.6, 0.1)):
            cr.set_source_rgba(0, 0, 0, a)
            for k in range(8):
                ang = k * math.pi / 4
                cr.mask_surface(mask, radius * math.cos(ang), 2.2 + radius * math.sin(ang))
        return shadow

    def _render(self, layout, rgb, alpha: float, glow) -> cairo.ImageSurface:
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self.width * self.scale, self.height * self.scale
        )
        surface.set_device_scale(self.scale, self.scale)
        cr = cairo.Context(surface)
        cr.set_source_surface(self._shadow_layer, 0, 0)
        cr.paint()
        cr.translate(0, self.pad)
        if glow is not None:
            # bloom: wide, faint strokes in the accent around sung words
            PangoCairo.layout_path(cr, layout)
            for width, a in ((12.0, 0.05), (7.0, 0.08), (3.5, 0.14)):
                cr.set_source_rgba(*glow, a)
                cr.set_line_width(width)
                cr.stroke_preserve()
            cr.new_path()
        cr.set_source_rgba(*rgb, alpha)
        cr.move_to(0, 0)
        PangoCairo.show_layout(cr, layout)
        return surface


class LyricsEngine:
    """Lyrics from the daemon, drawn in the current look onto `widget`."""

    def __init__(self, cfg: EncoreConfig, runtime_dir: str, *, desktop: bool):
        self.cfg = cfg
        # desktop: the click-through overlay (line style in a strip, no card
        # there); otherwise the full-screen page, where the line sits centered
        self.desktop = desktop
        self.position = cfg.overlay_position if desktop else "center"
        self.runtime_dir = runtime_dir
        self.socket_path = os.path.join(runtime_dir, "encore.sock")
        self.state: dict | None = None
        self.view: View = HIDDEN
        self.prev_draw: tuple[LineRaster, View] | None = None
        self.transition_from: float | None = None
        self.anim_id = 0  # the frame source (tick callback or timer) while anything moves
        self.anim_kind = "timer"
        self.drawn_at = 0.0  # the frame time of the last lyric frame the tick drew
        self.frame_now: float | None = None  # the display frame being drawn (monotonic s)
        self.timeout_id = 0
        self.rasters: dict[tuple, LineRaster] = {}
        self.small: dict[tuple, LineRaster] = {}
        # word and cover textures, bounded by bytes: big column words at 4K run to megabytes
        self.word_cache = ByteLRU(WORD_CACHE_BYTES)
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
        self.fade_words: tuple[str, ...] = ()  # the words of the line last seen
        self.line_dx = 0.0
        self.column_visible = False
        self._last_fade_key = ""
        self.places: dict[tuple, list[tuple[float, float]]] = {}
        self.decoder = LineDecoder()
        self._resolved_key = None
        self._resolved_cache = None
        self.accent_rgb: tuple[float, float, float] = (1.0, 1.0, 1.0)
        self.colors = color_scheme({}, wallpaper_palette())
        self._accent_palette: dict | None = None
        self.credit_track = ""
        self.credit_until = 0.0
        self.credit_timer = 0
        self.pulse_id = 0
        self.connection: Gio.SocketConnection | None = None
        self.connecting = False
        self.closed = False
        self.cancel = Gio.Cancellable()

        # what the host hears about
        self.wants_visible = False
        self.suspended = False
        self.on_visibility: Callable[[bool], None] | None = None
        self.on_style_changed: Callable[[str], None] | None = None
        self.on_size_changed: Callable[[], None] | None = None
        self.on_runtime_file: Callable[[str], None] | None = None

        self.widget = _Canvas(self.render)
        self.windowed = False  # the Stage: the canvas fills a resizable window
        self.screen_w, self.screen_h = 0, 0
        self.set_screen(1920, 1080)
        self._watch_runtime_dir()
        self.try_connect()

    # host ------------------------------------------------------------------

    def set_screen(self, width: int, height: int) -> None:
        """The output the canvas lives on: type and layout scale with it."""
        if (width, height) == (self.screen_w, self.screen_h):
            return
        self.screen_w, self.screen_h = width, height
        self.content_width = int(width * WIDTH_FRACTION)
        for cache in (self.rasters, self.small, self.places):
            cache.clear()
        self.word_cache = ByteLRU(WORD_CACHE_BYTES)
        self.layout_canvas()
        self.widget.queue_draw()

    def set_windowed(self, windowed: bool) -> None:
        """In the Stage the canvas fills the page: a size request there would
        stop the window from shrinking."""
        if windowed != self.windowed:
            self.windowed = windowed
            self.layout_canvas()

    def layout_canvas(self) -> None:
        """Column styles draw in a centered region on a fixed screen, so frames
        repaint less; the others, and every style in the Stage, fill their window."""
        if self.style in ("stack", "visual") and not self.windowed:
            self.widget.set_halign(Gtk.Align.CENTER)
            self.widget.set_valign(Gtk.Align.CENTER)
            self.widget.set_size_request(int(self.screen_w * 0.8), int(self.screen_h * 0.8))
        else:
            self.widget.set_halign(Gtk.Align.FILL)
            self.widget.set_valign(Gtk.Align.FILL)
            self.widget.set_size_request(-1, -1)

    def strip_height(self) -> int:
        """Height of the desktop line strip: two rows of the main line plus
        slide headroom, two of the next line, the credit. The surface is
        transparent, but every extra pixel is composited on each frame."""
        line = self._line_px()
        small = max(12, int(line * 0.6))
        return int(line * 3.6 + small * 4.2 + 40)

    def set_suspended(self, suspended: bool) -> None:
        """A hidden host stops every timer; showing again resumes at once."""
        if suspended != self.suspended:
            self.suspended = suspended
            self.apply()

    # socket ----------------------------------------------------------------

    def _watch_runtime_dir(self) -> None:
        gfile = Gio.File.new_for_path(self.runtime_dir)
        self.monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._on_dir_event)

    def _on_dir_event(self, _monitor, child, _other, event) -> None:
        path = child.get_path() or ""
        if self.on_runtime_file is not None and event in (
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.CHANGED,
            Gio.FileMonitorEvent.DELETED,
        ):
            self.on_runtime_file(os.path.basename(path))
        if event not in (Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.CHANGED):
            return
        if should_connect(path):
            self.try_connect()
        if os.path.basename(path) == "encore.look":
            self._reload_look()

    def _reload_look(self) -> None:
        self.look_cache = read_look(self.look_path)
        self.word_cache = ByteLRU(WORD_CACHE_BYTES)  # colors may have changed
        self.widget.queue_draw()
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
            self.layout_canvas()
            if self.on_style_changed is not None:
                self.on_style_changed(self.style)
        elif size_changed and self.on_size_changed is not None:
            self.on_size_changed()  # the desktop line strip's height depends on the size
        self.apply()

    def try_connect(self) -> None:
        if self.closed or self.connection is not None or self.connecting:
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

            logging.getLogger("encore").exception("lyrics apply failed")
        self._read_more()

    def _disconnect(self) -> None:
        if self.connection is not None:
            self.connection.close(None)
            self.connection = None
        self.state = None
        if self.closed:
            return
        self.apply()
        GLib.timeout_add(500, self._late_retry)

    def _late_retry(self) -> bool:
        self.try_connect()
        return False

    # scheduling ------------------------------------------------------------

    def apply(self) -> None:
        if self.closed:
            return  # an apply queued before shutdown must not start a frame source
        now = time.monotonic()
        palette = (self.state or {}).get("palette") or {}
        if palette != self._accent_palette:
            # the scheme scans the palette; rebuild it only when the palette changes
            self._accent_palette = palette
            self.colors = color_scheme(palette, wallpaper_palette())
            if self.color_override:
                self.accent_rgb = _hex_rgb(self.color_override)
            else:
                self.accent_rgb = _hex_rgb(self.colors.accent)
        view = build_view(self.state, now)
        # only the line style slides one line into the next; building its big
        # raster (shadow passes, bloom) for the other styles was pure waste
        if (
            self.style == "line"
            and should_transition(self.view.line_key, view.line_key)
            and self.view.visible
        ):
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
        if show_window != self.wants_visible:
            self.wants_visible = show_window
            if self.on_visibility is not None:
                self.on_visibility(show_window)
        if show_window and not view.visible:
            self.widget.queue_draw()  # the card is state-driven, no timers
        if self.style == "line":
            in_transition = self.transition_from is not None
            active = view.visible and (view.animating or in_transition)
            wake = view.wake_in
        else:
            self.transition_from = None
            self.prev_draw = None
            self._track_column(view, now)
            playing = (self.state or {}).get("status") == "playing"
            drifting = self._moves_on_its_own(view) and playing
            in_motion = self._in_motion(now)
            active = view.visible and (in_motion or drifting)
            wake = next_word_boundary(self.state, now) if view.visible else None
            if wake is None:
                wake = view.wake_in
        pulse = not self.suspended and self._pulse_wanted(view)
        if pulse and not self.pulse_id:
            self.pulse_id = GLib.timeout_add(PULSE_MS, self._pulse_tick)
        elif not pulse and self.pulse_id:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0
        if self.suspended:  # a hidden host costs nothing until it shows again
            self._drop_anim()
            return
        if active:
            self._ensure_anim()
        else:
            self._drop_anim()
            if view.visible and wake is not None:
                self.timeout_id = GLib.timeout_add(max(16, int(wake * 1000) + 8), self._wake)
        self.widget.queue_draw()

    def _pop_seconds(self) -> float:
        return POP_SETTLE if self.motion else 0.16

    def _slide_seconds(self) -> float:
        return SLIDE_SETTLE if self.motion else 0.16

    def _track_column(self, view: View, now: float) -> None:
        """Start the pop, slide or line exit a new view asks for (lyricview.column_change)."""
        ix = current_word_index(view) if view.visible else None
        words = tuple(t for t, _ in view.words)
        prev = (self._last_fade_key, self.fade_words, self.last_word_ix, self.column_visible)
        self.column_visible = view.visible
        change = column_change(prev, view.line_key, words, ix, view.visible, self.style != "code")
        if change is None:
            return
        if change.exit is not None:
            key, old_words, old_ix = change.exit
            self.exit_snapshot = (key, list(old_words), old_ix)
            self.exit_from = now
        if change.slide:
            self.slide_from = now
        if change.pop:
            self.fade_from = now
        self.last_word_ix, self._last_fade_key, self.fade_words = ix, view.line_key, words

    def _moves_on_its_own(self, view: View) -> bool:
        """Slow continuous motion while playing: the drift, or the code style
        typing a word out letter by letter."""
        if not view.visible:
            return False
        if self.style == "code":
            return typing(view.words)
        return self._drifts()

    def _drifts(self) -> bool:
        """Whether this style floats while playing (code stands still: a frame per word)."""
        return self.motion and self.style != "code"

    def _in_motion(self, now: float) -> bool:
        """A pop, a slide (and its ghosts) or a line's exit is under way."""
        if self.style == "code":
            return False
        return (
            (now - self.fade_from) < self._pop_seconds()
            or (now - self.slide_from) < self._slide_seconds()
            or self.exit_snapshot is not None
        )

    def _wake(self) -> bool:
        self.timeout_id = 0
        self.apply()
        return False

    def _ensure_anim(self) -> None:
        # Pops, slides and exits follow the display's frame clock: a 33 ms timer
        # drifts against the 60 Hz refresh and delivered frames 14 and 65 ms
        # apart (measured), which reads as judder where the eye tracks motion.
        # The clock runs GTK's whole frame cycle at the refresh rate, so slow
        # motion (drift, sweeps, typing) goes back to a timer (motion.frame_source).
        if not self.anim_id:
            self.drawn_at = 0.0
            self._add_source("display" if self._fast(time.monotonic()) else "timer")

    def _add_source(self, kind: str) -> None:
        self.anim_kind = kind
        if kind == "display":
            self.anim_id = self.widget.add_tick_callback(self._on_tick)
        else:
            self.frame_now = None
            self.anim_id = GLib.timeout_add(TIMER_MS, self._on_timer)

    def _drop_anim(self) -> None:
        if self.anim_id:
            if self.anim_kind == "display":
                self.widget.remove_tick_callback(self.anim_id)
            else:
                GLib.source_remove(self.anim_id)
            self.anim_id = 0
        self.frame_now = None

    def _on_tick(self, _widget, clock) -> bool:
        self.frame_now = clock.get_frame_time() / 1_000_000
        return self._animate()

    def _on_timer(self) -> bool:
        return self._animate()

    def _now(self) -> float:
        """The time a frame shows: the display frame's while the clock drives us."""
        if self.anim_id and self.anim_kind == "display" and self.frame_now is not None:
            return self.frame_now
        return time.monotonic()

    def _fast(self, now: float) -> bool:
        """A pop, slide, exit or line change is moving fast (the display clock's
        job): the first 0.2 s of a spring, where nearly all of its travel is;
        its slow tail runs on the timer."""
        if self.style == "line":
            if self.transition_from is not None and now - self.transition_from < SPRING_FAST:
                return True
            # on the show the fill edge sweeps the big line fast; the desktop
            # strip, always on, keeps it on the timer
            playing = (self.state or {}).get("status") == "playing"
            return not self.desktop and playing and self.view.visible and self.view.animating
        if self.style == "code":
            return False
        playing = (self.state or {}).get("status") == "playing"
        if self.motion and self.style == "visual" and self.view.visible and playing:
            ix = current_word_index(self.view)
            if ix >= 0 and block_moving(self.view.words[ix][1]):
                return True  # the Highlight block sweeps across its word
        return (
            now - self.fade_from < SPRING_FAST
            or now - self.slide_from < SPRING_FAST
            or self.exit_snapshot is not None
        )

    def _animate(self) -> bool:
        now = self._now()
        if self.transition_from is not None and now - self.transition_from > self._line_seconds():
            self.transition_from = None
            self.prev_draw = None
        view = build_view(self.state, now)
        changed_key = view.line_key != self.view.line_key
        self.view = view
        if self.style == "line":
            fast = self._fast(now)
            continuous = view.animating or self.transition_from is not None
        else:
            self._track_column(view, now)
            playing = (self.state or {}).get("status") == "playing"
            if self.exit_snapshot is not None and now - self.exit_from >= EXIT_SECONDS:
                self.exit_snapshot = None
            fast = self._fast(now)
            continuous = (self._moves_on_its_own(view) and playing) or self._in_motion(now)
        source = frame_source(bool(fast), bool(continuous))
        if changed_key or not view.visible or source is None:
            self.anim_id = 0
            self.frame_now = None
            GLib.idle_add(self.apply)
            return False
        if should_draw(now - self.drawn_at, frame_interval(bool(fast), bool(continuous))):
            self.drawn_at = now
            self.widget.queue_draw()
        if source != self.anim_kind:  # hand over to the other clock; this one ends
            self._add_source(source)
            return False
        return True

    # rendering -------------------------------------------------------------

    def _accent(self) -> tuple[float, float, float]:
        return self.accent_rgb

    def _raster_for(self, view: View) -> LineRaster | None:
        if not view.visible:
            return None
        rest = _hex_rgb(self.look_cache.get("lyric_color", self.colors.lyric))
        key = (view.line_key, self.size, self._accent(), rest)
        raster = self.rasters.get(key)
        if raster is None:
            trace(f"line raster {len(view.text)} chars")
            raster = LineRaster(
                view.text,
                [w for w, _ in view.words],
                self.font,
                self._line_px(),
                self.content_width,
                self._accent(),
                self.widget.get_scale_factor() or 1,
                rest=rest,
                rest_alpha=0.6,
            )
            self.rasters[key] = raster
            while len(self.rasters) > RASTER_CACHE:
                self.rasters.pop(next(iter(self.rasters)))
        return raster

    def _pulse_wanted(self, view: View) -> bool:
        """Full screen only: playing, synced lyrics, and a gap over PULSE_GAP_SECONDS away."""
        if self.desktop or view.visible or self._card_active():
            return False
        state = self.state or {}
        lyrics = state.get("lyrics") or {}
        gap = state.get("gap")
        if state.get("status") != "playing" or gap is None or lyrics.get("sync") in (None, "none"):
            return False
        until = gap.get("until")
        return until is None or until - live_position(state, time.monotonic()) > PULSE_GAP_SECONDS

    def _pulse_tick(self) -> bool:
        self.widget.queue_draw()
        return True

    def _draw_pulse(self, sc: Scene, width: float, height: float) -> None:
        size = int(self._line_px() * 1.6)
        rgb = _hex_rgb(self.look_cache.get("lyric_color", self.colors.lyric))
        key = ("pulse", size, rgb)
        raster = self.small.get(key)
        if raster is None:
            raster = LineRaster(
                "♪", ["♪"], self.font, size, size * 3, rgb, self.widget.get_scale_factor() or 1
            )
            self.small[key] = raster
        beat = 0.5 + 0.5 * math.sin(time.monotonic() * 2 * math.pi)  # 1 Hz
        alpha = 0.25 + 0.45 * beat
        sc.image(raster.bright_img, (width - raster.width) / 2, (height - raster.height) / 2, alpha)

    def _blurred_small(self, raster: LineRaster, radius: float):
        """A small raster blurred once by the renderer; (texture, margin) or None.
        Keyed by the raster's content key: an evicted raster's id comes back for
        another line, and would hand it the wrong blur."""
        key = ("blur", raster.key, radius)
        hit = self.word_cache.get(key)
        if hit is not None:
            return hit[0]
        native = self.widget.get_native()
        renderer = native.get_renderer() if native is not None else None
        if renderer is None:
            return None
        margin = int(radius * 3)
        w, h = raster.width + 2 * margin, raster.height + 2 * margin
        snapshot = Gtk.Snapshot()
        snapshot.push_blur(radius)
        Scene(snapshot).image(raster.dim_img, margin, margin)
        snapshot.pop()
        node = snapshot.to_node()
        if node is None:
            return None
        texture = renderer.render_texture(node, Graphene.Rect().init(0, 0, w, h))
        value = (texture, float(margin))
        self.word_cache.put(key, (value,), w * h * 4)
        return value

    def _line_px(self) -> int:
        """Line type size: 4% of the screen height on the desktop strip, 5.6%
        on the Stage and Full screen, at the default size 30 (lyricview.line_unit)."""
        return line_unit(getattr(self, "screen_h", 1080), self.size, self.desktop)

    def _small_raster(self, text: str, alpha_key: str) -> LineRaster | None:
        if not text:
            return None
        size = max(12, int(self._line_px() * 0.6))
        tint = _hex_rgb(self.look_cache.get("secondary_color", self.colors.secondary))
        key = (text, size, alpha_key, tint)
        raster = self.small.get(key)
        if raster is None:
            raster = LineRaster(
                text,
                [],
                self.font,
                size,
                self.content_width,
                (1, 1, 1),
                self.widget.get_scale_factor() or 1,
                rest=tint,
                rest_alpha=0.75,
            )
            raster.key = key
            self.small[key] = raster
            while len(self.small) > RASTER_CACHE:
                self.small.pop(next(iter(self.small)))
        return raster

    def _paint_line(
        self, sc: Scene, raster: LineRaster, view: View, y: float, alpha: float
    ) -> None:
        with sc.group(self.line_dx, y, alpha=alpha):
            sc.image(raster.dim_img, 0, 0)
            pad = raster.pad
            full, partial = [], None
            for rects, (_, fill) in zip(raster.rects, view.words):
                if fill >= 1.0:
                    full.extend(rects)
                elif fill > 0.0 and partial is None:
                    partial = (rects, fill)
            for x, ry, rw, rh in full:
                with sc.clip(x - 2, ry - pad, rw + 4, rh + 2 * pad):
                    sc.image(raster.bright_img, 0, 0)
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
                    top, height = ry - pad, rh + 2 * pad
                    with (
                        sc.clip(x - 2, top, min(take, rw) + 4, height),
                        sc.fade_out_right(edge - feather, edge, top, height),
                    ):
                        sc.image(raster.bright_img, 0, 0)

    def _word_surface(
        self,
        text: str,
        size: int,
        rgb,
        dim: bool,
        style: str = "heavy",
        shear: float = 0.0,
        fill: float | None = None,
    ):
        """A rendered word with baked shadow (and glow when bright).

        style: a typeface role (encorelib.typeface): heavy, semibold, medium,
        serif or mono. shear bakes a horizontal skew in, so frames can blit 1:1.
        A dim word has no glow and a 0.55 fill, unless `fill` says otherwise:
        Secondary words are drawn full, their color already sits behind.
        """
        key = (text, size, rgb, dim, style, round(shear, 3), fill)
        hit = self.word_cache.get(key)
        if hit is not None:
            return hit
        scale = self.widget.get_scale_factor() or 1
        measure = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        layout = PangoCairo.create_layout(cairo.Context(measure))
        desc = Pango.FontDescription.from_string(face_string(self.font, style))
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
        cr2.set_source_rgba(*rgb, fill if fill is not None else 0.55 if dim else 1.0)
        cr2.move_to(0, 0)
        PangoCairo.show_layout(cr2, layout)
        out = (Image.from_surface(surface, w, h), w, h)
        self.word_cache.put(key, out, surface.get_stride() * surface.get_height())
        return out

    def _paint_word(self, sc: Scene, img: Image, cx, cy, alpha=1.0, scale=1.0):
        sc.image_centered(img, cx, cy, alpha, scale)

    def _drift(self, now: float, index: int, boost: float = 1.0) -> tuple[float, float]:
        """A slow float so the constellation feels alive; still while paused."""
        if not self.motion or (self.state or {}).get("status") != "playing":
            return (0.0, 0.0)
        return (
            4.0 * boost * math.sin(now * 0.7 + index * 1.7),
            3.0 * boost * math.sin(now * 0.9 + index * 2.3 + 1.1),
        )

    def _pop(self, now: float) -> tuple[float, float]:
        """(opacity, scale) of the word being sung: it pops in on the spring."""
        return pop_in(now - self.fade_from, self.motion)

    def _line_seconds(self) -> float:
        """How long the line style's line change runs: the spring's settle."""
        return max(TRANSITION_SECONDS, POP_SETTLE if self.motion else 0.16)

    # rolling column (stack and visual styles) --------------------------------
    # Reference semantics (official hero video, 6 fps): three slots scroll up.
    # bottom = the word being sung (visual: on a sweeping Highlight marker),
    # middle = the word just sung, big; top = the word before, small.

    SLOT_SCALE: ClassVar[dict] = SLOT_SCALE
    SLOT_ALPHA: ClassVar[dict] = SLOT_ALPHA

    def _word_style(self, line_key: str, index: int, on_block: bool = False) -> str:
        return role_for(self.style, line_key, index, on_block)

    def _stagger(self, line_key: str, index: int, width: int) -> float:
        return stagger(line_key, index, width)

    def _resolved(self):
        """The scheme after look overrides and `color` (see colors.resolve).

        Frames ask several times each; it only changes with the palette or look.
        """
        key = (self.colors, tuple(sorted(self.look_cache.items())), self.color_override)
        if key != self._resolved_key:
            self._resolved_key = key
            self._resolved_cache = resolve(self.colors, self.look_cache, self.color_override)
        return self._resolved_cache

    def _trio(self) -> tuple[tuple, tuple, tuple]:
        """(lyric, highlight, secondary) colors after the user's overrides."""
        r = self._resolved()
        return _hex_rgb(r.lyric), _hex_rgb(r.highlight), _hex_rgb(r.secondary)

    def _on_highlight(self) -> tuple:
        return _hex_rgb(self._resolved().on_highlight)

    def _column_base(self, height: int) -> float:
        """Column font unit: a tenth of the screen height at the default size
        (lyricview.COLUMN_BASE), as Verci's hero sets it."""
        return getattr(self, "screen_h", height) * COLUMN_BASE * (self.size / 30.0)

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

    def _draw_rolling(self, sc: Scene, width, height, view: View) -> None:
        now = self._now()
        if self.exit_snapshot is not None:
            age = now - self.exit_from
            if age < EXIT_SECONDS:
                # line change: the finished column rises and fades as one piece,
                # its ghosts trailing below it along the same path
                key, texts, old_ix = self.exit_snapshot
                trail = ghosts(age / EXIT_SECONDS) if self.motion else []
                rise = height * EXIT_RISE
                main = (1.0, -ease_out(age / EXIT_SECONDS) * rise)
                for lag, alpha in [*reversed(trail), (0.0, 1.0)]:
                    eased = ease_out((age - lag) / EXIT_SECONDS)
                    if old_ix >= 0:
                        self._draw_column(
                            sc,
                            width,
                            height,
                            key,
                            texts,
                            old_ix,
                            1.0,
                            1.0,
                            now - lag,
                            dy=-eased * rise,
                            fade=(1 - eased) * alpha,
                            ghost_of=main if lag > 0 else None,
                            pop=False,  # the leaving column's last word is already up
                        )
            else:
                self.exit_snapshot = None
        ix = current_word_index(view)
        if ix < 0:
            return
        texts = [t for t, _ in view.words]
        age = now - self.slide_from
        main_slide = settle_curve(age, self.motion, SLIDE_SETTLE)
        if self.motion and age < FAST_SECONDS:
            # the words that moved leave ghosts along the fast part of their
            # slide, drawn first; the spring's slow tail leaves none
            for lag, alpha in reversed(ghosts(age / FAST_SECONDS)):
                slide = settle_curve(age - lag, True, SLIDE_SETTLE)
                self._draw_column(
                    sc,
                    width,
                    height,
                    view.line_key,
                    texts,
                    ix,
                    1.0,
                    slide,
                    now - lag,
                    fade=alpha,
                    ghost_of=(main_slide, 0.0),
                )
        self._draw_column(
            sc, width, height, view.line_key, texts, ix, view.words[ix][1], main_slide, now
        )

    def _draw_column(
        self,
        sc: Scene,
        width,
        height,
        line_key,
        texts,
        ix,
        fill,
        slide,
        now,
        dy=0.0,
        fade=1.0,
        ghost_of: tuple[float, float] | None = None,
        pop=True,
    ) -> None:
        """The rolling column at `now`.

        A ghost pass (`ghost_of` = the main pass's slide and dy) draws only the
        words (no Highlight block, no glyphs), faded by `fade`, and only where a
        copy lags its word by GHOST_MIN_PX or more: a copy on top of its word is
        invisible and would only cost a draw. Only the two words that travel
        farthest (the sung word and the one just sung) trail: every extra
        textured node costs the renderer, and the top words are small and fading.
        """
        ghost = ghost_of is not None
        lyric, highlight, secondary = self._trio()
        cy = height * COLUMN_CY + dy
        base = self._column_base(height)
        visual = self.style == "visual"
        alone = ix == 0  # first word of a line sits big in the middle
        timings = ((self.state or {}).get("line") or {}).get("words") or []
        for i in range(max(0, ix - 3), ix + 1):
            target = ix - i  # 0 current, 1 previous, 2 two back, 3 leaving
            if alone:
                target = 1
            slot = column_slot(ix, i, slide)
            alpha = self._lerp_slot(self.SLOT_ALPHA, slot) * fade
            if alpha <= (0.05 if ghost else 0.01):
                continue
            scale_rel = self._lerp_slot(self.SLOT_SCALE, slot)
            if i < len(timings):  # a word held longer is set larger (Verso's rule)
                held = float(timings[i].get("end", 0)) - float(timings[i].get("start", 0))
                scale_rel *= held_scale(held)
            # raster at the largest size the word passes through on its way to
            # the target slot (tilt baked in): the GPU only ever scales down,
            # with mipmaps, so slides stay crisp instead of bloating up
            target_slot = max(0, min(2, target))
            largest = max(self.SLOT_SCALE[target_slot], self.SLOT_SCALE[target_slot - 1])
            ref_size = max(12, int(base * largest))
            current = i == ix
            if current and pop:  # the word being sung pops in on the spring
                pop_alpha, pop_scale = self._pop(now)
                alpha *= pop_alpha
                scale_rel *= pop_scale
                if alpha <= 0.01:
                    continue
            zoom = max(0.05, (base * scale_rel) / ref_size)
            # the drum tilt follows the slot every frame (a transform, not baked in),
            # so a word leans smoothly as it rises instead of snapping
            shear = max(-0.2, min(0.2, -0.10 * (slot - 1)))
            sung_rgb = self._on_highlight() if visual else _hex_rgb(self._resolved().column_sung)
            if current:
                # Highlight (or `color`) when the user picked one; else the readable
                # accent, since the scheme's highlight is a block fill, too dark bare
                rgb, dim = sung_rgb, False
            elif slot >= 1.6:
                rgb, dim = secondary, True
            else:
                rgb, dim = lyric, False
            word_fill = 1.0 if dim else None  # Secondary carries its own dimming
            img, w, h = self._word_surface(
                texts[i],
                ref_size,
                rgb,
                dim,
                self._word_style(line_key, i, current and visual),
                0.0,
                word_fill,
            )
            # the word just sung hands its sung color, face and block over to its
            # resting look across the slide, instead of switching in one frame
            handover = 0.0
            if i == ix - 1 and not ghost and slide < 1.0:
                handover = 1.0 - max(0.0, min(1.0, slide))
            was = None
            if handover > 0.0:
                was = self._word_surface(
                    texts[i], ref_size, sung_rgb, False, self._word_style(line_key, i, visual)
                )
            # a long word never runs past the canvas, in the Stage least of all
            zoom = fit_zoom(zoom, w - 16, width * 0.94)
            cx = width / 2 + self._stagger(line_key, i, width)
            y = self._slot_y(slot, cy, base)
            if ghost_of is not None:
                if target > 1:  # only the sung word and the big one just sung trail
                    continue
                main_slide, main_dy = ghost_of
                main_slot = column_slot(ix, i, main_slide)
                main_y = self._slot_y(main_slot, height * COLUMN_CY + main_dy, base)
                if abs(y - main_y) < GHOST_MIN_PX:
                    continue
            if self.motion and (self.state or {}).get("status") == "playing" and current:
                cx += 2.0 * math.sin(now * 1.3 + i)
            with sc.group(cx, y, zoom, skew_x=shear):
                block_alpha = 0.0
                block = 1.0
                if current and visual and not ghost:
                    block_alpha = 0.92 * alpha
                    block = block_width(fill)
                elif visual and handover > 0.0:
                    block_alpha = 0.92 * alpha * handover  # the block fades as it rises
                if block_alpha > 0.0:
                    pad_x, pad_y = 10, 4
                    bw = (w - 16 + 2 * pad_x) * block
                    bh = h - 16 + 2 * pad_y
                    with sc.group(skew_x=-0.18 - shear):
                        sc.rect(-(w - 16) / 2 - pad_x, -bh / 2 + 1, bw, bh, highlight, block_alpha)
                if was is not None:
                    wimg, ww, wh = was
                    sc.image(wimg, -ww / 2, -wh / 2, alpha * handover)
                    sc.image(img, -w / 2, -h / 2, alpha * (1.0 - handover))
                else:
                    sc.image(img, -w / 2, -h / 2, alpha)
                if visual and slot <= 1.4 and not ghost:
                    glyph = glyph_for(texts[i])
                    if glyph:
                        gimg, gw, gh = self._word_surface(
                            glyph, max(14, int(ref_size * 0.62)), highlight, False
                        )
                        # the symbol pops in beside the word it belongs to
                        glyph_pop = (
                            1.0
                            if not current
                            else ease_out((now - self.fade_from) / GLYPH_POP_SECONDS)
                        )
                        with sc.group(w / 2 - 4 + gw / 2, 0, 0.6 + 0.4 * glyph_pop, alpha):
                            sc.image(gimg, -gw / 2, -gh / 2)

    # constellation ------------------------------------------------------------

    def _positions(self, line_key: str, words: list[str], width, height):
        word_px = self._line_px() * 1.8  # the sung word's size, as _draw_cluster sets it
        key = (line_key, width, height, word_px)
        hit = self.places.get(key)
        if hit is None:
            hit = chain_words(words, width, height, seed=line_key, word_px=word_px)
            self.places[key] = hit
            while len(self.places) > 8:
                self.places.pop(next(iter(self.places)))
        return hit

    def _draw_cluster(self, sc: Scene, width, height, line_key, texts, ix, now, fade=1.0):
        positions = self._positions(line_key, texts, width, height)
        unit = self._line_px() * 1.8  # the sung word; about 108 px at 1080p and size 30
        lyric, _highlight, secondary = self._trio()
        accent = self.accent_rgb
        # hairlines in the accent, brighter toward the newest word
        pop = ease_out((now - self.fade_from) / 0.12)  # the newest hairline draws in
        for i in range(min(ix, len(positions) - 1)):
            age = ix - 1 - i
            (x1, y1), (x2, y2) = positions[i], positions[i + 1]
            if age == 0 and pop < 1.0:
                x2, y2 = x1 + (x2 - x1) * pop, y1 + (y2 - y1) * pop
            sc.line(x1, y1, x2, y2, 2.0, accent, max(0.16, 0.55 - 0.08 * age) * fade)
        spark, _sw, _sh = self._word_surface("✦", max(12, int(unit * 0.3)), accent, False)
        past = max(16, int(unit * 0.5))
        for i in range(ix):
            dx, dy = self._drift(now, i)
            x, y = positions[i][0] + dx, positions[i][1] + dy
            self._paint_word(sc, spark, x, y - past * 1.05, 0.55 * fade)
            older = ix - 1 - i
            rgb = lyric if older < 2 else secondary
            role = self._word_style(line_key, i)
            fill = 1.0 if older >= 2 else None  # Secondary carries its own dimming
            img, _w, _h = self._word_surface(texts[i], past, rgb, older >= 2, role, 0.0, fill)
            self._paint_word(sc, img, x, y, max(0.45, 0.95 - 0.1 * older) * fade)
        if 0 <= ix < len(positions):
            role = self._word_style(line_key, ix)
            img, _w, _h = self._word_surface(texts[ix], int(unit), accent, False, role)
            alpha, zoom = self._pop(now)
            dx, dy = self._drift(now, ix, 1.6)
            x, y = positions[ix][0] + dx, positions[ix][1] + dy
            # the sparkle on the sung word breathes once a second
            beat = 0.8 + 0.2 * math.sin(now * 2 * math.pi)
            self._paint_word(sc, spark, x, y - unit * 0.62, 0.9 * beat * alpha * fade, 1.15)
            self._paint_word(sc, img, x, y, alpha * fade, zoom)

    def _draw_constellation(self, sc: Scene, width, height, view: View) -> None:
        now = self._now()
        if self.exit_snapshot is not None:
            age = now - self.exit_from
            if age < EXIT_SECONDS:
                # the finished chain rises a little and draws back as it fades,
                # so the new chain never grows on top of it
                line_key, texts, ix = self.exit_snapshot
                eased = ease_out(age / EXIT_SECONDS)
                shrink = 1.0 - 0.12 * eased
                rise = height * 0.1 * eased
                with sc.group(width / 2 * (1 - shrink), height / 2 * (1 - shrink) - rise, shrink):
                    self._draw_cluster(
                        sc, width, height, line_key, texts, ix, now, 1 - age / EXIT_SECONDS
                    )
            else:
                self.exit_snapshot = None
        ix = current_word_index(view)
        if ix < 0:
            return
        self._draw_cluster(sc, width, height, view.line_key, [t for t, _ in view.words], ix, now)

    # credit, card -------------------------------------------------------------

    # code ----------------------------------------------------------------------

    def _draw_code(self, sc: Scene, width, height, view: View) -> None:
        """Past lines as comments, the current one typed word by word, a block caret.

        The block sits centred and shrinks as one (codeview.fit_scale) when
        its widest row, the whole current line included, would not fit.
        """
        state = self.state or {}
        lines = [ln.get("text") or "" for ln in ((state.get("lyrics") or {}).get("lines") or [])]
        index = int((state.get("line") or {}).get("index", 0))
        rows = code_rows(lines, index, typed_text(view.words), CODE_ROWS)
        lyric, _highlight, secondary = self._trio()
        caret = _hex_rgb(self._resolved().sung)
        size = int(self._line_px() * 0.9)
        number_size = max(10, int(size * 0.8))
        row_h = size * 1.75
        gutter = number_size * 2.6  # room for three digits
        caret_w = size * 0.56
        drawn = []
        for row in rows:
            surface = None
            if row.text:
                rgb = lyric if row.current else secondary
                fill = None if row.current else 1.0  # Secondary carries its own dimming
                surface = self._word_surface(
                    row.text, size, rgb, not row.current, "mono", 0.0, fill
                )
            drawn.append((row, surface))
        # the whole current line sets the scale, so it holds while the line is typed
        full = self._word_surface(view.text, size, lyric, False, "mono") if view.text else None
        widths = [s[1] - 16 for _r, s in drawn if s is not None]
        if full is not None:
            widths.append(full[1] - 16 + size * 0.18 + caret_w)
        # the block (gutter and widest row) sits centred, shrunk as one to fit
        total = gutter + max(widths, default=0.0)
        scale = fit_scale([total], width * 0.9)
        text_x = line_x(width, total * scale) + gutter * scale
        with sc.group(text_x, height * 0.6, scale):
            for k, (row, surface) in enumerate(drawn):
                back = len(rows) - 1 - k  # rows above the current one
                y = -back * row_h
                alpha = 1.0 if row.current else max(0.3, 0.8 - 0.1 * back)
                number, nw, nh = self._word_surface(
                    str(row.number), number_size, secondary, True, "mono", 0.0, 1.0
                )
                sc.image(number, -number_size * 0.9 - (nw - 16) - 8, y - nh / 2, alpha)
                typed_w = 0.0
                if surface is not None:
                    img, w, h = surface
                    sc.image(img, -8, y - h / 2, alpha)
                    typed_w = w - 16
                if row.current:
                    gap = size * 0.18 if row.text else 0.0
                    sc.rect(typed_w + gap, y - size * 0.55, caret_w, size * 1.1, caret, 0.9)

    def _draw_credit(self, sc: Scene, width, height) -> None:
        credit = self._credit_text()
        if not credit:
            return
        raster = self._small_raster(credit, "credit")
        if raster is None:
            return
        sc.image(raster.dim_img, 0, height - raster.height - 14, 0.6)

    def _card_active(self) -> bool:
        if self.style == "line" and self.desktop:
            return False  # the desktop strip window has no room for the card
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

    def _cover_image(self, path: str) -> Image | None:
        key = ("cover", path)
        hit = self.word_cache.get(key)
        if hit is None:
            hit = (Image.from_file(path),)
            img = hit[0]
            self.word_cache.put(
                key, hit, img.texture.get_width() * img.texture.get_height() * 4 if img else 1
            )
        return hit[0]

    def _draw_card(self, sc: Scene, width, height) -> None:
        state = self.state or {}
        track = state.get("track") or {}
        art = track.get("art") or ""
        size = max(240.0, height * 0.30)
        cx, cy = width / 2, height * 0.42
        x, y = cx - size / 2, cy - size / 2
        sc.shadow(x, y, size, size, 24, 0.55, dy=12, blur=48)  # deep, soft, GPU-drawn
        cover = self._cover_image(art) if art else None
        if cover is not None:
            with sc.rounded_clip(x, y, size, size, 24):
                sc.cover(cover, x, y, size, size)
        else:
            sc.rounded_rect(x, y, size, size, 24, (1, 1, 1), 0.08)
        y2 = cy + size / 2 + 26
        title = track.get("title") or ""
        artist = track.get("artist") or ""
        if title:
            ts, _tw, th = self._word_surface(
                title[:48], max(21, int(self.size * 0.95)), (1, 1, 1), False
            )
            self._paint_word(sc, ts, cx, y2 + th / 2)
            y2 += th + 4
        if artist:
            asf, _aw, ah = self._word_surface(
                artist[:48], max(14, int(self.size * 0.58)), (1, 1, 1), True
            )
            self._paint_word(sc, asf, cx, y2 + ah / 2, 0.8)
            y2 += ah + 18
        # decorative pill controls (the overlay itself stays click-through)
        paused = state.get("status") == "paused"
        glyphs = ["󰒮", "󰐊" if paused else "󰏤", "󰒭"]
        radius = 21.0
        gap = 64.0
        for i, glyph in enumerate(glyphs):
            gx = cx + (i - 1) * gap
            sc.rounded_rect(gx - radius, y2, 2 * radius, 2 * radius, radius, (1, 1, 1), 0.10)
            gs, _gw, _gh = self._word_surface(glyph, 19, (1, 1, 1), False)
            self._paint_word(sc, gs, gx, y2 + radius, 0.92)
        y2 += 2 * radius + 16
        ls, lw, lh = self._word_surface("󰍥  Lyrics", 15, (1, 1, 1), True)
        sc.rounded_rect(cx - lw / 2 - 14, y2, lw + 28, lh + 10, (lh + 10) / 2, (1, 1, 1), 0.08)
        self._paint_word(sc, ls, cx, y2 + (lh + 10) / 2, 0.9)

    def render(self, snapshot, width: float, height: float) -> None:
        """One frame as GPU render nodes (see encoregui/scene.py)."""
        sc = Scene(snapshot)
        view = self.view
        if not view.visible:
            if self._card_active():
                self._draw_card(sc, width, height)
            elif self.pulse_id:
                self._draw_pulse(sc, width, height)
            return
        if self.style in ("stack", "visual"):
            self._draw_rolling(sc, width, height, view)
            self._draw_credit(sc, width, height)
            return
        if self.style == "code":
            self._draw_code(sc, width, height, view)
            self._draw_credit(sc, width, height)
            return
        if self.style == "constellation":
            self._draw_constellation(sc, width, height, view)
            self._draw_credit(sc, width, height)
            return
        raster = self._raster_for(view)
        if raster is None:
            return
        now = self._now()
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
        }[self.position]

        self.line_dx = line_x(width, raster.width)  # the line sits centred on the canvas
        if self.transition_from is not None:
            age = now - self.transition_from
            eased = ease_out(age / TRANSITION_SECONDS)
            if self.prev_draw is not None:
                prev_raster, prev_view = self.prev_draw
                self._paint_line(sc, prev_raster, prev_view, base - eased * SLIDE_PX, 1 - eased)
            # the new line pops up into place: on the spring, it rises a touch past it
            rise = settle_curve(age, self.motion, POP_SETTLE)
            self._paint_line(sc, raster, view, base + (1 - rise) * SLIDE_PX, eased)
        else:
            self._paint_line(sc, raster, view, base, 1.0)

        y = base + raster.height
        if next_raster:
            y += 8
            soft = self._blurred_small(next_raster, NEXT_LINE_BLUR)
            if soft is not None:
                texture, margin = soft
                img = Image(
                    texture, next_raster.width + 2 * margin, next_raster.height + 2 * margin
                )
                # Secondary carries its own dimming
                sc.image(img, self.line_dx - margin, y - margin)
            else:
                sc.image(next_raster.dim_img, self.line_dx, y)
            y += next_raster.height
        if credit_raster:
            y += 4
            sc.image(credit_raster.dim_img, self.line_dx, y, 0.6)

    def _credit_expired(self) -> bool:
        self.credit_timer = 0
        self.widget.queue_draw()
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
        """Stop for good: socket, timers and the runtime-dir watch."""
        self.closed = True
        self.cancel.cancel()
        self._drop_anim()
        for attr in ("timeout_id", "credit_timer", "pulse_id"):
            if getattr(self, attr):
                GLib.source_remove(getattr(self, attr))
                setattr(self, attr, 0)
        self.monitor.cancel()
        if self.connection is not None:
            self.connection.close(None)
            self.connection = None


class _Canvas(Gtk.Widget):
    """The overlay's drawing surface: frames are snapshots, composed on the GPU."""

    def __init__(self, render):
        super().__init__()
        self._render = render

    def do_snapshot(self, snapshot) -> None:
        self._render(snapshot, self.get_width(), self.get_height())
