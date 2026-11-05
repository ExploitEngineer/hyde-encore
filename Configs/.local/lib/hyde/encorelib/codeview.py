"""The code style's rows: past lines as comments, the current one being typed.

After the reference app's Codestyle: the mono partner, line numbers at the
left, the lines already sung dimmed like comments, and the current line
typed in word by word (a word appears when it starts, on the same lead and
timing as every style) with a block caret after it.
"""

from __future__ import annotations

from typing import NamedTuple


class CodeRow(NamedTuple):
    number: int  # the line's number in the song, from 1
    text: str
    current: bool


def typed_text(words: tuple[tuple[str, float], ...]) -> str:
    """The words of the current line that have started, as typed so far."""
    return " ".join(text for text, fill in words if fill > 0.0)


def code_rows(lines: list[str], index: int, typed: str, rows: int = 6) -> list[CodeRow]:
    """The last `rows - 1` lines before `index` as comments, then the typed line."""
    first = max(0, index - (rows - 1))
    past = [
        CodeRow(i + 1, f"// {lines[i]}" if lines[i].strip() else "", False)
        for i in range(first, min(index, len(lines)))
    ]
    return [*past, CodeRow(index + 1, typed, True)]


def fit_scale(widths: list[float], available: float, floor: float = 0.25) -> float:
    """One scale for every row, so the widest fits `available` (never above 1,
    never below `floor`): long lines shrink the block instead of running off."""
    widest = max(widths, default=0.0)
    if widest <= 0.0 or widest <= available:
        return 1.0
    return max(floor, available / widest)
