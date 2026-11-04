"""Seeded word placement for the constellation overlay style.

Positions are a pure function of the line key, so a replayed line scatters
identically, and every client computing them agrees.
"""

from __future__ import annotations

import hashlib
import math
import random

FALLBACK_SHRINK = 0.6


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha1(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def place_words(
    words: list[str],
    width: int,
    height: int,
    seed: str,
    margin: int = 140,
    min_dist: int = 120,
) -> list[tuple[float, float]]:
    """One (x, y) per word: a left-to-right meander with jitter and spacing.

    When the space is too tight for `min_dist`, the constraint shrinks
    rather than failing, so every word always gets a position.
    """
    rng = _rng(seed)
    n = max(1, len(words))
    inner_w = max(1.0, width - 2.0 * margin)
    inner_h = max(1.0, height - 2.0 * margin)
    step = inner_w / n
    out: list[tuple[float, float]] = []
    for i, _word in enumerate(words):
        placed = None
        dist = float(min_dist)
        while placed is None:
            for _attempt in range(24):
                x = margin + step * (i + rng.uniform(0.1, 0.9))
                x += rng.uniform(-0.6, 0.6) * step
                x = min(max(x, margin), width - margin)
                y = margin + rng.uniform(0.0, 1.0) * inner_h
                if all(math.hypot(x - px, y - py) >= dist for px, py in out):
                    placed = (x, y)
                    break
            dist *= FALLBACK_SHRINK
        out.append(placed)
    return out


def sparkles(seed: str, width: int, height: int, k: int = 6) -> list[tuple[float, float]]:
    rng = _rng(f"sparkle:{seed}")
    return [(rng.uniform(0, width), rng.uniform(0, height)) for _ in range(k)]


# step lengths as a share of the screen height, so the chain grows with the type
CHAIN_MIN_STEP = 0.11
CHAIN_MAX_STEP = 0.24


def chain_words(words: list[str], width: int, height: int, seed: str) -> list[tuple[float, float]]:
    """Verci-style chain: each word lands near the previous one.

    A random walk with bounded steps, biased to meander rightward and
    reflected back into a center band, so the cluster stays compact and
    readable instead of scattering over the whole screen.
    """
    rng = _rng(f"chain:{seed}")
    min_step, max_step = CHAIN_MIN_STEP * height, CHAIN_MAX_STEP * height
    x_lo, x_hi = width * 0.14, width * 0.86
    y_lo, y_hi = height * 0.24, height * 0.76
    x = x_lo + rng.uniform(0.05, 0.3) * (x_hi - x_lo)
    y = y_lo + rng.uniform(0.2, 0.8) * (y_hi - y_lo)
    heading = rng.uniform(-0.9, 0.9)
    out = [(x, y)]
    for _ in words[1:]:
        step = rng.uniform(min_step, max_step)
        heading += rng.uniform(-1.1, 1.1)
        dx = abs(math.cos(heading)) * step * (1 if rng.random() < 0.72 else -1)
        dy = math.sin(heading) * step * 0.8
        x, y = x + dx, y + dy
        if not x_lo <= x <= x_hi:
            x = max(x_lo, min(x_hi, 2 * (x_lo if x < x_lo else x_hi) - x))
        if not y_lo <= y <= y_hi:
            y = max(y_lo, min(y_hi, 2 * (y_lo if y < y_lo else y_hi) - y))
        px, py = out[-1]
        dist = math.hypot(x - px, y - py)
        if dist < min_step:
            scale = min_step / max(dist, 1e-6)
            x, y = px + (x - px) * scale, py + (y - py) * scale
            x = max(x_lo, min(x_hi, x))
            y = max(y_lo, min(y_hi, y))
            if math.hypot(x - px, y - py) < min_step:
                angle = rng.uniform(0, 2 * math.pi)
                x = max(x_lo, min(x_hi, px + min_step * 1.1 * math.cos(angle)))
                y = max(y_lo, min(y_hi, py + min_step * 1.1 * math.sin(angle)))
        out.append((x, y))
    return _centered(out, width, height, (x_lo, x_hi, y_lo, y_hi))


def _centered(points, width, height, band) -> list[tuple[float, float]]:
    """Shift the whole chain so its bounding box sits on the screen center.

    The walk starts left and meanders right, so short lines used to hang in
    the left third; centering keeps every line framed like a title.
    """
    x_lo, x_hi, y_lo, y_hi = band
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    dx = width / 2 - (min(xs) + max(xs)) / 2
    dy = height / 2 - (min(ys) + max(ys)) / 2
    return [(max(x_lo, min(x_hi, x + dx)), max(y_lo, min(y_hi, y + dy))) for x, y in points]
