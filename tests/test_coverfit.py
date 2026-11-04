from pytest import approx

from encorelib.coverfit import CoverFit, fit_cover


def test_fit_fills_when_upscale_small():
    f = fit_cover(1500, 1500, 1920, 1080)
    assert f == CoverFit("fill", 0, -420, 1920, 1920)


def test_fit_fills_wide_art_exactly():
    assert fit_cover(1600, 900, 1920, 1080) == CoverFit("fill", 0, 0, 1920, 1080)


def test_fit_frames_small_cover():
    f = fit_cover(640, 640, 1920, 1080)
    assert (f.mode, f.w, f.h, f.x, f.y) == ("framed", 800, 800, 560, 140)


def test_fit_frame_never_outgrows_the_view():
    f = fit_cover(400, 400, 1000, 600)  # 1.25x would be 500 px, taller than 0.8 * 600
    assert f.mode == "framed" and f.h == approx(480) and f.y == approx(60)


def test_fit_uses_device_pixels():
    f = fit_cover(1500, 1500, 1920, 1080, scale=2)
    assert f.mode == "framed" and f.w == approx(864)  # 0.8 * 1080 caps 1500 * 1.25 / 2


def test_fit_without_an_image():
    f = fit_cover(0, 0, 1920, 1080)
    assert (f.w, f.h) == (0, 0)
