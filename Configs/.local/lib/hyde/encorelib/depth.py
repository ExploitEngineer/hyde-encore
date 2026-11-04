"""Depth for the lyrics list: how far a line is from the current one, and where to scroll.

The current line floats (full size and opacity, sharp); the lines beside it
recede one step, every other line two, like Apple Music's lyrics.
"""

from __future__ import annotations

# per step: (scale, opacity, blur radius in px)
DEPTH = ((1.0, 1.0, 0.0), (0.94, 0.55, 1.5), (0.9, 0.32, 3.0))
ANCHOR = 0.38  # the current line's center sits at this share of the view's height


def step(distance: int) -> int:
    """0 for the current line, 1 for its neighbours, 2 for everything else."""
    return min(abs(distance), len(DEPTH) - 1)


def scroll_target(
    tops: list[float], heights: list[float], current: int, view_h: float, anchor: float = ANCHOR
) -> float:
    """The scroll offset that puts the current line's center at the anchor; never
    above the top, but past the end is fine (the last lines rise, like Apple Music)."""
    if not tops or current < 0 or current >= len(tops):
        return 0.0
    return max(0.0, tops[current] + heights[current] / 2 - anchor * view_h)


def visible_range(
    tops: list[float], heights: list[float], scroll: float, view_h: float
) -> tuple[int, int]:
    """(first, last) line indexes to draw: the lines overlapping the view plus
    one of slack on each side, so a line never pops at the edge."""
    n = len(tops)
    if n == 0:
        return (0, -1)
    overlapping = [
        i for i in range(n) if tops[i] + heights[i] > scroll and tops[i] < scroll + view_h
    ]
    if not overlapping:
        return (n - 1, n - 1) if scroll >= tops[-1] else (0, 0)
    return (max(0, overlapping[0] - 1), min(n - 1, overlapping[-1] + 1))
