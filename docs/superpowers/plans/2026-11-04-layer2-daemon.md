# Layer 2: Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GLib daemon (`encore.py`) provably right under real use: bounded work when skipping fast, the player's real playback rate, and an automated end-to-end test suite that runs it against fake MPRIS players on a private bus.

**Architecture:** A reusable isolated harness (`tests/e2e/harness.py`) starts a private `dbus-daemon`, a short private runtime dir under `/run/user/$UID`, private cache/state dirs, fake players and the repo's daemon as subprocesses; pytest drives it with `playerctl` and reads `encore.sock` through `encorelib.protocol.read_state`, so the test process never imports `gi`.
Fetch threads go through a small latest-wins job runner in `encorelib/jobs.py`; the rate comes from a `Gio.DBusProxy` on the MPRIS Player interface, since Playerctl does not expose `Rate`.

**Tech Stack:** Python 3 stdlib, PyGObject (daemon only), dbus-daemon, playerctl, pytest.

**Spec:** owner brief, layer 2 ("bounded worker pool for fast skips, real playback rate, and an automated pytest E2E of the GLib daemon against fake_mpris.py"; "rebuild the isolated harness in tests/e2e/ and use it for every perf claim"); `docs/STATE.md` Known gaps (daemon) and Broken (`measure_overlay.sh`).

## Findings that shape this plan

- `Playerctl.Player` has no rate property (checked: can-*, loop-status, metadata, playback-status, player-instance, player-name, position, shuffle, source, status, volume).
- `fake_mpris.py` reports `Rate` as a constant 1.0, read-only, and its position ignores rate.
- The daemon starts one `threading.Thread` per track for lyrics and one for the palette; results are gated by `FetchGate`, but nothing bounds the threads, and a stale lookup can hold the network for up to ~20 s (three LRCLIB searches and Spicy at 5 s each).
- A private runtime dir must stay short: AF_UNIX socket paths cap at 108 bytes (the scratchpad path failed).
- `dbus-daemon`, `dbus-run-session`, `busctl`, `gdbus` and `playerctl` are installed.

## Global Constraints

- `encorelib/` stays stdlib only, no `gi`; `jobs.py` uses `threading` only.
- E2E tests never touch the owner's session: private bus, private runtime/cache/state dirs; they never start GUI processes (overlay, glow, player).
- Tests that need `dbus-daemon`, `playerctl` or PyGObject skip with a clear reason when missing; they carry the `e2e` marker and run in the default `python3 -m pytest -q`.
- Waiting in tests is condition-based with a deadline (poll state until a predicate holds), never a bare sleep.
- Ruff clean, conventional commits without attribution, Markdown one sentence per line, no em dash.
- Branch `layer2-daemon` from `main`; the first commit adds this plan and bumps STATE `verified:` (the layer 1 follow-up missed it).

## Review Focus

- A fake player that vanishes mid-fetch, or the daemon starting before any player exists; expect "stopped" then a clean follow once a player appears (test in Task 2).
- Skipping 6 tracks in under a second with slow work queued; expect the final track's lyrics and art, never an older track's (tests in Tasks 3 and 4).
- A player that reports `Rate` 0, negative or missing; expect rate 1.0 and no crash (test in Task 5).
- Harness teardown after a failing test; expect no leftover dbus-daemon, daemon or fake processes and no files left in `/run/user/$UID` (test in Task 1).
- Two daemons on one private bus (second start); expect "already running" and exit 0, first keeps serving (test in Task 2).

---

### Task 1: Isolated harness

**Files:**
- Create: `tests/e2e/harness.py`, `tests/e2e/conftest.py`, `tests/e2e/test_harness.py`
- Modify: `pyproject.toml` (register the `e2e` marker)

**Interfaces:**
- Produces:
  - `Harness(tmp_path: Path)`, a context manager. `__enter__` starts `dbus-daemon --session --nofork --print-address=1` and reads the address, makes `run = mkdtemp(prefix="enc-", dir=f"/run/user/{uid}")`, sets `env` with `DBUS_SESSION_BUS_ADDRESS`, `XDG_RUNTIME_DIR=run`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`, `ENCORE_LYRICS_DIRS` under `tmp_path`. `__exit__` terminates every child (SIGTERM, then SIGKILL after 3 s), stops the bus, removes `run`.
  - `h.start_player(name="encoretest", art="") -> subprocess.Popen` (fake_mpris), `h.start_daemon() -> subprocess.Popen` (repo `encore.py daemon`), `h.ctl(name, *args) -> str` (`playerctl -p name ...` in `h.env`), `h.state() -> dict | None` (`read_state(run/hyde/encore.sock)`), `h.wait(predicate, timeout=5.0) -> dict` (polls `state()` every 50 ms, raises `AssertionError` with the last state on timeout), `h.write_lrc(artist, title, text)`, `h.socket: Path`.
  - Fixture `harness` in `tests/e2e/conftest.py`, skipping when `dbus-daemon`, `playerctl` or `gi` with `Playerctl 2.0` are missing.

- [ ] **Step 1: Write failing tests** in `tests/e2e/test_harness.py`: `test_harness_is_private` (socket path under `/run/user/<uid>/enc-`, not the real `$XDG_RUNTIME_DIR/hyde`; env bus address differs from the parent's); `test_harness_cleans_up` (after exit: no child alive (`poll()` not None), run dir gone); `test_daemon_reports_stopped_without_players` (`h.wait(lambda s: s["status"] == "stopped")`).
- [ ] **Step 2: Run** `python3 -m pytest tests/e2e/test_harness.py -q`; expected FAIL (no harness module).
- [ ] **Step 3: Implement `harness.py`, the fixture and the marker.**
- [ ] **Step 4: Run** the same command; expected PASS, and `ls /run/user/$UID | grep enc-` empty afterwards.
- [ ] **Step 5: Commit** `test: add an isolated end-to-end harness for the daemon`.

### Task 2: Daemon end-to-end behaviour

**Files:**
- Create: `tests/e2e/test_daemon.py`
- Modify: `tests/e2e/fake_mpris.py` (`--title/--artist` override for a second distinct player)

**Interfaces:**
- Consumes: `Harness` (Task 1).

- [ ] **Step 1: Write the tests** (they pin current behaviour; any that fail are bugs, fixed under systematic-debugging before going on):
  `test_follows_player_and_local_lyrics` (synthetic `.lrc` for track 1; after `play`, state has the title, `lyrics.source == "local"`);
  `test_seek_lands_on_line` (`position 12` while paused gives `line.index` of the line at 12 s);
  `test_pause_freezes_position` (two states 0.5 s apart while paused share `position`);
  `test_gap_released_after_hold` (synthetic lrc with a 30 s break; at last word + 4.5 s `line is None` and `gap.until` is the next start);
  `test_handover_to_newer_player` (second fake `--name other` starts playing; `player == "other"`);
  `test_player_vanishes` (kill the fake; state goes `stopped`; a new fake is followed);
  `test_second_daemon_exits` (second `start_daemon()` exits 0 within 3 s, first still answers);
  `test_shutdown_removes_runtime_files` (SIGINT the daemon; `encore.sock`, `encore.hyprlock`, `encore.track` gone).
- [ ] **Step 2: Run** `python3 -m pytest tests/e2e/test_daemon.py -q`; expected PASS; a failure is a daemon bug: reproduce, fix with a unit test where the logic is pure, ledger it.
- [ ] **Step 3: Commit** `test: cover the daemon end to end on a private bus`.

### Task 3: Latest-wins job runner

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/jobs.py`, `tests/test_jobs.py`

**Interfaces:**
- Produces: `LatestJobs(workers: int = 2)`; `submit(fn: Callable[[], None]) -> None` queues `fn`, replacing any queued job that has not started; at most `workers` jobs run at once, on daemon threads; `idle() -> bool`; `running() -> int`.

- [ ] **Step 1: Write failing tests:** `test_runs_a_job`; `test_queued_job_is_replaced` (2 workers blocked on an `Event`, submit A then B: after release only B runs, A never starts); `test_never_exceeds_workers` (submit 10 blocking jobs: `running() <= 2` throughout, and exactly the first two plus the last run); `test_job_exception_does_not_kill_worker` (a raising job, then a normal one still runs).
- [ ] **Step 2: Run** `python3 -m pytest tests/test_jobs.py -q`; expected FAIL (module missing).
- [ ] **Step 3: Implement** with one `threading.Condition`, a single pending slot and a running counter; workers are started on demand and exit when nothing is pending.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat: add a latest-wins job runner for daemon fetches`.

### Task 4: Daemon uses bounded jobs

**Files:**
- Modify: `Configs/.local/lib/hyde/encore.py` (`refresh_track`, `start_palette`)
- Test: `tests/e2e/test_daemon.py`

**Interfaces:**
- Consumes: `LatestJobs` (Task 3); `FetchGate` stays as the result guard.
- Produces: `Encore.lyrics_jobs = LatestJobs(2)`, `Encore.palette_jobs = LatestJobs(1)`.

- [ ] **Step 1: Write failing test** `test_fast_skips_end_on_last_track`: six `next` calls within 0.6 s with `.lrc` files for both fake tracks and a cover; the final state names the last track with its own lyrics and art, and `/proc/<daemon>/status` `Threads:` never exceeds the idle count + 3 while sampling every 50 ms.
- [ ] **Step 2: Run** it; expected FAIL on the thread bound.
- [ ] **Step 3: Implement**: replace both `threading.Thread(...).start()` calls with `submit`.
- [ ] **Step 4: Run** `python3 -m pytest -q`; expected PASS.
- [ ] **Step 5: Commit** `feat: bound lyric and palette work when skipping tracks`.

### Task 5: Real playback rate

**Files:**
- Modify: `tests/e2e/fake_mpris.py` (`Rate` readwrite, set via `Properties.Set`, emits `PropertiesChanged`; position advances at the rate)
- Modify: `Configs/.local/lib/hyde/encore.py` (rate proxy per followed player)
- Test: `tests/e2e/test_daemon.py`

**Interfaces:**
- Consumes: `clean_rate`, `PlaybackClock.sync(position, playing, rate)` (layer 1).
- Produces: `Encore.rate_proxy`: a `Gio.DBusProxy` for `org.mpris.MediaPlayer2.<player_instance>`, `/org/mpris/MediaPlayer2`, `org.mpris.MediaPlayer2.Player`, recreated in `choose_player` when the followed player changes; `refresh_playback` passes `clean_rate(proxy.get_cached_property("Rate"))`; `g-properties-changed` with `Rate` resyncs and publishes.

- [ ] **Step 1: Write failing tests:** `test_rate_is_followed` (`gdbus call ... org.freedesktop.DBus.Properties.Set ... Rate <1.5>`; state `rate == 1.5`; position advances about 1.5 s per second within 10%); `test_bad_rate_falls_back` (set `Rate` 0.0, state `rate == 1.0`).
- [ ] **Step 2: Run**; expected FAIL (rate stays 1.0).
- [ ] **Step 3: Implement** the fake's writable rate, then the daemon proxy.
- [ ] **Step 4: Run** `python3 -m pytest -q`; expected PASS.
- [ ] **Step 5: Commit** `feat: follow the player's playback rate`.

### Task 6: Perf harness replaces measure_overlay.sh

**Files:**
- Create: `tests/e2e/measure.py`
- Delete: `tests/e2e/measure_overlay.sh`

**Interfaces:**
- Consumes: `Harness`.
- Produces: `python3 tests/e2e/measure.py [--seconds N] [--overlay] [--glow]`: daemon CPU (ticks from `/proc/<pid>/stat`) playing, paused, idle; with `--overlay`/`--glow` the GUI process too (these draw on the real screen, so they run only when the owner agrees).

- [ ] **Step 1: Run** `python3 tests/e2e/measure.py --seconds 10` (daemon only).
  Expected: playing under 1% of a core, paused 0 ticks, real runtime dir untouched.
- [ ] **Step 2: Commit** `test: measure daemon cost on the isolated harness`.

### Task 7: Docs

- [ ] **Step 1: DECISIONS** #21 latest-wins job runner (bounded, why not a ThreadPoolExecutor: queued stale jobs would still run), #22 rate via a D-Bus proxy (Playerctl lacks it), #23 isolated E2E harness (private bus, short runtime dir).
- [ ] **Step 2: STATE**: fixed daemon gaps out, new measured daemon numbers with the harness named, `measure_overlay.sh` out of Broken, overlay/glow perf re-measure listed as needing the owner's OK; bump `verified:`.
- [ ] **Step 3: AGENTS** Commands: E2E is `python3 -m pytest -q` (or `-m "not e2e"` for the fast loop); perf is `python3 tests/e2e/measure.py`.
- [ ] **Step 4: Verify** `python3 -m pytest -q`, both ruff commands; commit `docs: record layer 2 daemon results`.
