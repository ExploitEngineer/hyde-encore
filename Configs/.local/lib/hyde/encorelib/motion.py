"""Motion helpers shared by the window's widgets: easing, drift, grain."""

from __future__ import annotations

import math
import random

FIELD_FPS = 1  # the blobs move a few px/s under an 80 px blur: steps are invisible at 1 fps


def field_rate(playing: bool, idle: bool) -> int:
    """How many times a second the album field drifts: while music plays, or while
    nothing plays at all (the idle light); 0 holds it still (paused, or no player)."""
    return FIELD_FPS if playing or idle else 0


def _clamp(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def ease_out(t: float) -> float:
    """Cubic ease-out: fast start, soft landing. Clamped to 0..1."""
    t = _clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    """Cubic ease-in-out, symmetric around 0.5."""
    t = _clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blob_center(
    t: float,
    orbit: tuple[float, float],
    period: tuple[float, float],
    phase: float,
    center: tuple[float, float] = (0.5, 0.5),
) -> tuple[float, float]:
    """Where a drifting blob sits at time t, as fractions of the width and height.

    Two unrelated periods give a slow Lissajous wander that never repeats visibly.
    """
    ax, ay = orbit
    px, py = period
    cx, cy = center
    return (
        cx + ax * math.sin(2 * math.pi * t / px + phase),
        cy + ay * math.cos(2 * math.pi * t / py + phase * 1.7),
    )


def held_scale(duration: float) -> float:
    """How much bigger a word drawn big gets for being held: 1.0 at 0.3 s, 1.18 at 1.2 s."""
    if duration <= 0.3:
        return 1.0
    if duration >= 1.2:
        return 1.18
    return 1.0 + 0.18 * (duration - 0.3) / 0.9


GRAIN_MAX = 14  # alpha of the brightest speck: about 5% white; the strength is baked in


def grain_texture_bytes(size: int = 128, seed: int = 7) -> bytes:
    """A tile of fine white grain as premultiplied BGRA bytes, drawn as is (no opacity node:
    GTK's renderer ignores an opacity node over a repeat node)."""
    rng = random.Random(seed)
    out = bytearray(size * size * 4)
    for i in range(size * size):
        a = int(rng.random() ** 2 * GRAIN_MAX)  # mostly dark, a few brighter specks
        out[i * 4 : i * 4 + 4] = (a, a, a, a)  # white, premultiplied
    return bytes(out)
