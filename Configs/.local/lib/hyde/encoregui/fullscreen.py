"""The show: the lyrics big, over the cover or clear black, never a trap.

One page serves two app pages: Full screen (the window fullscreened, the
engine sized to its output) and the Stage (the same show in the normal
window, the engine sized to the window). The page hosts a LyricsEngine (the
same renderer as the desktop overlay) over a CoverBackdrop. Moving the mouse
shows a top bar (Home or Exit, Window or Full screen, style, background,
glow, look) and a bottom bar (cover, song, seek, transport, volume); three
seconds without motion fade them out and hide the pointer. Esc and the Exit
button always return to Home. While the show is in sight it writes
`encore.stage` with the output it is on, so the desktop overlay there hides;
the flag goes the moment the window is on another workspace, minimized or in
the tray.
"""

from __future__ import annotations

import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from encoregui.cover import CoverBackdrop, CoverView
from encoregui.field import AlbumField
from encoregui.glass import GlassPanel
from encoregui.home import SeekBar, Transport, VolumeControl, cover_path, meta_labels, set_meta
from encoregui.lyrics import LyricsEngine
from encoregui.popovers import build_look_menu
from encoregui.ui import icon_button, icon_image, set_icon, trace
from encorelib.look import read_look
from encorelib.screen import field_shows, screen_state
from encorelib.stageflag import render as render_flag
from encorelib.stageflag import stage_size, wanted
from encorelib.stream import STYLES

STAGE_FLAG = "encore.stage"
HIDE_AFTER_MS = int(os.environ.get("ENCORE_FULL_HIDE_MS", "3000"))  # tests keep the bars up
BAR_FADE_MS = 200
RESIZE_SETTLE_MS = 120  # the Stage engine re-lays its type once a resize settles
FULL_SEEK_PX = 420
STAGE_SEEK_PX = 240


class FullPage(Gtk.Overlay):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.engine: LyricsEngine | None = None
        self.hide_timer = 0
        self.over_bar = False
        self.stage_path = os.path.join(win.runtime_dir, STAGE_FLAG)
        self.style_buttons: dict[str, Gtk.Button] = {}
        self.monitor_handler = 0
        self.windowed = False  # the Stage: the show inside the normal window
        self.connector = "*"  # the output the window is on; "*" until known
        self.allocation = (0, 0)
        self.resize_timer = 0
        # the flag follows the window: another workspace or the tray hides nothing
        for signal in ("notify::suspended", "map", "unmap"):
            win.connect(signal, lambda *_: self.sync_flag())

        # what is shown: the show (field, backdrop and lyrics) or the idle field
        self.show = Gtk.Overlay()
        self.clear_field = AlbumField()  # under a clear background: black light, not a void
        self.show.set_child(self.clear_field)
        self.backdrop = CoverBackdrop()
        self.show.add_overlay(self.backdrop)
        self.canvas_holder = Gtk.Overlay()
        self.canvas_holder.set_child(Gtk.Box())
        self.show.add_overlay(self.canvas_holder)
        self.idle = Gtk.Overlay()
        self.idle_field = AlbumField()
        self.idle.set_child(self.idle_field)
        waiting = Gtk.Label(label="Waiting for music")
        waiting.add_css_class("idle-title")
        waiting.set_halign(Gtk.Align.CENTER)
        waiting.set_valign(Gtk.Align.CENTER)
        self.idle.add_overlay(waiting)
        self.pages = Gtk.Stack()
        self.pages.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.pages.set_transition_duration(600)
        self.pages.add_named(self.show, "show")
        self.pages.add_named(self.idle, "idle")
        self.set_child(self.pages)
        # GTK 4 has no size signal on an overlay: a drawing area that draws
        # nothing reports the page's size as it changes (the Stage follows it)
        probe = Gtk.DrawingArea()
        probe.set_can_target(False)
        probe.connect("resize", self._on_resize)
        self.add_overlay(probe)

        self.top = self._revealer(self._build_top(), Gtk.Align.START)
        self.bottom = self._revealer(self._build_bottom(), Gtk.Align.END)
        self.add_overlay(self.top)
        self.add_overlay(self.bottom)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: self._wake())
        self.add_controller(motion)
        for bar in (self.top, self.bottom):
            hover = Gtk.EventControllerMotion()
            hover.connect("enter", lambda *_: self._set_over_bar(True))
            hover.connect("leave", lambda *_: self._set_over_bar(False))
            bar.add_controller(hover)

    # bars ---------------------------------------------------------------------

    def _revealer(self, child: Gtk.Widget, valign: Gtk.Align) -> Gtk.Revealer:
        """A bar on glass that slides in from its edge of the screen."""
        glass = GlassPanel(child)
        glass.set_backdrop(self.backdrop.blurred_texture, self.backdrop)
        glass.set_halign(Gtk.Align.FILL)
        glass.set_margin_start(22)
        glass.set_margin_end(22)
        if valign == Gtk.Align.START:
            glass.set_margin_top(18)
        else:
            glass.set_margin_bottom(22)
        revealer = Gtk.Revealer()
        revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
            if valign == Gtk.Align.START
            else Gtk.RevealerTransitionType.SLIDE_UP
        )
        revealer.set_transition_duration(BAR_FADE_MS)
        revealer.set_valign(valign)
        revealer.set_child(glass)
        revealer.set_reveal_child(True)
        return revealer

    def _build_top(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=10)
        bar.add_css_class("fullbar")
        for side in ("top", "bottom"):
            getattr(bar, f"set_margin_{side}")(10)
        bar.set_margin_start(14)
        bar.set_margin_end(14)
        self.exit_button = Gtk.Button()
        self.exit_button.add_css_class("pill")
        box = Gtk.Box(spacing=6)
        close = Gtk.Image.new_from_icon_name("window-close-symbolic")
        close.set_pixel_size(14)
        box.append(close)
        self.exit_label = Gtk.Label(label="Exit full screen")
        box.append(self.exit_label)
        self.exit_button.set_child(box)
        self.exit_button.set_tooltip_text("Back to Home (Esc)")
        self.exit_button.connect("clicked", lambda *_: self.win.show_page("home"))
        bar.append(self.exit_button)
        # Full screen <-> the Stage window, the show carrying on
        self.mode_button = Gtk.Button()
        self.mode_button.add_css_class("pill")
        mode_box = Gtk.Box(spacing=6)
        self.mode_icon = icon_image("view-restore-symbolic")
        self.mode_icon.set_pixel_size(14)
        mode_box.append(self.mode_icon)
        self.mode_label = Gtk.Label(label="Window")
        mode_box.append(self.mode_label)
        self.mode_button.set_child(mode_box)
        self.mode_button.connect(
            "clicked", lambda *_: self.win.show_page("full" if self.windowed else "stage")
        )
        bar.append(self.mode_button)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)
        for style in STYLES:
            button = Gtk.Button(label=style.capitalize())
            button.add_css_class("pill")
            button.set_tooltip_text(f"{style.capitalize()} style")
            button.connect("clicked", lambda _b, s=style: self.win.look(style=s))
            self.style_buttons[style] = button
            bar.append(button)
        self.bg_button = Gtk.Button(label="Cover")
        self.bg_button.add_css_class("pill")
        self.bg_button.set_tooltip_text("Background: the album cover or clear black")
        self.bg_button.connect("clicked", lambda *_: self._toggle_background())
        bar.append(self.bg_button)
        self.glow_button = icon_button(
            "weather-clear-symbolic", lambda *_: self.win.encore("glow"), tooltip="Screen-edge glow"
        )
        bar.append(self.glow_button)
        look = icon_button(
            "preferences-color-symbolic", lambda *_: self.look_menu.popup(), tooltip="Lyrics look"
        )
        self.look_menu = build_look_menu(self.win, look)
        bar.append(look)
        return bar

    def _build_bottom(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=16)
        bar.add_css_class("fullbar")
        for side in ("top", "bottom"):
            getattr(bar, f"set_margin_{side}")(8)
        bar.set_margin_start(16)
        bar.set_margin_end(22)
        self.thumb = CoverView(56)
        self.thumb.PAD = 10
        self.thumb.set_size_request(76, 76)
        bar.append(self.thumb)
        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        meta.set_valign(Gtk.Align.CENTER)
        self.title, self.artist = meta_labels()
        for label in (self.title, self.artist):
            label.set_xalign(0)
            label.set_width_chars(22)
            label.set_max_width_chars(22)
        meta.append(self.title)
        meta.append(self.artist)
        bar.append(meta)
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        middle.set_hexpand(True)
        middle.set_valign(Gtk.Align.CENTER)
        self.seek = SeekBar(self.win, width=FULL_SEEK_PX)
        self.transport = Transport(self.win)
        middle.append(self.seek)
        middle.append(self.transport)
        bar.append(middle)
        self.volume = VolumeControl(self.win)
        self.volume.set_valign(Gtk.Align.CENTER)
        bar.append(self.volume)
        return bar

    def _set_over_bar(self, over: bool) -> None:
        self.over_bar = over
        if over:
            self._wake()

    def _wake(self) -> None:
        for bar in (self.top, self.bottom):
            bar.set_reveal_child(True)
        self.set_cursor(None)
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
        self.hide_timer = GLib.timeout_add(HIDE_AFTER_MS, self._sleep)

    def _sleep(self) -> bool:
        self.hide_timer = 0
        if self.over_bar:
            return False
        for bar in (self.top, self.bottom):
            bar.set_reveal_child(False)
        self.set_cursor(Gdk.Cursor.new_from_name("none", None))
        return False

    def _toggle_background(self) -> None:
        current = read_look(self.win.look_path).get("stage_bg", "art")
        self.win.look(stage_bg="clear" if current == "art" else "art")

    # life cycle ---------------------------------------------------------------

    def enter(self, windowed: bool = False) -> None:
        """Start drawing, or switch between Full screen and the Stage while drawing:
        the engine sizes to the output (Full screen) or to this page (Stage)."""
        trace(f"full.enter windowed={windowed}")
        self._set_windowed(windowed)
        if self.engine is None:
            self.engine = LyricsEngine(self.win.cfg, self.win.runtime_dir, desktop=False)
            self.engine.on_style_changed = lambda _s: self._sync_look()
            self.canvas_holder.add_overlay(self.engine.widget)
        self.engine.set_windowed(windowed)
        self.engine.set_suspended(False)
        # the compositor says which output the window is on, possibly after a
        # move: follow its enter-monitor events and size the engine to that output
        surface = self.win.get_surface()
        if surface is not None and not self.monitor_handler:
            self.monitor_handler = surface.connect("enter-monitor", self._on_enter_monitor)
        self._on_enter_monitor(surface, self._monitor())
        if windowed:
            self._fit_to_page()
        self._wake()

    def _set_windowed(self, windowed: bool) -> None:
        self.windowed = windowed
        self.exit_label.set_label("Home" if windowed else "Exit full screen")
        self.mode_label.set_label("Full screen" if windowed else "Window")
        set_icon(
            self.mode_icon, "view-fullscreen-symbolic" if windowed else "view-restore-symbolic"
        )
        # the bottom bar fits the window: a shorter seek bar and song column
        self.seek.scale.set_size_request(STAGE_SEEK_PX if windowed else FULL_SEEK_PX, -1)
        for label in (self.title, self.artist):
            label.set_width_chars(16 if windowed else 22)
            label.set_max_width_chars(16 if windowed else 22)
        self.mode_button.set_tooltip_text(
            "Fill the screen (F)" if windowed else "Back to the Stage window (W)"
        )

    def _on_enter_monitor(self, _surface, monitor: Gdk.Monitor | None) -> None:
        if self.win.page not in ("stage", "full"):
            return
        if monitor is not None and self.engine is not None and not self.windowed:
            geometry = monitor.get_geometry()
            self.engine.set_screen(geometry.width, geometry.height)
        # "*" hides every desktop overlay until the output is known
        self.connector = monitor.get_connector() if monitor is not None else "*"
        self.sync_flag()

    def _on_resize(self, _probe, width: int, height: int) -> None:
        if (width, height) == self.allocation:
            return
        self.allocation = (width, height)
        if self.windowed and self.engine is not None:
            # a drag resizes many times a second: lay the type out once it settles
            if self.resize_timer:
                GLib.source_remove(self.resize_timer)
            self.resize_timer = GLib.timeout_add(RESIZE_SETTLE_MS, self._resize_settled)

    def _resize_settled(self) -> bool:
        self.resize_timer = 0
        self._fit_to_page()
        return False

    def _fit_to_page(self) -> None:
        if self.engine is None or not self.windowed:
            return
        width, height = self.allocation
        if width <= 0 or height <= 0:
            return  # not allocated yet: the probe's first resize lays it out
        trace(f"full.fit {width}x{height}")
        self.engine.set_screen(*stage_size(width, height))

    def sync_flag(self) -> None:
        """Hold the flag while the show is in sight, drop it the moment it is not."""
        if wanted(self.win.page, self.win.get_mapped(), self.win.is_suspended()):
            self._write_flag(self.connector)
        else:
            self.clear_flag()

    def leave(self) -> None:
        """Stop drawing and let the desktop overlay back."""
        self.backdrop.cancel_hero()  # a hero still under way must not enter() later
        if self.engine is not None:
            self.engine.set_suspended(True)
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = 0
        if self.resize_timer:
            GLib.source_remove(self.resize_timer)
            self.resize_timer = 0
        surface = self.win.get_surface()
        if surface is not None and self.monitor_handler:
            surface.disconnect(self.monitor_handler)
            self.monitor_handler = 0
        self.set_cursor(None)
        self.clear_flag()

    def shutdown(self) -> None:
        if self.engine is not None:
            self.engine.shutdown()
            self.engine = None
        self.clear_flag()

    def _monitor(self) -> Gdk.Monitor | None:
        surface = self.win.get_surface()
        if surface is None:
            return None
        return surface.get_display().get_monitor_at_surface(surface)

    def _write_flag(self, connector: str) -> None:
        try:
            with open(self.stage_path, "w", encoding="utf-8") as f:
                f.write(render_flag(connector, os.getpid()))
        except OSError:
            pass

    def clear_flag(self) -> None:
        try:
            os.unlink(self.stage_path)
        except OSError:
            pass

    # state --------------------------------------------------------------------

    def update(self, state: dict, colors) -> None:
        mode = screen_state(state, time.monotonic())
        self.pages.set_visible_child_name("idle" if mode == "idle" else "show")
        look = read_look(self.win.look_path)
        for field in (self.idle_field, self.clear_field):
            field.set_colors(colors)
            field.set_playing(state.get("status") == "playing")
            field.set_motion(look.get("motion", True))
            field.set_gradient(look.get("gradient", 2))
        self.idle_field.set_idle(mode == "idle")  # the clear field holds whenever paused
        set_meta(self.title, self.artist, state)
        self.seek.update(state)
        self.transport.update(state)
        self.volume.update(state)
        path = cover_path(state)
        self.thumb.set_path(path)
        self.backdrop.set_path(path)
        self._sync_look()

    def _sync_look(self) -> None:
        look = read_look(self.win.look_path)
        style = look.get("style", self.win.cfg.overlay_style)
        for name, button in self.style_buttons.items():
            if (name == style) != button.has_css_class("on"):
                if name == style:
                    button.add_css_class("on")
                else:
                    button.remove_css_class("on")
        background = look.get("stage_bg", "art")
        self.backdrop.set_mode(background)
        # under a cover the field would only cost; without one it is the light
        self.clear_field.set_visible(field_shows(background, self.backdrop.texture is not None))
        label = "Cover" if background == "art" else "Clear"
        if self.bg_button.get_label() != label:
            self.bg_button.set_label(label)
        glow_on = self.win.running("encore-glow.pid")
        if glow_on != self.glow_button.has_css_class("on"):
            if glow_on:
                self.glow_button.add_css_class("on")
            else:
                self.glow_button.remove_css_class("on")
