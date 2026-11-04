"""Bounded background work where only the newest request matters.

Skipping through songs asks for lyrics and a palette per track. Starting a
thread per request let stale lookups pile up on a slow network; a plain
pool would still run every queued stale job. LatestJobs runs at most
`workers` jobs at once and keeps a single queued slot: a newer submit
replaces a job that has not started yet. Jobs already running finish
(urllib cannot be interrupted); callers discard their stale results.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger("encore")


class LatestJobs:
    def __init__(self, workers: int = 2):
        self._workers = max(1, workers)
        self._cond = threading.Condition()
        self._pending: Callable[[], None] | None = None
        self._running = 0

    def submit(self, fn: Callable[[], None]) -> None:
        """Queue fn, replacing a queued job that has not started."""
        with self._cond:
            self._pending = fn
            if self._running < self._workers:
                self._running += 1
                threading.Thread(target=self._work, name="encore-job", daemon=True).start()

    def running(self) -> int:
        """Worker threads alive (each runs a job or is about to take one)."""
        with self._cond:
            return self._running

    def idle(self) -> bool:
        with self._cond:
            return self._running == 0 and self._pending is None

    def join(self, timeout: float | None = None) -> bool:
        """Wait until nothing runs or waits; False on timeout."""
        with self._cond:
            return self._cond.wait_for(
                lambda: self._running == 0 and self._pending is None, timeout
            )

    def _work(self) -> None:
        while True:
            with self._cond:
                fn, self._pending = self._pending, None
                if fn is None:
                    self._running -= 1
                    self._cond.notify_all()
                    return
            try:
                fn()
            except Exception:
                log.exception("background job failed")
