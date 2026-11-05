# hyde-encore agent guide

## What this is
HyDE add-on: the Encore app (Home, Lyrics, Stage window, Full screen), word-synced lyrics on the desktop (five styles), beat-reactive edge glow, hyprlock lyrics layout, all colored from the album art.
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
- E2E: `python3 -m pytest -q` includes `tests/e2e/` (marker `e2e`, about 20 s): the daemon against fake players on a private bus and runtime dir (`tests/e2e/harness.py`); `-m "not e2e"` for the fast loop. `python3 -m pytest -q -m lab tests/e2e/test_app.py` (opt-in) drives the window on the hidden monitor: launch, close to tray, Quit. Never touch the owner's session for tests.
- Visuals: `python3 tests/e2e/stage.py --style <line|stack|constellation|visual|code> [--glow] [--app home|lyrics|stage|full|settings|look] [--no-player|--no-lyrics|--stop-player|--long-lyrics] [--cover /abs.jpg] [--at 5.0,12.4] [--clip N] [--then full]` renders the real surfaces on a hidden monitor and writes stills (or a clip; `--then` switches page inside it) to `.stage/`; judge every visual change there, never on the owner's screen. The lab monitor gets a fresh name per run and aborts if it ever takes one of the owner's workspaces. `ENCORE_TRACE=/abs/file` makes the app append a timestamp per paint (entry timing).
- Demo: `python3 tests/e2e/showreel.py [--out .stage/showreel]` records the scripted demo take (Home, Stage, Full screen through every style; original cover and lyrics on a fake player) on the hidden monitor and cuts `clip.mp4` at the window's aspect.
- Perf: `python3 tests/e2e/measure.py --lab [--overlay --style S] [--glow] [--app home|lyrics|stage|full] [--look k=v]` on the isolated harness and hidden monitor; only its numbers back perf claims. Budget: overlay ~6.5% of one core animating, 0 paused/hidden; the window under 4% playing, 1.5% paused, 3% idle. Every full-window repaint costs 8-16 ms here, so frames are the cost (DECISIONS #36).
- Never `pkill -f`/`pgrep -f` with a pattern that also appears in the same shell command; it matches and kills that shell. Anchor patterns (`^python3 ...$`) or run from a script file.

## Architecture
- `Configs/.local/lib/hyde/encorelib/`: pure logic, unit-tested, no `gi`.
  Look: colors (album scheme, readable floors, gradient blob colors), typeface (the face of each word per style, nearest shipped weight), glowfield (glow geometry), motion (easing, damped spring, ghost trails, pops, blob drift, grain, held-word scale), depth (the Lyrics list's depth steps and scroll target).
  Engine: model, lrc, words (CJK-aware tokens), timing, clock, providers, query (LRCLIB search variants), lookup, cache, palette, protocol, session, config, service (find or start the daemon).
  Daemon support: jobs (latest-wins workers), journal (lookup log).
  View logic: look (live look file, persisted), profiles, stream (socket decoding, style list), lyricview (incl. the 120 ms lead), wordrects, constellation, glyphs, bytecache (byte-bounded texture LRU), single (pidfile lock).
  App logic: artwork (HD covers), transport (time, seek, volume, keys), coverfit (fill or frame a cover), screen (idle, waiting, no lyrics, plain, lyrics), lifecycle (close to tray or quit), lockscreen (hyprlock layout switch), dbusmenu (tray menu data), stageflag (the `encore.stage` flag, held while the show is in sight), codeview (the code style's rows).
- `Configs/.local/lib/hyde/encore.py`: GLib/Playerctl daemon and CLI (`app`, `toggle`, `glow`, `style`, `look`, `follow`, `lock`, `profile`, `status`, `lookups`); `encore.sh` is the hyde-shell entry (sets LD_PRELOAD for `overlay` and `glow`).
- `Configs/.local/lib/hyde/encoregui/`: GTK4, separate from the daemon. The app (`org.hyde.encore`, one process): `app.py` (unique application, window, actions, polling), `home.py` (Home and Lyrics pages), `lyriclist.py` (the Lyrics page's list with depth), `fullscreen.py` (the show: Full screen and the windowed Stage page, its entry, writes `encore.stage`), `glass.py` (frosted bars from the backdrop's cached blur), `field.py` (the album field: the window's light, the idle screen and Clear in Full screen), `popovers.py` (look menu, Settings), `cover.py` (GPU covers, the full-screen backdrop and its cached blur), `tray.py` (StatusNotifierItem), `ui.py` (CSS tokens, fonts, icons, trace). The desktop surfaces (own processes): `lyrics.py` (LyricsEngine, the shared renderer, GPU nodes through `scene.py`), `overlay.py` (click-through layer-shell host, hides under the Stage or Full screen), `glow.py` (one full-screen edge-glow window), `outputs.py` (pick their output).
- Runtime dir `$XDG_RUNTIME_DIR/hyde/`: `encore.sock` (state), `encore.look` (live look, glow and app keys; kept in `$XDG_STATE_HOME/hyde/encore.look`), `encore.follow` (pinned player), `encore.stage` (the Stage or Full screen is in sight on this output), pidfiles, hyprlock line, track and cover files. Every file there is written through `encorelib/files.py` and is a courtesy: a full tmpfs must never stop a surface or the socket (DECISIONS #38). Surface and command logs: `$XDG_CACHE_HOME/hyde/encore/logs/`.
- State protocol: JSON lines on `encore.sock`, schema in `docs/superpowers/plans/2026-11-03-encore-core.md`.
- Upstream fragments hold only encore's additions, to merge into HyDE's files: `Configs/.local/share/hyde/schema/*.toml` and `Configs/.local/share/hypr/lua/{variables,start_up,key_binds,window_rules}.encore.lua`; the launcher entry and icon are `Configs/.local/share/applications/org.hyde.encore.desktop` and `icons/hicolor/scalable/apps/org.hyde.encore.svg`.
