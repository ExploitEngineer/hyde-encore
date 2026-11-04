"""The two popovers of the Encore window, after the reference apps.

The look menu (palette button): lyric style, font, text size and the three
lyric colors. The Settings panel (Settings pill): the edge glow (gradient,
animation, thickness, glow, override colors, display), the lock screen and
Quit. Both write the live look file; every surface follows it at once.
"""

from __future__ import annotations

import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

from encoregui.ui import rgba_hex
from encorelib.look import MAX_SIZE, MIN_SIZE, read_look
from encorelib.stream import STYLES

PREFERRED_FONTS = (
    "SF Pro Display",
    "SF Pro Rounded",
    "Inter",
    "Helvetica Neue",
    "Futura",
    "Didot",
    "Georgia",
    "JetBrainsMono Nerd Font",
)
GLOW_ANIMATIONS = ("music", "breathe", "static")


def installed_fonts() -> list[str]:
    """The preferred lyric fonts this system actually has."""
    try:
        out = subprocess.run(
            ["fc-list", ":", "family"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return list(PREFERRED_FONTS[:1])
    have = {name.strip() for line in out.splitlines() for name in line.split(",")}
    return [f for f in PREFERRED_FONTS if f in have] or list(PREFERRED_FONTS[:1])


def monitor_names() -> list[str]:
    monitors = Gdk.Display.get_default().get_monitors()
    names = []
    for i in range(monitors.get_n_items()):
        names.append(monitors.get_item(i).get_connector() or f"Display {i + 1}")
    return names or ["Display"]


def _section(box: Gtk.Box, text: str) -> None:
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class("section")
    box.append(label)


def _hsep(box: Gtk.Box) -> None:
    sep = Gtk.Box()
    sep.add_css_class("hsep")
    box.append(sep)


def _panel_row(box: Gtk.Box, label: str, widget: Gtk.Widget) -> None:
    row = Gtk.Box(spacing=10, margin_top=4, margin_bottom=4)
    text = Gtk.Label(label=label, xalign=0)
    text.add_css_class("row-label")
    text.set_hexpand(True)
    row.append(text)
    row.append(widget)
    box.append(row)


def _color_picker(callback) -> Gtk.ColorDialogButton:
    dialog = Gtk.ColorDialog()
    dialog.set_with_alpha(False)
    picker = Gtk.ColorDialogButton.new(dialog)
    picker.connect("notify::rgba", lambda b, _p: callback(b))
    return picker


def _set_rgba(button: Gtk.ColorDialogButton, color: str) -> None:
    rgba = Gdk.RGBA()
    rgba.parse(color)
    button.set_rgba(rgba)


class LookMenu:
    """Style, font, text size and lyric colors, as a menu-like popover."""

    def __init__(self, win, anchor: Gtk.Widget):
        self.win = win
        self.items: list[Gtk.Button] = []
        self.syncing = False
        popover = Gtk.Popover()
        popover.add_css_class("menu-like")
        popover.set_parent(anchor)
        popover.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(250, -1)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(560)
        scroller.set_child(box)
        popover.set_child(scroller)
        self.popover = popover

        _section(box, "Style")
        for style in STYLES:
            self._item(
                box, style.capitalize(), lambda *_a, s=style: win.look(style=s), ("style", style)
            )
        _hsep(box)
        _section(box, "Font")
        for family in installed_fonts():
            self._item(box, family, lambda *_a, f=family: win.look(font=f), ("font", family))
        _hsep(box)
        _section(box, "Text Size")
        size_row = Gtk.Box(spacing=8, margin_start=14, margin_end=10)
        self.size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, MIN_SIZE, MAX_SIZE, 1)
        self.size.set_hexpand(True)
        self.size.set_draw_value(False)
        self.size.connect(
            "value-changed",
            lambda scale: None if self.syncing else win.look(size=int(scale.get_value())),
        )
        reset = Gtk.Button(label="Reset")
        reset.add_css_class("pill")
        reset.connect("clicked", lambda *_: win.look(size=None))
        size_row.append(self.size)
        size_row.append(reset)
        box.append(size_row)
        _hsep(box)
        _section(box, "Color")
        auto = {"lyric_color": None, "highlight_color": None, "secondary_color": None}
        self._item(box, "Auto Sync", lambda *_: win.look(**auto), ("auto", None))
        self.colors: dict[str, Gtk.ColorDialogButton] = {}
        for key, label in (
            ("lyric_color", "Lyric Text..."),
            ("highlight_color", "Highlight..."),
            ("secondary_color", "Secondary Text..."),
        ):
            row = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=2, margin_bottom=2)
            picker = _color_picker(lambda b, k=key: self._on_color(k, b))
            self.colors[key] = picker
            text = Gtk.Label(label=label, xalign=0)
            text.add_css_class("row-label")
            row.append(picker)
            row.append(text)
            box.append(row)
        self._item(box, "Reset Colors", lambda *_: win.look(**auto))
        popover.connect("show", lambda *_: self.sync())

    def _item(self, box: Gtk.Box, label: str, callback, mark_key=None) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("item")
        row = Gtk.Box(spacing=6)
        mark = Gtk.Label(label="")
        mark.add_css_class("mark")
        text = Gtk.Label(label=label, xalign=0)
        text.set_hexpand(True)
        row.append(mark)
        row.append(text)
        button.set_child(row)
        button.mark = mark  # type: ignore[attr-defined]
        button.mark_key = mark_key  # type: ignore[attr-defined]
        button.connect("clicked", callback)
        box.append(button)
        self.items.append(button)
        return button

    def _on_color(self, key: str, button: Gtk.ColorDialogButton) -> None:
        if not self.syncing:
            self.win.look(**{key: rgba_hex(button.get_rgba())})

    def sync(self) -> None:
        look = read_look(self.win.look_path)
        style = look.get("style", "line")
        font = look.get("font", "")
        auto = not any(k in look for k in ("lyric_color", "highlight_color", "secondary_color"))
        for item in self.items:
            on = False
            if item.mark_key:
                key, value = item.mark_key
                on = (
                    (key == "style" and value == style)
                    or (key == "font" and value == font)
                    or (key == "auto" and auto)
                )
            item.mark.set_label("✓" if on else "")
        self.syncing = True
        try:
            self.size.set_value(look.get("size", 30))
            colors = self.win.colors
            defaults = {
                "lyric_color": "#" + colors.lyric,
                "highlight_color": "#" + colors.highlight,
                "secondary_color": "#" + colors.secondary,
            }
            for key, button in self.colors.items():
                _set_rgba(button, look.get(key) or defaults[key])
        finally:
            self.syncing = False


class SettingsPanel:
    """Glow settings, display, lock screen and Quit, as Lumn's Settings popover."""

    def __init__(self, win, anchor: Gtk.Widget):
        self.win = win
        self.syncing = False
        popover = Gtk.Popover()
        popover.set_parent(anchor)
        popover.set_has_arrow(False)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panel.add_css_class("panel")
        panel.set_size_request(300, -1)
        popover.set_child(panel)
        self.popover = popover
        self.panel = panel
        title = Gtk.Label(label="encore", xalign=0)
        title.add_css_class("panel-title")
        panel.append(title)

        self.gradient = Gtk.DropDown.new_from_strings(["1 Color", "2 Colors"])
        self.gradient.connect(
            "notify::selected", lambda d, _p: self._set(glow_colors=d.get_selected() + 1)
        )
        _panel_row(panel, "Gradient", self.gradient)
        self.animation = Gtk.DropDown.new_from_strings(["Music Sync", "Breathe", "Static"])
        self.animation.connect(
            "notify::selected",
            lambda d, _p: self._set(glow_animation=GLOW_ANIMATIONS[d.get_selected()]),
        )
        _panel_row(panel, "Animation", self.animation)

        self.scales: dict[str, Gtk.Scale] = {}
        for attr, label, lo, hi in (
            ("thickness", "Thickness", 40, 220),
            ("intensity", "Glow", 10, 100),
        ):
            caption = Gtk.Label(label=label, xalign=0)
            caption.add_css_class("row-label")
            caption.set_margin_top(6)
            panel.append(caption)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
            scale.set_draw_value(False)
            scale.connect(
                "value-changed", lambda s, a=attr: self._set(**{f"glow_{a}": int(s.get_value())})
            )
            self.scales[attr] = scale
            panel.append(scale)

        self.override = Gtk.Switch()
        self.override.set_valign(Gtk.Align.CENTER)
        self.override.connect("state-set", lambda _s, on: self._set(glow_override=bool(on)))
        _panel_row(panel, "Override album color", self.override)
        wheels = Gtk.Box(spacing=16, homogeneous=True, margin_top=4)
        self.pickers: dict[str, Gtk.ColorDialogButton] = {}
        for key, label in (("glow_primary", "Primary"), ("glow_secondary", "Secondary")):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            caption = Gtk.Label(label=label)
            caption.add_css_class("dim")
            picker = _color_picker(lambda b, k=key: self._set(**{k: rgba_hex(b.get_rgba())}))
            picker.set_size_request(-1, 42)
            self.pickers[key] = picker
            col.append(caption)
            col.append(picker)
            wheels.append(col)
        panel.append(wheels)

        display_caption = Gtk.Label(label="Display", xalign=0)
        display_caption.add_css_class("row-label")
        display_caption.set_margin_top(8)
        panel.append(display_caption)
        self.display = Gtk.DropDown.new_from_strings(monitor_names())
        self.display.connect("notify::selected", self._on_display)
        panel.append(self.display)

        self.lock = Gtk.Switch()
        self.lock.set_valign(Gtk.Align.CENTER)
        self.lock.connect("state-set", self._on_lock)
        _panel_row(panel, "Lock screen player", self.lock)

        quit_button = Gtk.Button(label="Quit encore")
        quit_button.add_css_class("pill")
        quit_button.set_halign(Gtk.Align.START)
        quit_button.set_margin_top(8)
        quit_button.connect("clicked", lambda *_: win.quit_all())
        panel.append(quit_button)
        popover.connect("show", lambda *_: self.sync())

    def _set(self, **changes) -> bool:
        if not self.syncing:
            self.win.look(**changes)
        return False

    def _on_display(self, dropdown, _pspec) -> None:
        names = monitor_names()
        index = dropdown.get_selected()
        if 0 <= index < len(names):
            self._set(glow_monitor=names[index])  # the glow moves there at once

    def _on_lock(self, _switch, state) -> bool:
        if not self.syncing and state:
            self.win.run(["hyde-shell", "hyprlock.sh", "--select"])
        return False

    def sync(self) -> None:
        look = read_look(self.win.look_path)
        self.syncing = True
        try:
            self.gradient.set_selected(look.get("glow_colors", 2) - 1)
            names = monitor_names()
            if look.get("glow_monitor") in names:
                self.display.set_selected(names.index(look["glow_monitor"]))
            self.animation.set_selected(GLOW_ANIMATIONS.index(look.get("glow_animation", "music")))
            self.scales["thickness"].set_value(look.get("glow_thickness", 130))
            self.scales["intensity"].set_value(look.get("glow_intensity", 85))
            self.override.set_active(look.get("glow_override", False))
            for key, button in self.pickers.items():
                default = "#6B7CE8" if key == "glow_primary" else "#C86BE8"
                _set_rgba(button, look.get(key) or default)
        finally:
            self.syncing = False


def build_look_menu(win, anchor: Gtk.Widget) -> Gtk.Popover:
    menu = LookMenu(win, anchor)
    menu.popover.menu = menu  # type: ignore[attr-defined]
    return menu.popover


def build_settings_popover(win, anchor: Gtk.Widget) -> Gtk.Popover:
    panel = SettingsPanel(win, anchor)
    panel.popover.menu = panel  # type: ignore[attr-defined]
    return panel.popover
