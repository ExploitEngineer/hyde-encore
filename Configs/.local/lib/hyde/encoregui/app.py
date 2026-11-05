"""The Encore app: one window you open from the app launcher.

A unique Gtk.Application (`org.hyde.encore`): launching Encore again brings
the open window forward, and `encore app --open <page>` switches the open
window to that page. The window polls the daemon's state and hands it to
each page; the pages call back into the window for player commands and look
changes, so the actions live in one place.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from encoregui.field import AlbumField
from encoregui.fullscreen import FullPage
from encoregui.home import HomePage, LyricsPage, cover_path
from encoregui.popovers import build_look_menu, build_settings_popover
from encoregui.tray import Tray
from encoregui.ui import accent_rules, hex_rgb, icon_button, icon_image, install_css, trace
from encorelib.colors import scheme as color_scheme
from encorelib.config import load_config
from encorelib.lifecycle import close_action
from encorelib.lockscreen import ENCORE_LAYOUT, read_layout
from encorelib.look import read_look, state_look_path, update_look
from encorelib.motion import ease_out, lerp
from encorelib.palette import wallpaper_palette
from encorelib.protocol import read_state
from encorelib.screen import screen_state
from encorelib.service import surface_log
from encorelib.session import player_label
from encorelib.single import pid_alive, read_pid
from encorelib.transport import HeldKeys, key_action, page_after, step_volume

APP_ID = os.environ.get("ENCORE_APP_ID", "org.hyde.encore")
ENCORE_PY = str(Path(__file__).resolve().parent.parent / "encore.py")
POLL_MS = 400
PAGE_MS = 280  # Home <-> Lyrics
FULL_ENTER_MS = 220  # the Home cover grows while the compositor goes full screen
FULL_LEAVE_MS = 240
FULL_COVER = 400  # the Home cover grows to this on the way into full screen
PAGES = ("home", "lyrics", "stage", "full")
POPOVERS = ("look", "settings")  # --open names that mean Home with that popover up
RECONNECT_AFTER = 1.0  # seconds without an answer before saying so
SEEK_STEP = 5
VOLUME_STEP = 0.05


class EncoreWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, runtime_dir: str):
        super().__init__(application=app, title="Encore")
        self.runtime_dir = runtime_dir
        self.look_path = f"{runtime_dir}/encore.look"
        self.look_state = state_look_path()  # every change is kept for the next boot
        self.staterc = self.look_state.parent / "staterc"  # HyDE's hyprlock layout choice
        self.sock_path = f"{runtime_dir}/encore.sock"
        self.journal_path = f"{runtime_dir}/encore.lookups"
        self.cfg = load_config()
        self.add_css_class("encore-app")
        self.set_default_size(960, 760)
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
        self.came_from = "home"  # the page Full screen was entered from
        self.held_keys = HeldKeys()
        self.silent_since: float | None = None
        self.restarted = False
        self.lock_on = False
        self.toggles: dict[str, Gtk.Button] = {}
        self.tray = Tray()
        self.held = False  # the app stays alive while the window hides in the tray
        self.cover_timer = 0

        overlay = Gtk.Overlay()
        self.set_child(overlay)
        self.field = AlbumField()  # the album's light under every page
        overlay.set_child(self.field)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay.add_overlay(root)
        self.header = self._build_header()
        root.append(self.header)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(PAGE_MS)
        self.stack.set_vexpand(True)
        root.append(self.stack)
        self.home = HomePage(self)
        self.lyrics = LyricsPage(self)
        self.stack.add_named(self.home, "home")
        self.stack.add_named(self.lyrics, "lyrics")
        self.full = FullPage(self)
        self.stack.add_named(self.full, "full")
        atexit.register(self.full.clear_flag)  # the desktop overlay must never stay hidden
        self.connect("notify::fullscreened", self._on_fullscreened)
        self.connect("close-request", self._on_close_request)
        self.toolbar = self._build_toolbar()
        root.append(self.toolbar)

        key = Gtk.EventControllerKey()
        # capture phase: Space pauses even when a just-clicked button has focus
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_key)
        # held keys by hardware keycode: Shift changes the keyval between press and release
        key.connect("key-released", lambda _c, _keyval, code, _state: self.held_keys.release(code))
        # a release lost to a focus change must never swallow the next press
        self.connect("notify::is-active", lambda *_: self.held_keys.down.clear())
        self.add_controller(key)
        self._poll()
        GLib.timeout_add(POLL_MS, self._poll)
        # once Home has painted: warm the GPU pipelines full screen will need
        GLib.timeout_add(700, lambda: (self.full.backdrop.warm_up(self.get_native()), False)[1])
        if os.environ.get("ENCORE_TRACE"):  # timing runs: every paint leaves a breadcrumb

            def hook(w):
                clock = w.get_frame_clock()
                clock.connect("before-paint", lambda *_: trace("paint-begin"))
                clock.connect("after-paint", lambda *_: trace("paint"))

            self.connect("realize", hook)
        GLib.idle_add(lambda: (self.set_focus(None), False)[1])  # no focus ring at open

    # pages ------------------------------------------------------------------

    def show_page(self, name: str) -> None:
        trace(f"show_page {name} from {self.page}")
        if name in POPOVERS:
            popover = self.look_menu if name == "look" else self.settings
            self.show_page("home")
            GLib.timeout_add(400, lambda: (popover.popup(), False)[1])
            return
        if name not in PAGES:
            name = "home"
        previous = self.page
        if name == previous and name in ("stage", "full"):
            return
        leaving_full = previous == "full" and name != "full"
        self.page = name
        if name == "full":
            self.came_from = previous
            self.fullscreen()
            for chrome in (self.header, self.toolbar):
                chrome.set_visible(False)
            if previous == "stage":  # the show is already up: it only grows
                self.full.enter(windowed=False)
                return
            # the entry moment, without a crossfade (two full-HD offscreens per frame
            # are slow here): the Home cover grows, the page cuts, and the backdrop
            # carries the same cover on to the whole screen, then the lyrics arrive
            self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
            self._cover_timeline(
                self.home.art, max(FULL_COVER, self.home.art), FULL_ENTER_MS, self._hero_into_full
            )
            return
        if name == "stage":
            for chrome in (self.header, self.toolbar):
                chrome.set_visible(False)
            if leaving_full:  # page first: the unfullscreen notify must not send us Home
                self.unfullscreen()
                # a hero entry still under way must never finish into Full screen,
                # and the cover the entry grew goes back to Home's size
                self._stop_cover_timeline()
                self.home.cover.set_side(self.home.art)
                self.full.backdrop.cancel_hero()
            self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
            self.stack.set_transition_duration(PAGE_MS)
            self.stack.set_visible_child_name("full")
            self.full.enter(windowed=True)
            return
        if previous == "stage":
            self.full.leave()
        if leaving_full:
            self.full.leave()
            self.unfullscreen()
            self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
            self._cover_timeline(max(FULL_COVER, self.home.art), self.home.art, FULL_LEAVE_MS, None)
        else:
            self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
            self.stack.set_transition_duration(PAGE_MS)
        self.stack.set_visible_child_name(name)
        for chrome in (self.header, self.toolbar):  # the show is the page alone
            chrome.set_visible(True)
        trace(f"home cover {self.home.cover.side}")
        if name == "lyrics":
            GLib.timeout_add(260, lambda: (self.lyrics.scroll_to_current(True), False)[1])

    def _hero_into_full(self) -> None:
        """Cut to the full page and let its backdrop grow the cover from where Home had it."""
        ok, bounds = self.home.cover.compute_bounds(self.stack)
        side = max(FULL_COVER, self.home.art)
        if ok and self.page == "full" and self.stack.get_visible_child() is self.home:
            x = bounds.get_x() + (bounds.get_width() - side) / 2
            y = bounds.get_y() + (bounds.get_height() - side) / 2
        else:
            x, y = (self.stack.get_width() - side) / 2, (self.stack.get_height() - side) / 2
        self.stack.set_visible_child_name("full")
        self.full.backdrop.enter_from(x, y, side, side, done=self.full.enter)

    def _stop_cover_timeline(self) -> None:
        if self.cover_timer:
            self.remove_tick_callback(self.cover_timer)
            self.cover_timer = 0

    def _cover_timeline(self, start: int, end: int, ms: int, done) -> None:
        """Grow or shrink the Home cover over `ms`, then call `done`; one step per
        display frame, at the frame's time, so the growth never judders."""
        self._stop_cover_timeline()
        began = time.monotonic()

        def step(_widget, clock) -> bool:
            t = (clock.get_frame_time() / 1_000_000 - began) * 1000 / ms
            self.home.cover.set_side(int(lerp(start, end, ease_out(t))))
            if t >= 1.0:
                self.cover_timer = 0
                trace("cover timeline done")
                if done is not None:
                    done()
                return False
            return True

        self.cover_timer = self.add_tick_callback(step)

    def _on_fullscreened(self, *_) -> None:
        trace(f"fullscreened {self.is_fullscreen()}")
        # the compositor took full screen away (a keybind, another window): never
        # trap; back where Full screen was entered from
        if not self.is_fullscreen() and self.page == "full":
            self.show_page("stage" if self.came_from == "stage" else "home")

    def toggle_lyrics(self) -> None:
        self.show_page("home" if self.page == "lyrics" else "lyrics")

    def _build_header(self) -> Gtk.Widget:
        header = Gtk.CenterBox()
        header.set_margin_top(14)
        header.set_margin_start(16)
        header.set_margin_end(16)
        self.chip = Gtk.MenuButton()
        self.chip.add_css_class("chip")
        self.chip.set_tooltip_text("The player Encore follows")
        chip_box = Gtk.Box(spacing=6)
        self.chip_label = Gtk.Label(label="Automatic")
        arrow = icon_image("pan-down-symbolic")
        arrow.set_pixel_size(12)
        chip_box.append(self.chip_label)
        chip_box.append(arrow)
        self.chip.set_child(chip_box)
        self.chip_menu = Gtk.Popover()
        self.chip_menu.add_css_class("menu-like")
        self.chip_menu.set_has_arrow(False)
        self.chip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.chip_box.set_size_request(220, -1)
        self.chip_menu.set_child(self.chip_box)
        self.chip_menu.connect("show", lambda *_: self._fill_chip_menu())
        self.chip.set_popover(self.chip_menu)
        header.set_start_widget(self.chip)
        self.status = Gtk.Label(label="")
        self.status.add_css_class("status")
        header.set_center_widget(self.status)
        return header

    def _fill_chip_menu(self) -> None:
        child = self.chip_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.chip_box.remove(child)
            child = nxt
        following = self.state.get("player") or ""
        for name in ["auto", *(self.state.get("players") or [])]:
            button = Gtk.Button()
            button.add_css_class("item")
            row = Gtk.Box(spacing=6)
            mark = Gtk.Label(label="✓" if name == following else "")
            mark.add_css_class("mark")
            label = "Automatic (most recent)" if name == "auto" else player_label(name)
            text = Gtk.Label(label=label, xalign=0)
            text.set_hexpand(True)
            row.append(mark)
            row.append(text)
            button.set_child(row)
            button.connect("clicked", lambda _b, n=name: self._pick_player(n))
            self.chip_box.append(button)

    def _pick_player(self, name: str) -> None:
        self.chip_menu.popdown()
        self.encore("follow", name)

    def _toggle(self, key: str, icon: str, tooltip: str, callback) -> Gtk.Button:
        button = icon_button(icon, lambda *_: callback(), tooltip=tooltip)
        button.base_tooltip = tooltip  # type: ignore[attr-defined]
        self.toggles[key] = button
        return button

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
            self._toggle(
                "desktop",
                "media-view-subtitles-symbolic",
                "Lyrics on the desktop",
                lambda: self.encore("toggle"),
            )
        )
        bar.append(
            self._toggle(
                "glow", "weather-clear-symbolic", "Screen-edge glow", lambda: self.encore("glow")
            )
        )
        settings = Gtk.Button(label="Settings")
        settings.add_css_class("pill")
        self.settings = build_settings_popover(self, settings)
        settings.connect("clicked", lambda *_: self.settings.popup())
        bar.append(settings)
        bar.append(
            self._toggle(
                "lock",
                "system-lock-screen-symbolic",
                "Lyrics on the lock screen",
                lambda: self.encore("lock", "off" if self.lock_on else "on"),
            )
        )
        bar.append(
            icon_button(
                "view-restore-symbolic",
                lambda *_: self.show_page("stage"),
                tooltip="Stage window (W)",
            )
        )
        bar.append(
            icon_button(
                "view-fullscreen-symbolic",
                lambda *_: self.show_page("full"),
                tooltip="Full screen (F)",
            )
        )
        return bar

    # closing and the tray --------------------------------------------------

    def _on_close_request(self, *_) -> bool:
        """Closing keeps Encore in the tray while desktop lyrics or glow run; else quits."""
        if (
            close_action(self.running("encore-overlay.pid"), self.running("encore-glow.pid"))
            == "quit"
        ):
            self.quit_all()
            return True
        if self.page in ("stage", "full"):
            self.show_page("home")
        app = self.get_application()
        if app is not None and not self.held:
            app.hold()
            self.held = True
        self.set_visible(False)
        self.tray.start(self.show_window, self._tray_action)
        self._sync_toggles()
        return True

    def show_window(self) -> None:
        """Bring the window back (from the tray or a new launch)."""
        if not self.get_visible():
            self.set_visible(True)
        self.present()
        if self.held:
            app = self.get_application()
            if app is not None:
                app.release()
            self.held = False
        self.tray.stop()

    def _tray_action(self, action: str) -> None:
        if action == "open":
            self.show_window()
        elif action in ("play-pause", "next"):
            self.ctl(action)
        elif action == "desktop":
            self.encore("toggle")
        elif action == "glow":
            self.encore("glow")
        elif action == "quit":
            self.quit_all()

    # actions ----------------------------------------------------------------

    @staticmethod
    def run(cmd: list[str]) -> None:
        # a command's complaint lands in the cache log, never in /dev/null
        with open(surface_log("app-commands"), "a", encoding="utf-8") as log_file:
            subprocess.Popen(cmd, stdout=log_file, stderr=log_file, start_new_session=True)

    def encore(self, *args: str) -> None:
        """Run an encore command with this window's environment."""
        self.run([sys.executable, ENCORE_PY, *args])

    def _player_args(self) -> list[str]:
        player = self.state.get("player")
        return ["-p", player] if player else []

    def ctl(self, command: str) -> None:
        self.run(["playerctl", *self._player_args(), command])

    def seek(self, seconds: int) -> None:
        sign = "+" if seconds > 0 else "-"
        self.run(["playerctl", *self._player_args(), "position", f"{abs(seconds)}{sign}"])

    def seek_to(self, seconds: float) -> None:
        self.run(["playerctl", *self._player_args(), "position", f"{max(0.0, seconds):.2f}"])

    def set_volume(self, volume: float) -> None:
        if self.state.get("volume") is None:
            return
        self.run(["playerctl", *self._player_args(), "volume", f"{volume:.2f}"])

    def look(self, **changes) -> None:
        update_look(self.look_path, persist=self.look_state, **changes)
        menu = getattr(self.look_menu, "menu", None)
        if menu is not None:
            menu.sync()

    def quit_all(self) -> None:
        """Quit Encore: the desktop lyrics and the glow stop with the window."""
        self.tray.stop()
        self.full.shutdown()
        # Quit means off: the next engine start must not bring them back
        update_look(self.look_path, persist=self.look_state, desktop_lyrics_on=False, glow_on=False)
        for name in ("encore-overlay.pid", "encore-glow.pid"):
            pid = read_pid(Path(self.runtime_dir) / name)
            if pid is not None and pid_alive(pid):
                self.run(["kill", str(pid)])
        app = self.get_application()
        if app is not None:
            app.quit()

    def running(self, name: str) -> bool:
        """Whether a surface (pidfile name) runs: encore-overlay.pid, encore-glow.pid."""
        pid = read_pid(Path(self.runtime_dir) / name)
        return pid is not None and pid_alive(pid)

    def _on_key(self, _ctl, keyval, code, state) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        action = key_action(Gdk.keyval_name(keyval) or "", ctrl, self.page)
        if action is None:
            return False
        if not self.held_keys.press(code, action):
            return True  # auto-repeat of a key that acts once per press
        if action == "play-pause":
            self.ctl("play-pause")
        elif action in ("next", "previous"):
            self.ctl(action)
        elif action in ("seek-back", "seek-forward"):
            self.seek(SEEK_STEP if action == "seek-forward" else -SEEK_STEP)
        elif action in ("volume-up", "volume-down"):
            volume = self.state.get("volume")
            if volume is not None:
                delta = VOLUME_STEP if action == "volume-up" else -VOLUME_STEP
                self.set_volume(step_volume(volume, delta))
        elif action == "lyrics":
            self.toggle_lyrics()
        elif action in ("fullscreen", "stage", "back"):
            self.show_page(page_after(action, self.page, self.came_from) or "home")
        elif action == "quit":
            self.quit_all()
        return True

    # state ------------------------------------------------------------------

    def _poll(self) -> bool:
        raw = read_state(self.sock_path)
        self._sync_connection(raw is not None)
        state = raw or {}
        self.state = state
        palette = state.get("palette") or {}
        if palette != self.palette:
            # the lyrics, glow and window share one scheme
            self.palette = palette
            self.colors = color_scheme(palette, wallpaper_palette())
            self.accent = hex_rgb(self.colors.accent)
            self.accent_css.load_from_string(accent_rules(self.colors))
            self.field.set_colors(self.colors)
        idle = screen_state(state, time.monotonic()) == "idle"
        self.field.set_cover("" if idle else cover_path(state))
        self.field.set_playing(state.get("status") == "playing")
        self.field.set_idle(idle)
        look = read_look(self.look_path)
        self.field.set_motion(look.get("motion", True))
        self.field.set_gradient(look.get("gradient", 2))
        self.chip_label.set_label(player_label(state.get("player") or ""))
        self.chip.set_sensitive(bool(state.get("players")))
        for page in (self.home, self.lyrics, self.full):
            page.update(state, self.colors)
        self._sync_toggles()
        return True

    def _sync_connection(self, answered: bool) -> None:
        """Say so when the engine stops answering, and start it again once per outage."""
        now = time.monotonic()
        if answered:
            self.silent_since = None
            self.restarted = False
            if self.status.get_label():
                self.status.set_label("")
            return
        if self.silent_since is None:
            self.silent_since = now
        if now - self.silent_since >= RECONNECT_AFTER:
            self.status.set_label("Reconnecting…")
            if not self.restarted:
                self.restarted = True
                from encorelib.service import ensure_daemon

                # off the main loop: starting the unit may take seconds
                threading.Thread(
                    target=ensure_daemon,
                    args=(Path(self.sock_path), os.environ.get("XDG_SESSION_DESKTOP", "")),
                    kwargs={"fallback": lambda: self.encore("daemon")},
                    daemon=True,
                ).start()

    def _sync_toggles(self) -> None:
        try:
            layout = read_layout(self.staterc.read_text(encoding="utf-8"))
        except OSError:
            layout = None
        self.lock_on = layout == ENCORE_LAYOUT
        states = {
            "desktop": self.running("encore-overlay.pid"),
            "glow": self.running("encore-glow.pid"),
            "lock": self.lock_on,
        }
        if self.tray.active:
            self.tray.update(
                states["desktop"], states["glow"], self.state.get("status") == "playing"
            )
        for key, on in states.items():
            button = self.toggles.get(key)
            if button is None:
                continue
            if on != button.has_css_class("on"):
                if on:
                    button.add_css_class("on")
                else:
                    button.remove_css_class("on")
            text = f"{button.base_tooltip}: {'on' if on else 'off'}"
            if button.get_tooltip_text() != text:
                button.set_tooltip_text(text)


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

    def on_startup(application) -> None:
        install_css()
        # app actions, reachable over D-Bus (org.gtk.Actions) like any GTK app's
        for name, handler in (
            ("close", lambda: holder["window"].close()),
            ("quit", lambda: holder["window"].quit_all()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, h=handler: "window" in holder and h())
            application.add_action(action)

    def on_command_line(application, command_line) -> int:
        # the first launch and every later one land here, in the first instance
        requested = _page_from(command_line.get_arguments())
        window = holder.get("window")
        if window is None:
            window = holder["window"] = EncoreWindow(application, runtime_dir)
            requested = requested or "home"
        if requested:
            window.show_page(requested)
        window.show_window()
        return 0

    app.connect("startup", on_startup)
    app.connect("command-line", on_command_line)
    return app.run(["encore", *(["--open", page] if page else [])])
