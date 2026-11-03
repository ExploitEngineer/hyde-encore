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
