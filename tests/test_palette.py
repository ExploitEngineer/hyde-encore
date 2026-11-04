from pathlib import Path

from paths import FIXTURES

from encorelib.palette import album_palette, fetch_art, parse_dcol, wallpaper_palette
from encorelib.providers import ProviderError


def test_parse_dcol_real_fixture():
    pal = parse_dcol((FIXTURES / "sample.dcol").read_text())
    assert pal["pry1"] == "231731"
    assert pal["txt1"] == "FFFFFF"
    assert pal["1xa8"] == "CAAAF0"
    assert not any(k.endswith("_rgba") for k in pal)


def test_parse_dcol_export_prefix():
    assert parse_dcol('export dcol_pry4="ABCDEF"\n') == {"pry4": "ABCDEF"}


def test_fetch_art_file_url_with_spaces(tmp_path):
    art = tmp_path / "My Album" / "cover art.jpg"
    art.parent.mkdir()
    art.write_bytes(b"img")
    url = "file://" + str(art).replace(" ", "%20")
    assert fetch_art(url, tmp_path / "cache") == art


def test_fetch_art_missing_file(tmp_path):
    assert fetch_art("file:///nope/x.jpg", tmp_path) is None


def test_fetch_art_empty(tmp_path):
    assert fetch_art("", tmp_path) is None


def test_fetch_art_http_cached(tmp_path):
    calls = []

    def fetch(url, headers):
        calls.append(url)
        return b"jpegbytes"

    first = fetch_art("https://i.scdn.co/image/abc", tmp_path, fetch)
    second = fetch_art("https://i.scdn.co/image/abc", tmp_path, fetch)
    assert first == second
    assert first.read_bytes() == b"jpegbytes"
    assert len(calls) == 1


def test_fetch_art_http_error(tmp_path):
    def fetch(url, headers):
        raise ProviderError("down")

    assert fetch_art("https://x/y.jpg", tmp_path, fetch) is None


class FakeRun:
    """Pretends to be magick + wallbash.sh: wallbash writes <prefix>.dcol."""

    def __init__(self, rc=0):
        self.rc = rc
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if self.rc == 0 and cmd[0].endswith("wallbash.sh"):
            Path(cmd[-1] + ".dcol").write_text((FIXTURES / "sample.dcol").read_text())
            Path(cmd[-1] + ".mpc").write_text("x")
        return self.rc


def test_album_palette_downscales_then_wallbash(tmp_path):
    art = tmp_path / "a.jpg"
    art.write_bytes(b"cover")
    run = FakeRun()
    pal = album_palette(art, tmp_path / "pal", run, wallbash=Path("/lib/hyde/wallbash.sh"))
    assert pal["1xa8"] == "CAAAF0"
    assert run.calls[0][0] == "magick"
    assert "256x256>" in run.calls[0]
    assert run.calls[1][0] == "/lib/hyde/wallbash.sh"
    leftovers = sorted(p.suffix for p in (tmp_path / "pal").iterdir())
    assert leftovers == [".dcol"]


def test_album_palette_cached_by_image_bytes(tmp_path):
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    run = FakeRun()
    album_palette(a, tmp_path / "pal", run, wallbash=Path("/w/wallbash.sh"))
    album_palette(b, tmp_path / "pal", run, wallbash=Path("/w/wallbash.sh"))
    assert len(run.calls) == 2


def test_album_palette_failure_is_empty(tmp_path):
    art = tmp_path / "a.jpg"
    art.write_bytes(b"cover")
    assert album_palette(art, tmp_path / "pal", FakeRun(rc=1), wallbash=Path("/w/x.sh")) == {}


def test_wallpaper_palette(tmp_path):
    (tmp_path / "hyde").mkdir()
    (tmp_path / "hyde" / "wall.dcol").write_text('dcol_pry1="000000"\n')
    assert wallpaper_palette(tmp_path) == {"pry1": "000000"}
    assert wallpaper_palette(tmp_path / "none") == {}


def test_cover_png_resizes_once_per_image(tmp_path):
    from encorelib.palette import cover_png

    art = tmp_path / "a.img"
    art.write_bytes(b"jpeg")
    calls = []

    def run(cmd):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"png")
        return 0

    first = cover_png(art, tmp_path / "covers", run)
    second = cover_png(art, tmp_path / "covers", run)
    assert first == second
    assert first.suffix == ".png"
    assert len(calls) == 1
    assert calls[0][0] == "magick" and "512x512" in " ".join(calls[0])


def test_cover_png_failure_is_none(tmp_path):
    from encorelib.palette import cover_png

    art = tmp_path / "a.img"
    art.write_bytes(b"jpeg")
    assert cover_png(art, tmp_path / "covers", lambda cmd: 1) is None


def _contrast(hex_a, hex_b):
    from encorelib.palette import contrast_ratio

    return contrast_ratio(hex_a, hex_b)


def test_pick_accent_light_mode_palette_is_readable_and_vivid():
    from encorelib.palette import LOCK_BACKGROUND, pick_accent

    pal = parse_dcol((FIXTURES / "light_mode.dcol").read_text())
    accent = pick_accent(pal)
    assert accent != "6B593A"  # the dark 1xa8 shade this palette would give
    assert _contrast(accent, LOCK_BACKGROUND) >= 7.0
    r, g, b = (int(accent[i : i + 2], 16) for i in (0, 2, 4))
    assert max(r, g, b) - min(r, g, b) >= 40  # a real color, not a grey


def test_pick_accent_dark_mode_palette_keeps_its_accent():
    from encorelib.palette import LOCK_BACKGROUND, pick_accent

    pal = parse_dcol((FIXTURES / "sample.dcol").read_text())
    accent = pick_accent(pal)
    assert _contrast(accent, LOCK_BACKGROUND) >= 7.0


def test_pick_accent_greyscale_and_empty():
    from encorelib.palette import pick_accent

    grey = {"1xa8": "D6D6D6", "1xa2": "2B2B2B", "txt1": "FFFFFF"}
    assert pick_accent(grey) == "D6D6D6"
    assert pick_accent({}) == "FFFFFF"


def test_contrast_ratio_extremes():
    assert round(_contrast("FFFFFF", "000000"), 1) == 21.0
    assert _contrast("777777", "777777") == 1.0
