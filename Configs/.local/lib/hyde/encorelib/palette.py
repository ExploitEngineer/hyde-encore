"""Album art palette through HyDE's own wallbash.sh."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

from .providers import Fetch, ProviderError, http_get

Run = Callable[[list[str]], int]

PALETTE_SIZE = "256x256>"
_DCOL = re.compile(r'^(?:export\s+)?dcol_([A-Za-z0-9]+)="?([^"\s]*)"?\s*$')


def _run(cmd: list[str]) -> int:
    try:
        return subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def fetch_art(art_url: str, dest_dir: Path, fetch: Fetch = http_get) -> Path | None:
    """Local path of the cover art, downloading http(s) art once."""
    if art_url.startswith("file://"):
        path = Path(unquote(urlparse(art_url).path))
        return path if path.is_file() else None
    if not art_url.startswith(("http://", "https://")):
        return None
    dest = Path(dest_dir) / f"{_sha1(art_url.encode())}.img"
    if dest.is_file():
        return dest
    try:
        data = fetch(art_url, {})
    except ProviderError:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return dest


def parse_dcol(text: str) -> dict[str, str]:
    palette = {}
    for line in text.splitlines():
        m = _DCOL.match(line.strip())
        if m and not m.group(1).endswith("rgba"):
            palette[m.group(1)] = m.group(2)
    return palette


def default_wallbash() -> Path:
    lib = os.environ.get("LIB_DIR") or str(Path.home() / ".local" / "lib")
    return Path(lib) / "hyde" / "wallbash.sh"


def album_palette(
    art: Path, cache_dir: Path, run: Run = _run, wallbash: Path | None = None
) -> dict[str, str]:
    """wallbash palette for a cover, computed once per image content."""
    try:
        key = _sha1(Path(art).read_bytes())
    except OSError:
        return {}
    cache_dir = Path(cache_dir)
    prefix = cache_dir / key
    dcol = prefix.with_suffix(".dcol")
    if not dcol.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        small = prefix.with_suffix(".small.png")
        try:
            if run(["magick", f"{art}[0]", "-resize", PALETTE_SIZE, str(small)]) != 0:
                return {}
            if run([str(wallbash or default_wallbash()), str(small), str(prefix)]) != 0:
                return {}
        finally:
            for extra in cache_dir.glob(f"{key}*"):
                if extra.suffix != ".dcol":
                    extra.unlink(missing_ok=True)
    try:
        return parse_dcol(dcol.read_text(encoding="utf-8"))
    except OSError:
        return {}


def wallpaper_palette(cache_home: Path | None = None) -> dict[str, str]:
    root = cache_home or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    try:
        return parse_dcol((Path(root) / "hyde" / "wall.dcol").read_text(encoding="utf-8"))
    except OSError:
        return {}
