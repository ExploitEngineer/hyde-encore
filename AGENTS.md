# hyde-encore agent guide

## What this is
HyDE add-on: word-synced lyrics overlay (four styles), beat-reactive edge glow, player window, hyprlock lyrics layout, all colored from the album art.
Goal: match, then beat, the reference apps Verci and Lumn, then upstream PRs to HyDE-Project/HyDE, so everything must look like HyDE wrote it.

## Hard rules
- Mirror HyDE's tree: scripts in `Configs/.local/lib/hyde/`, hyprlock layouts in `Configs/.config/hypr/hyprlock/`, wallbash templates in `Configs/.config/hyde/wallbash/`.
- Follow HyDE conventions: Python via its `pyutils`, shell via `globalcontrol.sh`, invoked through `hyde-shell`. Read the matching upstream file before writing a new one.
- Prefer deps HyDE already ships (playerctl, cava, hyprlock, wallbash). A new dependency needs a DECISIONS.md entry.
- Read `CONTRIBUTING.md` and `COMMIT_MESSAGE_GUIDELINES.md` in the upstream clone before the first commit of feature code.
- License GPL-3.0. Code borrowed from MIT projects keeps its notice.
- Never send playerctl commands to the owner's real players (Spotify, browsers); drive `fake_mpris.py` with `-p encoretest`.
- Visual work is done only after a side-by-side, full-resolution comparison with `.reference/`.

## Paths
- Upstream reference clone (read-only, shallow): `~/Documents/dev/reference/HyDE`
- Reference apps (local, gitignored): `.reference/r1..r7.mp4` (Instagram reels), `.reference/site/` (official verci-hero.mp4, lumn-demo.mp4, verci-styles.png, verci-settings.png, full-res frames). Findings: `docs/superpowers/specs/2026-11-04-verci-parity.md`.
- Prior art: see `docs/PRODUCT.md`.

## Commands
- Tests: `python3 -m pytest -q`
- Lint: `uvx ruff check Configs tests` and `uvx ruff format --check Configs tests`
- Python runs on system `python3` (DECISIONS #8); `encorelib/` must not import `gi`.
- E2E: `python3 -m pytest -q` includes `tests/e2e/` (marker `e2e`, about 15 s): the daemon against fake players on a private bus and runtime dir (`tests/e2e/harness.py`); `-m "not e2e"` for the fast loop. Never touch the owner's session for tests.
- Visuals: `python3 tests/e2e/stage.py --style <line|stack|constellation|visual> [--glow] [--player lyrics] [--at 5.0,12.4]` renders the real surfaces on a hidden monitor and writes stills to `.stage/`; judge every visual change there, never on the owner's screen.
- Perf: `python3 tests/e2e/measure.py --lab [--overlay --style S] [--glow]` on the isolated harness and hidden monitor; only its numbers back perf claims. Budget: overlay ~6.5% of one core animating, 0 paused/hidden.
- Never `pkill -f`/`pgrep -f` with a pattern that also appears in the same shell command; it matches and kills that shell. Anchor patterns (`^python3 ...$`) or run from a script file.

## Architecture
- `Configs/.local/lib/hyde/encorelib/`: pure logic, unit-tested, no `gi`.
  Look: colors (album scheme), glowfield (glow geometry).
  Engine: model, lrc, words (CJK-aware tokens), timing, clock, providers, query (LRCLIB search variants), lookup, cache, palette, protocol, session, config, service (find or start the daemon).
  Daemon support: jobs (latest-wins workers), journal (lookup log).
  View logic: look (runtime look file), profiles, stream (socket decoding, style list), lyricview, wordrects, constellation, glyphs, single (pidfile lock).
- `Configs/.local/lib/hyde/encore.py`: GLib/Playerctl daemon and CLI; `encore.sh` is the hyde-shell entry (sets LD_PRELOAD for `overlay` and `glow`).
- `Configs/.local/lib/hyde/encoregui/`: GTK4 processes, each separate from the daemon: `overlay.py` (layer-shell lyrics drawn as GPU render nodes through `scene.py`, plus the visual-style art layer), `glow.py` (one full-screen edge-glow window), `player.py` (normal app window `org.hyde.encore.player` with the look menu and glow popover).
- Runtime dir `$XDG_RUNTIME_DIR/hyde/`: `encore.sock` (state), `encore.look` (live look and glow keys), pidfiles, hyprlock line, track and cover files.
- State protocol: JSON lines on `encore.sock`, schema in `docs/superpowers/plans/2026-11-03-encore-core.md`.
- Upstream fragments hold only encore's additions, to merge into HyDE's files: `Configs/.local/share/hyde/schema/*.toml` and `Configs/.local/share/hypr/lua/{variables,start_up,key_binds,window_rules}.encore.lua`.
