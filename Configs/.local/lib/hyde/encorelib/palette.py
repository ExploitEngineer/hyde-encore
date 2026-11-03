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
COVER_SIZE = "512x512>"
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


def cover_png(art: Path, cache_dir: Path, run: Run = _run) -> Path | None:
    """A PNG copy of the cover for hyprlock, made once per image content."""
    try:
        key = _sha1(Path(art).read_bytes())
    except OSError:
        return None
    dest = Path(cache_dir) / f"{key}.png"
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.png")
    if run(["magick", f"{art}[0]", "-resize", COVER_SIZE, str(tmp)]) != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, dest)
    return dest


LOCK_BACKGROUND = "1A1A1A"  # the dimmed, blurred lock screen is dark
MIN_CONTRAST = 7.0
_ACCENT_KEY = re.compile(r"^[1-4]xa[1-9]$")


def _luminance(hex_color: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two RRGGBB colors."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _chroma(hex_color: str) -> int:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return max(r, g, b) - min(r, g, b)


def pick_accent(palette: dict[str, str], background: str = LOCK_BACKGROUND) -> str:
    """Most vivid palette accent that stays readable on a dark background.

    wallbash builds light-mode palettes for bright covers, where the usual
    accent slot is a dark shade; picking by contrast keeps lyrics readable.
    """
    candidates = [
        v
        for k, v in palette.items()
        if _ACCENT_KEY.match(k)
        and re.fullmatch(r"[0-9A-Fa-f]{6}", v)
        and contrast_ratio(v, background) >= MIN_CONTRAST
    ]
    if not candidates:
        return "FFFFFF"
    return max(candidates, key=lambda v: (_chroma(v), _luminance(v)))


def wallpaper_palette(cache_home: Path | None = None) -> dict[str, str]:
    root = cache_home or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    try:
        return parse_dcol((Path(root) / "hyde" / "wall.dcol").read_text(encoding="utf-8"))
    except OSError:
        return {}
