"""JSON-lines decoding for encore.sock clients."""

from __future__ import annotations

import json
import os

MAX_TAIL_BYTES = 1024 * 1024


class LineDecoder:
    """Buffers raw socket chunks and yields complete JSON objects."""

    def __init__(self):
        self._tail = b""

    def feed(self, data: bytes) -> list[dict]:
        self._tail += data
        *lines, self._tail = self._tail.split(b"\n")
        if len(self._tail) > MAX_TAIL_BYTES:
            self._tail = b""
        out = []
        for raw in lines:
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out

    def reset(self) -> None:
        self._tail = b""


def should_connect(event_path: str, socket_name: str = "encore.sock") -> bool:
    """True when a runtime-dir file event is about the daemon's socket."""
    return os.path.basename(event_path) == socket_name


STYLES = ("line", "stack", "constellation", "visual", "code")
