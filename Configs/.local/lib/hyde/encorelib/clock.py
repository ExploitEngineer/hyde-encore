"""Smooth playback position between MPRIS position queries."""

from __future__ import annotations

import math
import time
from collections.abc import Callable

MAX_RATE = 8.0


def clean_rate(value: object) -> float:
    """A usable playback rate from an MPRIS Rate value, else 1.0.

    MPRIS forbids 0 (pause is a status, not a rate) and encore cannot sing
    backwards, so zero, negative, non-finite and absurd values become 1.0.
    """
    try:
        rate = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(rate) or rate <= 0 or rate > MAX_RATE:
        return 1.0
    return rate


class PlaybackClock:
    """Interpolates the player's position from the last known anchor."""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self._now = now
        self._position = 0.0
        self._ts = now()
        self.playing = False
        self.rate = 1.0

    def sync(self, position: float, playing: bool, rate: float | None = None) -> None:
        """Re-anchor on the player's position; rate=None keeps the current rate."""
        self._position = position
        self._ts = self._now()
        self.playing = playing
        if rate is not None:
            self.rate = clean_rate(rate)

    def position(self) -> float:
        if not self.playing:
            return self._position
        return self._position + (self._now() - self._ts) * self.rate

    def anchor(self) -> tuple[float, float]:
        return self._position, self._ts
