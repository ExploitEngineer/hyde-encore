"""Atomic file writes that never leave a temp file behind.

Both go through a temp file beside the target and rename it into place, so a
reader sees the old file or the new one, never a half. If anything fails (a
full runtime dir, say) the temp is removed and the error propagates: the
caller decides whether that is fatal, the directory stays clean either way.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        _discard(tmp)
        raise


def copy_atomic(src: Path, dst: Path) -> None:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        _discard(tmp)
        raise


def _discard(tmp: str) -> None:
    try:
        os.unlink(tmp)
    except OSError:
        pass
