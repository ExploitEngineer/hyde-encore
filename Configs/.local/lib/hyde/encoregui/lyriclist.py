"""The lyrics list: every line of the song as type with depth.

Each line is rasterised once (LineRaster, like the overlay) and drawn as a
texture: the current line sharp and full, each word brightening over 140 ms
as it is sung; its neighbours a step back (smaller, dimmer, softer, blurred
once into a texture), everything else two steps. The list eases to keep
the current line at 38% of the view, fades at the top and bottom, lifts a
line under the pointer and seeks on click. Frames run only while a word
brightens or the list scrolls; between words a one-shot wake sleeps until
the next word starts, so a full-window repaint (the expensive thing on
this driver) happens a few times per word, not thirty times a second.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gtk, Pango

from encoregui.lyrics import LineRaster
from encoregui.scene import Image, Scene
from encorelib.bytecache import ByteLRU
from encorelib.depth import DEPTH, scroll_target, step, visible_range
from encorelib.lyricview import LEAD_SECONDS, live_position, lyric_row, next_word_boundary
from encorelib.motion import ease_out
from encorelib.words import split_words

LINE_PX = 26
GAP = 18
EDGE_FADE = 90  # px of fade at the top and bottom
SCROLL_SECONDS = 0.42
SCROLL_MS = 50  # 20 fps: every repaint of the window costs about 10 ms on this driver
WORD_FADE = 0.15  # seconds a sung word takes to brighten (three frames)
FRAME_MS = 50
HOVER_ALPHA = 0.7
RASTER_BYTES = 24 * 1024 * 1024
PAD_X = 6


def _hex_rgb(color: str) -> tuple[float, float, float]:
    color = (color or "").lstrip("#")
    try:
        return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (0.92, 0.92, 0.94)


class LyricList(Gtk.Widget):
    def __init__(self, font: str = "SF Pro Display"):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.font = font
        self.lines: list[dict] = []
        self.key = ""
        self.state: dict = {}
        self.colors = None
        self.rasters = ByteLRU(RASTER_BYTES)
        self.blurred = ByteLRU(RASTER_BYTES)  # receded lines, blurred once, as textures
        self.tops: list[float] = []
        self.heights: list[float] = []
        self.layout_width = 0
        self.current = -1
        self.scroll = 0.0
        self.scroll_from = 0.0
        self.scroll_to = 0.0
        self.scroll_started = 0.0
        self.scroll_tick = 0
        self.anim_id = 0
        self.wake_id = 0
        self.drawn = ()  # what the last frame showed, to skip repaints that change nothing
        self.hovered = -1
        self.on_seek: Callable[[float], None] | None = None
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", lambda *_: self._set_hovered(-1))
        self.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)
        self.set_cursor_from_name("default")
        self.connect("unmap", lambda *_: self._stop_timers())

    # inputs -----------------------------------------------------------------

    def set_colors(self, colors) -> None:
        if colors is not self.colors:
            self.colors = colors
            self.rasters = ByteLRU(RASTER_BYTES)  # the type's colors changed
            self.blurred = ByteLRU(RASTER_BYTES)
            self.queue_draw()

    def set_lines(self, lines: list[dict], key: str) -> None:
        """The song's lines (dicts with start and text); key names the song."""
        if key == self.key:
            return
        self.key = key
        self.lines = [ln for ln in lines if (ln.get("text") or "").strip()]
        self.tops, self.heights = [], []
        self.layout_width = 0
        self.current = -1
        self.scroll = self.scroll_to = self.scroll_from = 0.0
        self.queue_draw()

    def set_state(self, state: dict) -> None:
        self.state = state
        current = lyric_row(state)
        if current != self.current:
            self.current = current
            self._scroll_to_current(instant=self.scroll_to == 0.0 and self.scroll == 0.0)
        self._schedule()
        shown = (current, (state.get("line") or {}).get("index"), state.get("status"))
        if shown != self.drawn:
            self.queue_draw()

    # layout -----------------------------------------------------------------

    def _ensure_layout(self, width: int) -> None:
        if self.tops and self.layout_width == width:
            return
        self.layout_width = width
        self.tops, self.heights = [], []
        y = 0.0
        for index in range(len(self.lines)):
            raster = self._raster(index, width)
            height = raster.height if raster is not None else LINE_PX * 1.4
            self.tops.append(y)
            self.heights.append(height)
            y += height + GAP

    def _raster(self, index: int, width: int) -> LineRaster | None:
        if self.colors is None or width <= 0:
            return None
        text = self.lines[index]["text"]
        rest = _hex_rgb(self.colors.lyric)
        key = (text, width, LINE_PX, rest)
        hit = self.rasters.get(key)
        if hit is not None:
            return hit[0]
        raster = LineRaster(
            text,
            split_words(text),
            self.font,
            LINE_PX,
            width,
            rest,  # sung words: the lyric color, with the bloom
            self.get_scale_factor() or 1,
            rest=rest,
            rest_alpha=1.0,  # depth sets the opacity, not the raster
            align=Pango.Alignment.LEFT,
        )
        self.rasters.put(key, (raster,), raster.width * raster.height * 8)
        return raster

    def _blurred(self, raster: LineRaster, radius: float) -> tuple[Gdk.Texture, float] | None:
        """The dim line blurred by `radius`, rendered once; (texture, margin)."""
        key = (id(raster), radius)
        hit = self.blurred.get(key)
        if hit is not None:
            return hit
        native = self.get_native()
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
        self.blurred.put(key, value, w * h * 4)
        return value

    def _scroll_to_current(self, instant: bool) -> None:
        view_h = self.get_height()
        if not self.tops or view_h <= 0:
            return
        target = scroll_target(self.tops, self.heights, self.current, view_h)
        if instant:
            self.scroll = self.scroll_to = self.scroll_from = target
            return
        self.scroll_from, self.scroll_to = self.scroll, target
        self.scroll_started = time.monotonic()
        if not self.scroll_tick:  # 30 fps, not the frame clock: half the repaints
            self.scroll_tick = GLib.timeout_add(SCROLL_MS, self._on_scroll_tick)

    def _on_scroll_tick(self) -> bool:
        t = (time.monotonic() - self.scroll_started) / SCROLL_SECONDS
        self.scroll = self.scroll_from + (self.scroll_to - self.scroll_from) * ease_out(t)
        self.queue_draw()
        if t >= 1.0:
            self.scroll = self.scroll_to
            self.scroll_tick = 0
            return False
        return True

    def scroll_to_current(self, instant: bool = False) -> None:
        """The Lyrics page's 'back to the current line' button."""
        self._scroll_to_current(instant)
        self.queue_draw()

    # word brightening ---------------------------------------------------------

    def _word_alphas(self, now: float) -> list[float]:
        """How bright each word of the current line is: 0 unsung, rising over WORD_FADE."""
        line = self.state.get("line") or {}
        words = line.get("words") or []
        position = live_position(self.state, now) + LEAD_SECONDS
        alphas = []
        for word in words:
            elapsed = position - float(word.get("start", 0.0))
            alphas.append(0.0 if elapsed < 0 else min(1.0, elapsed / WORD_FADE))
        return alphas

    def _fading(self, now: float) -> bool:
        return any(0.0 < a < 1.0 for a in self._word_alphas(now))

    def _schedule(self) -> None:
        """A 30 fps timer while a word brightens; else one wake at the next word."""
        now = time.monotonic()
        playing = self.state.get("status") == "playing" and self.get_mapped()
        if self.wake_id:
            GLib.source_remove(self.wake_id)
            self.wake_id = 0
        if playing and self._fading(now):
            if not self.anim_id:
                self.anim_id = GLib.timeout_add(FRAME_MS, self._on_frame)
            return
        if self.anim_id:
            GLib.source_remove(self.anim_id)
            self.anim_id = 0
        if playing:
            wake = next_word_boundary(self.state, now)
            if wake is not None:
                self.wake_id = GLib.timeout_add(max(16, int(wake * 1000) + 8), self._on_wake)

    def _on_frame(self) -> bool:
        self.queue_draw()
        if not self._fading(time.monotonic()) or not self.get_mapped():
            self.anim_id = 0
            self._schedule()
            return False
        return True

    def _on_wake(self) -> bool:
        self.wake_id = 0
        self.queue_draw()
        self._schedule()
        return False

    def _stop_timers(self) -> None:
        for attr in ("anim_id", "wake_id", "scroll_tick"):
            if getattr(self, attr):
                GLib.source_remove(getattr(self, attr))
                setattr(self, attr, 0)

    # pointer ----------------------------------------------------------------

    def _line_at(self, y: float) -> int:
        content_y = y + self.scroll
        for index, top in enumerate(self.tops):
            if top <= content_y <= top + self.heights[index]:
                return index
        return -1

    def _set_hovered(self, index: int) -> None:
        if index != self.hovered:
            self.hovered = index
            self.set_cursor_from_name("pointer" if index >= 0 else "default")
            self.queue_draw()

    def _on_motion(self, _controller, _x, y) -> None:
        self._set_hovered(self._line_at(y))

    def _on_click(self, _gesture, _n, _x, y) -> None:
        index = self._line_at(y)
        if index >= 0 and self.on_seek is not None:
            self.on_seek(float(self.lines[index].get("start") or 0))

    # drawing ----------------------------------------------------------------

    def do_snapshot(self, snapshot) -> None:
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0 or not self.lines or self.colors is None:
            return
        self._ensure_layout(w - 2 * PAD_X)
        if self.scroll_to == 0.0 and self.current >= 0 and self.tops:
            # first frame with a size: land on the current line without a scroll
            self.scroll = self.scroll_to = self.scroll_from = scroll_target(
                self.tops, self.heights, self.current, h
            )
        sc = Scene(snapshot)
        now = time.monotonic()
        line = self.state.get("line") or {}
        self.drawn = (self.current, line.get("index"), self.state.get("status"))
        first, last = visible_range(self.tops, self.heights, self.scroll, h)
        if True:  # per-line edge fade: an alpha each, never a mask (an offscreen per paint)
            for index in range(first, last + 1):
                raster = self._raster(index, w - 2 * PAD_X)
                if raster is None:
                    continue
                depth = step(index - self.current) if self.current >= 0 else 1  # plain: readable
                scale, alpha, blur = DEPTH[depth]
                if index == self.hovered and index != self.current:
                    alpha = max(alpha, HOVER_ALPHA)
                    blur = min(blur, 1.0)
                y = self.tops[index] - self.scroll
                cx, cy = PAD_X + raster.width / 2, y + raster.height / 2
                alpha *= max(0.0, min(1.0, cy / EDGE_FADE, (h - cy) / EDGE_FADE))
                if alpha <= 0.01:
                    continue
                with sc.group(cx, cy, scale, alpha):
                    if index == self.current and line:
                        self._paint_current(sc, raster, self._word_alphas(now))
                    elif blur > 0 and (soft := self._blurred(raster, blur)) is not None:
                        texture, margin = soft
                        img = Image(texture, raster.width + 2 * margin, raster.height + 2 * margin)
                        sc.image(img, -raster.width / 2 - margin, -raster.height / 2 - margin)
                    else:
                        sc.image(raster.dim_img, -raster.width / 2, -raster.height / 2)

    def _paint_current(self, sc: Scene, raster: LineRaster, alphas: list[float]) -> None:
        """The current line: unsung words at 55%, each sung word brightening in place."""
        ox, oy = -raster.width / 2, -raster.height / 2
        sc.image(raster.dim_img, ox, oy, 0.55)
        pad = raster.pad
        for rects, alpha in zip(raster.rects, alphas):
            if alpha <= 0.0:
                continue
            for x, ry, rw, rh in rects:
                with sc.clip(ox + x - 2, oy + ry - pad, rw + 4, rh + 2 * pad):
                    sc.image(raster.bright_img, ox, oy, alpha)
