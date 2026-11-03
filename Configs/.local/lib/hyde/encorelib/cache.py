"""On-disk cache of fetched lyrics, one JSON file per track key."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from .model import Lyrics

MISS_TTL_SECONDS = 7 * 86400
CACHED_MISS = Lyrics((), "none", "miss")


class LyricsCache:
    def __init__(self, root: Path):
        self.dir = Path(root) / "lyrics"

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Lyrics | None:
        """Cached lyrics, CACHED_MISS for a recent known miss, or None if not cached."""
        path = self._path(key)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("miss"):
                if time.time() - path.stat().st_mtime > MISS_TTL_SECONDS:
                    return None
                return CACHED_MISS
            return Lyrics.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, key: str, lyrics: Lyrics | None) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {"miss": True} if lyrics is None else lyrics.to_dict()
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, self._path(key))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
