"""Full screen: the lyrics big, over the cover or clear black, never a trap.

The page hosts a LyricsEngine (the same renderer as the desktop overlay)
over a CoverBackdrop. Moving the mouse shows a top bar (Exit, style,
background, glow, look) and a bottom bar (cover, song, seek, transport,
volume); three seconds without motion fade them out and hide the pointer.
Esc and the Exit button always return to Home. While the page is up it
writes `encore.stage` with the output it covers, so the desktop overlay on
that output hides itself.
"""

from __future__ import annotations

import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from encoregui.cover import CoverBackdrop, CoverView
from encoregui.home import SeekBar, Transport, VolumeControl, cover_path, meta_labels, set_meta
from encoregui.idle import IdleField
from encoregui.lyrics import LyricsEngine
from encoregui.popovers import build_look_menu
from encoregui.ui import icon_button
from encorelib.look import read_look
from encorelib.screen import screen_state
from encorelib.stream import STYLES

STAGE_FLAG = "encore.stage"
HIDE_AFTER_MS = int(os.environ.get("ENCORE_FULL_HIDE_MS", "3000"))  # tests keep the bars up
BAR_FADE_MS = 200


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

        # what is shown: the show (backdrop and lyrics) or the idle field
        self.show = Gtk.Overlay()
        self.backdrop = CoverBackdrop()
        self.show.set_child(self.backdrop)
        self.canvas_holder = Gtk.Overlay()
        self.canvas_holder.set_child(Gtk.Box())
        self.show.add_overlay(self.canvas_holder)
        self.idle = Gtk.Overlay()
        self.idle_field = IdleField()
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
        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        revealer.set_transition_duration(BAR_FADE_MS)
        revealer.set_valign(valign)
        revealer.set_child(child)
        revealer.set_reveal_child(True)
        return revealer

    def _build_top(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=10)
        bar.add_css_class("fullbar")
        bar.set_margin_top(18)
        bar.set_margin_start(22)
        bar.set_margin_end(22)
        exit_button = Gtk.Button()
        exit_button.add_css_class("pill")
        box = Gtk.Box(spacing=6)
        close = Gtk.Image.new_from_icon_name("window-close-symbolic")
        close.set_pixel_size(14)
        box.append(close)
        box.append(Gtk.Label(label="Exit full screen"))
        exit_button.set_child(box)
        exit_button.set_tooltip_text("Back to the window (Esc)")
        exit_button.connect("clicked", lambda *_: self.win.show_page("home"))
        bar.append(exit_button)
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
        bar.set_margin_bottom(22)
        bar.set_margin_start(26)
        bar.set_margin_end(26)
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
        self.seek = SeekBar(self.win, width=420)
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

    def enter(self) -> None:
        """Start drawing: a fresh engine sized to the output the window is on."""
        if self.engine is None:
            self.engine = LyricsEngine(self.win.cfg, self.win.runtime_dir, desktop=False)
            self.engine.on_style_changed = lambda _s: self._sync_look()
            self.canvas_holder.add_overlay(self.engine.widget)
        self.engine.set_suspended(False)
        # the compositor says which output the window is on, possibly after a
        # move: follow its enter-monitor events and size the engine to that output
        surface = self.win.get_surface()
        if surface is not None and not self.monitor_handler:
            self.monitor_handler = surface.connect("enter-monitor", self._on_enter_monitor)
        self._on_enter_monitor(surface, self._monitor())
        self._wake()

    def _on_enter_monitor(self, _surface, monitor: Gdk.Monitor | None) -> None:
        if self.win.page != "full":
            return
        if monitor is not None:
            geometry = monitor.get_geometry()
            if self.engine is not None:
                self.engine.set_screen(geometry.width, geometry.height)
        # "*" hides every desktop overlay until the output is known
        self._write_flag(monitor.get_connector() if monitor is not None else "*")

    def leave(self) -> None:
        """Stop drawing and let the desktop overlay back."""
        if self.engine is not None:
            self.engine.set_suspended(True)
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = 0
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
                f.write(connector + "\n")
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
        self.idle_field.set_colors(colors)
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
        label = "Cover" if background == "art" else "Clear"
        if self.bg_button.get_label() != label:
            self.bg_button.set_label(label)
        glow_on = self.win.running("encore-glow.pid")
        if glow_on != self.glow_button.has_css_class("on"):
            if glow_on:
                self.glow_button.add_css_class("on")
            else:
                self.glow_button.remove_css_class("on")
