"""Which face each lyric word is set in, from the families this system has.

The look's font picks the primary sans; the serif partner is Instrument
Serif (Newsreader when missing) and the mono partner JetBrainsMono Nerd Font
(Maple Mono when missing). Each style mixes them per word with the same
seeded picker, so a song always gets the same mix:

- line: primary heavy only
- stack, visual: primary heavy, serif italic and primary regular, about
  50/25/25; the word on visual's Highlight block is never heavy
- constellation: primary semibold, one serif italic word in four

A weight comes from what the family ships, the nearest one (ties to the
heavier): asking Pango for a weight a family lacks makes it embolden the
outline, and a synthetic bold is never used. Italic may be slanted by Pango
when the serif ships no italic face (neither installed serif does here).
"""

from __future__ import annotations

from typing import NamedTuple

from .lyricview import _stable_unit

# the families the Font menu offers, when installed, in this order
DISPLAY_FONTS = (
    "SF Pro Display",
    "Inter",
    "Newsreader",
    "Instrument Serif",
    "Alfa Slab One",
    "Electrolize",
    "Anurati",
    "JetBrainsMono Nerd Font",
    "Maple Mono",
)
# where a user coming from the reference app would look (tooltips, not the list)
ALIASES = {"Newsreader": "New York", "Instrument Serif": "Didot"}
SERIFS = ("Instrument Serif", "Newsreader")
MONOS = ("JetBrainsMono Nerd Font", "Maple Mono")
PARTNER_FAMILIES = SERIFS + MONOS

ROLE_WEIGHT = {"heavy": 700, "semibold": 600, "medium": 400, "serif": 400, "mono": 400}
_WEIGHT_WORD = {
    100: "Thin",
    200: "Ultra-Light",
    300: "Light",
    400: "Normal",
    500: "Medium",
    600: "Semi-Bold",
    700: "Bold",
    800: "Ultra-Bold",
    900: "Heavy",
}

# family -> the (weight, italic) faces it ships
Faces = dict[str, set[tuple[int, bool]]]


class Face(NamedTuple):
    family: str
    weight: int
    italic: bool


def role_for(style: str, line_key: str, index: int, on_block: bool = False) -> str:
    """The role of a word in a style: heavy, serif, medium, semibold (or mono)."""
    if style == "line":
        return "heavy"
    if style == "code":
        return "mono"
    unit = _stable_unit(line_key, index)
    if style == "constellation":
        return "serif" if unit < 0.25 else "semibold"
    role = "heavy" if unit < 0.5 else "serif" if unit < 0.75 else "medium"
    if on_block and role == "heavy":
        return "medium"  # the block carries the weight; the word on it stays light
    return role


def nearest_weight(want: int, have: set[int]) -> int:
    """The shipped weight closest to `want`, the heavier on a tie; `want` when unknown."""
    if not have:
        return want
    return min(have, key=lambda w: (abs(w - want), -w))


def _weights(family: str, have: Faces) -> set[int]:
    faces = have.get(family, set())
    upright = {w for w, italic in faces if not italic}
    return upright or {w for w, _ in faces}


def _first(families: tuple[str, ...], have: Faces, fallback: str) -> str:
    return next((f for f in families if f in have), fallback)


def serif_partner(have: Faces) -> str:
    return _first(SERIFS, have, "Serif")


def mono_partner(have: Faces) -> str:
    return _first(MONOS, have, "Monospace")


def primary_family(font: str, have: Faces) -> str:
    """The first installed family of a font list ("SF Pro Display, Inter, sans-serif"),
    else the first installed display font, else fontconfig's Sans; with nothing
    known at all (no font list read), the first name."""
    names = tuple(name.strip() for name in font.split(",") if name.strip())
    if not have:
        return names[0] if names else DISPLAY_FONTS[0]
    return _first(names, have, _first(DISPLAY_FONTS, have, "Sans"))


def face_for(role: str, primary: str, have: Faces) -> Face:
    """The face a role is set in, with a weight the family really ships."""
    if role == "serif":
        family = serif_partner(have)
    elif role == "mono":
        family = mono_partner(have)
    else:
        family = primary
    weight = nearest_weight(ROLE_WEIGHT.get(role, 400), _weights(family, have))
    return Face(family, weight, role == "serif")


def pango_string(face: Face) -> str:
    """A Pango font description string for a face."""
    word = _WEIGHT_WORD.get(face.weight, "Normal")
    return f"{face.family} {word}{' Italic' if face.italic else ''}"


def menu_fonts(shown: list[str], current: str) -> list[str]:
    """The Font menu's families: the installed display set, plus the family in
    use when it is another one (set from the CLI), so the menu never shows a
    font the surfaces are not using."""
    return shown if current in shown else [*shown, current]
