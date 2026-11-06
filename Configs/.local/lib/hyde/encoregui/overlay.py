"""GTK4 layer-shell lyrics overlay: the desktop host of the lyric renderer.

A click-through surface on the OVERLAY layer above every window. The
drawing, the daemon socket and the look live in encoregui.lyrics; this
module owns the layer-shell window: its anchors (a strip for the line
style, the whole output for the others), the empty input region that lets
clicks through, the output it sits on, and hiding while Encore's full
screen covers that output. It never draws a full-screen cover.
"""

from __future__ import annotations

import os
import sys

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

from encoregui.lyrics import LyricsEngine
from encoregui.outputs import find_monitor, place_on
from encorelib.config import EncoreConfig
from encorelib.single import pid_alive
from encorelib.stageflag import covers

STAGE_FLAG = "encore.stage"  # written by the app while its full screen is up


class DesktopOverlay:
    def __init__(self, app: Gtk.Application, cfg: EncoreConfig, runtime_dir: str):
        self.cfg = cfg
        self.stage_path = os.path.join(runtime_dir, STAGE_FLAG)
        self.engine = LyricsEngine(cfg, runtime_dir, desktop=True)

        self.window = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(self.window)
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(self.window, "encore")
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.NONE)
        self.monitor = place_on(self.window, cfg.overlay_monitor)

        css = Gtk.CssProvider()
        css.load_from_string("window, window.background { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        # the canvas floats over an empty child, so column styles can center a
        # smaller region in the full-output window
        holder = Gtk.Overlay()
        holder.set_child(Gtk.Box())
        holder.add_overlay(self.engine.widget)
        self.window.set_child(holder)
        self.window.connect("realize", self._claim_input_shape)
        self.window.connect("map", self._claim_input_shape)

        self.hidden_by_stage = self._stage_covers_me()
        self.engine.on_visibility = lambda _show: self._sync_visibility()
        self.engine.on_style_changed = lambda _style: self._apply_style_geometry()
        self.engine.on_size_changed = self._size_window
        self.engine.on_runtime_file = self._on_runtime_file
        self._apply_style_geometry()
        self.window.present()
        self.window.set_visible(False)
        self._sync_visibility()

    # window ----------------------------------------------------------------

    def _apply_style_geometry(self) -> None:
        """A bottom/top strip for the line style; the whole output for the others."""
        full = self.engine.style != "line"
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
        monitor = find_monitor(display, self.cfg.overlay_monitor)
        if monitor is None and display.get_monitors().get_n_items():
            monitor = display.get_monitors().get_item(0)
        width = monitor.get_geometry().width if monitor else 1920
        height = monitor.get_geometry().height if monitor else 1080
        self.engine.set_screen(width, height)
        self.window.set_default_size(self.engine.content_width, self.engine.strip_height())

    def _claim_input_shape(self, window) -> None:
        surface = window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())

    # the app's full screen -------------------------------------------------

    def _stage_covers_me(self) -> bool:
        """True while the app's full screen is up on this overlay's output."""
        try:
            with open(self.stage_path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return False
        mine = self.cfg.overlay_monitor or (self.monitor.get_connector() if self.monitor else "")
        return covers(text, mine, pid_alive)  # a crashed app never keeps us hidden

    def _on_runtime_file(self, name: str) -> None:
        if name != STAGE_FLAG:
            return
        hidden = self._stage_covers_me()
        if hidden != self.hidden_by_stage:
            self.hidden_by_stage = hidden
            self._sync_visibility()

    def _sync_visibility(self) -> None:
        self.engine.set_suspended(self.hidden_by_stage)
        want = self.engine.wants_visible and not self.hidden_by_stage
        if want != self.window.get_visible():
            self.window.set_visible(want)

    def shutdown(self) -> None:
        self.engine.shutdown()


def run_overlay(cfg: EncoreConfig, runtime_dir: str) -> int:
    app = Gtk.Application(application_id="org.hyde.encore.overlay")
    holder: dict[str, DesktopOverlay] = {}

    def on_activate(application):
        holder["overlay"] = DesktopOverlay(application, cfg, runtime_dir)
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
