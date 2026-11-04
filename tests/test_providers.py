import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import FIXTURES

from encorelib.config import EncoreConfig
from encorelib.model import Line, Lyrics, Word
from encorelib.providers import (
    NotFound,
    ProviderError,
    TrackInfo,
    find_lyrics,
    http_get,
    local_lrc,
    lrclib,
    spicy,
    track_key,
)

SPOTIFY_ID = "4uLU6hMCjMI75M1A2tKUQC"


def track(**kw) -> TrackInfo:
    base = {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "length": 215.4,
        "url": "",
        "trackid": f"/com/spotify/track/{SPOTIFY_ID}",
        "player": "spotify",
    }
    base.update(kw)
    return TrackInfo(**base)


class FakeFetch:
    """Routes URLs by path to fixture bytes, a NotFound, or an error."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        path = urlparse(url).path
        result = self.routes.get(path, NotFound(url))
        if isinstance(result, Exception):
            raise result
        return result


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_track_key_normalizes_feat():
    a = track(title="Test Song (feat. Someone)")
    b = track(title="Test Song [feat. Other]")
    assert track_key(a) == track_key(track()) == track_key(b)


def test_track_key_case_and_length_rounding():
    assert track_key(track(artist="TEST artist", length=215.0)) == track_key(track())


def test_track_key_non_latin():
    k = track_key(track(title="夜に駆ける", artist="YOASOBI"))
    assert k == track_key(track(title="夜に駆ける", artist="YOASOBI"))
    assert len(k) == 40


def test_local_sibling_lrc(tmp_path):
    folder = tmp_path / "My Music"
    folder.mkdir()
    (folder / "a b.mp3").write_bytes(b"")
    (folder / "a b.lrc").write_text("[00:01.00]local line")
    url = "file://" + str(folder / "a%20b.mp3").replace(" ", "%20")
    lyr = local_lrc(track(url=url), [])
    assert lyr.lines[0].text == "local line"
    assert lyr.source == "local"


def test_local_search_dir(tmp_path):
    (tmp_path / "Test Artist - Test Song.lrc").write_text("[00:01.00]from dir")
    assert local_lrc(track(), [tmp_path]).lines[0].text == "from dir"


def test_local_none(tmp_path):
    assert local_lrc(track(), [tmp_path]) is None


def test_lrclib_get_synced():
    fetch = FakeFetch({"/api/get": fixture("lrclib_get.json")})
    lyr = lrclib(track(), fetch)
    assert lyr.sync == "line"
    assert lyr.lines[0] == Line(12.5, 15.0, "Hello world")
    assert lyr.source == "lrclib"
    q = parse_qs(urlparse(fetch.calls[0][0]).query)
    assert q["artist_name"] == ["Test Artist"]
    assert q["duration"] == ["215"]


def test_lrclib_404_then_search_duration_match():
    fetch = FakeFetch({"/api/search": fixture("lrclib_search.json")})
    lyr = lrclib(track(length=216.0), fetch)
    assert lyr.lines[0].text == "right version"


def test_lrclib_search_no_close_duration():
    fetch = FakeFetch({"/api/search": b"[]"})
    assert lrclib(track(), fetch) is None


def test_lrclib_plain_only():
    body = json.dumps({"instrumental": False, "plainLyrics": "a\nb", "syncedLyrics": None})
    lyr = lrclib(track(), FakeFetch({"/api/get": body.encode()}))
    assert lyr.sync == "none"
    assert [ln.text for ln in lyr.lines] == ["a", "b"]


def test_lrclib_instrumental():
    body = json.dumps({"instrumental": True, "plainLyrics": None, "syncedLyrics": None})
    lyr = lrclib(track(), FakeFetch({"/api/get": body.encode()}))
    assert lyr == Lyrics((), "none", "lrclib")


def test_spicy_requires_spotify():
    fetch = FakeFetch({})
    assert spicy(track(player="mpv"), "key", fetch) is None
    assert fetch.calls == []


def test_spicy_accepts_uri_trackid():
    fetch = FakeFetch({f"/v1/lyrics/{SPOTIFY_ID}": fixture("spicy_line.json")})
    assert spicy(track(trackid=f"spotify:track:{SPOTIFY_ID}"), "key", fetch) is not None


def test_spicy_syllable_to_words():
    fetch = FakeFetch({f"/v1/lyrics/{SPOTIFY_ID}": fixture("spicy_syllable.json")})
    lyr = spicy(track(), "sl_sk_x", fetch)
    assert fetch.calls[0][1]["Authorization"] == "Bearer sl_sk_x"
    assert lyr.sync == "word"
    assert lyr.source == "spicy_lyrics"
    first = lyr.lines[0]
    assert first.words == (Word("Never", 10.0, 10.6), Word("gonna", 10.6, 11.2))
    assert first.text == "Never gonna"
    assert (first.start, first.end) == (10.0, 12.5)
    assert lyr.lines[1].end == 14.0
    assert lyr.credit == "Lyrics by uploader1, synced by maker2 on Spicy Lyrics"


def test_spicy_cjk_line_text():
    syllables = [
        {"Text": "夜", "StartTime": 1.0, "EndTime": 1.3, "IsPartOfWord": False},
        {"Text": "に", "StartTime": 1.3, "EndTime": 1.6, "IsPartOfWord": False},
    ]
    body = {
        "Type": "Syllable",
        "Content": [{"Lead": {"StartTime": 1.0, "EndTime": 1.6, "Syllables": syllables}}],
    }
    fetch = FakeFetch({f"/v1/lyrics/{SPOTIFY_ID}": json.dumps(body).encode()})
    line = spicy(track(), "k", fetch).lines[0]
    assert line.text == "夜に"
    assert [w.text for w in line.words] == ["夜", "に"]


def test_spicy_line_type():
    fetch = FakeFetch({f"/v1/lyrics/{SPOTIFY_ID}": fixture("spicy_line.json")})
    lyr = spicy(track(), "k", fetch)
    assert lyr.sync == "line"
    assert lyr.lines[0] == Line(5.0, 7.5, "Line one")
    assert lyr.credit is None


def test_spicy_not_found():
    assert spicy(track(), "k", FakeFetch({})) is None


CFG = EncoreConfig(lyrics_dirs=(), spicy_key="k")


def test_find_lyrics_prefers_word_sync():
    fetch = FakeFetch(
        {
            "/api/get": fixture("lrclib_get.json"),
            f"/v1/lyrics/{SPOTIFY_ID}": fixture("spicy_syllable.json"),
        }
    )
    assert find_lyrics(track(), CFG, fetch).source == "spicy_lyrics"


def test_find_lyrics_keeps_lrclib_without_key():
    fetch = FakeFetch({"/api/get": fixture("lrclib_get.json")})
    cfg = EncoreConfig(lyrics_dirs=())
    assert find_lyrics(track(), cfg, fetch).source == "lrclib"
    assert all("spicylyrics" not in u for u, _ in fetch.calls)


def test_find_lyrics_local_word_sync_skips_network(tmp_path):
    (tmp_path / "Test Artist - Test Song.lrc").write_text("[00:01.00]<00:01.00>a <00:01.50>b")
    fetch = FakeFetch({})
    cfg = EncoreConfig(lyrics_dirs=(tmp_path,), spicy_key="k")
    assert find_lyrics(track(), cfg, fetch).source == "local"
    assert fetch.calls == []


def test_find_lyrics_provider_error_skipped():
    fetch = FakeFetch(
        {
            "/api/get": ProviderError("boom"),
            f"/v1/lyrics/{SPOTIFY_ID}": fixture("spicy_line.json"),
        }
    )
    assert find_lyrics(track(), CFG, fetch).source == "spotify"


def test_find_lyrics_all_fail():
    fetch = FakeFetch({"/api/get": ProviderError("x"), "/api/search": ProviderError("y")})
    assert find_lyrics(track(), CFG, fetch) is None


def test_find_lyrics_lrclib_disabled():
    fetch = FakeFetch({"/api/get": fixture("lrclib_get.json")})
    cfg = EncoreConfig(lyrics_dirs=(), lrclib=False)
    assert find_lyrics(track(), cfg, fetch) is None


@pytest.mark.parametrize("path", [Path("/nonexistent/dir")])
def test_local_missing_dir_is_fine(path):
    assert local_lrc(track(), [path]) is None


@pytest.fixture
def http_server():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["ua"] = self.headers.get("User-Agent")
            seen["auth"] = self.headers.get("Authorization")
            code = {"/ok": 200, "/missing": 404}.get(self.path, 500)
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b"hello")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_http_get_sends_user_agent_and_headers(http_server):
    base, seen = http_server
    assert http_get(f"{base}/ok", {"Authorization": "Bearer x"}) == b"hello"
    assert "hyde-encore" in seen["ua"]
    assert seen["auth"] == "Bearer x"


def test_http_get_404_is_not_found(http_server):
    base, _ = http_server
    with pytest.raises(NotFound):
        http_get(f"{base}/missing", {})


def test_http_get_500_is_provider_error(http_server):
    base, _ = http_server
    with pytest.raises(ProviderError) as e:
        http_get(f"{base}/boom", {})
    assert not isinstance(e.value, NotFound)


def test_http_get_unreachable_is_provider_error():
    with pytest.raises(ProviderError):
        http_get("http://127.0.0.1:9/", {})


JUNK = json.dumps(
    {"instrumental": False, "plainLyrics": "probe", "syncedLyrics": "[00:00.00]probe"}
).encode()


def test_lrclib_rejects_implausible_get_and_searches():
    fetch = FakeFetch({"/api/get": JUNK, "/api/search": fixture("lrclib_search_real.json")})
    lyr = lrclib(track(length=216.0), fetch)
    assert lyr.lines[0].text == "line one"


def test_lrclib_search_skips_implausible_candidates():
    junk = {"duration": 216.0, "instrumental": False, "syncedLyrics": "[00:00.00]probe"}
    good = json.loads(fixture("lrclib_search_real.json"))[0]
    fetch = FakeFetch({"/api/search": json.dumps([junk, good]).encode()})
    assert lrclib(track(album="", length=216.0), fetch).lines[0].text == "line one"


class SearchFetch:
    """LRCLIB stand-in that answers /api/search by (track_name, artist_name)."""

    def __init__(self, answers):
        self.answers = answers
        self.urls = []

    def __call__(self, url, headers):
        self.urls.append(url)
        parsed = urlparse(url)
        if parsed.path != "/api/search":
            raise NotFound(url)
        q = parse_qs(parsed.query)
        key = (q.get("track_name", [""])[0], q.get("artist_name", [""])[0])
        return json.dumps(self.answers.get(key, [])).encode()


def synced_record(text="synced line", duration=141.0):
    lrc = "\n".join(f"[00:{10 + i:02d}.00]{text} {i}" for i in range(5))
    return {"duration": duration, "instrumental": False, "syncedLyrics": lrc, "plainLyrics": text}


def test_lrclib_empty_artist_omits_param():
    fetch = SearchFetch({})
    assert lrclib(track(artist="", album="Album", length=141.0), fetch) is None
    assert fetch.urls
    assert all("artist_name" not in u and "/api/get" not in u for u in fetch.urls)


def test_lrclib_feat_retry():
    fetch = SearchFetch({("Stay", "The Kid LAROI"): [synced_record("stay")]})
    t = track(
        title="Stay (feat. Justin Bieber)",
        artist="The Kid LAROI, Justin Bieber",
        album="",
        length=141.0,
    )
    lyr = lrclib(t, fetch)
    assert lyr.sync == "line"
    assert lyr.lines[0].text == "stay 0"
    assert len(fetch.urls) == 2


def test_lrclib_prefers_synced_over_earlier_plain():
    plain = {"duration": 141.0, "instrumental": False, "plainLyrics": "a\nb", "syncedLyrics": None}
    fetch = SearchFetch({("Song", "Artist"): [plain, synced_record()]})
    lyr = lrclib(track(title="Song", artist="Artist", album="", length=141.0), fetch)
    assert lyr.sync == "line"


def test_lrclib_falls_back_to_plain_when_nothing_synced():
    plain = {"duration": 141.0, "instrumental": False, "plainLyrics": "a\nb", "syncedLyrics": None}
    fetch = SearchFetch({("Song", "Artist"): [plain]})
    lyr = lrclib(track(title="Song", artist="Artist", album="", length=141.0), fetch)
    assert lyr.sync == "none"
    assert [ln.text for ln in lyr.lines] == ["a", "b"]
