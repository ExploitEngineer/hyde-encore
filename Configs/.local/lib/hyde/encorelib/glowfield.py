"""Geometry and color of the screen-edge glow, free of GTK.

The frame is one loop: u runs 0..1 clockwise from the top-left corner
(top edge left to right, right edge down, bottom edge right to left,
left edge up). Two comets travel that loop; the color flows between the
two album colors along it.
"""

from __future__ import annotations

import math

COMETS = 2
COMET_WIDTH = 0.07  # share of the loop a comet's glow spans (gaussian sigma)
COLOR_WAVES = 2  # how many color cycles fit around the frame


def perimeter_u(edge: str, t: float, width: float, height: float) -> float:
    """Loop position of point t (0..1 along the strip's own axis) on an edge."""
    total = 2 * (width + height)
    if edge == "top":
        along = t * width
    elif edge == "right":
        along = width + t * height
    elif edge == "bottom":
        along = width + height + (1 - t) * width
    else:  # left
        along = 2 * width + height + (1 - t) * height
    return (along / total) % 1.0


def _loop_distance(a: float, b: float) -> float:
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


def comet_strength(u: float, phase: float) -> float:
    """0..1 brightness of the comets at loop position u; heads sit at phase + k/COMETS."""
    best = 0.0
    for k in range(COMETS):
        d = _loop_distance(u, phase + k / COMETS)
        best = max(best, math.exp(-0.5 * (d / COMET_WIDTH) ** 2))
    return best


def edge_mix(u: float, phase: float) -> float:
    """0..1 blend from the first album color to the second along the loop."""
    return 0.5 + 0.5 * math.cos(2 * math.pi * (u * COLOR_WAVES - phase))


def falloff_stops(alpha: float) -> list[tuple[float, float]]:
    """(offset, alpha) stops from the screen edge inward: a soft, light-like decay."""
    shape = ((0.0, 1.0), (0.12, 0.62), (0.3, 0.3), (0.55, 0.11), (0.8, 0.03), (1.0, 0.0))
    return [(offset, alpha * k) for offset, k in shape]
