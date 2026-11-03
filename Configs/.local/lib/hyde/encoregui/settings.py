"""The encore settings window: style list, font, size, colors, glow, profiles.

A compact dark GTK4 panel modelled on the reference app's menu: sections
with muted headers, checkmarked rows, a size slider with Reset, color
swatches with Auto Sync, glow and motion switches. Everything writes the
runtime look file, which the overlay and glow apply live.
"""

from __future__ import annotations

import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from encorelib.look import MAX_SIZE, MIN_SIZE, read_look, update_look
from encorelib.profiles import apply_profile
from encorelib.protocol import read_state
from encorelib.single import claim, release

STYLE_LABELS = {
    "line": "Line",
    "stack": "Stack",
    "visual": "Visual",
    "constellation": "Constellation",
}
PREFERRED_FONTS = [
    "JetBrainsMono Nerd Font",
    "Inter",
    "SF Pro Display",
    "Helvetica Neue",
    "Futura",
    "Didot",
    "Georgia",
    "Noto Serif",
    "Cantarell",
    "DejaVu Sans",
]


def installed_fonts() -> list[str]:
    """The preferred families that are actually installed, in order."""
    try:
        out = subprocess.run(
            ["fc-list", ":", "family"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return PREFERRED_FONTS[:1]
    have = {name.strip() for line in out.splitlines() for name in line.split(",")}
    fonts = [f for f in PREFERRED_FONTS if f in have]
    return fonts or PREFERRED_FONTS[:1]


FONTS = installed_fonts()

CSS = """
window.encore-settings { background: #1c1d22; color: #e8e8ec; border-radius: 14px; }
.panel { padding: 10px 6px 12px 6px; }
.section { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #7d7f89;
           margin: 12px 14px 4px 14px; }
button.row { background: transparent; border: none; border-radius: 7px; padding: 5px 12px;
             margin: 0 6px; min-height: 24px; color: #e8e8ec; box-shadow: none; }
button.row:hover { background: rgba(255,255,255,0.07); }
button.row.selected { background: #2b6ff5; color: white; }
button.row .check { color: #8fb2ff; min-width: 16px; }
button.row.selected .check { color: white; }
.sep { background: rgba(255,255,255,0.08); min-height: 1px; margin: 8px 12px; }
.pill { background: rgba(255,255,255,0.09); border-radius: 8px; padding: 3px 12px; border: none;
        color: #e8e8ec; box-shadow: none; }
.pill:hover { background: rgba(255,255,255,0.16); }
.pill.accent { background: #2b6ff5; color: white; }
.title { font-size: 15px; font-weight: 800; margin: 6px 14px 0 14px; }
.sub { color: #7d7f89; margin: 0 14px; font-size: 12px; }
scale trough { background: rgba(255,255,255,0.14); min-height: 4px; }
scale highlight { background: #2b6ff5; }
scale slider { background: #f2f2f5; min-width: 16px; min-height: 16px; }
switch { background: rgba(255,255,255,0.16); }
switch:checked { background: #2b6ff5; }
.swatch { min-width: 22px; min-height: 22px; border-radius: 11px; border: 2px solid transparent;
          padding: 0; margin: 0 3px; box-shadow: none; }
.swatch.active { border-color: white; }
.footer { color: #7d7f89; font-size: 12px; margin: 2px 14px; }
"""


def _swatch_css(index: int, color: str) -> str:
    return f".sw{index} {{ background: {color}; }}"


class Settings(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, look_path: str, sock_path: str):
        super().__init__(application=app, title="encore")
        self.look_path = look_path
        self.sock_path = sock_path
        self.add_css_class("encore-settings")
        self.set_default_size(330, -1)
        self.set_resizable(False)
        self.row_buttons: dict[str, Gtk.Button] = {}
        self.style_rows: dict[str, Gtk.Button] = {}
        self.font_rows: dict[str, Gtk.Button] = {}
        self.swatch_buttons: list[Gtk.Button] = []
        self.swatch_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), self.swatch_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(820)
        self.set_child(scroller)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("panel")
        scroller.set_child(box)

        self.title = Gtk.Label(label="encore", xalign=0)
        self.title.add_css_class("title")
        self.sub = Gtk.Label(label="", xalign=0)
        self.sub.add_css_class("sub")
        box.append(self.title)
        box.append(self.sub)

        # profiles -----------------------------------------------------------
        box.append(self._section("SOUND SETUP"))
        pbox = Gtk.Box(spacing=8, margin_start=14, margin_end=14, margin_top=4)
        working = self._pill("Working", lambda *_: self._profile("working"))
        show = self._pill("Full Show", lambda *_: self._profile("show"), accent=True)
        showws = self._pill("Show workspace", lambda *_: self._show_workspace())
        for pill in (working, show, showws):
            pbox.append(pill)
        box.append(pbox)

        # style --------------------------------------------------------------
        box.append(self._section("STYLE"))
        for key, label in STYLE_LABELS.items():
            button = self._row(label, lambda *_a, k=key: self._set(style=k))
            self.style_rows[key] = button
            box.append(button)

        # font ---------------------------------------------------------------
        box.append(self._section("FONT"))
        for family in FONTS:
            button = self._row(family, lambda *_a, f=family: self._set(font=f))
            self.font_rows[family] = button
            box.append(button)

        # size ---------------------------------------------------------------
        box.append(self._section("TEXT SIZE"))
        sbox = Gtk.Box(spacing=10, margin_start=14, margin_end=14, margin_top=4)
        self.size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, MIN_SIZE, MAX_SIZE, 1
        )
        self.size_scale.set_hexpand(True)
        self.size_scale.set_draw_value(False)
        self.size_scale.connect("value-changed", self._on_size)
        reset = self._pill("Reset", lambda *_: self._set(size=None))
        sbox.append(self.size_scale)
        sbox.append(reset)
        box.append(sbox)

        # colors -------------------------------------------------------------
        box.append(self._section("COLOR"))
        self.auto_row = self._row("Auto Sync (album colors)", lambda *_: self._set(color=None))
        box.append(self.auto_row)
        cbox = Gtk.Box(margin_start=14, margin_end=14, margin_top=6, margin_bottom=2)
        for i in range(5):
            swatch = Gtk.Button()
            swatch.add_css_class("swatch")
            swatch.add_css_class(f"sw{i}")
            swatch.connect("clicked", lambda _b, idx=i: self._pick_swatch(idx))
            self.swatch_buttons.append(swatch)
            cbox.append(swatch)
        box.append(cbox)

        # switches -----------------------------------------------------------
        box.append(self._section("EFFECTS"))
        self.motion_switch = self._switch(box, "Text motion", self._on_motion)
        self.next_switch = self._switch(box, "Show next line", self._on_next)
        self.glow_switch = self._switch(box, "Edge glow", self._on_glow)
        self.lyrics_switch = self._switch(box, "Lyrics overlay", self._on_lyrics)

        box.append(self._sep())
        foot = Gtk.Box(margin_start=14, margin_end=14)
        quit_button = self._pill("Reset look", lambda *_: self._reset())
        close = self._pill("Done", lambda *_: self.close(), accent=True)
        foot.append(quit_button)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        foot.append(spacer)
        foot.append(close)
        box.append(foot)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        self.refresh()
        GLib.timeout_add_seconds(2, self._poll)

    # widgets ------------------------------------------------------------------

    @staticmethod
    def _section(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("section")
        return label

    @staticmethod
    def _sep() -> Gtk.Box:
        sep = Gtk.Box()
        sep.add_css_class("sep")
        return sep

    @staticmethod
    def _pill(label: str, callback, accent: bool = False) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("pill")
        if accent:
            button.add_css_class("accent")
        button.connect("clicked", callback)
        return button

    def _row(self, label: str, callback) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("row")
        inner = Gtk.Box(spacing=8)
        check = Gtk.Label(label="")
        check.add_css_class("check")
        text = Gtk.Label(label=label, xalign=0)
        text.set_hexpand(True)
        inner.append(check)
        inner.append(text)
        button.set_child(inner)
        button.check = check  # type: ignore[attr-defined]
        button.connect("clicked", callback)
        return button

    def _switch(self, box: Gtk.Box, label: str, callback) -> Gtk.Switch:
        row = Gtk.Box(margin_start=14, margin_end=14, margin_top=3, margin_bottom=3)
        text = Gtk.Label(label=label, xalign=0)
        text.set_hexpand(True)
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("state-set", callback)
        row.append(text)
        row.append(switch)
        box.append(row)
        return switch

    # actions ------------------------------------------------------------------

    def _set(self, **changes) -> None:
        update_look(self.look_path, **changes)
        self.refresh()

    def _on_size(self, scale) -> None:
        if getattr(self, "_syncing", False):
            return
        update_look(self.look_path, size=int(scale.get_value()))

    def _on_motion(self, _switch, state) -> bool:
        if not getattr(self, "_syncing", False):
            update_look(self.look_path, motion=bool(state))
        return False

    def _on_next(self, _switch, state) -> bool:
        if not getattr(self, "_syncing", False):
            update_look(self.look_path, next_line=bool(state))
        return False

    def _on_glow(self, _switch, state) -> bool:
        if not getattr(self, "_syncing", False):
            self._daemon_toggle("glow", bool(state))
        return False

    def _on_lyrics(self, _switch, state) -> bool:
        if not getattr(self, "_syncing", False):
            self._daemon_toggle("toggle", bool(state))
        return False

    @staticmethod
    def _running(pidfile: str) -> bool:
        from encorelib.single import pid_alive, read_pid

        pid = read_pid(pidfile)  # type: ignore[arg-type]
        return pid is not None and pid_alive(pid)

    def _daemon_toggle(self, command: str, want_on: bool) -> None:
        pidfile = self.sock_path.rsplit("/", 1)[0] + (
            "/encore-glow.pid" if command == "glow" else "/encore-overlay.pid"
        )
        if self._running(pidfile) != want_on:
            subprocess.Popen(
                ["hyde-shell", "encore", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    def _profile(self, name: str) -> None:
        glow = apply_profile(self.look_path, name)
        if glow is not None:
            self._daemon_toggle("glow", glow)
            self._daemon_toggle("toggle", True)
        self.refresh()

    def _show_workspace(self) -> None:
        subprocess.Popen(
            ["hyde-shell", "encore", "show"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.close()

    def _reset(self) -> None:
        update_look(
            self.look_path,
            style=None,
            font=None,
            size=None,
            color=None,
            next_line=None,
            motion=None,
        )
        self.refresh()

    def _pick_swatch(self, index: int) -> None:
        colors = getattr(self, "swatch_colors", [])
        if index < len(colors):
            self._set(color=colors[index])

    def _on_key(self, _ctl, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    # state --------------------------------------------------------------------

    def _poll(self) -> bool:
        self.refresh(from_poll=True)
        return True

    def refresh(self, from_poll: bool = False) -> None:
        look = read_look(self.look_path)
        state = read_state(self.sock_path) or {}
        track = state.get("track") or {}
        status = state.get("status") or "stopped"
        self.sub.set_label(
            f"{track.get('title', 'nothing playing')} - {track.get('artist', '')}".strip(" -")
            if status != "stopped"
            else "nothing playing"
        )
        style = look.get("style", "line")
        for key, button in self.style_rows.items():
            self._mark(button, key == style)
        font = look.get("font", FONTS[0])
        for family, button in self.font_rows.items():
            self._mark(button, family == font)
        self._syncing = True
        try:
            self.size_scale.set_value(look.get("size", 30))
            self.motion_switch.set_active(look.get("motion", True))
            self.next_switch.set_active(look.get("next_line", True))
            glow_on = self._running(self.sock_path.rsplit("/", 1)[0] + "/encore-glow.pid")
            lyrics_on = self._running(self.sock_path.rsplit("/", 1)[0] + "/encore-overlay.pid")
            self.glow_switch.set_active(glow_on)
            self.lyrics_switch.set_active(lyrics_on)
        finally:
            self._syncing = False
        color = look.get("color")
        self._mark(self.auto_row, color is None)
        palette = state.get("palette") or {}
        self.swatch_colors = [
            f"#{palette[k]}" for k in ("1xa8", "2xa8", "3xa8", "4xa8", "txt1") if k in palette
        ]
        css = "".join(_swatch_css(i, c) for i, c in enumerate(self.swatch_colors))
        self.swatch_provider.load_from_string(css or ".sw0 {}")
        for i, button in enumerate(self.swatch_buttons):
            button.set_visible(i < len(self.swatch_colors))
            if i < len(self.swatch_colors) and self.swatch_colors[i] == color:
                button.add_css_class("active")
            else:
                button.remove_css_class("active")

    @staticmethod
    def _mark(button: Gtk.Button, selected: bool) -> None:
        button.check.set_label("✓" if selected else "")  # type: ignore[attr-defined]
        if selected:
            button.add_css_class("selected")
        else:
            button.remove_css_class("selected")


def run_settings(look_path: str, sock_path: str, pidfile: str) -> int:
    if not claim(pidfile):
        subprocess.run(["hyprctl", "dispatch", "focuswindow", "title:^encore$"], check=False)
        return 0
    app = Gtk.Application(
        application_id="org.hyde.encore.settings", flags=Gio.ApplicationFlags.NON_UNIQUE
    )

    def on_activate(application):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        Settings(application, look_path, sock_path).present()

    app.connect("activate", on_activate)
    try:
        return app.run(None)
    finally:
        release(pidfile)


if __name__ == "__main__":
    sys.exit(0)
