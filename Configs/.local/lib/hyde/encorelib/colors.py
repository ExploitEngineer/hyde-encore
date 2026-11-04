"""One color scheme for every encore surface, derived from the cover.

wallbash gives four accent families (1xa*..4xa*), each a ramp of shades.
The first family with real color drives the scheme; a grey cover hands
over to the active HyDE theme (the wallpaper palette), so encore still
belongs to the desktop, and only when both are grey does a curated
default step in. Text colors are chosen by contrast, never assumed.
"""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass

from .palette import contrast_ratio

DEFAULT_ACCENT = "B48CFF"  # soft violet: reads well on any dark desktop
MIN_CHROMA = 0.08  # a family whose most colorful shade is below this is grey
DARK = "101014"  # what lyrics sit on: the overlay's shadowed text, dark desktops
INK = "16121C"  # dark text for light highlight blocks
_KEY = re.compile(r"^([1-4])xa([1-9])$")


@dataclass(frozen=True)
class Scheme:
    accent: str  # sung words, first glow color
    accent2: str  # second hue: glow gradient, accents
    highlight: str  # the block behind the word being sung
    on_highlight: str  # text on that block
    lyric: str  # resting lyric text, a light tint of the accent
    secondary: str  # older and upcoming words
    source: str  # "cover", "theme" or "default"


def _rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: tuple[float, float, float]) -> str:
    return "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _hls(color: str) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(*_rgb(color))


def _from_hls(h: float, lightness: float, saturation: float) -> str:
    return _hex(colorsys.hls_to_rgb(h, lightness, saturation))


def _mix(a: str, b: str, amount: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * amount for x, y in zip(ra, rb, strict=True)))


def _hue_gap(a: str, b: str) -> float:
    gap = abs(_hls(a)[0] - _hls(b)[0]) * 360 % 360
    return min(gap, 360 - gap)


def _families(palette: dict[str, str]) -> list[list[str]]:
    """Accent shades grouped by wallbash family, family 1 first."""
    groups: dict[str, list[str]] = {}
    for key in sorted(palette):
        m = _KEY.match(key)
        value = palette[key]
        if m and re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            groups.setdefault(m.group(1), []).append(value.upper())
    return [groups[k] for k in sorted(groups)]


def _readable(color: str, minimum: float = 4.5) -> str:
    """The color, lightened along its own hue until it reads on DARK."""
    h, lightness, s = _hls(color)
    while contrast_ratio(color, DARK) < minimum and lightness < 0.97:
        lightness = min(0.97, lightness + 0.03)
        color = _from_hls(h, lightness, s)
    return color


def _chroma(color: str) -> float:
    r, g, b = _rgb(color)
    return max(r, g, b) - min(r, g, b)


def _vivid(color: str) -> str:
    """The color's hue as a vivid, readable tone.

    wallbash ramps are muted by design, and HLS saturation rates pale tints
    highly, so picking a shade straight from the ramp gave pastel accents.
    """
    h, _lightness, s = _hls(color)
    return _from_hls(h, 0.68, min(0.85, max(0.6, s * 1.4)))


def _colorful(palette: dict[str, str]) -> list[str]:
    """One vivid representative per family that has real color (by chroma, not HLS)."""
    picks = []
    for shades in _families(palette):
        best = max(shades, key=_chroma)
        if _chroma(best) >= MIN_CHROMA:
            picks.append(_vivid(best))
    return picks


def _highlight(accent: str) -> tuple[str, str]:
    """A saturated mid-tone block and the text color that reads on it."""
    h, _, s = _hls(accent)
    lightness, saturation = 0.47, max(s, 0.55)
    while True:
        block = _from_hls(h, lightness, saturation)
        text = "FFFFFF" if contrast_ratio("FFFFFF", block) >= contrast_ratio(INK, block) else INK
        if contrast_ratio(text, block) >= 4.5 or not 0.3 < lightness < 0.6:
            return block, text
        lightness += -0.03 if text == "FFFFFF" else 0.03


def scheme(cover: dict[str, str], theme: dict[str, str]) -> Scheme:
    """The scheme for a cover palette, falling back to the theme's palette."""
    picks, source = _colorful(cover), "cover"
    if not picks:
        picks, source = _colorful(theme), "theme"
    if not picks:
        picks, source = [DEFAULT_ACCENT], "default"
    accent = _readable(picks[0])
    second = next((c for c in picks[1:] if _hue_gap(c, accent) >= 25), None)
    if second is None:
        h, lightness, s = _hls(accent)
        second = _from_hls((h + 40 / 360) % 1.0, lightness, s)
    highlight, on_highlight = _highlight(accent)
    return Scheme(
        accent=accent,
        accent2=_readable(second),
        highlight=highlight,
        on_highlight=on_highlight,
        lyric=_mix(accent, "FFFFFF", 0.72),
        secondary=_readable(_mix(accent, "FFFFFF", 0.35), 3.0),
        source=source,
    )


def text_on(block: str) -> str:
    """White or ink, whichever reads better on a block color."""
    return "FFFFFF" if contrast_ratio("FFFFFF", block) >= contrast_ratio(INK, block) else INK


@dataclass(frozen=True)
class Resolved:
    """The colors one frame draws with, after the user's overrides."""

    sung: str  # line fill and constellation: `color`, else the accent
    column_sung: str  # stack's sung word: Highlight, else `color`, else the accent
    highlight: str  # visual's block: Highlight, else `color`, else the scheme block
    on_highlight: str
    lyric: str
    secondary: str


def _hexless(value: str) -> str:
    return value.lstrip("#").upper()


def resolve(colors: Scheme, look: dict, override: str) -> Resolved:
    """Apply look overrides (Lyric Text, Highlight, Secondary) and `color` to a scheme."""
    color = _hexless(override) if override else ""
    picked = _hexless(look["highlight_color"]) if look.get("highlight_color") else ""
    highlight = picked or color or colors.highlight
    return Resolved(
        sung=color or colors.accent,
        column_sung=picked or color or colors.accent,
        highlight=highlight,
        on_highlight=text_on(highlight),
        lyric=_hexless(look["lyric_color"]) if look.get("lyric_color") else colors.lyric,
        secondary=(
            _hexless(look["secondary_color"]) if look.get("secondary_color") else colors.secondary
        ),
    )
