"""The two popovers of the Encore window, after the reference apps.

The look menu (palette button): lyric style, font, text size and the three
lyric colors. The Settings panel (Settings pill): the edge glow (gradient,
animation, thickness, glow, override colors, display), the lock screen, and
an Encore section (HD covers, which players to follow, start at login,
Quit). Both write the live look file; every surface follows it at once.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from encoregui.lyrics import installed_faces
from encoregui.ui import SWATCH_PX, SWATCH_RING_ALPHA, eyebrow, rgba_hex
from encorelib.look import MAX_SIZE, MIN_SIZE, effective_autostart, effective_players, read_look
from encorelib.session import player_label
from encorelib.stream import STYLES
from encorelib.typeface import ALIASES, DISPLAY_FONTS, menu_fonts, primary_family

GLOW_ANIMATIONS = ("music", "breathe", "static")


def installed_fonts() -> list[str]:
    """The display fonts this system actually has, in the menu's order."""
    have = installed_faces()
    return [f for f in DISPLAY_FONTS if f in have] or list(DISPLAY_FONTS[:1])


def monitor_names() -> list[str]:
    monitors = Gdk.Display.get_default().get_monitors()
    names = []
    for i in range(monitors.get_n_items()):
        names.append(monitors.get_item(i).get_connector() or f"Display {i + 1}")
    return names or ["Display"]


def _section(box: Gtk.Box, text: str) -> None:
    label = Gtk.Label(label=eyebrow(text), xalign=0)
    label.add_css_class("section")
    box.append(label)


def _hsep(box: Gtk.Box) -> None:
    sep = Gtk.Box()
    sep.add_css_class("hsep")
    box.append(sep)


def _panel_row(box: Gtk.Box, label: str, widget: Gtk.Widget) -> None:
    row = Gtk.Box(spacing=10)
    row.add_css_class("panel-row")
    text = Gtk.Label(label=label, xalign=0)
    text.add_css_class("row-label")
    text.set_hexpand(True)
    row.append(text)
    row.append(widget)
    box.append(row)


class Swatch(Gtk.Button):
    """An 18 px round color swatch with a 1 px light ring that opens the color
    dialog. GtkColorDialogButton's swatch keeps a 32 px natural width that CSS
    cannot narrow, so the round is drawn here."""

    def __init__(self, callback):
        super().__init__()
        self.add_css_class("swatch")
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.START)
        self.rgba = Gdk.RGBA()
        self.rgba.parse("#808080")
        self.callback = callback
        self.dot = Gtk.DrawingArea()
        self.dot.set_content_width(SWATCH_PX)
        self.dot.set_content_height(SWATCH_PX)
        self.dot.set_draw_func(self._draw)
        self.set_child(self.dot)
        self.connect("clicked", lambda *_: self._choose())

    def get_rgba(self) -> Gdk.RGBA:
        return self.rgba

    def set_rgba(self, rgba: Gdk.RGBA) -> None:
        self.rgba = rgba
        self.dot.queue_draw()
        self.callback(self)

    def _draw(self, _area, cr, width: int, height: int) -> None:
        radius = min(width, height) / 2
        cr.arc(width / 2, height / 2, radius - 0.5, 0, 2 * math.pi)
        cr.set_source_rgba(self.rgba.red, self.rgba.green, self.rgba.blue, 1.0)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, SWATCH_RING_ALPHA)
        cr.set_line_width(1.0)
        cr.stroke()

    def _choose(self) -> None:
        dialog = Gtk.ColorDialog()
        dialog.set_with_alpha(False)
        root = self.get_root()

        def done(source, result) -> None:
            try:
                picked = source.choose_rgba_finish(result)
            except GLib.Error:
                return  # dismissed
            if picked is not None:
                self.set_rgba(picked)

        dialog.choose_rgba(root if isinstance(root, Gtk.Window) else None, self.rgba, None, done)


def _color_picker(callback) -> Swatch:
    return Swatch(callback)


def _value_row(box: Gtk.Box, label: str, scale: Gtk.Scale) -> Gtk.Label:
    """A slider under its caption, the value at the caption's right."""
    row = Gtk.Box(spacing=8, margin_top=6)
    caption = Gtk.Label(label=label, xalign=0)
    caption.add_css_class("row-label")
    caption.set_hexpand(True)
    value = Gtk.Label(label=str(int(scale.get_value())), xalign=1)
    value.add_css_class("value")
    row.append(caption)
    row.append(value)
    box.append(row)
    box.append(scale)
    scale.connect("value-changed", lambda s: value.set_label(str(int(s.get_value()))))
    return value


def _set_rgba(button: Swatch, color: str) -> None:
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
        _section(box, "Background")
        for value, label in (("art", "Cover"), ("clear", "Clear")):
            self._item(box, label, lambda *_a, v=value: win.look(stage_bg=v), ("stage_bg", value))
        _section(box, "Gradient")
        for value, label in ((1, "1 Color"), (2, "2 Colors")):
            self._item(box, label, lambda *_a, v=value: win.look(gradient=v), ("gradient", value))
        _hsep(box)
        _section(box, "Font")
        self.fonts = installed_fonts()
        self.font = Gtk.DropDown.new_from_strings(self.fonts)
        self.font.set_margin_start(14)
        self.font.set_margin_end(14)
        self.font.set_margin_bottom(4)
        self.font.set_tooltip_text(
            "; ".join(f"{ours} stands in for {theirs}" for ours, theirs in ALIASES.items())
        )
        self.font.connect("notify::selected", self._on_font)
        box.append(self.font)
        _hsep(box)
        _section(box, "Text Size")
        size_row = Gtk.Box(spacing=8, margin_start=14, margin_end=10)
        self.size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, MIN_SIZE, MAX_SIZE, 1)
        self.size.set_hexpand(True)
        self.size.set_draw_value(False)
        self.size.connect("value-changed", self._on_size)
        self.size_value = Gtk.Label(label="30")
        self.size_value.add_css_class("value")
        self.size_value.set_width_chars(2)
        self.size_value.set_xalign(1)
        reset = Gtk.Button(label="Reset")
        reset.add_css_class("pill")
        reset.connect("clicked", lambda *_: win.look(size=None))
        size_row.append(self.size)
        size_row.append(self.size_value)
        size_row.append(reset)
        box.append(size_row)
        _hsep(box)
        _section(box, "Color")
        auto = {"lyric_color": None, "highlight_color": None, "secondary_color": None}
        self._item(box, "Auto Sync", lambda *_: win.look(**auto), ("auto", None))
        self.colors: dict[str, Swatch] = {}
        for key, label in (
            ("lyric_color", "Lyric Text..."),
            ("highlight_color", "Highlight..."),
            ("secondary_color", "Secondary Text..."),
        ):
            row = Gtk.Box(spacing=10, margin_start=16, margin_end=12)
            row.add_css_class("panel-row")
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

    def _on_font(self, dropdown: Gtk.DropDown, _pspec) -> None:
        index = dropdown.get_selected()
        if not self.syncing and 0 <= index < len(self.fonts):
            self.win.look(font=self.fonts[index])

    def _on_size(self, scale: Gtk.Scale) -> None:
        value = int(scale.get_value())
        self.size_value.set_label(str(value))
        if not self.syncing:
            self.win.look(size=value)

    def _on_color(self, key: str, button: Swatch) -> None:
        if not self.syncing:
            self.win.look(**{key: rgba_hex(button.get_rgba())})

    def sync(self) -> None:
        look = read_look(self.win.look_path)
        style = look.get("style", "line")
        auto = not any(k in look for k in ("lyric_color", "highlight_color", "secondary_color"))
        for item in self.items:
            on = False
            if item.mark_key:
                key, value = item.mark_key
                on = (
                    (key == "style" and value == style)
                    or (key == "auto" and auto)
                    or (key == "stage_bg" and value == look.get("stage_bg", "art"))
                    or (key == "gradient" and value == look.get("gradient", 2))
                )
            item.mark.set_label("✓" if on else "")
        self.syncing = True
        try:
            primary = primary_family(
                look.get("font") or self.win.cfg.overlay_font, installed_faces()
            )
            fonts = menu_fonts(self.fonts, primary)
            if fonts != self.fonts:  # a family set from the CLI joins the menu
                self.font.get_model().append(primary)
                self.fonts = fonts
            self.font.set_selected(self.fonts.index(primary))
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
        # taller than the window on small screens: scroll instead of clipping
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(560)
        scroller.set_child(panel)
        popover.set_child(scroller)
        self.popover = popover
        self.panel = panel
        title = Gtk.Label(label=eyebrow("Glow"), xalign=0)
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
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
            scale.set_draw_value(False)
            scale.connect(
                "value-changed", lambda s, a=attr: self._set(**{f"glow_{a}": int(s.get_value())})
            )
            self.scales[attr] = scale
            _value_row(panel, label, scale)

        self.override = Gtk.Switch()
        self.override.set_valign(Gtk.Align.CENTER)
        self.override.connect("state-set", lambda _s, on: self._set(glow_override=bool(on)))
        _panel_row(panel, "Override album color", self.override)
        wheels = Gtk.Box(spacing=16, homogeneous=True)
        self.pickers: dict[str, Swatch] = {}
        for key, label in (("glow_primary", "Primary"), ("glow_secondary", "Secondary")):
            col = Gtk.Box(spacing=10)
            col.add_css_class("panel-row")
            caption = Gtk.Label(label=label, xalign=0)
            caption.add_css_class("row-label")
            picker = _color_picker(lambda b, k=key: self._set(**{k: rgba_hex(b.get_rgba())}))
            self.pickers[key] = picker
            col.append(picker)
            col.append(caption)
            wheels.append(col)
        panel.append(wheels)

        display_caption = Gtk.Label(label="Display", xalign=0)
        display_caption.add_css_class("row-label")
        display_caption.set_margin_top(8)
        panel.append(display_caption)
        self.display = Gtk.DropDown.new_from_strings(monitor_names())
        self.display.connect("notify::selected", self._on_display)
        panel.append(self.display)

        lock_row = Gtk.Box(spacing=8)
        self.lock = Gtk.Switch()
        self.lock.set_valign(Gtk.Align.CENTER)
        self.lock.connect("state-set", self._on_lock)
        preview = Gtk.Button(label="Preview")
        preview.add_css_class("pill")
        preview.set_tooltip_text("Show the Encore lock screen for a moment")
        preview.connect("clicked", lambda *_: win.encore("lock", "preview"))
        lock_row.append(preview)
        lock_row.append(self.lock)
        _panel_row(panel, "Lock screen lyrics", lock_row)

        _hsep(panel)
        encore_title = Gtk.Label(label=eyebrow("Encore"), xalign=0)
        encore_title.add_css_class("panel-title")
        panel.append(encore_title)
        self.hd = Gtk.Switch()
        self.hd.set_valign(Gtk.Align.CENTER)
        self.hd.set_tooltip_text(
            "Look up sharp covers on Apple Music's catalog when a player's is small"
        )
        self.hd.connect("state-set", lambda _s, on: self._set(hd_covers=bool(on)))
        _panel_row(panel, "HD covers", self.hd)
        self.autostart = Gtk.Switch()
        self.autostart.set_valign(Gtk.Align.CENTER)
        self.autostart.set_tooltip_text("Start the lyrics engine with the session")
        self.autostart.connect("state-set", lambda _s, on: self._set(autostart=bool(on)))
        _panel_row(panel, "Start at login", self.autostart)
        follow_caption = Gtk.Label(label="Follow", xalign=0)
        follow_caption.add_css_class("row-label")
        follow_caption.set_margin_top(6)
        panel.append(follow_caption)
        self.follow_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        panel.append(self.follow_box)
        self.follow_checks: dict[str, Gtk.CheckButton] = {}

        quit_button = Gtk.Button(label="Quit Encore")
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
        if not self.syncing:
            self.win.encore("lock", "on" if state else "off")
        return False

    def _fill_follow(self, look: dict) -> None:
        """One check per known player; none checked means every player."""
        child = self.follow_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.follow_box.remove(child)
            child = nxt
        self.follow_checks = {}
        chosen = set(effective_players(self.win.cfg, look))
        present = [p.split(".", 1)[0] for p in self.win.state.get("players") or []]
        names = []
        for name in [*present, *chosen]:
            if name and name not in names:
                names.append(name)
        every = Gtk.CheckButton(label="Every player")
        every.add_css_class("row-label")
        every.set_active(not chosen)
        every.connect("toggled", self._on_every)
        self.follow_box.append(every)
        for name in names:
            check = Gtk.CheckButton(label=player_label(name))
            check.add_css_class("row-label")
            check.set_active(name in chosen)
            check.connect("toggled", lambda _b, n=name: self._toggle_follow(n))
            self.follow_checks[name] = check
            self.follow_box.append(check)
        if not names:
            hint = Gtk.Label(label="Open a music player to pick from", xalign=0)
            hint.add_css_class("dim")
            self.follow_box.append(hint)

    def _on_every(self, button: Gtk.CheckButton) -> None:
        if self.syncing or not button.get_active():
            return
        self.syncing = True
        try:
            for check in self.follow_checks.values():
                check.set_active(False)
        finally:
            self.syncing = False
        self._set(players=[])

    def _toggle_follow(self, name: str) -> None:
        if self.syncing:
            return
        chosen = [n for n, c in self.follow_checks.items() if c.get_active()]
        self._set(players=chosen)
        self.syncing = True
        try:
            self.follow_box.get_first_child().set_active(not chosen)  # "Every player"
        finally:
            self.syncing = False

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
            self.lock.set_active(self.win.lock_on)
            self.hd.set_active(look.get("hd_covers", self.win.cfg.hd_covers))
            self.autostart.set_active(effective_autostart(self.win.cfg, look))
            self._fill_follow(look)
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
