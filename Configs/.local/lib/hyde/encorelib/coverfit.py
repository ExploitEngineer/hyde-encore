"""Where a cover goes on a full-screen page without ever looking soft.

A cover fills the view when that needs at most FILL_MAX of its pixels
(a 1500 px cover fills 1920x1080 at 1.28x). A smaller one is framed:
shown sharp at no more than FRAME_MAX of its pixel size, inside
FRAME_SHARE of the view, over a blurred copy of itself.
"""

from __future__ import annotations

from dataclasses import dataclass

FILL_MAX = 1.35
FRAME_MAX = 1.25
FRAME_SHARE = 0.8


@dataclass(frozen=True)
class CoverFit:
    mode: str  # "fill" or "framed"
    x: float
    y: float
    w: float
    h: float


def fit_cover(img_w: int, img_h: int, view_w: float, view_h: float, scale: float = 1.0) -> CoverFit:
    """The cover's rect in view (logical) pixels; `scale` is the output's scale factor."""
    if img_w <= 0 or img_h <= 0 or view_w <= 0 or view_h <= 0:
        return CoverFit("framed", view_w / 2, view_h / 2, 0, 0)
    zoom = max(view_w * scale / img_w, view_h * scale / img_h)  # device px per image px
    if zoom <= FILL_MAX:
        w, h = img_w * zoom / scale, img_h * zoom / scale
        return CoverFit("fill", (view_w - w) / 2, (view_h - h) / 2, w, h)
    s = min(FRAME_MAX / scale, FRAME_SHARE * view_w / img_w, FRAME_SHARE * view_h / img_h)
    w, h = img_w * s, img_h * s
    return CoverFit("framed", (view_w - w) / 2, (view_h - h) / 2, w, h)


HOME_ART_SHARE = 0.4  # of the Home page's height
HOME_ART_RANGE = (256, 480)


def home_art(page_height: int) -> int:
    """Home's cover side for a page height: 256 px in the default window,
    growing with a tall or tiled window, capped so it never turns into a poster."""
    low, high = HOME_ART_RANGE
    return max(low, min(high, round(page_height * HOME_ART_SHARE)))


LYRICS_CARD_MIN = (820, 380)
LYRICS_CARD_MAX = (1400, 720)
LYRICS_CARD_SHARE = (0.85, 0.6)  # of the Lyrics page's width and height


def lyrics_card(page_width: int, page_height: int) -> tuple[int, int]:
    """The Lyrics page card's size: as designed in the default window, growing
    with a big or tiled one so the list gets the room."""
    sizes = []
    for size, low, high, share in zip(
        (page_width, page_height), LYRICS_CARD_MIN, LYRICS_CARD_MAX, LYRICS_CARD_SHARE, strict=True
    ):
        sizes.append(max(low, min(high, round(size * share))))
    return sizes[0], sizes[1]
