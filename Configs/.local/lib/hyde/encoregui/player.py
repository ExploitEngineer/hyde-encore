"""The encore player window, modelled on the reference player.

A normal app window: rounded album art with an album-tinted glow behind
it, title and artist, round transport controls, a Lyrics pill that
switches to a side-by-side lyrics view, and a bottom toolbar. The
palette button opens the lyrics look menu (styles, fonts, size, the
three lyric colors); Settings opens the glow popover (gradient,
animation, thickness, glow, override colors, display).
"""

from __future__ import annotations

import subprocess

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from encorelib.look import MAX_SIZE, MIN_SIZE, read_look, update_look
from encorelib.palette import pick_accent
from encorelib.protocol import read_state
from encorelib.single import claim, pid_alive, read_pid, release
from encorelib.stream import STYLES

UI_FONT = "SF Pro Display"
ART = 236
ART_EXPANDED = 330
EXPAND_MS = 220
POLL_MS = 400

CSS = """
window.encore-player { background: #18171a; }
.title { font-family: "SF Pro Display"; font-size: 19px; font-weight: 700; color: #ececf0; }
.artist { font-family: "SF Pro Display"; font-size: 14px; color: #8e8d94; }
.art-frame { border-radius: 26px; padding: 7px; background: rgba(255,255,255,0.06);
             box-shadow: 0 0 0 1px rgba(255,255,255,0.10), 0 18px 48px rgba(0,0,0,0.55); }
.art-frame picture { border-radius: 20px; }
button.round { min-width: 42px; min-height: 42px; border-radius: 999px; padding: 0;
               background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.07);
               box-shadow: none; color: #d8d8de; }
button.round:hover { background: rgba(255,255,255,0.13); }
button.round.big { min-width: 56px; min-height: 56px; }
button.pill { border-radius: 999px; padding: 6px 16px; min-height: 0;
              background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.07);
              box-shadow: none; color: #d8d8de; font-family: "SF Pro Display"; font-size: 13px; }
button.pill:hover { background: rgba(255,255,255,0.13); }
button.pill.on { color: #ff6f9c; background: rgba(255,111,156,0.12); }
.bottombar button.round { min-width: 40px; min-height: 40px; }
.card { background: rgba(255,255,255,0.035); border-radius: 22px;
        border: 1px solid rgba(255,255,255,0.08); padding: 26px; }
.lyric { font-family: "SF Pro Display"; font-size: 21px; font-weight: 700; color: rgba(236,236,240,0.30); }
.lyric.current { color: #f4f4f7; }
.lyric.near { color: rgba(236,236,240,0.48); }
.vsep { background: rgba(255,255,255,0.08); min-width: 1px; }
popover.menu-like > contents { background: #1f1d20; border-radius: 12px; padding: 6px 0;
                              border: 1px solid rgba(255,255,255,0.09); }
.section { font-family: "SF Pro Display"; font-size: 12px; font-weight: 600; color: #6f6d74;
           margin: 8px 14px 2px 14px; }
button.item { background: transparent; border: none; box-shadow: none; border-radius: 6px;
              padding: 3px 10px; margin: 0 5px; min-height: 22px; color: #ececf0;
              font-family: "SF Pro Display"; font-size: 13px; }
button.item:hover { background: #2f6ef7; color: white; }
.mark { min-width: 14px; color: #ececf0; }
.hsep { background: rgba(255,255,255,0.08); min-height: 1px; margin: 5px 12px; }
.row-label { font-family: "SF Pro Display"; font-size: 13px; color: #ececf0; }
.panel { background: #232125; border-radius: 14px; padding: 16px 18px;
         border: 1px solid rgba(255,255,255,0.09); }
.panel-title { font-family: "SF Pro Display"; font-size: 13px; font-weight: 700; color: #ececf0; }
.dim { color: #8e8d94; font-size: 12px; }
dropdown > button { background: rgba(255,255,255,0.08); border: none; box-shadow: none;
                    border-radius: 7px; min-height: 26px; padding: 0 8px; color: #ececf0; }
scale trough { background: rgba(255,255,255,0.14); min-height: 4px; border-radius: 4px; }
scale highlight { background: #6b7ce8; border-radius: 4px; }
scale slider { background: #9a9aa2; min-width: 18px; min-height: 18px; border-radius: 9px; }
switch { background: rgba(255,255,255,0.16); }
switch:checked { background: #6b7ce8; }
"""


def _hex_rgb(color: str) -> tuple[float, float, float]:
    color = (color or "").lstrip("#")
    try:
        return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (0.55, 0.35, 0.45)


def _rgba_hex(rgba: Gdk.RGBA) -> str:
    return f"#{round(rgba.red * 255):02X}{round(rgba.green * 255):02X}{round(rgba.blue * 255):02X}"


ADWAITA_SYMBOLIC = "/usr/share/icons/Adwaita/symbolic"


def _icon_image(name: str) -> Gtk.Image:
    """The named symbolic icon from the user's theme, else Adwaita's file.

    HyDE's icon themes (Tela) lack several media/symbolic icons and do not
    inherit Adwaita, and a display's theme cannot be swapped per app.
    """
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    if theme.has_icon(name):
        return Gtk.Image.new_from_icon_name(name)
    import glob

    for path in glob.glob(f"{ADWAITA_SYMBOLIC}/*/{name}.svg"):
        return Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(path)))
    return Gtk.Image.new_from_icon_name(name)


def _set_icon(image: Gtk.Image, name: str) -> None:
    fresh = _icon_image(name)
    if fresh.get_storage_type() == Gtk.ImageType.GICON:
        image.set_from_gicon(fresh.get_gicon())
    else:
        image.set_from_icon_name(name)


def _icon_button(icon: str, callback, big: bool = False, tooltip: str = "") -> Gtk.Button:
    button = Gtk.Button()
    button.add_css_class("round")
    if big:
        button.add_css_class("big")
    image = _icon_image(icon)
    image.set_pixel_size(22 if big else 16)
    button.set_child(image)
    button.set_tooltip_text(tooltip or None)
    button.connect("clicked", callback)
    return button


class ArtView(Gtk.DrawingArea):
    """Album art with the reference look: rounded image, thin light ring,
    soft drop shadow. Painted directly, so its size is exact."""

    PAD = 26  # room for the shadow around the art

    def __init__(self, side: int):
        super().__init__()
        self.side = side
        self.path = ""
        self.surface = None
        self.set_draw_func(self._draw)
        self._apply_size()

    def _apply_size(self) -> None:
        total = self.side + 2 * self.PAD
        self.set_content_width(total)
        self.set_content_height(total)

    def set_side(self, side: int) -> None:
        if side != self.side:
            self.side = side
            self._apply_size()
            self.queue_draw()

    def set_art(self, path: str) -> None:
        self.path = path
        try:
            self.surface = cairo.ImageSurface.create_from_png(path) if path else None
        except (cairo.Error, OSError):
            self.surface = None
        self.queue_draw()

    @staticmethod
    def _rounded(cr, x, y, w, h, r) -> None:
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -1.5708, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
        cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        cr.arc(x + r, y + r, r, 3.1416, 4.7124)
        cr.close_path()

    def _draw(self, _area, cr, width, height) -> None:
        side = self.side
        x = (width - side) / 2
        y = (height - side) / 2
        radius = side * 0.085
        for grow, alpha in ((22, 0.05), (14, 0.09), (7, 0.14), (2, 0.20)):
            cr.set_source_rgba(0, 0, 0, alpha)
            self._rounded(
                cr, x - grow / 2, y - grow / 2 + 8, side + grow, side + grow, radius + grow / 2
            )
            cr.fill()
        ring = 6
        cr.set_source_rgba(1, 1, 1, 0.07)
        self._rounded(cr, x - ring, y - ring, side + 2 * ring, side + 2 * ring, radius + ring)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.set_line_width(1)
        self._rounded(
            cr,
            x - ring + 0.5,
            y - ring + 0.5,
            side + 2 * ring - 1,
            side + 2 * ring - 1,
            radius + ring,
        )
        cr.stroke()
        cr.save()
        self._rounded(cr, x, y, side, side, radius)
        cr.clip()
        if self.surface is not None:
            iw, ih = self.surface.get_width(), self.surface.get_height()
            zoom = max(side / max(1, iw), side / max(1, ih))
            cr.translate(x + (side - iw * zoom) / 2, y + (side - ih * zoom) / 2)
            cr.scale(zoom, zoom)
            cr.set_source_surface(self.surface, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_GOOD)
            cr.paint()
        else:
            cr.set_source_rgba(1, 1, 1, 0.06)
            cr.paint()
        cr.restore()


class Player(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, runtime_dir: str, start: str = "player"):
        super().__init__(application=app, title="encore")
        self.runtime_dir = runtime_dir
        self.look_path = f"{runtime_dir}/encore.look"
        self.sock_path = f"{runtime_dir}/encore.sock"
        self.add_css_class("encore-player")
        self.set_default_size(960, 660)
        self.state: dict = {}
        self.art_path = ""
        self.accent = (0.55, 0.35, 0.45)
        self.expanded = 0.0  # 0..1 art hover expansion
        self.expand_target = 0.0
        self.expand_timer = 0
        self.lyrics_mode = False
        self.lyric_rows: list[Gtk.Label] = []
        self.lyric_key = ""
        self.current_line = -1

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
        self.stack.add_named(self._build_player_page(), "player")
        self.stack.add_named(self._build_lyrics_page(), "lyrics")
        root.append(self._build_toolbar())

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        self._poll()
        GLib.timeout_add(POLL_MS, self._poll)
        GLib.idle_add(lambda: (self.set_focus(None), False)[1])  # no focus ring at open
        if start == "lyrics":
            GLib.idle_add(lambda: (self._toggle_lyrics(), False)[1])
        elif start in ("look", "glow"):
            popover = self.look_menu if start == "look" else self.glow_popover
            GLib.timeout_add(400, lambda: (popover.popup(), False)[1])

    # pages --------------------------------------------------------------------

    def _art_widget(self, size: int) -> tuple[Gtk.Widget, ArtView]:
        art = ArtView(size)
        art.set_halign(Gtk.Align.CENTER)
        art.set_valign(Gtk.Align.CENTER)
        return art, art

    def _meta(self) -> tuple[Gtk.Label, Gtk.Label]:
        title = Gtk.Label(label="Nothing playing")
        title.add_css_class("title")
        title.set_ellipsize(3)
        title.set_max_width_chars(34)
        artist = Gtk.Label(label="")
        artist.add_css_class("artist")
        artist.set_ellipsize(3)
        artist.set_max_width_chars(40)
        return title, artist

    def _controls(self) -> tuple[Gtk.Box, Gtk.Button]:
        row = Gtk.Box(spacing=12)
        row.set_halign(Gtk.Align.CENTER)
        play = _icon_button(
            "media-playback-start-symbolic", lambda *_: self._ctl("play-pause"), big=True
        )
        for widget in (
            _icon_button(
                "media-seek-backward-symbolic", lambda *_: self._seek(-15), tooltip="Back 15 s"
            ),
            _icon_button("media-skip-backward-symbolic", lambda *_: self._ctl("previous")),
            play,
            _icon_button("media-skip-forward-symbolic", lambda *_: self._ctl("next")),
            _icon_button(
                "media-seek-forward-symbolic", lambda *_: self._seek(15), tooltip="Forward 15 s"
            ),
        ):
            widget.set_valign(Gtk.Align.CENTER)
            row.append(widget)
        return row, play

    def _lyrics_pill(self) -> Gtk.Button:
        pill = Gtk.Button()
        pill.add_css_class("pill")
        box = Gtk.Box(spacing=6)
        icon = _icon_image("chat-message-new-symbolic")
        icon.set_pixel_size(14)
        box.append(icon)
        box.append(Gtk.Label(label="Lyrics"))
        pill.set_child(box)
        pill.connect("clicked", lambda *_: self._toggle_lyrics())
        return pill

    def _build_player_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.set_valign(Gtk.Align.CENTER)
        page.set_halign(Gtk.Align.CENTER)
        self.art_frame, self.art = self._art_widget(ART)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._expand(1.0))
        motion.connect("leave", lambda *_: self._expand(0.0))
        self.art_frame.add_controller(motion)
        page.append(self.art_frame)
        self.title, self.artist = self._meta()
        self.title.set_margin_top(8)
        page.append(self.title)
        page.append(self.artist)
        controls, self.play_button = self._controls()
        controls.set_margin_top(8)
        page.append(controls)
        self.lyrics_pill = self._lyrics_pill()
        self.lyrics_pill.set_halign(Gtk.Align.CENTER)
        page.append(self.lyrics_pill)
        return page

    def _build_lyrics_page(self) -> Gtk.Widget:
        page = Gtk.Box()
        page.set_valign(Gtk.Align.CENTER)
        page.set_halign(Gtk.Align.CENTER)
        card = Gtk.Box(spacing=28)
        card.add_css_class("card")
        card.set_size_request(820, 380)
        page.append(card)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left.set_valign(Gtk.Align.CENTER)
        frame, self.art_small = self._art_widget(210)
        left.append(frame)
        self.title_small, self.artist_small = self._meta()
        left.append(self.title_small)
        left.append(self.artist_small)
        controls, self.play_small = self._controls()
        left.append(controls)
        row = Gtk.Box(spacing=8)
        row.set_halign(Gtk.Align.CENTER)
        self.lyrics_pill_small = self._lyrics_pill()
        self.lyrics_pill_small.add_css_class("on")
        row.append(self.lyrics_pill_small)
        row.append(
            _icon_button("document-open-recent-symbolic", lambda *_: self._scroll_to_current(True))
        )
        left.append(row)
        card.append(left)
        sep = Gtk.Box()
        sep.add_css_class("vsep")
        card.append(sep)
        self.lyric_scroller = Gtk.ScrolledWindow()
        self.lyric_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.lyric_scroller.set_hexpand(True)
        self.lyric_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.lyric_box.set_margin_top(120)
        self.lyric_box.set_margin_bottom(220)
        self.lyric_scroller.set_child(self.lyric_box)
        card.append(self.lyric_scroller)
        return page

    def _build_toolbar(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=10)
        bar.add_css_class("bottombar")
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_margin_bottom(26)
        self.palette_button = _icon_button(
            "preferences-color-symbolic", lambda *_: self.look_menu.popup(), tooltip="Lyrics look"
        )
        self.look_menu = self._build_look_menu(self.palette_button)
        bar.append(self.palette_button)
        bar.append(
            _icon_button(
                "audio-volume-high-symbolic",
                lambda *_: self._hyde("toggle"),
                tooltip="Lyrics overlay",
            )
        )
        bar.append(
            _icon_button(
                "display-brightness-symbolic", lambda *_: self._hyde("glow"), tooltip="Glow"
            )
        )
        settings = Gtk.Button(label="Settings")
        settings.add_css_class("pill")
        self.glow_popover = self._build_glow_popover(settings)
        settings.connect("clicked", lambda *_: self.glow_popover.popup())
        bar.append(settings)
        bar.append(
            _icon_button(
                "video-display-symbolic",
                lambda *_: self._hyde("style", "next"),
                tooltip="Next lyrics style",
            )
        )
        bar.append(
            _icon_button(
                "system-lock-screen-symbolic",
                lambda *_: self._run(["hyde-shell", "hyprlock.sh", "--test", "Encore"]),
                tooltip="Preview lock screen",
            )
        )
        bar.append(
            _icon_button(
                "view-fullscreen-symbolic", lambda *_: self._hyde("show"), tooltip="Show workspace"
            )
        )
        return bar

    # look menu (styles, fonts, size, colors) ------------------------------------

    def _menu_item(self, box: Gtk.Box, label: str, callback, mark_key=None) -> Gtk.Button:
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
        self.menu_items.append(button)
        return button

    @staticmethod
    def _section(box: Gtk.Box, text: str) -> None:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("section")
        box.append(label)

    @staticmethod
    def _hsep(box: Gtk.Box) -> None:
        sep = Gtk.Box()
        sep.add_css_class("hsep")
        box.append(sep)

    def _build_look_menu(self, anchor: Gtk.Widget) -> Gtk.Popover:
        self.menu_items: list[Gtk.Button] = []
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

        self._section(box, "Style")
        for style in STYLES:
            self._menu_item(
                box, style.capitalize(), lambda *_a, s=style: self._look(style=s), ("style", style)
            )
        self._hsep(box)
        self._section(box, "Font")
        for family in self._fonts():
            self._menu_item(box, family, lambda *_a, f=family: self._look(font=f), ("font", family))
        self._hsep(box)
        self._section(box, "Text Size")
        size_row = Gtk.Box(spacing=8, margin_start=14, margin_end=10)
        self.size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, MIN_SIZE, MAX_SIZE, 1
        )
        self.size_scale.set_hexpand(True)
        self.size_scale.set_draw_value(False)
        self.size_scale.connect("value-changed", self._on_size)
        reset = Gtk.Button(label="Reset")
        reset.add_css_class("pill")
        reset.connect("clicked", lambda *_: self._look(size=None))
        size_row.append(self.size_scale)
        size_row.append(reset)
        box.append(size_row)
        self._hsep(box)
        self._section(box, "Color")
        self._menu_item(
            box,
            "Auto Sync",
            lambda *_: self._look(lyric_color=None, highlight_color=None, secondary_color=None),
            ("auto", None),
        )
        self.color_buttons: dict[str, Gtk.ColorDialogButton] = {}
        for key, label in (
            ("lyric_color", "Lyric Text..."),
            ("highlight_color", "Highlight..."),
            ("secondary_color", "Secondary Text..."),
        ):
            row = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=2, margin_bottom=2)
            dialog = Gtk.ColorDialog()
            dialog.set_with_alpha(False)
            picker = Gtk.ColorDialogButton.new(dialog)
            picker.connect("notify::rgba", lambda b, _p, k=key: self._on_color(k, b))
            self.color_buttons[key] = picker
            text = Gtk.Label(label=label, xalign=0)
            text.add_css_class("row-label")
            row.append(picker)
            row.append(text)
            box.append(row)
        self._menu_item(
            box,
            "Reset Colors",
            lambda *_: self._look(lyric_color=None, highlight_color=None, secondary_color=None),
        )
        popover.connect("show", lambda *_: self._sync_menu())
        return popover

    # glow popover ----------------------------------------------------------------

    def _panel_row(self, box: Gtk.Box, label: str, widget: Gtk.Widget) -> None:
        row = Gtk.Box(spacing=10, margin_top=4, margin_bottom=4)
        text = Gtk.Label(label=label, xalign=0)
        text.add_css_class("row-label")
        text.set_hexpand(True)
        row.append(text)
        row.append(widget)
        box.append(row)

    def _build_glow_popover(self, anchor: Gtk.Widget) -> Gtk.Popover:
        popover = Gtk.Popover()
        popover.set_parent(anchor)
        popover.set_has_arrow(False)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panel.add_css_class("panel")
        panel.set_size_request(300, -1)
        popover.set_child(panel)
        title = Gtk.Label(label="encore", xalign=0)
        title.add_css_class("panel-title")
        panel.append(title)

        self.gradient = Gtk.DropDown.new_from_strings(["1 Color", "2 Colors"])
        self.gradient.connect("notify::selected", self._on_gradient)
        self._panel_row(panel, "Gradient", self.gradient)
        self.animation = Gtk.DropDown.new_from_strings(["Music Sync", "Breathe", "Static"])
        self.animation.connect("notify::selected", self._on_animation)
        self._panel_row(panel, "Animation", self.animation)

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
            scale.connect("value-changed", self._on_glow_scale, attr)
            setattr(self, f"glow_{attr}", scale)
            panel.append(scale)

        self.override = Gtk.Switch()
        self.override.set_valign(Gtk.Align.CENTER)
        self.override.connect("state-set", self._on_override)
        self._panel_row(panel, "Override album color", self.override)
        wheels = Gtk.Box(spacing=16, homogeneous=True, margin_top=4)
        self.glow_pickers: dict[str, Gtk.ColorDialogButton] = {}
        for key, label in (("glow_primary", "Primary"), ("glow_secondary", "Secondary")):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            caption = Gtk.Label(label=label)
            caption.add_css_class("dim")
            dialog = Gtk.ColorDialog()
            dialog.set_with_alpha(False)
            picker = Gtk.ColorDialogButton.new(dialog)
            picker.set_size_request(-1, 42)
            picker.connect("notify::rgba", lambda b, _p, k=key: self._on_color(k, b))
            self.glow_pickers[key] = picker
            col.append(caption)
            col.append(picker)
            wheels.append(col)
        panel.append(wheels)

        display_caption = Gtk.Label(label="Display", xalign=0)
        display_caption.add_css_class("row-label")
        display_caption.set_margin_top(8)
        panel.append(display_caption)
        self.display = Gtk.DropDown.new_from_strings(self._monitors())
        self.display.connect("notify::selected", self._on_display)
        panel.append(self.display)

        self.lock_switch = Gtk.Switch()
        self.lock_switch.set_valign(Gtk.Align.CENTER)
        self.lock_switch.connect("state-set", self._on_lock_player)
        self._panel_row(panel, "Lock screen player", self.lock_switch)

        quit_button = Gtk.Button(label="Quit encore")
        quit_button.add_css_class("pill")
        quit_button.set_halign(Gtk.Align.START)
        quit_button.set_margin_top(8)
        quit_button.connect("clicked", lambda *_: self._quit_all())
        panel.append(quit_button)
        popover.connect("show", lambda *_: self._sync_glow_panel())
        return popover

    # actions ------------------------------------------------------------------

    @staticmethod
    def _run(cmd: list[str]) -> None:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )

    def _hyde(self, *args: str) -> None:
        self._run(["hyde-shell", "encore", *args])

    def _player_args(self) -> list[str]:
        player = self.state.get("player")
        return ["-p", player] if player else []

    def _ctl(self, command: str) -> None:
        self._run(["playerctl", *self._player_args(), command])

    def _seek(self, seconds: int) -> None:
        sign = "+" if seconds > 0 else "-"
        self._run(["playerctl", *self._player_args(), "position", f"{abs(seconds)}{sign}"])

    def _look(self, **changes) -> None:
        update_look(self.look_path, **changes)
        self._sync_menu()

    def _on_size(self, scale) -> None:
        if not getattr(self, "_syncing", False):
            update_look(self.look_path, size=int(scale.get_value()))

    def _on_color(self, key: str, button: Gtk.ColorDialogButton) -> None:
        if getattr(self, "_syncing", False):
            return
        update_look(self.look_path, **{key: _rgba_hex(button.get_rgba())})

    def _on_gradient(self, dropdown, _pspec) -> None:
        if not getattr(self, "_syncing", False):
            update_look(self.look_path, glow_colors=dropdown.get_selected() + 1)

    def _on_animation(self, dropdown, _pspec) -> None:
        if not getattr(self, "_syncing", False):
            update_look(
                self.look_path,
                glow_animation=("music", "breathe", "static")[dropdown.get_selected()],
            )

    def _on_glow_scale(self, scale, attr: str) -> None:
        if not getattr(self, "_syncing", False):
            update_look(self.look_path, **{f"glow_{attr}": int(scale.get_value())})

    def _on_override(self, _switch, state) -> bool:
        if not getattr(self, "_syncing", False):
            update_look(self.look_path, glow_override=bool(state))
        return False

    def _on_display(self, dropdown, _pspec) -> None:
        if getattr(self, "_syncing", False):
            return
        names = self._monitors()
        index = dropdown.get_selected()
        if 0 <= index < len(names):
            self._run(
                ["notify-send", "encore", f"Display {names[index]} applies on next overlay start"]
            )

    def _on_lock_player(self, _switch, state) -> bool:
        if not getattr(self, "_syncing", False) and state:
            self._run(["hyde-shell", "hyprlock.sh", "--select"])
        return False

    def _quit_all(self) -> None:
        for name in ("encore-overlay.pid", "encore-glow.pid"):
            pid = read_pid(f"{self.runtime_dir}/{name}")  # type: ignore[arg-type]
            if pid is not None and pid_alive(pid):
                self._run(["kill", str(pid)])
        self.close()

    def _toggle_lyrics(self) -> None:
        self.lyrics_mode = not self.lyrics_mode
        self.stack.set_visible_child_name("lyrics" if self.lyrics_mode else "player")
        if self.lyrics_mode:
            GLib.timeout_add(260, lambda: (self._scroll_to_current(True), False)[1])

    def _on_key(self, _ctl, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval == Gdk.KEY_space:
            self._ctl("play-pause")
            return True
        if keyval in (Gdk.KEY_l, Gdk.KEY_L):
            self._toggle_lyrics()
            return True
        return False

    @staticmethod
    def _fonts() -> list[str]:
        preferred = [
            "SF Pro Display",
            "SF Pro Rounded",
            "Inter",
            "Helvetica Neue",
            "Futura",
            "Didot",
            "Georgia",
            "JetBrainsMono Nerd Font",
        ]
        try:
            out = subprocess.run(
                ["fc-list", ":", "family"], capture_output=True, text=True, check=False
            ).stdout
        except OSError:
            return preferred[:1]
        have = {name.strip() for line in out.splitlines() for name in line.split(",")}
        return [f for f in preferred if f in have] or preferred[:1]

    @staticmethod
    def _monitors() -> list[str]:
        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        names = []
        for i in range(monitors.get_n_items()):
            m = monitors.get_item(i)
            names.append(m.get_connector() or f"Display {i + 1}")
        return names or ["Display"]

    # state --------------------------------------------------------------------

    def _poll(self) -> bool:
        state = read_state(self.sock_path) or {}
        self.state = state
        track = state.get("track") or {}
        title = track.get("title") or "Nothing playing"
        artist = track.get("artist") or ""
        for label, value in (
            (self.title, title),
            (self.title_small, title),
            (self.artist, artist),
            (self.artist_small, artist),
        ):
            if label.get_label() != value:
                label.set_label(value)
        icon = (
            "media-playback-pause-symbolic"
            if state.get("status") == "playing"
            else "media-playback-start-symbolic"
        )
        if icon != getattr(self, "_play_icon", None):
            self._play_icon = icon
            for button in (self.play_button, self.play_small):
                _set_icon(button.get_child(), icon)
        art = track.get("art") or ""
        if art != self.art_path:
            self.art_path = art
            for view in (self.art, self.art_small):
                view.set_art(art)
            self.accent = _hex_rgb(pick_accent(state.get("palette") or {}))
            self.backdrop.queue_draw()
        self._sync_lyrics(state)
        return True

    def _sync_lyrics(self, state: dict) -> None:
        lyrics = state.get("lyrics") or {}
        lines = lyrics.get("lines") or []
        key = f"{(state.get('track') or {}).get('key', '')}:{len(lines)}"
        if key != self.lyric_key:
            self.lyric_key = key
            child = self.lyric_box.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.lyric_box.remove(child)
                child = nxt
            self.lyric_rows = []
            texts = [ln.get("text", "") for ln in lines if ln.get("text")]
            if not texts:
                texts = ["No synced lyrics for this track"]
            for text in texts:
                label = Gtk.Label(label=text, xalign=0)
                label.add_css_class("lyric")
                label.set_wrap(True)
                label.set_max_width_chars(36)
                self.lyric_box.append(label)
                self.lyric_rows.append(label)
            self.current_line = -1
        line = state.get("line") or {}
        index = line.get("index", -1)
        if lines and 0 <= index < len(lines):
            # map line index (which counts empty gap lines) to text rows
            texts_before = sum(1 for ln in lines[: index + 1] if ln.get("text")) - 1
            index = max(0, texts_before)
        if index != self.current_line and self.lyric_rows:
            self.current_line = index
            for i, row in enumerate(self.lyric_rows):
                row.remove_css_class("current")
                row.remove_css_class("near")
                if i == index:
                    row.add_css_class("current")
                elif abs(i - index) == 1:
                    row.add_css_class("near")
            self._scroll_to_current(False)

    def _scroll_to_current(self, instant: bool) -> None:
        if not self.lyric_rows or not (0 <= self.current_line < len(self.lyric_rows)):
            return
        row = self.lyric_rows[self.current_line]
        ok, rect = row.compute_bounds(self.lyric_box)
        if not ok:
            return
        adj = self.lyric_scroller.get_vadjustment()
        target = max(0.0, rect.get_y() - 120)
        if instant:
            adj.set_value(target)
            return
        start = adj.get_value()
        steps = 10
        counter = {"i": 0}

        def step():
            counter["i"] += 1
            t = counter["i"] / steps
            eased = 1 - (1 - t) ** 3
            adj.set_value(start + (target - start) * eased)
            return counter["i"] < steps

        GLib.timeout_add(16, step)

    # hover expansion ------------------------------------------------------------

    def _expand(self, target: float) -> None:
        self.expand_target = target
        if not self.expand_timer:
            self.expand_timer = GLib.timeout_add(16, self._expand_step)

    def _expand_step(self) -> bool:
        step = 16 / EXPAND_MS
        if self.expanded < self.expand_target:
            self.expanded = min(self.expand_target, self.expanded + step)
        else:
            self.expanded = max(self.expand_target, self.expanded - step)
        eased = 1 - (1 - self.expanded) ** 3
        self.art.set_side(int(ART + (ART_EXPANDED - ART) * eased))
        self.backdrop.queue_draw()
        if self.expanded == self.expand_target:
            self.expand_timer = 0
            return False
        return True

    def _draw_backdrop(self, _area, cr, width, height) -> None:
        cr.set_source_rgb(0.094, 0.090, 0.102)
        cr.paint()
        r, g, b = self.accent
        eased = 1 - (1 - self.expanded) ** 3
        # album-tinted bloom behind the art, stronger when expanded
        cx, cy = width / 2, height * 0.36
        glow = cairo.RadialGradient(cx, cy, 20, cx, cy, max(width, height) * (0.38 + 0.25 * eased))
        glow.add_color_stop_rgba(0, r, g, b, 0.22 + 0.20 * eased)
        glow.add_color_stop_rgba(0.55, r, g, b, 0.07 + 0.10 * eased)
        glow.add_color_stop_rgba(1, r, g, b, 0.0)
        cr.set_source(glow)
        cr.paint()
        if eased > 0:
            wash = cairo.LinearGradient(0, 0, 0, height)
            wash.add_color_stop_rgba(0, r, g, b, 0.10 * eased)
            wash.add_color_stop_rgba(1, r * 0.4, g * 0.4, b * 0.4, 0.22 * eased)
            cr.set_source(wash)
            cr.paint()

    # menu sync -----------------------------------------------------------------

    def _sync_menu(self) -> None:
        look = read_look(self.look_path)
        style = look.get("style", "line")
        font = look.get("font", "")
        auto = not any(k in look for k in ("lyric_color", "highlight_color", "secondary_color"))
        for item in self.menu_items:
            kind = getattr(item, "mark_key", None)
            on = False
            if kind:
                key, value = kind
                on = (
                    (key == "style" and value == style)
                    or (key == "font" and value == font)
                    or (key == "auto" and auto)
                )
            item.mark.set_label("✓" if on else "")
        self._syncing = True
        try:
            self.size_scale.set_value(look.get("size", 30))
            palette = self.state.get("palette") or {}
            defaults = {
                "lyric_color": "#" + palette.get("1xa7", "F2A7C3"),
                "highlight_color": "#" + pick_accent(palette),
                "secondary_color": "#" + palette.get("2xa6", "A87C9A"),
            }
            for key, button in self.color_buttons.items():
                rgba = Gdk.RGBA()
                rgba.parse(look.get(key) or defaults[key])
                button.set_rgba(rgba)
        finally:
            self._syncing = False

    def _sync_glow_panel(self) -> None:
        look = read_look(self.look_path)
        self._syncing = True
        try:
            self.gradient.set_selected(look.get("glow_colors", 2) - 1)
            self.animation.set_selected(
                ("music", "breathe", "static").index(look.get("glow_animation", "music"))
            )
            self.glow_thickness.set_value(look.get("glow_thickness", 130))
            self.glow_intensity.set_value(look.get("glow_intensity", 85))
            self.override.set_active(look.get("glow_override", False))
            for key, button in self.glow_pickers.items():
                rgba = Gdk.RGBA()
                rgba.parse(look.get(key) or ("#6B7CE8" if key == "glow_primary" else "#C86BE8"))
                button.set_rgba(rgba)
        finally:
            self._syncing = False


def run_player(runtime_dir: str, pidfile: str, start: str = "player") -> int:
    if not claim(pidfile):
        subprocess.run(
            ["hyprctl", "dispatch", "focuswindow", "class:^org\\.hyde\\.encore\\.player$"],
            check=False,
        )
        return 0
    app = Gtk.Application(
        application_id="org.hyde.encore.player", flags=Gio.ApplicationFlags.NON_UNIQUE
    )

    def on_activate(application):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        Player(application, runtime_dir, start).present()

    app.connect("activate", on_activate)
    try:
        return app.run(None)
    finally:
        release(pidfile)
