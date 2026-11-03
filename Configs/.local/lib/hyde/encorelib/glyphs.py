"""Semantic glyphs for the visual style: a word gets a small icon beside it."""

from __future__ import annotations

import re

_CLEAN = re.compile(r"[^a-z']+")

GLYPHS = {
    "city": "󰅆",
    "left": "←",
    "right": "→",
    "up": "↑",
    "down": "↓",
    "started": "▶",
    "start": "▶",
    "stop": "■",
    "fire": "󰈸",
    "money": "󰄔",
    "cash": "󰄔",
    "phone": "󰏲",
    "call": "󰏲",
    "home": "󰋜",
    "house": "󰋜",
    "heart": "󰋑",
    "love": "󰋑",
    "star": "󰓎",
    "stars": "󰓎",
    "night": "󰖔",
    "moon": "󰖔",
    "sun": "󰖨",
    "rain": "󰖗",
    "glasses": "󱗹",
    "champagne": "󱗹",
    "drink": "󱗹",
    "shot": "󱗹",
    "car": "󰄋",
    "drive": "󰄋",
    "plane": "󰀝",
    "fly": "󰀝",
    "time": "󰥔",
    "clock": "󰥔",
    "eyes": "󰈈",
    "see": "󰈈",
    "crown": "󰆥",
    "king": "󰆥",
    "queen": "󰆥",
    "music": "󰝚",
    "song": "󰝚",
    "dance": "󰝚",
}


def glyph_for(word: str) -> str | None:
    key = _CLEAN.sub("", word.lower()).strip("'")
    return GLYPHS.get(key)
