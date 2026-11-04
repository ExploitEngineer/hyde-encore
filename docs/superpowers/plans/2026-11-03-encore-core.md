# hyde-encore Plan 1: Core daemon, lyrics engine, hyprlock layout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (owner's standing choice: inline execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A running `hyde-shell encore daemon` that follows the active MPRIS player, finds word-timed lyrics, tracks the sung word, publishes state on a socket, and drives a live lyric line on a new `Encore` hyprlock layout.

**Architecture:** Pure-Python library package `encorelib/` (no GTK, no D-Bus) holds parsing, timing, providers, cache, palette and protocol, all unit-tested.
`encore.py` wires it to Playerctl on a GLib main loop and serves JSON lines on `$XDG_RUNTIME_DIR/hyde/encore.sock`.
`encore.sh` is the `hyde-shell` entry point and runs `encore.py` with system `python3`.

**Tech Stack:** Python 3.11+ (system 3.14), PyGObject (`Playerctl` 2.0, `GLib`), stdlib `urllib`/`json`/`socket`, HyDE `pyutils`, `wallbash.sh` + ImageMagick, hyprlock, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-hyde-encore-design.md`

**Later plans (written after this one ships):** Plan 2 lyrics overlay (GTK4 layer-shell), Plan 3 edge glow (cava beat), Plan 4 `follow_album` spike and full-theme recolor.

## Global Constraints

- Repo tree mirrors HyDE: scripts in `Configs/.local/lib/hyde/`, hyprlock layouts in `Configs/.config/hypr/hyprlock/`, config defaults in `Configs/.local/share/hyde/schema/config.toml` and `schema.toml`.
- Python runs on system `python3`, not HyDE's venv: the venv has `include-system-site-packages = false` and cannot import `gi` (DECISIONS #8, added in Task 1).
- Library modules in `encorelib/` must not import `gi`; only `encore.py` does.
- Use `pyutils.logger.get_logger()` and `pyutils.xdg_base_dirs` the way `mediaplayer.py` does.
- Config arrives as env vars written by HyDE's `config.lua` from `config.toml`: section path upper-cased and joined by `_`, e.g. `[encore.lyrics] spicy_key` becomes `ENCORE_LYRICS_SPICY_KEY`. Read `$XDG_STATE_HOME/hyde/config` if present, then the process env, then defaults.
- Lyric sources, in order: local `.lrc`, LRCLIB, Spicy Lyrics (only with a user key and only for Spotify track IDs). Never Musixmatch.
- HTTP via `urllib.request` with a 5 second timeout and a `User-Agent: hyde-encore (https://github.com/ExploitEngineer/hyde-encore)` header (LRCLIB asks clients to identify themselves).
- Cache root `$XDG_CACHE_HOME/hyde/encore/`; runtime files under `$XDG_RUNTIME_DIR/hyde/`.
- Idle cost: no timers run while paused or stopped.
- License header: GPL-3.0 project; any code adapted from MIT projects keeps its notice.
- Commits: conventional type prefix, imperative, lines at most 72 chars, no agent attribution.
- Markdown: one sentence per line, no em dash character.

## Review Focus

1. Track change mid-fetch: a slow LRCLIB response for song A arrives after the user skipped to song B, and must be dropped, not shown on B.
2. Seek or scrub: position jumps backwards or forwards; the cursor must land on the right line immediately, not walk there.
3. Lyrics with gaps: instrumental breaks, empty `[mm:ss]` lines, and the time before the first line must show no highlighted word.
4. Player switching: two players open (Spotify plus a paused browser tab); encore follows the one that is playing, as playerctld does.
5. Weird metadata: missing artist, `feat.` in titles, non-Latin text, a `file://` art URL with spaces, no art at all.

Tests: 1 in Task 8 (`FetchGate`), 2 in Tasks 2 and 3, 3 in Task 2, 4 in Task 8 (`pick_player`), 5 in Tasks 5 and 6.

## File Structure

```text
Configs/.local/lib/hyde/
  encore.sh                 hyde-shell entry: exec system python3 encore.py "$@"
  encore.py                 CLI + daemon wiring (Playerctl, GLib, socket, hyprlock file)
  encorelib/__init__.py
  encorelib/model.py        Word, Line, Lyrics dataclasses
  encorelib/lrc.py          plain + enhanced LRC parser
  encorelib/timing.py       word estimator + cursor lookup
  encorelib/clock.py        PlaybackClock
  encorelib/providers.py    local .lrc, LRCLIB, Spicy fetch + parse, provider chain
  encorelib/cache.py        JSON cache of Lyrics per track key
  encorelib/palette.py      cover art fetch, wallbash.sh run, .dcol parse
  encorelib/config.py       EncoreConfig from env file + env
  encorelib/protocol.py     state dict builder, hyprlock markup, socket server/client
Configs/.config/hypr/hyprlock/Encore.conf
Configs/.local/share/hyde/schema/config.toml   (fragment: [encore] sections)
Configs/.local/share/hyde/schema/schema.toml   (fragment: properties.encore)
tests/conftest.py            puts Configs/.local/lib/hyde on sys.path
tests/fixtures/              sample .lrc, enhanced .lrc, LRCLIB json, Spicy json
tests/test_*.py
```

Socket protocol (consumed by Plans 2 and 3, fixed here): one JSON object per line, sent on connect and on every change, plus a resync every 1 s while playing.

```json
{"v": 1, "ts": 12345.678, "status": "playing", "player": "spotify",
 "track": {"key": "...", "title": "...", "artist": "...", "album": "...", "length": 215.3, "art": "/path/cover.png"},
 "lyrics": {"sync": "word", "source": "lrclib", "credit": null, "lines": [{"start": 61.9, "text": "hello world"}]},
 "position": 63.21, "rate": 1.0,
 "line": {"index": 12, "start": 61.9, "end": 65.4, "text": "hello world", "words": [{"text": "hello", "start": 61.9, "end": 62.3}]},
 "next": "text of next line",
 "gap": null,
 "palette": {"pry1": "1E1E2E", "pry4": "...", "txt1": "...", "1xa8": "..."}}
```

`ts` is `time.monotonic()` (CLOCK_MONOTONIC, shared across processes), so clients compute the live position as `position + (now - ts) * rate` when `status == "playing"`.

Gaps (added in layer 1, still `v: 1`): a line stops being live 4 s after its last word (`timing.GAP_HOLD_SECONDS`) or at a blank line; then `line` is `null` and `gap` is `{"after": <last started line index, -1 in the intro>, "until": <start of the next non-blank line>}`.
`gap` is `null` while a line is live (and for unsynced lyrics); in the outro it is `{"after": <last line>, "until": null}`; `next` always names the next non-blank line.
`line.text` is the source text, so scripts without spaces (Chinese, Japanese) render without inserted spaces; each `words[].text` is a substring of it.

---

### Task 1: Test harness, model, LRC parser

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/__init__.py`, `encorelib/model.py`, `encorelib/lrc.py`
- Create: `tests/conftest.py`, `tests/fixtures/plain.lrc`, `tests/fixtures/enhanced.lrc`, `tests/test_lrc.py`, `pyproject.toml` (repo root, pytest + ruff config only, `line-length = 100` like upstream)
- Modify: `docs/DECISIONS.md` (add #8 system python3), `AGENTS.md` (Commands: `python3 -m pytest -q`, `ruff check Configs tests`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Word(text: str, start: float, end: float)`
  - `@dataclass(frozen=True) Line(start: float, end: float, text: str, words: tuple[Word, ...])` (`words` empty when only line timing is known)
  - `@dataclass(frozen=True) Lyrics(lines: tuple[Line, ...], sync: Literal["word", "line", "none"], source: str, credit: str | None = None)` plus `to_dict()` / `Lyrics.from_dict(d)`
  - `parse_lrc(text: str, source: str = "lrc") -> Lyrics`

- [ ] **Step 1: Write failing tests** in `tests/test_lrc.py`:
  - `test_plain_lines`: `"[00:12.50]Hello world\n[00:15.00]Second"` gives 2 lines, `lines[0].start == 12.5`, `lines[0].end == 15.0`, `sync == "line"`, `words == ()`.
  - `test_last_line_end`: last line `end == start + 5.0` (fallback when no following line).
  - `test_multi_timestamp`: `"[00:01.00][00:30.00]Chorus"` yields two lines sorted by start.
  - `test_offset_tag`: `"[offset:500]\n[00:10.00]x"` gives `start == 10.5` (positive offset delays, per LRC convention lyrics shift later).
  - `test_enhanced_words`: `"[00:10.00]<00:10.00>Hel <00:10.40>lo <00:10.90>you<00:11.50>"` gives `sync == "word"`, 3 words, `words[1] == Word("lo", 10.4, 10.9)`, last word end `11.5`.
  - `test_empty_lines_kept_as_gaps`: `"[00:05.00]a\n[00:08.00]\n[00:20.00]b"` keeps a line with `text == ""` at 8.0 so the gap shows nothing.
  - `test_metadata_tags_ignored`: `[ar:..]`, `[ti:..]`, `[length:..]` produce no lines.
  - `test_no_timestamps`: unsynced text gives `sync == "none"` with one `Line` per text line at `start == 0`.
  - `test_roundtrip_dict`: `Lyrics.from_dict(l.to_dict()) == l`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_lrc.py -q`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `model.py` and `lrc.py`. Timestamps accept `mm:ss`, `mm:ss.xx`, `mm:ss.xxx`. Strip trailing whitespace from word text but keep the inter-word space out of `text`.
- [ ] **Step 4: Run** the tests. Expected: PASS. Also `ruff check Configs tests` clean.
- [ ] **Step 5: Commit** `feat: add lyrics model and LRC parser`.

### Task 2: Word estimator and cursor lookup

**Files:**
- Create: `encorelib/timing.py`, `tests/test_timing.py`

**Interfaces:**
- Consumes: `Word`, `Line`, `Lyrics` (Task 1)
- Produces:
  - `estimate_words(line: Line) -> Line` returns a `Line` whose `words` span `[start, end)`, durations weighted by `len(word) + 2` (Claude's heuristic, tune by eye in Task 9), last word ending at `min(line.end, line.start + 0.45 * len(line.text))` so a long instrumental gap after a line does not stretch its last word.
  - `with_words(lyrics: Lyrics) -> Lyrics` applies `estimate_words` to every line lacking words; keeps `sync` as reported by the source.
  - `@dataclass(frozen=True) Cursor(line: int, word: int, progress: float)` where `-1` means none and `progress` is 0..1 within the word.
  - `locate(lyrics: Lyrics, t: float) -> Cursor`, binary search on line starts.

- [ ] **Step 1: Write failing tests:**
  - `test_estimate_spans_line`: line 10.0 to 12.0, text `"a bb ccc"` gives 3 words, first start 10.0, words contiguous, last end <= 12.0.
  - `test_estimate_caps_long_gap`: line 10.0 to 40.0, text `"hi"` gives last end `10.0 + 0.45 * 2`.
  - `test_estimate_empty_text`: `""` gives `words == ()`.
  - `test_locate_before_first_line`: `t` before first start gives `Cursor(-1, -1, 0.0)`.
  - `test_locate_in_word`: mid-word gives right indices and `progress` between 0 and 1.
  - `test_locate_between_words`: in the gap between word end and next word start gives the previous word with `progress == 1.0`.
  - `test_locate_gap_line`: inside an empty-text line gives `Cursor(i, -1, 0.0)` (Review Focus 3).
  - `test_locate_after_end`: after the last line's end gives `Cursor(last, -1, 0.0)`.
  - `test_locate_seek_back`: calling with 60.0 then 5.0 returns the 5.0 answer (stateless; Review Focus 2).
- [ ] **Step 2: Run**, expect FAIL.
- [ ] **Step 3: Implement** with `bisect` over a precomputed tuple of starts.
- [ ] **Step 4: Run**, expect PASS.
- [ ] **Step 5: Commit** `feat: add word timing estimator and cursor lookup`.

### Task 3: Playback clock

**Files:**
- Create: `encorelib/clock.py`, `tests/test_clock.py`

**Interfaces:**
- Produces: `class PlaybackClock(now: Callable[[], float] = time.monotonic)` with `sync(position: float, playing: bool, rate: float = 1.0) -> None`, `position() -> float`, `playing: bool`, `rate: float`, `anchor() -> tuple[float, float]` returning `(position_at_ts, ts)` for the protocol.

- [ ] **Step 1: Write failing tests** with a fake `now`:
  - `test_advances_while_playing`: sync(10, True) then now += 2.5 gives 12.5.
  - `test_frozen_while_paused`: sync(10, False), now += 5 gives 10.
  - `test_rate`: rate 2.0 doubles advance.
  - `test_resync_jump`: sync(10, True), now += 1, sync(100, True) gives 100 (seek; Review Focus 2).
  - `test_anchor`: `anchor()` returns the last synced position and its timestamp.
- [ ] **Step 2: Run**, expect FAIL. **Step 3: Implement.** **Step 4: Run**, expect PASS.
- [ ] **Step 5: Commit** `feat: add playback clock`.

### Task 4: Config

**Files:**
- Create: `encorelib/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) EncoreConfig(enable: bool = False, players: tuple[str, ...] = (), lyrics_dirs: tuple[Path, ...] = (...defaults...), spicy_key: str = "", lrclib: bool = True, hyprlock_color: str = "", hyprlock_dim: str = "")` and `load_config(env: Mapping[str, str] | None = None, env_file: Path | None = None) -> EncoreConfig`.
  - Env names: `ENCORE_ENABLE`, `ENCORE_PLAYERS` (comma list), `ENCORE_LYRICS_DIRS` (colon list), `ENCORE_LYRICS_SPICY_KEY` (also accepted: `SPICY_LYRICS_SECRET_KEY`), `ENCORE_LYRICS_LRCLIB`, `ENCORE_HYPRLOCK_COLOR`, `ENCORE_HYPRLOCK_DIM`.
  - Precedence: process env over env file over defaults. Booleans accept `1/0/true/false`.

- [ ] **Step 1: Write failing tests:** defaults with empty env; env file `export ENCORE_LYRICS_SPICY_KEY="abc"` is read; process env overrides file; bad boolean falls back to default.
- [ ] **Step 2-4:** run FAIL, implement (reuse the `export KEY="v"` parsing rules from `mediaplayer.load_env_file`), run PASS.
- [ ] **Step 5: Commit** `feat: add encore config loader`.

### Task 5: Lyrics providers and cache

**Files:**
- Create: `encorelib/providers.py`, `encorelib/cache.py`, `tests/test_providers.py`, `tests/test_cache.py`, `tests/fixtures/lrclib_get.json`, `tests/fixtures/spicy_syllable.json`

**Interfaces:**
- Consumes: `parse_lrc`, `Lyrics`, `Line`, `Word` (Task 1), `EncoreConfig` (Task 4)
- Produces:
  - `@dataclass(frozen=True) TrackInfo(title: str, artist: str, album: str, length: float, url: str, trackid: str, player: str)` and `track_key(t: TrackInfo) -> str` (sha1 of normalized `artist|title|round(length)`; normalization lowercases, strips `(feat. ...)`/`[feat. ...]` and surrounding whitespace).
  - `Fetch = Callable[[str, dict[str, str]], bytes]` and `http_get(url: str, headers: dict[str, str]) -> bytes` (urllib, 5 s timeout, User-Agent from Global Constraints; raises `ProviderError` on HTTP or network failure, `None`-equivalent on 404 handled by caller).
  - `local_lrc(t: TrackInfo, search_dirs: list[Path]) -> Lyrics | None`: if `t.url` is `file://`, try the sibling `<stem>.lrc`; then `<dir>/<artist> - <title>.lrc` in each search dir (default `$XDG_DATA_HOME/lyrics`, `~/Music/Lyrics`).
  - `lrclib(t: TrackInfo, fetch: Fetch = http_get) -> Lyrics | None`: `GET https://lrclib.net/api/get?artist_name=&track_name=&album_name=&duration=`; on 404 fall back to `GET /api/search?track_name=&artist_name=` and pick the first result whose `duration` is within 2 s; prefer `syncedLyrics` (parse with `parse_lrc`, which detects enhanced word tags), else `plainLyrics` with `sync="none"`, `instrumental: true` gives empty `Lyrics(sync="none")`.
  - `spicy(t: TrackInfo, key: str, fetch: Fetch = http_get) -> Lyrics | None`: only when `t.player == "spotify"` and `t.trackid` matches `/com/spotify/track/<id>` or `spotify:track:<id>`; `GET https://api.spicylyrics.org/v1/lyrics/<id>` with `Authorization: Bearer <key>`; maps `Type` `Syllable` to word sync, `Line` to line sync, `Static` to none; sets `credit` when `source` is the Spicy community catalogue.
  - `find_lyrics(t: TrackInfo, cfg: EncoreConfig, fetch: Fetch = http_get) -> Lyrics | None`: order local, then LRCLIB; if result is not word-synced and a Spicy key is set and the track is Spotify, try Spicy and prefer it when word-synced. Errors from one provider are logged and skipped.
  - `class LyricsCache(root: Path)` with `get(key: str) -> Lyrics | None`, `put(key: str, lyrics: Lyrics | None) -> None` (stores a miss marker so missing tracks are not refetched for 7 days), files at `root/lyrics/<key>.json`, atomic write via temp file plus `os.replace`.

- [ ] **Step 1: Confirm the Spicy schema.** Open `https://developers.spicylyrics.org/docs/reference/get.lyrics` in the browser (the page renders client-side) and save a representative `Syllable` response into `tests/fixtures/spicy_syllable.json`. If the docs are not reachable, write the fixture from the docs' example only when the owner supplies a key and a real response; until then mark `spicy` tests `xfail(reason="schema unconfirmed")` and record that in STATE.md.
- [ ] **Step 2: Write failing tests** (all with a fake `fetch` returning fixture bytes or raising):
  - `test_track_key_normalizes_feat`: `"Song (feat. X)"` and `"Song"` share a key (Review Focus 5).
  - `test_track_key_non_latin`: Japanese title produces a stable key without error (Review Focus 5).
  - `test_local_sibling_lrc`: `file:///tmp/My Music/a b.mp3` with `a b.lrc` beside it (spaces in path, Review Focus 5) returns parsed lyrics.
  - `test_lrclib_get_synced`: fixture gives `sync in ("line", "word")` and correct first line.
  - `test_lrclib_404_then_search_duration_match`: picks the search hit within 2 s, skips one 10 s off.
  - `test_lrclib_instrumental`: returns `Lyrics(sync="none")` with no lines.
  - `test_spicy_requires_spotify`: `player="mpv"` never calls fetch.
  - `test_spicy_syllable_to_words` (fixture-based).
  - `test_find_lyrics_prefers_word_sync`: LRCLIB line-synced plus Spicy word-synced returns Spicy.
  - `test_find_lyrics_provider_error_skipped`: LRCLIB raising `ProviderError` still lets local or Spicy win; all failing returns `None`.
  - `test_cache_roundtrip_and_miss_marker`: `put(k, None)` then `get` signals a cached miss (distinguish "miss cached" from "not cached": `get` returns `Lyrics(lines=(), sync="none", source="miss")`), stale after 7 days via file mtime.
- [ ] **Step 3: Run**, expect FAIL. **Step 4: Implement.** **Step 5: Run**, expect PASS.
- [ ] **Step 6: Live smoke check** (network): `python3 -c` calling `lrclib()` for a well-known song prints the first 3 lines. Expected: real lyrics.
- [ ] **Step 7: Commit** `feat: add lyrics providers and cache`.

### Task 6: Album palette

**Files:**
- Create: `encorelib/palette.py`, `tests/test_palette.py`, `tests/fixtures/sample.dcol`

**Interfaces:**
- Produces:
  - `fetch_art(art_url: str, dest_dir: Path, fetch: Fetch = http_get) -> Path | None`: handles `file://` (URL-decoded, spaces OK), `http(s)://` (cached by sha1 of URL), empty or unreadable gives `None` (Review Focus 5).
  - `parse_dcol(text: str) -> dict[str, str]`: `dcol_pry1="1E1E2E"` style lines to `{"pry1": "1E1E2E", ...}`, also accepting `export` prefixes.
  - `album_palette(art: Path, cache_dir: Path, run: Callable[[list[str]], int] = subprocess-based) -> dict[str, str]`: runs `<LIB_DIR>/hyde/wallbash.sh <art> <cache_dir>/<sha1(art bytes)>` once per image (reuse existing `.dcol`), returns `parse_dcol` of the output; returns `{}` on failure so callers fall back to wallpaper colors.
  - `wallpaper_palette() -> dict[str, str]`: `parse_dcol` of `$XDG_CACHE_HOME/hyde/wall.dcol`, `{}` if missing.

- [ ] **Step 1: Read** upstream `wallbash.sh` output section to copy the exact `.dcol` key format into `tests/fixtures/sample.dcol` (generate one real file: `~/.local/lib/hyde/wallbash.sh <some image> <scratchpad>/x` and copy it).
- [ ] **Step 2: Write failing tests:** `parse_dcol` on the fixture has `pry1` and `txt1`; `fetch_art` with a `file://` URL containing `%20`; `fetch_art("")` is `None`; `album_palette` calls `run` once for two calls with the same image; failing `run` gives `{}`.
- [ ] **Step 3-5:** run FAIL, implement, run PASS.
- [ ] **Step 6: Commit** `feat: add album art palette via wallbash`.

### Task 7: Protocol, hyprlock markup, socket server

**Files:**
- Create: `encorelib/protocol.py`, `tests/test_protocol.py`

**Interfaces:**
- Consumes: `Lyrics`, `Cursor`, `locate`, `PlaybackClock`, `TrackInfo`, palette dicts.
- Produces:
  - `build_state(status: str, track: TrackInfo | None, art: Path | None, lyrics: Lyrics | None, clock: PlaybackClock, palette: dict[str, str]) -> dict` matching the schema in File Structure (`line` is `null` when the cursor has no line; `lyrics` is `null` while fetching or when none found).
  - `hyprlock_markup(lyrics: Lyrics | None, cursor: Cursor, accent: str, dim: str) -> str`: Pango markup of the current line, words up to and including the cursor word in `<span foreground="#accent">`, the rest in `#dim`, all text passed through `GLib`-free XML escaping (`html.escape` with `quote=False`); empty string when no line or empty line.
  - `class StateServer(path: Path)`: `start() -> socket.socket` (removes a stale socket file the way `cava.py` checks liveness first), `accept()`, `broadcast(state: dict) -> None` (drops clients that error), `close()`; it keeps the last state and sends it to a new client on accept.
  - `read_state(path: Path, timeout: float = 0.3) -> dict | None`: client helper reading the first line.

- [ ] **Step 1: Write failing tests:**
  - `test_build_state_schema`: keys and types match the JSON example; `ts` equals the clock anchor ts.
  - `test_markup_highlights_sung_words`: cursor word 1 of 3 gives first two words accent, third dim.
  - `test_markup_escapes`: `"rock & roll <3"` is escaped.
  - `test_markup_gap_is_empty`: empty-text line gives `""`.
  - `test_server_sends_last_state_on_connect`: start server in a temp dir, broadcast, then `read_state` receives it.
  - `test_server_drops_dead_client`: a closed client does not break the next broadcast.
- [ ] **Step 2-4:** run FAIL, implement, run PASS.
- [ ] **Step 5: Commit** `feat: add state protocol, hyprlock markup and socket server`.

### Task 8: Daemon, CLI and hyde-shell entry

**Files:**
- Create: `Configs/.local/lib/hyde/encore.py`, `Configs/.local/lib/hyde/encore.sh`, `tests/test_player_select.py`

**Interfaces:**
- Consumes: everything above.
- Produces (CLI, used by Plans 2-4 and the layout):
  - `hyde-shell encore daemon` runs the service in the foreground (single instance: exit 0 with a message if the socket is live).
  - `hyde-shell encore status` prints the current state JSON or `{"status": "stopped"}`.
  - `hyde-shell encore hyprlock` prints the contents of `$XDG_RUNTIME_DIR/hyde/encore.hyprlock` or nothing.
  - `hyde-shell encore daemon --if-enabled` exits 0 silently unless `ENCORE_ENABLE` is true (used by autostart).
  - `pick_player(players: list[tuple[str, str]], allow: tuple[str, ...]) -> str | None` in `encore.py`, pure: given `(name, status)` pairs returns the first `Playing`, else the first `Paused`, filtered by `allow` when non-empty.
  - `class FetchGate` in `encore.py`, pure: `begin(key: str) -> int` returns a new token and makes it current; `accept(token: int, key: str) -> bool` is true only for the current token and key.
- Daemon behavior (the implementer writes it; the decisions are):
  - `Playerctl.PlayerManager` on a GLib main loop, same signal set as `mediaplayer.py` (`name-appeared`, `player-vanished`, `playback-status`, `metadata`, `seeked`).
  - On metadata change: build `TrackInfo`, broadcast with `lyrics: null`, start a worker thread for cache, then `find_lyrics`, then `with_words`; deliver via `GLib.idle_add` and drop the result unless `FetchGate.accept` (Review Focus 1). Palette work runs in the same worker.
  - While playing: one `GLib.timeout_add(50, tick)`; tick computes `locate`, and only when `(line, word)` changes writes the hyprlock file atomically and broadcasts. Every 1 s it resyncs the clock from `player.get_position()` and broadcasts. When paused or stopped the timeout is removed (Global Constraints idle cost).
  - Hyprlock colors: `cfg.hyprlock_color` or palette `1xa8`, dim `cfg.hyprlock_dim` or palette `txt1` at 50% alpha (`#RRGGBB80`).
  - SIGINT/SIGTERM: remove socket and hyprlock file, exit 0.
- `encore.sh`: sources nothing heavy, `exec python3 "$(dirname "$(realpath "$0")")/encore.py" "$@"` with a comment stating why system python is used (DECISIONS #8). Plan 2 adds `LD_PRELOAD` here for the overlay subcommand only.

- [ ] **Step 1: Write failing tests** in `tests/test_player_select.py`: `pick_player` playing beats paused regardless of order (Review Focus 4), allow-list filters, none gives `None`; `FetchGate`: `t1 = begin("A"); t2 = begin("B")` then `accept(t1, "A") is False` and `accept(t2, "B") is True` (Review Focus 1).
- [ ] **Step 2-4:** run FAIL, implement `pick_player` and `FetchGate`, run PASS.
- [ ] **Step 5: Implement** the daemon and CLI.
- [ ] **Step 6: Install for local E2E** by symlinking the repo files into the live tree: `ln -s` each of `encore.py`, `encore.sh`, `encorelib/` into `~/.local/lib/hyde/` (list the targets first; never overwrite an existing non-symlink).
- [ ] **Step 7: E2E with Spotify** (owner plays a song with known lyrics): run `hyde-shell encore daemon` in a terminal; in another, `watch -n 0.2 hyde-shell encore hyprlock`. Expected: the highlighted word follows the singer; seeking in Spotify jumps the line within 1 s; skipping 3 tracks quickly ends on the right song's lyrics; pausing stops updates.
- [ ] **Step 8: Idle check:** with music paused, `pidstat -p <pid> 1 10` shows 0.00 %CPU average and `strace -c -f -p <pid>` over 10 s shows no periodic timer wakeups. Record numbers in STATE.md.
- [ ] **Step 9: Second player:** play a YouTube video in the browser while Spotify is paused, then switch back; encore follows the playing one.
- [ ] **Step 10: Commit** `feat: add encore daemon and hyde-shell entry`.

### Task 9: hyprlock layout, config schema, docs

**Files:**
- Create: `Configs/.config/hypr/hyprlock/Encore.conf`, `Configs/.local/share/hypr/lua/start_up.encore.lua`
- Create: `Configs/.local/share/hyde/schema/config.toml` and `schema.toml` fragments containing only the new `[encore]`, `[encore.lyrics]`, `[encore.hyprlock]` sections, written in upstream's exact style (comment per key, `[properties.encore...]` blocks with `default`, `description`, `type`).
- Modify: `README.md` (install-for-testing steps, suggested keybind snippet for `~/.config/hypr/hyprland.lua` is deferred to Plan 2), `docs/STATE.md`, `AGENTS.md`.

**Interfaces:**
- Consumes: `hyde-shell encore hyprlock`, upstream hyprlock variables `$BACKGROUND_PATH`, `$MPRIS_IMAGE`, `$MPRIS_TITLE`, `$MPRIS_ARTIST`, `$TIME`.

- [ ] **Step 1: Read** upstream `HyDE.conf` and `Arfan on Clouds.conf` fully and copy their structure, variable usage and comment header style.
- [ ] **Step 2: Write `Encore.conf`:** blurred `$BACKGROUND_PATH`, large album art from `$MPRIS_IMAGE` (rounded), title and artist via `cmd[update:1000] $MPRIS_TITLE` / `$MPRIS_ARTIST`, lyric label `text = cmd[update:100] cat "$XDG_RUNTIME_DIR/hyde/encore.hyprlock" 2>/dev/null` (a `cat`, not a Python start, so the lock screen stays cheap), time, and the input field. When nothing plays the lyric label is empty and the layout still looks like a clean HyDE lock screen.
- [ ] **Step 3: Preview without locking:** ask the owner first (live desktop), then use `hyde-shell hyprlock.sh --test-preview "Encore"` and screenshot with `grim` to the scratchpad; check alignment, clipping and font sizes at 1920x1080; zoom before calling something a bug.
- [ ] **Step 4: Real lock test** (owner present, Spotify playing): select the layout through `hyde-shell hyprlock.sh` picker, lock, watch the lyric line advance, unlock. Also lock with the daemon stopped: lock screen works, lyric label empty.
- [ ] **Step 5: Autostart:** read upstream `Configs/.local/share/hypr/lua/start_up.lua` and `variables.lua` (`hc.start.*` entries), add `Configs/.local/share/hypr/lua/start_up.encore.lua` holding the exact entry to merge upstream (`hyde-shell encore daemon --if-enabled`, run as a HyDE app service like `hyde_config`), and document in README how to add it to `~/.config/hypr/hyprland.lua` for local use.
- [ ] **Step 6: Validate schema fragments** parse with `python3 -c "import tomllib; tomllib.load(open(...,'rb'))"`.
- [ ] **Step 7: Update STATE.md** (shipped, measured idle numbers, local HyDE env file `~/.local/state/hyde/config` missing although `config-watcher` runs: investigate separately), bump `verified:` after checking docs against code, add up to 3 ideas.
- [ ] **Step 8: Commit** `feat: add Encore hyprlock layout and config schema`, then push.
