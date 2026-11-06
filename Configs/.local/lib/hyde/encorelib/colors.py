"""One color scheme for every encore surface, derived from the cover.

wallbash gives four accent families (1xa*..4xa*), each a ramp of shades.
The first family with real color drives the scheme; a grey cover hands
over to the active HyDE theme (the wallpaper palette), so encore still
belongs to the desktop, and only when both are grey does a curated
default step in. Text colors are chosen by contrast, never assumed.

Floors on what Auto Sync derives, measured on BASE (the black light under
Clear and the Stage): Lyric Text at least 7:1, Secondary between 2.5:1 and
4:1 (readable, clearly behind), the text on the Highlight block at least
4.5:1 against the block, reached by moving the text, never the block. The
album field's blobs are capped at 28% luminance so type over them reads.
"""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass

from .palette import _luminance, contrast_ratio

DEFAULT_ACCENT = "B48CFF"  # soft violet: reads well on any dark desktop
MIN_CHROMA = 0.15  # below this a family reads as grey (a slight cast must not turn garish)
DARK = "101014"  # what lyrics sit on: the overlay's shadowed text, dark desktops
INK = "16121C"  # dark text for light highlight blocks
BASE = "141317"  # the black light lyrics sit on in Clear and the Stage
LYRIC_FLOOR = 7.0
ON_BLOCK_FLOOR = 4.5
SECONDARY_BAND = (2.5, 4.0)
BLOB_MAX_LUMINANCE = 0.28
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


def luminance(color: str) -> float:
    """WCAG relative luminance of an RRGGBB color."""
    return _luminance(color)


def _readable(color: str, minimum: float = 4.5, on: str = DARK) -> str:
    """The color, lightened along its own hue until it reads on `on`."""
    h, lightness, s = _hls(color)
    while contrast_ratio(color, on) < minimum and lightness < 0.97:
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


def block_for(accent: str) -> str:
    """The Highlight block: the accent's hue as a saturated mid-tone."""
    h, _, s = _hls(accent)
    return _from_hls(h, 0.42, max(s, 0.55))


def text_on_block(block: str) -> str:
    """White or ink, whichever reads better on the block, darkened toward pure
    black when ink falls short of 4.5:1; the block itself never changes. On
    any color either pure white or pure black reaches 4.58:1."""
    text = text_on(block)
    if contrast_ratio(text, block) >= ON_BLOCK_FLOOR:
        return text
    if contrast_ratio("FFFFFF", block) >= ON_BLOCK_FLOOR:
        return "FFFFFF"
    for step in range(1, 11):
        darker = _mix(INK, "000000", step / 10)
        if contrast_ratio(darker, block) >= ON_BLOCK_FLOOR:
            return darker
    return "000000"


def _in_band(color: str, low: float, high: float, on: str = BASE) -> str:
    """The color moved along its own lightness until its contrast on `on` is in [low, high]."""
    h, lightness, s = _hls(color)
    for _ in range(100):
        ratio = contrast_ratio(color, on)
        if ratio > high and lightness > 0.0:
            lightness = max(0.0, lightness - 0.01)
        elif ratio < low and lightness < 1.0:
            lightness = min(1.0, lightness + 0.01)
        else:
            break
        color = _from_hls(h, lightness, s)
    return color


def _capped(color: str, ceiling: float = BLOB_MAX_LUMINANCE) -> str:
    """The color darkened along its own hue until its luminance is at most `ceiling`."""
    h, lightness, s = _hls(color)
    while luminance(color) > ceiling and lightness > 0.0:
        lightness = max(0.0, lightness - 0.01)
        color = _from_hls(h, lightness, s)
    return color


def blob_colors(colors: Scheme, gradient: int = 2) -> tuple[str, str, str]:
    """The album field's three blob colors: the accent alone (1) or the accent
    and the second hue (2), each capped at 28% luminance."""
    second = colors.accent2 if gradient == 2 else colors.accent
    return _capped(colors.accent), _capped(second), _capped(colors.accent)


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
    highlight = block_for(accent)
    return Scheme(
        accent=accent,
        accent2=_readable(second),
        highlight=highlight,
        on_highlight=text_on_block(highlight),
        lyric=_readable(_mix(accent, "FFFFFF", 0.72), LYRIC_FLOOR, BASE),
        secondary=_in_band(_mix(accent, "FFFFFF", 0.35), *SECONDARY_BAND),
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
        on_highlight=text_on_block(highlight),
        lyric=_hexless(look["lyric_color"]) if look.get("lyric_color") else colors.lyric,
        secondary=(
            _hexless(look["secondary_color"]) if look.get("secondary_color") else colors.secondary
        ),
    )
