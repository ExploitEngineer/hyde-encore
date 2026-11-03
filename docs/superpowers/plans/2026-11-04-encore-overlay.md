# hyde-encore Plan 2: Lyrics overlay

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (owner's standing choice: inline execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hyde-shell encore overlay` shows the current lyric line floating above all windows, click-through, with a smooth left-to-right fill across each word as it is sung, the next line dimmed below, colored from the album; `hyde-shell encore toggle` shows and hides it.

**Architecture:** A separate GTK4 process (`encore.py overlay`) subscribes to the daemon's `encore.sock` and renders on a gtk4-layer-shell OVERLAY surface.
All timing and layout decisions live in pure, unit-tested `encorelib/lyricview.py`; the GTK code in `encoregui/overlay.py` only draws.
Each line is rasterised once into cached Cairo surfaces (dim and bright, shadow baked in); per frame the overlay paints the dim surface and the bright surface clipped to the sung region, so a frame costs two blits, not text layout.

**Tech Stack:** Python 3 (system), PyGObject (`Gtk` 4.0, `Gtk4LayerShell` 1.0, `Gio`, `GLib`), Pango/PangoCairo, pycairo, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-hyde-encore-design.md` (section 2, "Lyrics overlay"; quality bar).

## Global Constraints

- Everything from Plan 1's Global Constraints still holds (HyDE tree, system `python3`, `encorelib/` never imports `gi`, conventional commits without attribution, one sentence per Markdown line, no em dash).
- GTK code lives in `Configs/.local/lib/hyde/encoregui/` (mirrors HyDE's `pygui/`), never at the top of `lib/hyde/` where `hyde-shell` would list it as a command.
- Layer shell: layer OVERLAY, namespace `encore`, keyboard mode NONE, empty input region (click-through), never in window lists.
- `encore.sh` sets `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so` only for the `overlay` subcommand (gtk4-layer-shell must load before libwayland-client).
- The overlay process sets `GSK_RENDERER=cairo` before importing Gtk unless the user already set `GSK_RENDERER` (measured 2026-11-04 on the owner's laptop, steady 60 fps fill: cairo 6.8% of one core, vulkan 11.8%, gl 15.0%, ngl 15.5%, before the raster cache).
- Performance budget (spec quality bar): while a line is being sung, overlay under 5% of one core averaged over 10 s at 60 fps on the owner's laptop; while paused, between lines, hidden, or with no lyrics, no frame clock runs (0% CPU).
- Idle wake-ups: no polling timers; socket (re)connection waits on a `Gio.FileMonitor` of `$XDG_RUNTIME_DIR/hyde/`.
- Readability: text always has a baked-in dark shadow so it reads on light and dark windows.
- Colors: sung = `pick_accent(palette)` (Plan 1, contrast-safe), unsung = white at 40%, next line = white at 30%, unless configured.
- Spicy Lyrics community syncs must be credited: when `lyrics.credit` is set, show it small under the lines for the first 10 s of each track and whenever paused.

## Review Focus

1. Song with lyrics only for part of the track (long intro, outro, instrumental bridge): overlay must hide during gaps longer than 4 s, not freeze on a stale line.
2. Daemon restarts or starts after the overlay: overlay must reconnect by itself and show lyrics again within a second.
3. A long line wider than 80% of the screen: it must wrap onto two rows and the fill must follow the words across both rows.
4. Track change mid-line: old line must not flash with the new song's colors or keep animating.
5. Toggle pressed twice quickly, or overlay already running at login: never two overlays on screen.

Tests: 1 in Task 1, 2 in Task 2, 3 in Task 4 (word rects) plus Task 5 E2E, 4 in Task 1, 5 in Task 3.

## File Structure

```text
Configs/.local/lib/hyde/
  encore.sh                      + LD_PRELOAD for `overlay`
  encore.py                      + `overlay`, `toggle` subcommands; daemon spawns overlay if enabled
  encorelib/config.py            + overlay settings
  encorelib/lyricview.py         pure: live position, line choice, per-word fill, gaps, wake-up times
  encorelib/stream.py            pure: JSON-lines buffer decoder for socket clients
  encorelib/single.py            pure-ish: pidfile single-instance helpers for toggle
  encoregui/__init__.py
  encoregui/overlay.py           GTK4 layer-shell window, socket client, raster cache, drawing
Configs/.local/share/hyde/schema/{config,schema}.toml   + [encore.overlay]
docs/STATE.md, README.md, AGENTS.md
tests/test_lyricview.py, tests/test_stream.py, tests/test_single.py, tests/test_config.py (extended)
```

---

### Task 1: Pure lyric view model

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/lyricview.py`, `tests/test_lyricview.py`

**Interfaces:**
- Consumes: the Plan 1 state dict (`ts`, `status`, `position`, `rate`, `line`, `next`, `lyrics`, `track`, `palette`).
- Produces:
  - `GAP_HIDE_SECONDS = 4.0`, `FILL_FPS_HINT = 60`
  - `live_position(state: dict, now: float) -> float`: `position + (now - ts) * rate` when `status == "playing"`, else `position`.
  - `@dataclass(frozen=True) View(visible: bool, line_key: str, text: str, words: tuple[tuple[str, float], ...], next_text: str, animating: bool, wake_in: float | None)` where each word tuple is `(text, fill)` with `fill` in 0..1, `line_key` is `f"{track.key}:{line.index}"` (changes on every new line or track), `animating` is true while any word of the current line has `0 < fill < 1`, and `wake_in` is seconds until the next visual change when not animating (`None` when nothing will change without a new state).
  - `build_view(state: dict | None, now: float) -> View`.
- Rules the tests pin:
  - not visible when state is None, status is `stopped`, `lyrics` is null, `lyrics.sync == "none"`, or `line` is null;
  - not visible when the live position is more than `GAP_HIDE_SECONDS` past the last word's end of the current line and before the next line's start (Review Focus 1);
  - word fill = `clamp((pos - start) / (end - start), 0, 1)`, words already sung are 1, words not reached are 0;
  - paused: `animating` False and `wake_in` None even mid-word (frozen fill shown);
  - between words while playing: `animating` False, `wake_in` = next word start minus position, divided by rate;
  - `line_key` differs between the old and new track even at the same line index (Review Focus 4).

- [ ] **Step 1: Write failing tests** in `tests/test_lyricview.py` using small hand-made state dicts: `test_hidden_without_state_or_lyrics`, `test_live_position_playing_and_paused`, `test_fill_mid_word`, `test_sung_and_unsung_words`, `test_paused_mid_word_is_frozen`, `test_wake_in_between_words`, `test_hidden_in_long_gap_after_line`, `test_visible_in_short_gap`, `test_line_key_changes_with_track`, `test_rate_two_halves_wake_in`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_lyricview.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `lyricview.py`.
- [ ] **Step 4: Run** the tests. Expected: PASS. Full suite and ruff clean.
- [ ] **Step 5: Commit** `feat: add pure lyric view model for the overlay`.

### Task 2: Socket stream decoder and reconnect rules

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/stream.py`, `tests/test_stream.py`

**Interfaces:**
- Produces: `class LineDecoder` with `feed(data: bytes) -> list[dict]` (splits on `\n`, keeps a partial tail, skips lines that are not valid JSON objects, caps the tail at 1 MiB and drops it if exceeded) and `reset() -> None`.
- `should_connect(runtime_dir_event_path: str, socket_name: str = "encore.sock") -> bool`: true when a created/changed path's basename is the socket name (used by the overlay's file monitor).

- [ ] **Step 1: Write failing tests:** `test_split_across_chunks`, `test_multiple_lines_in_one_chunk`, `test_invalid_json_skipped`, `test_non_object_skipped`, `test_oversized_tail_dropped`, `test_reset_clears_partial`, `test_should_connect_on_socket_only` (Review Focus 2).
- [ ] **Step 2-4:** run FAIL, implement, run PASS.
- [ ] **Step 5: Commit** `feat: add JSON-lines stream decoder for socket clients`.

### Task 3: Overlay config and single-instance toggle helpers

**Files:**
- Modify: `encorelib/config.py`, `tests/test_config.py`
- Create: `encorelib/single.py`, `tests/test_single.py`

**Interfaces:**
- `EncoreConfig` gains: `overlay_enable: bool = False`, `overlay_position: str = "bottom"` (`top|center|bottom`, anything else falls back to bottom), `overlay_margin: int = 120`, `overlay_font: str = "JetBrainsMono Nerd Font"`, `overlay_size: int = 30`, `overlay_next_line: bool = True`, `overlay_color: str = ""`, `overlay_monitor: str = ""`.
  Env names follow HyDE: `ENCORE_OVERLAY_ENABLE`, `ENCORE_OVERLAY_POSITION`, `ENCORE_OVERLAY_MARGIN`, `ENCORE_OVERLAY_FONT`, `ENCORE_OVERLAY_SIZE`, `ENCORE_OVERLAY_NEXT_LINE`, `ENCORE_OVERLAY_COLOR`, `ENCORE_OVERLAY_MONITOR`; integers that do not parse fall back to defaults.
- `single.py`: `read_pid(path: Path) -> int | None` (missing, empty or garbage gives None), `pid_alive(pid: int) -> bool` (`os.kill(pid, 0)`, also checks `/proc/<pid>/cmdline` contains `encore` so a recycled pid is not mistaken), `claim(path: Path) -> bool` (atomically writes own pid with `O_CREAT|O_EXCL`; if the file exists but its pid is dead, replaces it; returns False when a live encore owns it), `release(path: Path) -> None` (removes only if it holds our pid).

- [ ] **Step 1: Write failing tests:** config defaults, every env name, bad int and bad position fallbacks; `test_claim_then_second_claim_fails`, `test_claim_replaces_dead_pid`, `test_release_only_own_pid`, `test_read_pid_garbage` (Review Focus 5).
- [ ] **Step 2-4:** run FAIL, implement, run PASS.
- [ ] **Step 5: Commit** `feat: add overlay settings and single-instance helpers`.

### Task 4: GTK overlay window

**Files:**
- Create: `Configs/.local/lib/hyde/encoregui/__init__.py`, `Configs/.local/lib/hyde/encoregui/overlay.py`
- Create: `encorelib/wordrects.py`, `tests/test_wordrects.py`

**Interfaces:**
- `wordrects.py` (pure): `word_byte_ranges(text: str, words: list[str]) -> list[tuple[int, int]]` maps each word to its UTF-8 byte span inside the line text, in order, tolerant of punctuation and repeated words (Pango index APIs take byte offsets). Tests: ASCII, repeated words, non-Latin (Japanese, Arabic), emoji.
- `encoregui/overlay.py`: `run_overlay(cfg: EncoreConfig) -> int`.
  - Window: `Gtk.Application` id `org.hyde.encore.overlay`, one `Gtk.ApplicationWindow` per run on `cfg.overlay_monitor` (empty: compositor's choice), layer-shell per Global Constraints, anchored per `overlay_position` with `overlay_margin`, width 80% of the monitor, transparent CSS background, `Gtk.DrawingArea` child.
  - Socket client: `Gio.SocketClient` to `encore.sock`, `LineDecoder` on reads; on EOF or error, disconnect and wait for the `Gio.FileMonitor` event (`should_connect`) to reconnect; also try once at startup.
  - Raster cache per `line_key` + size + colors: Pango layout with `set_width(80% px)`, `WRAP_WORD`, centered; render dim and bright `cairo.ImageSurface`s (ARGB32, device scale = monitor scale) with a shadow pass (black, alpha 0.55, offset 0,2, plus a 3 px stroke at alpha 0.30); word rectangles from `layout.index_to_pos` over `word_byte_ranges`, one rect list per word so wrapped words work.
  - Draw: paint dim surface; clip to the union of rects for words with fill 1 plus the partial rect (`x + width * fill`) of the active word; paint bright surface; next line (if enabled) from its own cached surface below; credit line rule from Global Constraints.
  - Frame scheduling: when `View.animating`, keep a tick callback that queues draws; when it stops, remove the tick and, if `wake_in` is set, add a one-shot `GLib.timeout_add` for that delay; on every new state, cancel the timeout and recompute. Hidden or paused: no tick, no timeout.
  - Line change: 200 ms cross-fade between old and new cached surfaces using the same tick mechanism.
  - Exit cleanly on SIGINT/SIGTERM via `GLibUnix.signal_add`, releasing the pidfile.
- `encore.py`: `overlay` subcommand (claims `$XDG_RUNTIME_DIR/hyde/encore-overlay.pid`, exits 0 if taken), `toggle` subcommand (if a live overlay holds the pidfile, SIGTERM it; else spawn `encore.sh overlay` detached with `start_new_session=True`). `daemon` spawns the overlay the same way at startup when `cfg.overlay_enable`.
- `encore.sh`: `if [ "$1" = overlay ]; then export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so${LD_PRELOAD:+:$LD_PRELOAD}"; fi`.

- [ ] **Step 1: Write failing `tests/test_wordrects.py`**, run FAIL, implement `wordrects.py`, run PASS.
- [ ] **Step 2: Implement** `encoregui/overlay.py` and the CLI wiring.
- [ ] **Step 3: Smoke run** with `tests/e2e/fake_mpris.py --art <colorful cover>` and the daemon: overlay appears bottom-center, click-through (a click on a window under the text reaches the window), `hyprctl layers` lists namespace `encore`.
- [ ] **Step 4: Commit** `feat: add GTK4 layer-shell lyrics overlay`.

### Task 5: End-to-end, performance, pixel check

**Files:**
- Create: `tests/e2e/measure_overlay.sh` (starts fake player + daemon + overlay, reports overlay CPU over 10 s playing mid-song, 10 s paused, 10 s in an instrumental gap)
- Modify: none unless fixing findings

- [ ] **Step 1: Performance:** run `tests/e2e/measure_overlay.sh`. Expected: playing under 5% of one core, paused 0 ticks, gap 0 ticks. If playing exceeds 5%, profile (`py-spy` if available, else `cProfile` on the draw function) and fix before continuing; never lower the frame rate without a ruling in the ledger.
- [ ] **Step 2: Pixel check** (ask the owner first; it draws on the live desktop): screenshot bursts with `grim -g` over the overlay region on a dark window and a light window, zoom before judging; check shadow legibility, no clipped descenders, wrap on a long line, credit line placement, cross-fade without flicker.
- [ ] **Step 3: Real Spotify** with the owner: one Spicy word-synced song and one LRCLIB line-synced song; overlay follows; `hyde-shell encore toggle` twice hides and shows; daemon restart is survived (Review Focus 2).
- [ ] **Step 4: Commit** fixes if any, `test: add overlay performance harness`.

### Task 6: Config schema, keybind, docs

**Files:**
- Modify: `Configs/.local/share/hyde/schema/config.toml`, `schema.toml` (add `[encore.overlay]` keys from Task 3 in upstream style), `README.md` (overlay usage, toggle, suggested bind), `docs/STATE.md`, `docs/DECISIONS.md` (#10 cairo renderer + raster cache, #11 overlay as separate process), `AGENTS.md`.
- Create: `Configs/.local/share/hypr/lua/key_binds.encore.lua` fragment: `hl.bind(MOD .. " + ALT + L", hl.dsp.exec_cmd("hyde-shell encore toggle"), {description = "[Utilities] toggle encore lyrics overlay"})` (free in upstream `key_binds.lua` and in the owner's binds as of 2026-11-04).

- [ ] **Step 1: Update** the fragments and docs; validate TOML with `tomllib` and Lua with `luac -p`.
- [ ] **Step 2: Add the bind locally** for the owner in `~/.config/hypr/keybindings.lua` only after asking (it is their config).
- [ ] **Step 3: Commit** `docs: document the lyrics overlay`, then whole-branch review, then push and PR.
