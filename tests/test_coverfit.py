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


def test_home_art_grows_with_the_window():
    from encorelib.coverfit import home_art

    assert home_art(630) == 256  # the default 960x760 window: as before
    assert home_art(870) == 348  # a 1280x1000 window
    assert home_art(5000) == 480  # never a poster
    assert home_art(0) == 256  # not laid out yet


def test_lyrics_card_grows_with_the_window():
    from encorelib.coverfit import lyrics_card

    assert lyrics_card(960, 630) == (820, 380)  # the default window: as before
    assert lyrics_card(1280, 870) == (1088, 522)
    assert lyrics_card(4000, 3000) == (1400, 720)
    assert lyrics_card(0, 0) == (820, 380)
