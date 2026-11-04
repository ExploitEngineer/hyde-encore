"""A small capped JSON-lines journal in the runtime dir.

The daemon notes every lyrics lookup here, so `hyde-shell encore lookups`
can answer "why are there no lyrics for this song?" without debug logging.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

KEEP = 50


def read_lines(path: Path) -> list[dict]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_capped(path: Path, record: dict, keep: int = KEEP) -> None:
    """Add a record, keeping only the newest `keep`; written atomically."""
    path = Path(path)
    rows = [*read_lines(path), record][-keep:]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
