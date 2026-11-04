import json
import struct
import zlib
from urllib.parse import parse_qs, urlparse

from paths import FIXTURES

from encorelib.artwork import apple_pick, apple_search_url, hd_art, image_size, spotify_large
from encorelib.providers import NotFound, ProviderError

SPOTIFY_640 = "https://i.scdn.co/image/ab67616d0000b273baf89eb11ec7c657805d2da0"
SPOTIFY_1500 = "https://i.scdn.co/image/ab67616d000082c1baf89eb11ec7c657805d2da0"
APPLE_ART = "https://is1-ssl.mzstatic.com/image/thumb/Music126/v4/b3/4050538793840.jpg"
JPEG_640 = (FIXTURES / "cover-640.jpg").read_bytes()


def png_bytes(width: int, height: int) -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x40\x60" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FakeWeb:
    """Serves bytes for URL prefixes; a value that is an exception is raised."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, _headers: dict) -> bytes:
        self.calls.append(url)
        for prefix, page in self.routes.items():
            if url.startswith(prefix):
                if isinstance(page, Exception):
                    raise page
                return page
        raise NotFound(url)


def apple_results(*records: tuple[str, str]) -> bytes:
    """An entity=album answer: (artist, album) per record."""
    return json.dumps(
        {
            "resultCount": len(records),
            "results": [
                {
                    "wrapperType": "collection",
                    "artistName": artist,
                    "collectionName": album,
                    "artworkUrl100": f"{APPLE_ART}/100x100bb.jpg",
                }
                for artist, album in records
            ],
        }
    ).encode()


def apple_songs(*records: tuple[str, str, str]) -> bytes:
    """An entity=song answer: (artist, album, track) per record."""
    return json.dumps(
        {
            "resultCount": len(records),
            "results": [
                {
                    "wrapperType": "track",
                    "kind": "song",
                    "artistName": artist,
                    "collectionName": album,
                    "trackName": track,
                    "artworkUrl100": f"{APPLE_ART}/100x100bb.jpg",
                }
                for artist, album, track in records
            ],
        }
    ).encode()


def test_spotify_large_rewrites_size_code():
    assert spotify_large(SPOTIFY_640) == SPOTIFY_1500
    cdn = "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02baf89eb11ec7c657805d2da0"
    assert spotify_large(cdn) == (
        "https://image-cdn-fa.spotifycdn.com/image/ab67616d000082c1baf89eb11ec7c657805d2da0"
    )


def test_spotify_large_ignores_other_urls():
    artist_image = "https://i.scdn.co/image/ab6761610000e5ebbaf89eb11ec7c657805d2da0"
    assert spotify_large(artist_image) is None
    assert (
        spotify_large("https://evil.example/image/ab67616d0000b273baf89eb11ec7c657805d2da0") is None
    )
    assert spotify_large("file:///tmp/a.png") is None
    assert spotify_large("https://i.ytimg.com/vi/x/hqdefault.jpg") is None
    assert spotify_large("") is None


def test_image_size_reads_png_and_jpeg():
    assert image_size(png_bytes(64, 48)) == (64, 48)
    assert image_size(JPEG_640) == (640, 640)
    assert image_size(b"not an image") is None
    assert image_size(JPEG_640[:20]) is None  # cut before the frame header


def test_apple_url_needs_artist_and_name():
    assert apple_search_url("", "Album", "Song") is None
    assert apple_search_url("Rick Astley", "", "") is None
    url = apple_search_url("Rick Astley feat. X", "Whenever You Need Somebody (2022 Remaster)", "")
    query = parse_qs(urlparse(url).query)
    assert url.startswith("https://itunes.apple.com/search?")
    assert query["term"] == ["Rick Astley Whenever You Need Somebody"]
    assert query["entity"] == ["album"]
    assert query["media"] == ["music"]


def test_apple_url_searches_songs_without_album():
    url = apple_search_url("Rick Astley", "", "Never Gonna Give You Up (Official Video)")
    query = parse_qs(urlparse(url).query)
    assert query["term"] == ["Rick Astley Never Gonna Give You Up"]
    assert query["entity"] == ["song"]


def test_pick_matches_cleaned_album_and_upsizes():
    results = json.loads(
        apple_results(
            ("Rick Astley", "Whenever You Need Somebody (Deluxe Edition - 2022 Remaster)")
        )
    )["results"]
    assert apple_pick(results, "Rick Astley", "Whenever You Need Somebody", "") == (
        f"{APPLE_ART}/2000x2000bb.jpg"
    )


def test_pick_rejects_other_artist():
    results = json.loads(apple_results(("Rick Astley Tribute Band", "Whenever You Need Somebody")))[
        "results"
    ]
    assert apple_pick(results, "Rick Astley", "Whenever You Need Somebody", "") is None


def test_pick_rejects_other_album():
    results = json.loads(apple_results(("Rick Astley", "Greatest Hits")))["results"]
    assert apple_pick(results, "Rick Astley", "Whenever You Need Somebody", "") is None


def test_pick_matches_single_by_album_name():
    results = json.loads(apple_results(("Rick Astley", "Never Gonna Give You Up - Single")))[
        "results"
    ]
    assert apple_pick(results, "Rick Astley", "Never Gonna Give You Up", "") == (
        f"{APPLE_ART}/2000x2000bb.jpg"
    )


def test_pick_matches_song_by_title_without_album():
    results = json.loads(
        apple_songs(
            ("RadioClub", "Never Gonna Give You Up - Single", "Never Gonna Give You Up"),
            ("Rick Astley", "Whenever You Need Somebody", "Never Gonna Give You Up"),
        )
    )["results"]
    assert apple_pick(results, "Rick Astley", "", "Never Gonna Give You Up (Official Video)") == (
        f"{APPLE_ART}/2000x2000bb.jpg"
    )


def test_pick_rejects_song_with_other_title():
    results = json.loads(
        apple_songs(("Rick Astley", "Whenever You Need Somebody", "Together Forever"))
    )["results"]
    assert apple_pick(results, "Rick Astley", "", "Never Gonna Give You Up") is None


def test_hd_art_prefers_spotify_large(tmp_path):
    original = tmp_path / "small.jpg"
    original.write_bytes(JPEG_640)
    big = png_bytes(1500, 1500)
    web = FakeWeb({SPOTIFY_1500: big})
    path = hd_art(SPOTIFY_640, original, "A", "B", "C", tmp_path / "hd", apple=True, fetch=web)
    assert path is not None and path.read_bytes() == big
    assert web.calls == [SPOTIFY_1500]


def test_hd_art_asks_apple_when_spotify_large_fails(tmp_path):
    original = tmp_path / "small.jpg"
    original.write_bytes(JPEG_640)
    big = png_bytes(1200, 1200)
    web = FakeWeb(
        {
            SPOTIFY_1500: ProviderError("HTTP 500"),
            "https://itunes.apple.com/search": apple_results(
                ("Rick Astley", "Hold Me in Your Arms")
            ),
            f"{APPLE_ART}/2000x2000bb.jpg": big,
        }
    )
    path = hd_art(
        SPOTIFY_640,
        original,
        "Rick Astley",
        "Hold Me in Your Arms",
        "Take Me to Your Heart",
        tmp_path / "hd",
        apple=True,
        fetch=web,
    )
    assert path is not None and path.read_bytes() == big
    assert web.calls[0] == SPOTIFY_1500 and web.calls[-1] == f"{APPLE_ART}/2000x2000bb.jpg"


def test_hd_art_asks_apple_for_small_cover(tmp_path):
    original = tmp_path / "small.jpg"
    original.write_bytes(JPEG_640)
    big = png_bytes(1600, 1600)
    web = FakeWeb(
        {
            "https://itunes.apple.com/search": apple_results(
                ("Rick Astley", "Hold Me in Your Arms")
            ),
            f"{APPLE_ART}/2000x2000bb.jpg": big,
        }
    )
    path = hd_art(
        "https://i.ytimg.com/vi/x/hqdefault.jpg",
        original,
        "Rick Astley",
        "Hold Me in Your Arms",
        "Take Me to Your Heart",
        tmp_path / "hd",
        apple=True,
        fetch=web,
    )
    assert path is not None and path.read_bytes() == big
    assert len(web.calls) == 2


def test_hd_art_asks_apple_without_any_cover(tmp_path):
    big = png_bytes(1100, 1100)
    web = FakeWeb(
        {
            "https://itunes.apple.com/search": apple_results(
                ("Rick Astley", "Hold Me in Your Arms")
            ),
            f"{APPLE_ART}/2000x2000bb.jpg": big,
        }
    )
    path = hd_art("", None, "Rick Astley", "Hold Me in Your Arms", "", tmp_path / "hd", True, web)
    assert path is not None and path.read_bytes() == big


def test_hd_art_skips_apple_when_source_is_big(tmp_path):
    original = tmp_path / "big.png"
    original.write_bytes(png_bytes(1200, 1200))
    web = FakeWeb({})
    path = hd_art(
        "https://example.com/a.png",
        original,
        "Rick Astley",
        "Album",
        "Song",
        tmp_path / "hd",
        apple=True,
        fetch=web,
    )
    assert path is None
    assert web.calls == []


def test_hd_art_falls_back_on_provider_error(tmp_path):
    original = tmp_path / "small.jpg"
    original.write_bytes(JPEG_640)
    web = FakeWeb({"https://itunes.apple.com/search": ProviderError("timed out")})
    path = hd_art(
        "https://i.ytimg.com/vi/x/hqdefault.jpg",
        original,
        "Rick Astley",
        "Album",
        "Song",
        tmp_path / "hd",
        apple=True,
        fetch=web,
    )
    assert path is None


def test_hd_art_rejects_bad_json(tmp_path):
    web = FakeWeb({"https://itunes.apple.com/search": b"<html>busy</html>"})
    assert hd_art("", None, "Rick Astley", "Album", "Song", tmp_path / "hd", True, web) is None


def test_hd_art_respects_switch(tmp_path):
    original = tmp_path / "small.jpg"
    original.write_bytes(JPEG_640)
    web = FakeWeb({})
    path = hd_art(
        "https://i.ytimg.com/vi/x/hqdefault.jpg",
        original,
        "Rick Astley",
        "Album",
        "Song",
        tmp_path / "hd",
        apple=False,
        fetch=web,
    )
    assert path is None
    assert web.calls == []


def test_hd_art_splits_artist_from_video_title(tmp_path):
    big = png_bytes(1100, 1100)
    web = FakeWeb(
        {
            "https://itunes.apple.com/search?term=Rick+Astley+Never+Gonna+Give+You+Up&": (
                apple_songs(
                    ("Rick Astley", "Whenever You Need Somebody", "Never Gonna Give You Up")
                )
            ),
            "https://itunes.apple.com/search": apple_songs(),
            f"{APPLE_ART}/2000x2000bb.jpg": big,
        }
    )
    path = hd_art(
        "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        None,
        "RickAstleyVEVO",
        "",
        "Rick Astley - Never Gonna Give You Up (Official Video)",
        tmp_path / "hd",
        apple=True,
        fetch=web,
    )
    assert path is not None and path.read_bytes() == big
    searches = [u for u in web.calls if u.startswith("https://itunes.apple.com/search")]
    assert len(searches) == 2  # the literal query, then the split; no duplicate queries
