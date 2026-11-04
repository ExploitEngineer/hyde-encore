"""The look shared by every page of the Encore window: CSS, icons, buttons."""

from __future__ import annotations

import glob

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk

UI_FONT = "SF Pro Display"
ADWAITA_SYMBOLIC = "/usr/share/icons/Adwaita/symbolic"

CSS = """
window.encore-app { background: #18171a; }
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
.time { font-family: "SF Pro Display"; font-size: 11px; color: #8e8d94; font-feature-settings: "tnum"; }
scale.seek trough, scale.volume trough { min-height: 4px; }
scale.seek slider, scale.volume slider { min-width: 12px; min-height: 12px; margin: -4px; border-radius: 6px;
                                         background: #ececf0; box-shadow: 0 1px 4px rgba(0,0,0,0.4); }
scale.seek highlight { background: #ececf0; }
.dim-icon { color: #8e8d94; }
menubutton.chip > button { border-radius: 999px; padding: 4px 12px; min-height: 0;
                           background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
                           box-shadow: none; color: #b8b7bf; font-family: "SF Pro Display"; font-size: 12px; }
menubutton.chip > button:hover { background: rgba(255,255,255,0.12); }
.status { font-family: "SF Pro Display"; font-size: 12px; color: #8e8d94; }
.idle-title { font-family: "SF Pro Display"; font-size: 30px; font-weight: 800; color: #f4f4f7; }
.lyric.message { color: rgba(236,236,240,0.55); font-size: 18px; font-weight: 600; }
.lyric.seekable:hover { color: rgba(236,236,240,0.75); }
.lyric.seekable.current:hover { color: #f4f4f7; }
button.round.on { border-color: rgba(255,255,255,0.18); }
"""


def hex_rgb(color: str) -> tuple[float, float, float]:
    color = (color or "").lstrip("#")
    try:
        return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (0.55, 0.35, 0.45)


def rgba_hex(rgba: Gdk.RGBA) -> str:
    return f"#{round(rgba.red * 255):02X}{round(rgba.green * 255):02X}{round(rgba.blue * 255):02X}"


def icon_image(name: str) -> Gtk.Image:
    """The named symbolic icon from the user's theme, else Adwaita's file.

    HyDE's icon themes (Tela) lack several media/symbolic icons and do not
    inherit Adwaita, and a display's theme cannot be swapped per app.
    """
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    if theme.has_icon(name):
        return Gtk.Image.new_from_icon_name(name)
    for path in glob.glob(f"{ADWAITA_SYMBOLIC}/*/{name}.svg"):
        return Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(path)))
    return Gtk.Image.new_from_icon_name(name)


def set_icon(image: Gtk.Image, name: str) -> None:
    fresh = icon_image(name)
    if fresh.get_storage_type() == Gtk.ImageType.GICON:
        image.set_from_gicon(fresh.get_gicon())
    else:
        image.set_from_icon_name(name)


def icon_button(icon: str, callback, big: bool = False, tooltip: str = "") -> Gtk.Button:
    button = Gtk.Button()
    button.add_css_class("round")
    if big:
        button.add_css_class("big")
    image = icon_image(icon)
    image.set_pixel_size(22 if big else 16)
    button.set_child(image)
    button.set_tooltip_text(tooltip or None)
    button.connect("clicked", callback)
    return button


def accent_rules(colors) -> str:
    """The few rules that follow the album: active pill, sliders, switches, menu hover."""
    a, h, on = colors.accent, colors.highlight, colors.on_highlight
    return (
        f"button.pill.on {{ color: #{a}; background: alpha(#{a}, 0.14); }}\n"
        f"button.round.on {{ color: #{a}; background: alpha(#{a}, 0.16); }}\n"
        f"scale highlight {{ background: #{a}; }}\n"
        f"switch:checked {{ background: #{h}; }}\n"
        f"button.item:hover {{ background: #{h}; color: #{on}; }}\n"
    )


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )
