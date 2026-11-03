"""Pure session logic for the daemon: player choice and stale-fetch guarding."""

from __future__ import annotations

import itertools


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
