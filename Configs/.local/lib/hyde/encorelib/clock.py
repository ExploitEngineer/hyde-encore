"""Smooth playback position between MPRIS position queries."""

from __future__ import annotations

import time
from collections.abc import Callable


class PlaybackClock:
    """Interpolates the player's position from the last known anchor."""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self._now = now
        self._position = 0.0
        self._ts = now()
        self.playing = False
        self.rate = 1.0

    def sync(self, position: float, playing: bool, rate: float = 1.0) -> None:
        self._position = position
        self._ts = self._now()
        self.playing = playing
        self.rate = rate

    def position(self) -> float:
        if not self.playing:
            return self._position
        return self._position + (self._now() - self._ts) * self.rate

    def anchor(self) -> tuple[float, float]:
        return self._position, self._ts
