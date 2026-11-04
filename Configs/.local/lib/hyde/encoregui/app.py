"""The Encore app: one window you open from the app launcher.

A unique Gtk.Application (`org.hyde.encore`): launching Encore again brings
the open window forward, and `encore app --open <page>` switches the open
window to that page. The window polls the daemon's state and hands it to
each page; the pages call back into the window for player commands and look
changes, so the actions live in one place.
"""

from __future__ import annotations

import os
import subprocess

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from encoregui.home import HomePage, LyricsPage
from encoregui.popovers import build_look_menu, build_settings_popover
from encoregui.ui import accent_rules, hex_rgb, icon_button, install_css
from encorelib.colors import scheme as color_scheme
from encorelib.look import state_look_path, update_look
from encorelib.palette import wallpaper_palette
from encorelib.protocol import read_state
from encorelib.single import pid_alive, read_pid

APP_ID = os.environ.get("ENCORE_APP_ID", "org.hyde.encore")
POLL_MS = 400
PAGES = ("home", "lyrics")


class EncoreWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, runtime_dir: str):
        super().__init__(application=app, title="Encore")
        self.runtime_dir = runtime_dir
        self.look_path = f"{runtime_dir}/encore.look"
        self.look_state = state_look_path()  # every change is kept for the next boot
        self.sock_path = f"{runtime_dir}/encore.sock"
        self.add_css_class("encore-app")
        self.set_default_size(960, 660)
        self.state: dict = {}
        self.palette: dict | None = None
        self.colors = color_scheme({}, wallpaper_palette())
        self.accent = hex_rgb(self.colors.accent)
        self.accent_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.accent_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
        )
        self.accent_css.load_from_string(accent_rules(self.colors))
        self.page = "home"

        overlay = Gtk.Overlay()
        self.set_child(overlay)
        self.backdrop = Gtk.DrawingArea()
        self.backdrop.set_draw_func(self._draw_backdrop)
        overlay.set_child(self.backdrop)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay.add_overlay(root)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(220)
        self.stack.set_vexpand(True)
        root.append(self.stack)
        self.home = HomePage(self)
        self.lyrics = LyricsPage(self)
        self.stack.add_named(self.home, "home")
        self.stack.add_named(self.lyrics, "lyrics")
        root.append(self._build_toolbar())

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        self._poll()
        GLib.timeout_add(POLL_MS, self._poll)
        GLib.idle_add(lambda: (self.set_focus(None), False)[1])  # no focus ring at open

    # pages ------------------------------------------------------------------

    def show_page(self, name: str) -> None:
        if name not in PAGES:
            name = "home"
        self.page = name
        self.stack.set_visible_child_name(name)
        if name == "lyrics":
            GLib.timeout_add(260, lambda: (self.lyrics.scroll_to_current(True), False)[1])

    def toggle_lyrics(self) -> None:
        self.show_page("home" if self.page == "lyrics" else "lyrics")

    def _build_toolbar(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=10)
        bar.add_css_class("bottombar")
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_margin_bottom(26)
        palette = icon_button(
            "preferences-color-symbolic", lambda *_: self.look_menu.popup(), tooltip="Lyrics look"
        )
        self.look_menu = build_look_menu(self, palette)
        bar.append(palette)
        bar.append(
            icon_button(
                "media-view-subtitles-symbolic",
                lambda *_: self.hyde("toggle"),
                tooltip="Lyrics on the desktop",
            )
        )
        bar.append(
            icon_button(
                "weather-clear-symbolic", lambda *_: self.hyde("glow"), tooltip="Screen glow"
            )
        )
        settings = Gtk.Button(label="Settings")
        settings.add_css_class("pill")
        self.settings = build_settings_popover(self, settings)
        settings.connect("clicked", lambda *_: self.settings.popup())
        bar.append(settings)
        bar.append(
            icon_button(
                "view-paged-symbolic",
                lambda *_: self.hyde("style", "next"),
                tooltip="Next lyrics style",
            )
        )
        bar.append(
            icon_button(
                "system-lock-screen-symbolic",
                lambda *_: self.run(["hyde-shell", "hyprlock.sh", "--test", "Encore"]),
                tooltip="Preview lock screen",
            )
        )
        bar.append(
            icon_button(
                "view-fullscreen-symbolic", lambda *_: self.hyde("show"), tooltip="Show workspace"
            )
        )
        return bar

    # actions ----------------------------------------------------------------

    @staticmethod
    def run(cmd: list[str]) -> None:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )

    def hyde(self, *args: str) -> None:
        self.run(["hyde-shell", "encore", *args])

    def _player_args(self) -> list[str]:
        player = self.state.get("player")
        return ["-p", player] if player else []

    def ctl(self, command: str) -> None:
        self.run(["playerctl", *self._player_args(), command])

    def seek(self, seconds: int) -> None:
        sign = "+" if seconds > 0 else "-"
        self.run(["playerctl", *self._player_args(), "position", f"{abs(seconds)}{sign}"])

    def look(self, **changes) -> None:
        update_look(self.look_path, persist=self.look_state, **changes)
        menu = getattr(self.look_menu, "menu", None)
        if menu is not None:
            menu.sync()

    def quit_all(self) -> None:
        """Quit Encore: the desktop lyrics and the glow stop with the window."""
        for name in ("encore-overlay.pid", "encore-glow.pid"):
            pid = read_pid(f"{self.runtime_dir}/{name}")  # type: ignore[arg-type]
            if pid is not None and pid_alive(pid):
                self.run(["kill", str(pid)])
        app = self.get_application()
        if app is not None:
            app.quit()

    def _on_key(self, _ctl, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval == Gdk.KEY_space:
            self.ctl("play-pause")
            return True
        if keyval in (Gdk.KEY_l, Gdk.KEY_L):
            self.toggle_lyrics()
            return True
        return False

    # state ------------------------------------------------------------------

    def _poll(self) -> bool:
        state = read_state(self.sock_path) or {}
        self.state = state
        palette = state.get("palette") or {}
        if palette != self.palette:
            # the lyrics, glow and window share one scheme
            self.palette = palette
            self.colors = color_scheme(palette, wallpaper_palette())
            self.accent = hex_rgb(self.colors.accent)
            self.accent_css.load_from_string(accent_rules(self.colors))
            self.backdrop.queue_draw()
        for page in (self.home, self.lyrics):
            page.update(state, self.colors)
        return True

    def _draw_backdrop(self, _area, cr, width, height) -> None:
        cr.set_source_rgb(0.094, 0.090, 0.102)
        cr.paint()
        r, g, b = self.accent
        eased = 1 - (1 - self.home.expanded) ** 3
        # album-tinted bloom behind the cover, stronger when it grows
        cx, cy = width / 2, height * 0.36
        glow = cairo.RadialGradient(cx, cy, 20, cx, cy, max(width, height) * (0.46 + 0.22 * eased))
        # the cover hides the center, so the visible ring carries the color
        glow.add_color_stop_rgba(0, r, g, b, 0.42 + 0.18 * eased)
        glow.add_color_stop_rgba(0.5, r, g, b, 0.17 + 0.10 * eased)
        glow.add_color_stop_rgba(1, r, g, b, 0.0)
        cr.set_source(glow)
        cr.paint()
        if eased > 0:
            wash = cairo.LinearGradient(0, 0, 0, height)
            wash.add_color_stop_rgba(0, r, g, b, 0.10 * eased)
            wash.add_color_stop_rgba(1, r * 0.4, g * 0.4, b * 0.4, 0.22 * eased)
            cr.set_source(wash)
            cr.paint()


def _page_from(arguments: list[str]) -> str | None:
    """The page after --open in a command line, if any."""
    if "--open" in arguments:
        index = arguments.index("--open")
        if index + 1 < len(arguments):
            return arguments[index + 1]
    return None


def run_app(runtime_dir: str, page: str | None = None) -> int:
    """Open Encore, or bring the open window forward (on `page` when given)."""
    app = Gtk.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    holder: dict[str, EncoreWindow] = {}

    def on_startup(_app) -> None:
        install_css()

    def on_command_line(application, command_line) -> int:
        # the first launch and every later one land here, in the first instance
        requested = _page_from(command_line.get_arguments())
        window = holder.get("window")
        if window is None:
            window = holder["window"] = EncoreWindow(application, runtime_dir)
            requested = requested or "home"
        if requested:
            window.show_page(requested)
        window.present()
        return 0

    app.connect("startup", on_startup)
    app.connect("command-line", on_command_line)
    return app.run(["encore", *(["--open", page] if page else [])])
