"""LineRaster's size can be measured without rasterising the line."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Configs/.local/lib/hyde"))

lyrics = pytest.importorskip("encoregui.lyrics")

FONT = "Sans"
LINES = [
    "I call your name at night",
    "Hold the time a little longer than the line can hold before it wraps around",
    "夜に駆ける",
    "♪",
]


@pytest.mark.parametrize("text", LINES)
def test_measure_matches_raster_height(text):
    width = 420
    measured = lyrics.measure_line_height(text, FONT, 26, width)
    raster = lyrics.LineRaster(text, text.split(), FONT, 26, width, (1, 1, 1), 1)
    assert measured == raster.height


def test_measure_pads_like_the_raster():
    # the pad (room for the baked shadow and bloom) is part of the height
    assert lyrics.measure_line_height("a", FONT, 26, 400) > 26
