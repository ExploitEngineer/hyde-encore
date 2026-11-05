"""Motion helpers shared by the window's widgets and the lyric styles: easing,
springs and ghost trails, drift, grain."""

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


PLAIN_SECONDS = 0.16  # motion off: every pop and slide is this plain ease-out
GHOST_LAGS = (0.055, 0.110)  # seconds behind the moving word, along its own path
GHOST_ALPHAS = (0.35, 0.18)
POP_SETTLE = 0.32  # a new word's pop
SLIDE_SETTLE = 0.24  # the column pushing up


def spring(t: float, settle: float = 0.32, zeta: float = 0.55) -> float:
    """A damped spring's step response: 0 at t=0, overshoots (about 1.13 at
    zeta 0.55, near 0.43 * settle), and is within 1% of 1 by `settle`, from
    where it is exactly 1 so animations can stop.

    The closed-form underdamped oscillator; the natural frequency is chosen
    so the decay envelope e^(-zeta w t) / sqrt(1 - zeta^2) reaches 1% at `settle`.
    """
    if t <= 0:
        return 0.0
    if t >= settle:
        return 1.0
    root = math.sqrt(1 - zeta * zeta)
    omega = math.log(1 / (0.01 * root)) / (zeta * settle)
    damped = omega * root
    decay = math.exp(-zeta * omega * t)
    return 1 - decay * (math.cos(damped * t) + zeta / root * math.sin(damped * t))


def ghosts(progress: float, count: int = 2) -> list[tuple[float, float]]:
    """The lagged copies drawn behind a sliding word: (lag in seconds, alpha).

    They swell toward mid-slide and are gone at both ends, so a settled column
    draws nothing extra.
    """
    if progress <= 0 or progress >= 1:
        return []
    weight = math.sin(math.pi * progress)
    pairs = zip(GHOST_LAGS, GHOST_ALPHAS, strict=True)
    return [(lag, alpha * weight) for lag, alpha in pairs][: max(0, count)]


def pop_in(age: float, motion: bool) -> tuple[float, float]:
    """(opacity, scale) of a word `age` seconds after it starts: scale rides the
    spring from 0.6 to 1.0 (overshooting), opacity is full well before it lands."""
    p = settle_curve(age, motion, POP_SETTLE)
    return min(1.0, max(0.0, p * 1.6)), 0.6 + 0.4 * p


def settle_curve(age: float, motion: bool, settle: float) -> float:
    """How far a pop or slide has come: the spring, or a plain 160 ms ease-out
    when motion is off."""
    if not motion:
        return ease_out(age / PLAIN_SECONDS)
    return spring(age, settle)


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
