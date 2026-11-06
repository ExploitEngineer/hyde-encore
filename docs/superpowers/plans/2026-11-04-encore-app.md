# Encore App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encore opens from the app launcher as one window with Home, Lyrics and an always-escapable Full screen, sharp HD covers, a tray, and deliberate states for every edge case.

**Architecture:** The daemon gains HD covers, a player list, volume, a player pin and persisted settings.
The lyric renderer moves out of `overlay.py` into a host-agnostic `LyricsEngine`, hosted by the click-through desktop overlay and by the new Full screen page.
`player.py` becomes a unique `Gtk.Application` (`org.hyde.encore`) split into `app.py`, `home.py`, `popovers.py`, `fullscreen.py`, `cover.py`, `idle.py` and `tray.py`; pure logic lives in new `encorelib` modules with unit tests.

**Tech Stack:** Python 3 on system `python3`, GTK4 via PyGObject (no libadwaita), Playerctl, gtk4-layer-shell (desktop overlay and glow only), Gio D-Bus (tray), ImageMagick (lock copy), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-04-encore-app-design.md`

## Global Constraints

- HyDE tree layout: scripts in `Configs/.local/lib/hyde/`, desktop entry in `Configs/.local/share/applications/`, icon in `Configs/.local/share/icons/hicolor/scalable/apps/`; entry through `hyde-shell encore <cmd>`.
- `encorelib/` never imports `gi`; every new pure module there has unit tests.
- No new dependencies. Plain GTK4 with our CSS, no libadwaita.
- Never send playerctl commands to the owner's real players; tests use `fake_mpris.py` on the harness's private bus. GUI checks run only on the hidden `encore-lab` monitor (`tests/e2e/stage.py`), never on the owner's screen.
- Unit tests must never write under the real `$XDG_STATE_HOME` or `$XDG_RUNTIME_DIR`; pass tmp paths explicitly.
- Every full-screen surface has Esc and a visible Exit button; the desktop overlay never draws a full-screen cover.
- Covers: never stretched more than 1.25x their pixel size when framed; fill mode only up to 1.35x (my call: a 1500 px cover fills 1920x1080 at 1.28x).
- HD covers on by default (owner); Spotify size code `ab67616d000082c1` serves 1500x1500 (verified 2026-11-04); Apple iTunes Search fallback, strict match.
- Perf: Full screen animating at or under today's overlay numbers per style (line ~9%, stack ~16%, constellation ~9%, visual ~19% of a core), 0 ticks paused or hidden; Home idle animation at most 2% of a core, 0 when the window is hidden.
- Commits: conventional style per upstream `COMMIT_MESSAGE_GUIDELINES.md`, no agent attribution anywhere, on branch `feat/encore-app`.
- Lint gate per task: `uvx ruff check Configs tests` and `uvx ruff format --check Configs tests` clean; `python3 -m pytest -q` green.
- Markdown docs: one sentence per line; no em dash.

## Review Focus

1. Spotify ads, podcasts, browser videos with no album or an empty artist: no Apple query, never a wrong cover (Task 1: `test_apple_url_needs_artist_and_name`, `test_pick_rejects_other_artist`).
2. The followed player quits while Full screen is up: the page falls to the idle field, bars and Esc keep working (Task 5: `test_idle_when_player_gone`; Task 8 lab check `full-player-quit`).
3. Network down or Apple slow: HD lookup gives up inside `HTTP_TIMEOUT`, the source cover and palette still publish (Task 1: `test_hd_art_falls_back_on_provider_error`).
4. Very long or CJK titles: Home and Full screen labels ellipsize with the full text as tooltip, the window never resizes (Task 2 adds `fake_mpris --title/--artist`; Task 7 lab still `home-long-title`).
5. Desktop lyrics or glow started by keybind before the app opens: the app shows them as on and Quit stops them (Task 10 lab test `test_app_reflects_running_surfaces`).

---

### Task 0: Branch and read the upstream rules

- [ ] **Step 1:** `git switch -c feat/encore-app` from clean `main`.
- [ ] **Step 2:** Read `~/Documents/dev/reference/HyDE/CONTRIBUTING.md` and `COMMIT_MESSAGE_GUIDELINES.md`; follow them for every commit below.
- [ ] **Step 3:** Save baseline stills for the refactor check in Task 4: for each style in `line stack constellation`, run `python3 tests/e2e/stage.py --style S --at 2.9,5.0,12.4 --look motion=false --out .stage/before-S`. Expected: three PNGs per style.

### Task 1: HD covers

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/artwork.py`
- Modify: `Configs/.local/lib/hyde/encore.py` (`start_palette`, `apply_palette`, `publish`), `encorelib/protocol.py` (`build_state`), `encorelib/config.py` (`hd_covers`), `Configs/.local/share/hyde/schema/{schema,config}.toml`
- Test: `tests/test_artwork.py`, `tests/test_protocol.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `spotify_large(url: str) -> str | None`; `image_size(data: bytes) -> tuple[int, int] | None`; `apple_search_url(artist: str, album: str, title: str) -> str | None`; `apple_pick(results: list[dict], artist: str, album: str, title: str) -> str | None`; `hd_art(art_url: str, original: Path | None, artist: str, album: str, title: str, dest_dir: Path, apple: bool, fetch: Fetch = http_get) -> Path | None`; constants `SPOTIFY_LARGE = "ab67616d000082c1"`, `HD_MIN_PX = 1000`, `APPLE_SIZE = 3000`.
- Produces: state field `track.cover` (path of the best cover, any image format; equals `track.art` when no HD copy exists). `track.art` keeps its meaning: the 512 px PNG lock copy.
- Produces: `EncoreConfig.hd_covers: bool = True` from `ENCORE_HD_COVERS`.

- [ ] **Step 1: Write the failing tests**

```python
def test_spotify_large_rewrites_size_code():
    url = "https://i.scdn.co/image/ab67616d0000b273baf89eb11ec7c657805d2da0"
    assert spotify_large(url) == "https://i.scdn.co/image/ab67616d000082c1baf89eb11ec7c657805d2da0"
    cdn = "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02baf89eb11ec7c657805d2da0"
    assert spotify_large(cdn).endswith("/ab67616d000082c1baf89eb11ec7c657805d2da0")

def test_spotify_large_ignores_other_urls():
    assert spotify_large("https://i.scdn.co/image/ab6761610000e5eb1234") is None  # artist image
    assert spotify_large("file:///tmp/a.png") is None
    assert spotify_large("https://i.ytimg.com/vi/x/hqdefault.jpg") is None

def test_image_size_reads_png_and_jpeg(tmp_path):
    assert image_size(write_png(tmp_path / "a.png", size=64).read_bytes()) == (64, 64)
    assert image_size(JPEG_640) == (640, 640)  # fixture: tests/fixtures/cover-640.jpg
    assert image_size(b"not an image") is None

def test_apple_url_needs_artist_and_name():
    assert apple_search_url("", "Album", "Song") is None
    assert apple_search_url("Rick Astley", "", "") is None
    url = apple_search_url("Rick Astley feat. X", "Whenever You Need Somebody (2022 Remaster)", "")
    assert "entity=album" in url and "Rick+Astley+Whenever+You+Need+Somebody" in url

def test_pick_matches_cleaned_album_and_upsizes():
    results = [{"artistName": "Rick Astley",
                "collectionName": "Whenever You Need Somebody (Deluxe Edition - 2022 Remaster)",
                "artworkUrl100": "https://is1-ssl.mzstatic.com/x/4050538793840.jpg/100x100bb.jpg"}]
    assert apple_pick(results, "Rick Astley", "Whenever You Need Somebody", "") \
        == "https://is1-ssl.mzstatic.com/x/4050538793840.jpg/3000x3000bb.jpg"

def test_pick_rejects_other_artist():
    results = [{"artistName": "Rick Astley Tribute Band", "collectionName": "Whenever You Need Somebody",
                "artworkUrl100": "https://x/100x100bb.jpg"}]
    assert apple_pick(results, "Rick Astley", "Whenever You Need Somebody", "") is None

def test_hd_art_prefers_spotify_large(tmp_path): ...      # fetch stub serves a 1500 px PNG for the 82c1 URL; result is that file
def test_hd_art_skips_apple_when_source_is_big(tmp_path): ...  # original 1200 px, apple=True: fetch never called
def test_hd_art_falls_back_on_provider_error(tmp_path): ...    # fetch raises ProviderError: returns None
def test_hd_art_respects_switch(tmp_path): ...                 # apple=False, small original: fetch never called
```

Add `tests/fixtures/cover-640.jpg` (any 640x640 JPEG made with `magick -size 640x640 xc:#a35a68 cover-640.jpg`).
In `tests/test_protocol.py`: `test_state_carries_cover` asserts `build_state(..., cover=Path("/c/full.jpg"))["track"]["cover"] == "/c/full.jpg"` and that `cover=None` falls back to the `art` path.
In `tests/test_config.py`: `test_hd_covers_default_on_and_env_off` (`ENCORE_HD_COVERS=false` gives False).

- [ ] **Step 2:** Run `python3 -m pytest -q tests/test_artwork.py tests/test_protocol.py tests/test_config.py`. Expected: FAIL (module and fields missing).
- [ ] **Step 3: Implement `encorelib/artwork.py`.** Spotify: match `/image/ab67616d` + 8-char size code + id on hosts `i.scdn.co` and `*.spotifycdn.com`, swap the size code. `image_size`: PNG IHDR, JPEG SOF0-SOF15 markers (skip DHT/DAC/JPG). Apple: `https://itunes.apple.com/search?term=<primary_artist + clean_title(album or title)>&entity=album&media=music&limit=10` (reuse `query.primary_artist`, `query.clean_title`); match when the lowercase, whitespace-collapsed `primary_artist` values are equal and `clean_title(collectionName)` equals `clean_title(album or title)`; replace `100x100bb` with `3000x3000bb`. `hd_art` order: Spotify large, else Apple only when `apple` and the original is missing or under `HD_MIN_PX` on its short side; downloads go through `palette.fetch_art` into `dest_dir`; any `ProviderError` returns None.
- [ ] **Step 4: Wire the daemon.** In `start_palette.work()`: palette and lock copy from the original as today; `cover = hd_art(art_url, original, info.artist, info.album, info.title, CACHE_DIR / "hd", apple=self.hd_covers) or original`; pass `cover` through `apply_palette` to `self.cover`; `publish` passes `cover=self.cover` to `build_state` (new keyword `cover: Path | None = None`). `self.hd_covers` reads `cfg.hd_covers` (Task 3 adds the look override). Add `hd_covers` to the schema and config toml fragments with a one-line description.
- [ ] **Step 5:** Run `python3 -m pytest -q`. Expected: PASS, including the e2e daemon tests (their `file://` art passes through as `cover`).
- [ ] **Step 6:** Commit `feat(encore): fetch HD album covers`.

### Task 2: Player list, volume and the player pin

**Files:**
- Modify: `encorelib/protocol.py`, `encorelib/session.py` (`pick_player`, new `player_label`), `encore.py` (`Encore` players, volume, runtime-dir monitor, `follow` CLI), `tests/e2e/fake_mpris.py`
- Test: `tests/test_protocol.py`, `tests/test_player_select.py`, `tests/e2e/test_daemon.py`

**Interfaces:**
- Produces: state fields `players: list[str]` (instances present, most recent first) and `volume: float | None` (0-1, None when the followed player's `Volume` read fails); `build_state(..., players=(), volume=None)`.
- Produces: `pick_player(players, allow, pin: str | None = None) -> str | None` (a present pin wins over status order); `player_label(instance: str) -> str` (`"spotify"` -> `"Spotify"`, `"brave.instance1234"` -> `"Brave"`, `"chromium.instance9"` -> `"Chromium"`).
- Produces: runtime file `$XDG_RUNTIME_DIR/hyde/encore.follow` (one instance name); CLI `encore follow <instance|auto>` writes or removes it; the daemon deletes it when that player vanishes.
- Produces: `fake_mpris.py` flags `--no-volume` (Get Volume fails), `--title`, `--artist`; `Volume` becomes writable and emits PropertiesChanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_pin_wins_over_playing():
    assert pick_player([("spotify", "Playing"), ("brave", "Paused")], (), pin="brave") == "brave"

def test_absent_pin_is_ignored():
    assert pick_player([("spotify", "Paused")], (), pin="mpv") == "spotify"

def test_player_label():
    assert player_label("spotify") == "Spotify"
    assert player_label("brave.instance1234") == "Brave"
```

E2E in `tests/e2e/test_daemon.py`:
`test_state_lists_players` (two fake players, `players` lists both, newest first);
`test_volume_published_and_follows_changes` (`h.ctl(name, "volume", "0.4")`, state `volume == 0.4`);
`test_volume_null_when_player_has_none` (`--no-volume`, state `volume is None`);
`test_follow_pin_switches_and_clears` (run `encore.py follow encoretest2`, state `player` switches while the other plays; stop that player, file is gone and `player` falls back).

- [ ] **Step 2:** Run `python3 -m pytest -q tests/test_player_select.py tests/e2e/test_daemon.py`. Expected: FAIL.
- [ ] **Step 3: Implement.** Volume via `player.props.volume` inside `try` (GLib.Error or None -> None), refreshed on the Playerctl `volume` signal and on player change. One `Gio.File.monitor_directory` on `RUNTIME_DIR` in the daemon; on `encore.follow` changes call `choose_player()`. Fake player: writable `Volume`, the three flags.
- [ ] **Step 4:** Run `python3 -m pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(encore): publish players and volume, pin a player`.

### Task 3: Persisted look and new settings keys

**Files:**
- Modify: `encorelib/look.py`, `encore.py` (paths, `run_daemon`, `run_toggle`, `run_glow_toggle`, `run_look`, `run_style`, `run_profile`), `encorelib/profiles.py`
- Test: `tests/test_look.py`, `tests/e2e/test_daemon.py`

**Interfaces:**
- Produces: `update_look(path: Path, persist: Path | None = None, **changes) -> dict` (also writes the merged look to `persist` when given); `restore_look(path: Path, persist: Path) -> bool` (copies `persist` to `path` only when `path` is missing; True when copied).
- Produces: new valid keys `stage_bg` (`"art"|"clear"`), `hd_covers`, `autostart`, `desktop_lyrics_on`, `glow_on` (bool), `players` (list of 0-16 strings, each 1-64 chars), `lock_previous` (string, 1-128 chars).
- Produces: `encore.py` constants `STATE_DIR = xdg_state_home() / "hyde"`, `LOOK_STATE = STATE_DIR / "encore.look"`; every CLI writer passes `persist=LOOK_STATE`.

- [ ] **Step 1: Write the failing tests** in `tests/test_look.py`: `test_new_keys_validate` (each key accepts its type and rejects others, e.g. `stage_bg="blur"` dropped, `players=["a"*65]` dropped); `test_update_mirrors_to_persist(tmp_path)` (both files hold the same dict); `test_restore_only_when_runtime_missing(tmp_path)` (copies once, second call returns False and leaves the runtime file as is).
E2E: `test_if_enabled_honors_autostart` (harness writes `{"autostart": true}` to `$XDG_STATE_HOME/hyde/encore.look`; `encore.py daemon --if-enabled` answers on the socket) and `test_if_enabled_stays_off_by_default`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** Daemon start: `restore_look(LOOK_PATH, LOOK_STATE)`; `--if-enabled` starts when `cfg.enable or look.get("autostart")`, then spawns the overlay when `cfg.overlay_enable or look.get("desktop_lyrics_on")` and the glow when `look.get("glow_on")`. The daemon's runtime-dir monitor (Task 2) also reloads `encore.look`: effective allow list `look.get("players") or cfg.players`, `self.hd_covers = look.get("hd_covers", cfg.hd_covers)`. `run_toggle` and `run_glow_toggle` record `desktop_lyrics_on` / `glow_on`.
- [ ] **Step 4:** Run `python3 -m pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(encore): remember the look and settings across reboots`.

### Task 4: Extract the lyric renderer

**Files:**
- Create: `Configs/.local/lib/hyde/encoregui/lyrics.py`
- Modify: `Configs/.local/lib/hyde/encoregui/overlay.py` (becomes the desktop host only)
- Test: `tests/test_overlay_raster.py` (update imports), stage stills

**Interfaces:**
- Produces: `class LyricsEngine` in `encoregui/lyrics.py`, no layer-shell import: `__init__(self, cfg: EncoreConfig, runtime_dir: str, *, desktop: bool)`; attributes `widget: Gtk.Widget` (the snapshot canvas), `style: str`, `state: dict | None`; callbacks `on_style_changed: Callable[[str], None] | None`, `on_runtime_file: Callable[[str], None] | None` (name of any changed file in the runtime dir); `shutdown() -> None`. `LineRaster` moves with it.
- Produces: `desktop=True` keeps today's behaviour minus the cover background; `desktop=False` (Full screen) always allows the no-lyrics card, in every style.
- Produces: `overlay.py` `class DesktopOverlay(app, cfg, runtime_dir)`: layer-shell window, style geometry, empty input region, `place_on`; hides its window while `encore.stage` names its monitor (or names `*`), shows it again when the file goes.
- Retired: `bg_window`, `_update_background`, `_sync_bg_window` (the desktop never draws a full-screen cover).

- [ ] **Step 1:** Move code; keep names of moved methods. `run_overlay` builds a `DesktopOverlay`.
- [ ] **Step 2:** Run `python3 -m pytest -q` and ruff. Expected: PASS.
- [ ] **Step 3:** For each style in `line stack constellation`: `python3 tests/e2e/stage.py --style S --at 2.9,5.0,12.4 --look motion=false --out .stage/after-S`, then `magick compare -metric AE .stage/before-S/<f> .stage/after-S/<f> null:` per still. Expected: AE under 0.1% of the pixels.
- [ ] **Step 4:** `python3 tests/e2e/stage.py --style visual --at 5.0,12.4`: the column with the Highlight block on a transparent desktop, no cover. Judge at full resolution.
- [ ] **Step 5:** `python3 tests/e2e/measure.py --lab --overlay --style stack` and `--style line`. Expected: within 1 point of the STATE.md numbers.
- [ ] **Step 6:** Commit `refactor(encore): share the lyric renderer between surfaces`.

### Task 5: Pure helpers for the window

**Files:**
- Create: `encorelib/transport.py`, `encorelib/coverfit.py`, `encorelib/screen.py`, `encorelib/lifecycle.py`
- Test: `tests/test_transport.py`, `tests/test_coverfit.py`, `tests/test_screen.py`, `tests/test_lifecycle.py`

**Interfaces:**
- `transport.fmt_time(seconds: float) -> str`; `transport.seek_to(position: float, delta: float, length: float) -> float`; `transport.step_volume(volume: float, delta: float) -> float`; `transport.key_action(key: str, ctrl: bool, page: str) -> str | None` with `page` in `home|lyrics|full` and actions `play-pause, seek-back, seek-forward, volume-up, volume-down, next, previous, lyrics, fullscreen, back, quit`.
- `coverfit.CoverFit(mode: str, x: float, y: float, w: float, h: float)` frozen dataclass; `coverfit.fit_cover(img_w: int, img_h: int, view_w: float, view_h: float, scale: float = 1.0) -> CoverFit` with `FILL_MAX = 1.35`, `FRAME_MAX = 1.25`, `FRAME_SHARE = 0.8`.
- `screen.screen_state(state: dict | None, now: float) -> str` in `idle|waiting|no_lyrics|plain|lyrics`; `screen.lookup_reason(entries: list[dict], artist: str, title: str) -> str`; `screen.pick_music_apps(apps: list[tuple[str, str, str]], limit: int = 3) -> list[str]` (`(desktop_id, name, categories)`; known ids `spotify.desktop`, `spotify-launcher.desktop`, `com.spotify.Client.desktop` first, then `Audio;Player` categories).
- `lifecycle.close_action(desktop_on: bool, glow_on: bool) -> str` in `hide|quit`.

- [ ] **Step 1: Write the failing tests**

```python
def test_fmt_time():
    assert [fmt_time(s) for s in (0, 7.9, 188, 3723)] == ["0:00", "0:07", "3:08", "1:02:03"]

def test_seek_and_volume_clamp():
    assert seek_to(5, -15, 200) == 0 and seek_to(195, 15, 200) == 199
    assert step_volume(0.97, 0.05) == 1.0 and step_volume(0.02, -0.05) == 0.0

def test_keys():
    assert key_action("space", False, "home") == "play-pause"
    assert key_action("Escape", False, "full") == "back"
    assert key_action("Escape", False, "home") is None
    assert key_action("f", False, "home") == key_action("F11", False, "lyrics") == "fullscreen"
    assert key_action("q", True, "full") == "quit"

def test_fit_fills_when_upscale_small():
    assert fit_cover(1500, 1500, 1920, 1080).mode == "fill"

def test_fit_frames_small_cover():
    f = fit_cover(640, 640, 1920, 1080)
    assert (f.mode, f.w, f.h, f.x, f.y) == ("framed", 800, 800, 560, 140)

def test_fit_uses_device_pixels():
    f = fit_cover(1500, 1500, 1920, 1080, scale=2)
    assert f.mode == "framed" and f.w == 864  # 0.8 * 1080 caps 1500 * 1.25 / 2

def test_idle_when_player_gone():
    assert screen_state(None, 0) == "idle"
    assert screen_state({"status": "stopped", "track": None}, 0) == "idle"

def test_waiting_then_no_lyrics():
    s = {"status": "playing", "track": {"key": "k"}, "lyrics": None, "position": 0.5, "ts": 0, "rate": 1}
    assert screen_state(s, 1.0) == "waiting" and screen_state(s, 3.0) == "no_lyrics"

def test_plain_and_synced():
    base = {"status": "playing", "track": {"key": "k"}, "position": 9, "ts": 0, "rate": 1}
    assert screen_state({**base, "lyrics": {"sync": "none", "lines": [{"start": 0, "text": "a"}]}}, 9) == "plain"
    assert screen_state({**base, "lyrics": {"sync": "line", "lines": [{"start": 0, "text": "a"}]}}, 9) == "lyrics"

def test_lookup_reason():
    e = [{"artist": "A", "title": "T", "result": "none"}, {"artist": "A", "title": "T", "result": "error: timed out"}]
    assert lookup_reason(e, "A", "T") == "Lyrics lookup failed. Check the connection."
    assert lookup_reason(e[:1], "A", "T") == "No synced lyrics found for this song."
    assert lookup_reason([], "A", "T") == "No synced lyrics found for this song."

def test_music_apps_known_first():
    apps = [("vlc.desktop", "VLC", "AudioVideo;Player;"), ("spotify.desktop", "Spotify", "Audio;Music;Player;")]
    assert pick_music_apps(apps) == ["spotify.desktop", "vlc.desktop"]

def test_close_action():
    assert close_action(False, False) == "quit"
    assert close_action(True, False) == close_action(False, True) == "hide"
```

- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. `screen_state` uses `lyricview.live_position` and the same 2 s grace as `overlay._card_active`.
- [ ] **Step 4:** Run `python3 -m pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(encore): window logic for time, covers, states and closing`.

### Task 6: The app shell, launcher entry and page split

**Files:**
- Create: `encoregui/app.py`, `encoregui/home.py`, `encoregui/popovers.py`, `encoregui/cover.py`, `Configs/.local/share/applications/org.hyde.encore.desktop`, `Configs/.local/share/icons/hicolor/scalable/apps/org.hyde.encore.svg`
- Delete: `encoregui/player.py` (its code moves to `home.py` and `popovers.py`)
- Modify: `encore.py` (CLI `app`; `player` and `menu` become aliases of `app`, `menu --rofi` stays), `Configs/.local/share/hypr/lua/window_rules.encore.lua`, `tests/e2e/stage.py` (`--app home|lyrics|full`, env `ENCORE_APP_ID`), `README.md` install links

**Interfaces:**
- Produces: `app.APP_ID = os.environ.get("ENCORE_APP_ID", "org.hyde.encore")`; `app.run_app(runtime_dir: str, page: str = "home") -> int` (unique `Gtk.Application`; a second launch with `--open <page>` switches the existing window to that page and presents it, then exits 0).
- Produces: `class EncoreWindow(Gtk.ApplicationWindow)` with `show_page(name: str)` for `home|lyrics|full`, `state: dict`, one 400 ms poll that hands the state to every page's `update(state: dict, colors: Scheme)` (`Scheme` from `encorelib.colors`).
- Produces: `home.HomePage`, `home.LyricsPage` (both `Gtk.Widget` with `update(state, colors)`); `popovers.build_look_menu(window, anchor) -> Gtk.Popover`; `popovers.build_settings_popover(window, anchor) -> Gtk.Popover`.
- Produces: `cover.CoverView(Gtk.Widget)` with `set_path(path: str)`, `set_side(px: int)`: decodes off the main thread with `Gdk.Texture.new_from_filename`, draws with a rounded clip and `append_scaled_texture(..., Gsk.ScalingFilter.TRILINEAR, ...)`; replaces the cairo `ArtView`.
- Desktop entry values: `Name=Encore`, `GenericName=Synced lyrics`, `Comment=Word-synced lyrics, full-screen visuals and edge glow for whatever is playing`, `Exec=hyde-shell encore app`, `Icon=org.hyde.encore`, `Categories=AudioVideo;Audio;Player;`, `Keywords=lyrics;music;spotify;karaoke;glow;`, `StartupWMClass=org.hyde.encore`, `Terminal=false`.

- [ ] **Step 1:** Split `player.py` with behaviour unchanged; Home art uses `track.cover` (fallback `track.art`) through `CoverView`.
- [ ] **Step 2:** `desktop-file-validate Configs/.local/share/applications/org.hyde.encore.desktop`. Expected: no output.
- [ ] **Step 3:** The icon: an original mark (a rounded square in the album-accent violet with a glowing ring and a lyric line), plain SVG, readable at 16 px.
- [ ] **Step 4:** Window rule matches `^org\\.hyde\\.encore$` (float, center, 960x660).
- [ ] **Step 5:** `python3 -m pytest -q` and ruff. Expected: PASS.
- [ ] **Step 6:** Lab check: `python3 tests/e2e/stage.py --app home --cover <1500 px cover>` and `--app lyrics`; launching `--app home` twice yields one `org.hyde.encore.lab` client. Compare with `.reference/site/frame-7.png` at full resolution: cover edges sharp, layout unchanged from today.
- [ ] **Step 7:** Link the desktop entry and icon into `~/.local/share/applications/` and `~/.local/share/icons/hicolor/scalable/apps/` (README steps); `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor` when the cache exists. "Encore" appears in `rofi -show drun -filter encore`.
- [ ] **Step 8:** Commit `feat(encore): open Encore from the app launcher`.

### Task 7: Home controls, idle and lyric states

**Files:**
- Create: `encoregui/idle.py`
- Modify: `encoregui/home.py`, `encoregui/app.py` (keys), `encoregui/popovers.py`
- Test: lab stills

**Interfaces:**
- Consumes: Task 2 state fields and `encore follow`; Task 5 `fmt_time`, `seek_to`, `step_volume`, `key_action`, `screen_state`, `lookup_reason`, `pick_music_apps`; `session.player_label`.
- Produces: `idle.IdleField(Gtk.Widget)` with `set_colors(colors: Scheme)`: two or three soft radial blobs drifting slowly, ticks at most 20 fps only while mapped and visible.

- [ ] **Step 1: Seek bar** under the title: elapsed and total via `fmt_time`, position from `live_position` every 250 ms while playing, seek on release with `playerctl -p <player> position <s>`; hidden when `length` is 0.
- [ ] **Step 2: Volume** slider with speaker icons, visible only when `volume` is not None; `playerctl -p <player> volume <v>` debounced 80 ms.
- [ ] **Step 3: Player chip** in the header: `player_label(state.player)`, menu lists `players` plus Automatic, runs `hyde-shell encore follow <name|auto>`.
- [ ] **Step 4: Bottom bar** in Lumn order: Look, Desktop lyrics (toggle, on from the overlay pidfile), Glow (toggle, on from the glow pidfile), Settings pill, Lock screen (toggle, wired in Task 9), Full screen. Every button has a tooltip; toggles carry the `.on` class when on. The old display and lock-preview actions are gone.
- [ ] **Step 5: States.** `idle`: Home swaps to an idle page with `IdleField`, "Nothing playing", and up to three buttons from `pick_music_apps` over `Gio.AppInfo.get_all()` that launch the app. Lyrics page: `waiting` shows "Looking for lyrics", `no_lyrics` shows `lookup_reason` over the journal at `encore.lookups`, `plain` shows the lines as a static list.
- [ ] **Step 6: Labels** ellipsize at the end with the full text as tooltip; the window never changes width.
Paused dims the cover to 85% opacity; a new cover crossfades over 300 ms in `CoverView`.
Clicking a row in the Lyrics page seeks to that line's `start`.
When `read_state` returns nothing for more than 1 s, the header shows "Reconnecting" and the window calls `encorelib.service.ensure_daemon` once per outage (the same call `encore.py ensure_daemon` makes).
- [ ] **Step 7: Keys** through `key_action` (Space, Left/Right, Up/Down, N/P, L, F/F11, Esc, Ctrl+Q).
- [ ] **Step 8:** Lab stills: `--app home` playing, paused, `--no-player` idle, `--app lyrics` with no lyrics, and `home-long-title` (`fake_mpris --title` of 120 chars and a CJK title). Judge every still at full resolution against `.reference/site/frame-7.png` and the `lumn-1.png` sheet.
- [ ] **Step 9:** `measure.py --lab --app home` idle: at most 2% of a core; hidden window: 0.
- [ ] **Step 10:** Commit `feat(encore): full transport, player choice and empty states in Home`.

### Task 8: Full screen

**Files:**
- Create: `encoregui/fullscreen.py`
- Modify: `encoregui/cover.py` (add `CoverBackdrop`), `encoregui/app.py`, `encoregui/overlay.py` (hide flag already in Task 4)
- Test: lab stills, lab clip, `measure.py`

**Interfaces:**
- Consumes: Task 4 `LyricsEngine(desktop=False)`; Task 5 `fit_cover`, `screen_state`; Task 3 `stage_bg`; Task 7 `IdleField`.
- Produces: `fullscreen.FullPage(Gtk.Overlay)` with `enter(window)`, `leave()`, `update(state, colors)`; `cover.CoverBackdrop(Gtk.Widget)` with `set_path(path: str)`, `set_mode(mode: str)` (`art|clear`).
- Produces: runtime file `encore.stage` holding the monitor connector while Full screen is up; removed on leave, on app quit and in an `atexit` handler.

- [ ] **Step 1: Enter and leave.** `show_page("full")` calls `window.fullscreen()`, creates the engine, writes `encore.stage`; Esc, the Exit button, or `notify::fullscreened` turning false return to Home, shut the engine down and remove the flag.
- [ ] **Step 2: Bars.** Top: Exit full screen, four style buttons (active marked), Cover / Clear toggle writing `stage_bg` with persist, Glow toggle, Look menu. Bottom: `CoverView` thumb, title and artist, seek bar, previous / play / next, volume when available. Pointer motion reveals both (200 ms crossfade) and restarts a 3 s timer; on timeout, unless the pointer is over a bar, hide them and set the cursor to `none`.
- [ ] **Step 3: Backdrop.** `art`: `fit_cover` decides; `fill` draws the texture with trilinear filtering plus scrims only behind the bars (top black 0.45 to 0, bottom 0 to 0.55); `framed` draws the cover blurred (`push_blur`, radius 60) under a 0.35 black wash, then the sharp cover at the `CoverFit` rect with 18 px corners and a soft shadow. Cover changes crossfade over 400 ms. `clear`: black.
- [ ] **Step 4: States.** `idle` shows `IdleField` with "Waiting for music"; `no_lyrics` and `plain` show the engine's cover, title and artist card; paused holds the frame and stops timers. During a `gap` whose `until` is more than 4 s away (and in the intro), the engine with `desktop=False` draws a soft "♪" pulsing at 1 Hz in the Lyric Text color, ticking at most 20 fps.
- [ ] **Step 5:** Lab stills for every style on `art` and `clear`, plus `idle`, `no_lyrics`, a 640 px cover (framed) and a 1500 px cover (fill); with the overlay running, check that it hides while Full screen is up and returns after. Lab check `full-player-quit`: stop the fake player while Full screen is up, the page falls to idle and Esc still exits. Side by side with `.reference/sheet-r7-1.png`, `.reference/site/hero-1.png` and `.reference/site/frame-16.5.png` at full resolution.
- [ ] **Step 6:** `measure.py --lab --app full --style S` for each style: at or under the overlay numbers in Global Constraints; paused 0 ticks.
- [ ] **Step 7:** Commit `feat(encore): full screen lyrics with controls you can always reach`.

### Task 9: Lock screen switch and the Settings Encore section

**Files:**
- Create: `encorelib/lockscreen.py`
- Modify: `encore.py` (CLI `lock on|off|preview|status`), `encoregui/home.py`, `encoregui/popovers.py`
- Test: `tests/test_lockscreen.py`, `tests/e2e/test_lock.py`

**Interfaces:**
- Produces: `lockscreen.read_layout(staterc: str) -> str | None`; `lockscreen.with_layout(staterc: str, name: str) -> str` (same result as HyDE's `set_conf`: replaces `HYPRLOCK_LAYOUT=...` or appends `HYPRLOCK_LAYOUT="<name>"`); `ENCORE_LAYOUT = "Encore"`, `DEFAULT_LAYOUT = "HyDE"`.
- Produces: `encore lock on` saves the current layout as `lock_previous` (persisted look) unless it is already Encore, writes staterc, runs `hyde-shell hyprlock.sh --reload`; `off` restores `lock_previous` or `HyDE`; `preview` runs `hyde-shell hyprlock.sh --test Encore`; `status` prints `on` or `off`.

- [ ] **Step 1: Write the failing tests**

```python
def test_read_layout():
    assert read_layout('A="1"\nHYPRLOCK_LAYOUT="Anurati"\n') == "Anurati"
    assert read_layout("") is None

def test_with_layout_replaces_and_appends():
    assert with_layout('HYPRLOCK_LAYOUT="Anurati"\nX="1"\n', "Encore") == 'HYPRLOCK_LAYOUT="Encore"\nX="1"\n'
    assert with_layout('X="1"\n', "Encore") == 'X="1"\nHYPRLOCK_LAYOUT="Encore"\n'
```

`tests/e2e/test_lock.py::test_lock_on_off_restores_previous`: tmp `XDG_STATE_HOME` with `HYPRLOCK_LAYOUT="Anurati"`, a stub `hyde-shell` first on `PATH` that logs its args; `lock on` then `lock off` leaves `Anurati` and logs two `--reload` calls.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the module and CLI; Home's Lock screen toggle and the Settings "Lock screen lyrics" switch call `hyde-shell encore lock on|off`, Preview calls `lock preview`.
- [ ] **Step 4:** Settings Encore section: "HD covers" switch (`hd_covers`), "Follow" checklist of `players` plus saved names (`players`, empty means all), "Start at login" switch (`autostart`), "Quit Encore" button (Task 10's quit action). All writes pass `persist`.
- [ ] **Step 5:** Run `python3 -m pytest -q`. Expected: PASS. Lab still of the Settings popover next to `.reference/site/lumn-2.png`.
- [ ] **Step 6:** Commit `feat(encore): lock screen switch and app settings`.

### Task 10: Close to tray and Quit

**Files:**
- Create: `encorelib/dbusmenu.py`, `encoregui/tray.py`
- Modify: `encoregui/app.py`
- Test: `tests/test_dbusmenu.py`, `tests/e2e/test_app.py` (marker `lab`, opt-in, registered in `pyproject.toml`)

**Interfaces:**
- Consumes: Task 5 `close_action`.
- Produces: `dbusmenu.layout(desktop_on: bool, glow_on: bool, playing: bool) -> tuple` returning the `GetLayout` tree `(0, {"children-display": "submenu"}, [(id, props, []), ...])` with ids `1 Open Encore, 2 Pause|Play, 3 Next, 4 Desktop lyrics (toggle-type checkmark), 5 Glow (toggle-type checkmark), 6 separator, 7 Quit`; `dbusmenu.ACTIONS: dict[int, str]`.
- Produces: `tray.Tray` with `start(on_activate: Callable[[], None], on_action: Callable[[str], None]) -> bool` (False when no `org.kde.StatusNotifierWatcher`), `update(desktop_on, glow_on, playing)`, `stop()`; exports `org.kde.StatusNotifierItem` at `/StatusNotifierItem` (IconName `org.hyde.encore`, Menu `/MenuBar`) and `com.canonical.dbusmenu` at `/MenuBar`; re-registers when the watcher reappears.

- [ ] **Step 1: Write the failing tests** in `tests/test_dbusmenu.py`: `test_layout_ids_and_labels`, `test_toggle_states` (`toggle-state` 1 or 0 follows the flags), `test_play_label_follows_status`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** `close-request`: `close_action(overlay_running, glow_running)`; `hide` hides the window, holds the app once and starts the tray; `quit` quits. Launcher activation and tray Open present the window and release the hold. The quit action (Ctrl+Q, tray Quit, Settings Quit) stops the overlay and glow from their pidfiles, removes `encore.stage`, quits; the daemon keeps running.
- [ ] **Step 4:** Lab tests (`python3 -m pytest -q -m lab tests/e2e/test_app.py`) with a fake `StatusNotifierWatcher` on the private bus: `test_second_launch_presents_one_window`, `test_close_with_glow_hides_and_registers_tray`, `test_close_with_nothing_on_quits`, `test_quit_stops_overlay_and_glow`, `test_app_reflects_running_surfaces`.
- [ ] **Step 5:** Run `python3 -m pytest -q` (default suite excludes `lab`). Expected: PASS.
- [ ] **Step 6:** Commit `feat(encore): keep running in the tray and quit cleanly`.

### Task 11: Retire the show workspace, update fragments and docs

**Files:**
- Modify: `encore.py` (remove `show`), `encorelib/profiles.py` (remove `SHOW_WORKSPACE`, `show_action`, the `show` profile), `tests/test_profiles.py`, `Configs/.local/share/hypr/lua/key_binds.encore.lua` (SUPER+ALT+M runs `hyde-shell encore app`, SUPER+ALT+E removed), `docs/DECISIONS.md`, `docs/STATE.md`, `docs/PRODUCT.md`, `AGENTS.md`, `README.md`

- [ ] **Step 1:** Remove the code and its tests; `python3 -m pytest -q` and ruff pass.
- [ ] **Step 2:** DECISIONS: #29 Encore is a launcher app with one window (Home, Lyrics, Full screen), supersedes the `menu` and `show` parts of #16; #30 HD covers (Spotify size code, Apple fallback, strict match, on by default); #31 shared `LyricsEngine`, supersedes #17, and #3 updated (the desktop overlay never draws a full-screen cover); #32 look and settings persist in `$XDG_STATE_HOME/hyde/encore.look`; #33 close to tray through StatusNotifierItem, Quit stops every surface.
- [ ] **Step 3:** PRODUCT.md Pieces describe the app; AGENTS.md architecture map lists the new modules; README covers launching from the app launcher and the new install links.
- [ ] **Step 4:** STATE.md rewritten in place with the measured numbers from Tasks 4, 7 and 8; `verified:` bumped after checking it against the code.
- [ ] **Step 5:** Commit `docs(encore): record the app shape`.

### Task 12: Final verification and owner check

- [ ] **Step 1:** `python3 -m pytest -q`, `python3 -m pytest -q -m lab`, `uvx ruff check Configs tests`, `uvx ruff format --check Configs tests`. Expected: all green.
- [ ] **Step 2:** Request a whole-branch review (superpowers:requesting-code-review); fix what it confirms.
- [ ] **Step 3:** Owner check on the real screen, owner driving: open Encore from rofi; play a Spotify song; seek, volume, next; open Lyrics; enter Full screen, switch style and background, leave with Esc; turn on Glow, close the window, reopen from the tray; Lock screen preview; Quit.
- [ ] **Step 4:** Add up to three ideas to STATE.md `## Ideas`; stop the brainstorm server (`scripts/stop-server.sh`).
