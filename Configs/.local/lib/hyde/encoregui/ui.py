"""The look shared by every page of the Encore window: CSS, icons, buttons."""

from __future__ import annotations

import glob
import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk

UI_FONT = "SF Pro Display"
ADWAITA_SYMBOLIC = "/usr/share/icons/Adwaita/symbolic"

# tokens (GTK CSS has no custom properties: rendered into the sheet once)
UI_BASE = "#141317"
UI_FG = "#ececf0"
UI_DIM = "#9a98a3"
UI_MUTED = "#6f6d76"
GLASS_FILL = "rgba(28,26,34,0.62)"
GLASS_FILL_HOVER = "rgba(44,41,52,0.72)"
GLASS_EDGE = "rgba(255,255,255,0.12)"
HAIRLINE = "rgba(255,255,255,0.08)"
FONT = '"SF Pro Display", "Inter", sans-serif'
SERIF = '"Instrument Serif", "Noto Serif", serif'

CSS = f"""
window.encore-app {{ background: {UI_BASE}; }}
* {{ font-family: {FONT}; }}
.title {{ font-size: 24px; font-weight: 800; color: {UI_FG}; letter-spacing: -0.2px; }}
.artist {{ font-size: 15px; font-weight: 500; color: {UI_DIM}; }}
button.round {{ min-width: 44px; min-height: 44px; border-radius: 999px; padding: 0;
               background: {GLASS_FILL}; border: 1px solid {GLASS_EDGE};
               box-shadow: 0 6px 18px rgba(0,0,0,0.28); color: #dcdbe2;
               transition: background-color 120ms ease-out, box-shadow 120ms ease-out, border-color 120ms ease-out; }}
button.round:hover {{ background: {GLASS_FILL_HOVER}; border-color: rgba(255,255,255,0.2); }}
button.round:active {{ background: rgba(16,14,20,0.8); box-shadow: 0 2px 6px rgba(0,0,0,0.35); }}
button.round.big {{ min-width: 60px; min-height: 60px; background: {UI_FG}; color: #16141a;
                   border-color: transparent; box-shadow: 0 10px 28px rgba(0,0,0,0.45); }}
button.round.big:hover {{ background: #ffffff; }}
button.round.big:active {{ background: #d6d5dc; }}
button.round.on {{ border-color: rgba(255,255,255,0.28); }}
button.pill {{ border-radius: 999px; padding: 7px 16px; min-height: 0;
              background: {GLASS_FILL}; border: 1px solid {GLASS_EDGE};
              box-shadow: 0 6px 18px rgba(0,0,0,0.28); color: #dcdbe2; font-size: 13px; font-weight: 600;
              transition: background-color 120ms ease-out, border-color 120ms ease-out; }}
button.pill:hover {{ background: {GLASS_FILL_HOVER}; border-color: rgba(255,255,255,0.2); }}
button.pill:active {{ background: rgba(16,14,20,0.8); }}
button.pill.on {{ color: #ff6f9c; background: rgba(255,111,156,0.12); }}
.bottombar button.round {{ min-width: 42px; min-height: 42px; }}
.card {{ background: rgba(20,18,24,0.42); border-radius: 24px;
        border: 1px solid {HAIRLINE}; padding: 26px; box-shadow: 0 24px 60px rgba(0,0,0,0.35); }}
.lyric {{ font-size: 21px; font-weight: 700; color: rgba(236,236,240,0.30); }}
.lyric.current {{ color: #f4f4f7; }}
.lyric.near {{ color: rgba(236,236,240,0.48); }}
.vsep {{ background: {HAIRLINE}; min-width: 1px; }}
popover.menu-like > contents {{ background: rgba(26,24,31,0.96); border-radius: 14px; padding: 6px 0;
                              border: 1px solid {GLASS_EDGE}; box-shadow: 0 24px 60px rgba(0,0,0,0.5); }}
.section {{ font-size: 11px; font-weight: 600; color: {UI_MUTED}; letter-spacing: 0.9px;
           margin: 10px 14px 2px 14px; }}
button.item {{ background: transparent; border: none; box-shadow: none; border-radius: 7px;
              padding: 4px 10px; margin: 0 6px; min-height: 22px; color: {UI_FG}; font-size: 13px;
              transition: background-color 90ms ease-out; }}
button.item:hover {{ background: #2f6ef7; color: white; }}
.mark {{ min-width: 14px; color: {UI_FG}; }}
.hsep {{ background: {HAIRLINE}; min-height: 1px; margin: 6px 12px; }}
.row-label {{ font-size: 13px; color: {UI_FG}; }}
.panel {{ background: rgba(28,26,34,0.96); border-radius: 16px; padding: 16px 18px;
         border: 1px solid {GLASS_EDGE}; box-shadow: 0 24px 60px rgba(0,0,0,0.5); }}
.panel-title {{ font-size: 11px; font-weight: 600; color: {UI_MUTED}; letter-spacing: 0.9px; }}
.dim {{ color: {UI_DIM}; font-size: 12px; }}
dropdown > button {{ background: rgba(255,255,255,0.08); border: none; box-shadow: none;
                    border-radius: 8px; min-height: 26px; padding: 0 8px; color: {UI_FG}; }}
scale trough {{ background: rgba(255,255,255,0.14); min-height: 4px; border-radius: 4px; }}
scale highlight {{ background: #6b7ce8; border-radius: 4px; }}
scale slider {{ background: #9a9aa2; min-width: 18px; min-height: 18px; border-radius: 9px; }}
switch {{ background: rgba(255,255,255,0.16); }}
switch:checked {{ background: #6b7ce8; }}
.time {{ font-size: 12px; color: {UI_DIM}; font-feature-settings: "tnum"; }}
scale.seek trough {{ min-height: 6px; border-radius: 3px; background: rgba(255,255,255,0.16); }}
scale.seek highlight {{ background: {UI_FG}; border-radius: 3px; }}
scale.seek slider {{ min-width: 14px; min-height: 14px; margin: -4px; border-radius: 7px;
                    background: {UI_FG}; box-shadow: 0 0 0 4px rgba(255,255,255,0.10), 0 2px 8px rgba(0,0,0,0.5);
                    transition: box-shadow 120ms ease-out; }}
scale.seek slider:hover {{ box-shadow: 0 0 0 7px rgba(255,255,255,0.16), 0 2px 8px rgba(0,0,0,0.5); }}
scale.volume trough {{ min-height: 4px; }}
scale.volume slider {{ min-width: 12px; min-height: 12px; margin: -4px; border-radius: 6px;
                      background: {UI_FG}; box-shadow: 0 1px 4px rgba(0,0,0,0.4); }}
.dim-icon {{ color: {UI_DIM}; }}
menubutton.chip > button {{ border-radius: 999px; padding: 4px 12px; min-height: 0;
                           background: rgba(255,255,255,0.05); border: 1px solid {HAIRLINE};
                           box-shadow: none; color: #b8b7bf; font-size: 12px;
                           transition: background-color 120ms ease-out; }}
menubutton.chip > button:hover {{ background: rgba(255,255,255,0.11); }}
.status {{ font-size: 12px; color: {UI_DIM}; }}
.idle-title {{ font-family: {SERIF}; font-style: italic; font-size: 44px; font-weight: 400;
              color: #f4f4f7; letter-spacing: -0.3px; }}
.lyric.message {{ color: rgba(236,236,240,0.55); font-size: 18px; font-weight: 600; }}
.lyric.seekable:hover {{ color: rgba(236,236,240,0.75); }}
.lyric.seekable.current:hover {{ color: #f4f4f7; }}
.glass button.pill, .glass button.round {{ background: rgba(255,255,255,0.07); box-shadow: none;
                                            border-color: rgba(255,255,255,0.08); }}
.glass button.pill:hover, .glass button.round:hover {{ background: rgba(255,255,255,0.14); }}
.glass button.round.big {{ background: {UI_FG}; }}
.fullbar .title {{ font-size: 15px; }} .fullbar .artist {{ font-size: 12px; }}
.fullbar .time {{ color: rgba(255,255,255,0.75); }}
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
        f"button.pill.on {{ color: #{a}; background: alpha(#{a}, 0.14); border-color: alpha(#{a}, 0.5); }}\n"
        f"button.round.on {{ color: #{a}; background: alpha(#{a}, 0.16); border-color: alpha(#{a}, 0.55); }}\n"
        f"scale.seek slider {{ box-shadow: 0 0 0 4px alpha(#{a}, 0.22), 0 0 18px alpha(#{a}, 0.55), 0 2px 8px rgba(0,0,0,0.5); }}\n"
        f"scale highlight {{ background: #{a}; }}\n"
        f"switch:checked {{ background: #{h}; }}\n"
        f"button.item:hover {{ background: #{h}; color: #{on}; }}\n"
    )


def trace(what: str) -> None:
    """Timing breadcrumbs for the stage tool: appended to $ENCORE_TRACE when set."""
    path = os.environ.get("ENCORE_TRACE")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.monotonic():.3f} {what}\n")


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )
