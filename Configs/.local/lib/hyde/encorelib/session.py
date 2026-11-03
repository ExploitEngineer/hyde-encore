"""Pure session logic for the daemon: player choice and stale-fetch guarding."""

from __future__ import annotations

import functools
import itertools
import logging

log = logging.getLogger("encore")


def _allowed(name: str, allow: tuple[str, ...]) -> bool:
    return not allow or any(name == a or name.startswith(f"{a}.") for a in allow)


def pick_player(players: list[tuple[str, str]], allow: tuple[str, ...]) -> str | None:
    """First playing player, else first paused one; stopped players never win."""
    candidates = [(name, status) for name, status in players if _allowed(name, allow)]
    for wanted in ("Playing", "Paused"):
        for name, status in candidates:
            if status == wanted:
                return name
    return None


class FetchGate:
    """Only the most recent fetch may deliver its result."""

    def __init__(self):
        self._counter = itertools.count(1)
        self._token = 0
        self._key: str | None = None

    def begin(self, key: str) -> int:
        self._token = next(self._counter)
        self._key = key
        return self._token

    def accept(self, token: int, key: str) -> bool:
        return token == self._token and key == self._key


def order_by_recency(names: list[str], recent: list[str]) -> list[str]:
    """Names reordered so the most recently started players come first."""
    rank = {name: i for i, name in enumerate(recent)}
    return sorted(names, key=lambda n: rank.get(n, len(rank)))


def guarded(default=None):
    """Log and swallow exceptions from GLib callbacks, returning `default`.

    An exception escaping a GLib timeout callback silently removes the source;
    escaping a signal handler aborts that update. Both should only cost one
    update, never the feature.
    """

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                log.exception("%s failed", fn.__name__)
                return default

        return inner

    return wrap


def micros_to_seconds(value) -> float:
    """MPRIS microseconds to seconds, tolerating players that send odd types."""
    try:
        seconds = float(value) / 1e6
    except (TypeError, ValueError):
        return 0.0
    return seconds if seconds > 0 else 0.0
