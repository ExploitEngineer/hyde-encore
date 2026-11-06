"""LineRaster geometry (needs PyGObject with Pango typelibs)."""

import pytest

gi = pytest.importorskip("gi")


def raster(text, words, size):
    try:
        from encoregui.lyrics import LineRaster
    except (ImportError, ValueError) as e:
        pytest.skip(f"GTK typelibs unavailable: {e}")
    return LineRaster(text, words, "Inter", size, 1600, (1.0, 0.2, 0.4), 1)


@pytest.mark.parametrize("size", [43, 58, 86])
def test_word_rects_sit_where_the_text_is_drawn(size):
    r = raster("gypsy jumping quickly", ["gypsy", "jumping", "quickly"], size)
    for rects in r.rects:
        for _x, y, _w, h in rects:
            # the text is drawn `pad` px down to leave room for shadow and bloom
            assert y >= r.pad - 1
            assert y + h <= r.height - r.pad + 1


def test_lit_copy_is_not_cut_below_the_descenders():
    r = raster("gypsy", ["gypsy"], 86)
    surface = r.bright
    surface.flush()
    stride, data = surface.get_stride(), surface.get_data()
    lowest = max(
        (row for row in range(r.height) if any(data[row * stride + 3 : (row + 1) * stride : 4])),
        default=0,
    )
    ((_x, y, _w, h),) = r.rects[0]
    assert lowest <= y + h + r.pad  # the paint clip (rect + pad) covers ink and bloom
