# State

Goal: match, then beat, Verci (lyrics) and Lumn (glow, player), polished enough to show publicly; upstream PRs to HyDE after.
Quality pass runs one layer at a time: 0 docs, 1 engine, 2 daemon, 3 overlay, 4 glow, 5 player, 6 lock screen and HyDE integration, 7 review.

## Shipped (main, PRs #1-#8)
- Engine (`encorelib/`): LRC and enhanced LRC parser (syllable tags merge into words), CJK-aware word tokens, word-timing estimator calibrated on real word sync, gap-aware cursor, playback clock that keeps the rate across resyncs, config loader, providers (local `.lrc` always wins and is never cached, LRCLIB with junk-upload filter and up to three search variants for feat. credits, release qualifiers and browser "Artist - Title" videos, Spicy Lyrics syllable sync with a user key), versioned LRU lyrics cache (2000 tracks, errors never cached), album palette via `wallbash.sh`, JSON-lines protocol v1 (`lyrics.lines`, `line.text`, `gap` whenever no line is live).
- Daemon (`encore daemon`): follows the most recently started MPRIS player or `[encore] players`, worker-thread fetches guarded against stale results, publishes `encore.sock` plus hyprlock line, track and cover files.
- Overlay (`encore toggle`, `encore style`): GTK4 layer-shell, click-through, styles `line` (karaoke strip), `stack` (rolling column, ghost trails, mixed fonts), `constellation` (word chain, hairlines, cluster fade), `visual` (full-bleed art layer, column with glyphs and a Highlight marker).
- Live look (`encore look`, runtime `encore.look`): style, font, size, Lyric Text / Highlight / Secondary colors, next line, motion.
- Glow (`encore glow`): one full-screen click-through window, 1/4-res texture scaled on the GPU, two comets circling, cava beat envelope or breathe fallback, 12.5 fps; look keys for gradient (1 or 2 colors), animation (music, breathe, static), thickness, intensity, override colors.
- Player window (`encore menu`, SUPER+ALT+M): art with tinted glow and hover-expand, transport, Lyrics pill with scrolling list, bottom toolbar, look menu, glow Settings popover.
- Profiles `working` and `show` (`encore profile`); `encore show` toggles the empty `encore` workspace.
- hyprlock `Encore.conf`: art, title, artist, word-highlighted line.
- Upstream fragments: schema and config toml, `variables.encore.lua` (hc.start), `key_binds.encore.lua` (SUPER+ALT+{L,K,M,E}), `window_rules.encore.lua` (player floats).
- 254 unit tests, ruff clean; `tests/e2e/fake_mpris.py` scriptable MPRIS player; `tests/tools/calibrate_timing.py` scores the estimator against cached word sync.

## Measured (this laptop, 2026-11-03/04)
- Daemon: playing ~0.4% of a core, ~40 MB RSS; paused 0 ticks over 10 s.
- Overlay animating: line ~6%, stack 9%, visual 11% of a core; paused and hidden 0.
- Glow: 2.5% of a core at 20 fps, measured before the drop to 12.5 fps.
- Estimated word timing: mean word-start error 0.21 s against 11 real word-synced songs (was 0.43 s); see DECISIONS #19.
- LRCLIB: feat. titles, browser video titles and empty-artist lookups that found nothing now return synced lyrics (live check 2026-11-04).
- Caveat: numbers came from `measure_overlay.sh` on the live runtime dir or a scratchpad harness that no longer exists; re-measure on the isolated harness (layer 2) before quoting them.

## Verified with the owner (2026-11-04)
- Real Spotify: follows Spotify over a stopped Brave tab; Spicy Lyrics word sync on "LEGACY (slowed down)" lights word by word in time.
- `Encore` hyprlock preview: real cover, title, artist, word-by-word line, readable colors.

## Unverified on screen
- Player lyrics list with a real synced song, art hover-expand, glow following the Settings popover live.
- Overlay click-through press test; a full-resolution pixel pass of each style against `.reference/`.

## Broken or placebo
- Glow popover Display picker only posts a notification; nothing moves.
- Player bottom bar: the display button cycles the style and the lock button previews hyprlock; neither matches the reference.
- `tests/e2e/measure_overlay.sh` runs the installed copy on the live runtime dir, so it can collide with a running session.
- Polish, parity, setup and player branches shipped without an independent review.

## Known gaps (daemon)
- The daemon never reads MPRIS `Rate`, so the clock stays at 1.0 (the clock side is ready).
- Fast skipping spawns one fetch and one palette thread per track (results are discarded safely).
- No automated test of the GLib daemon class.

## Not built
- Multi-monitor: overlay picks one output (`overlay.monitor`), glow takes the compositor's choice.
- Colors following the active HyDE theme (wallbash template for encore) and the opt-in `follow_album` full-theme recolor.
- Glow autostart; only the overlay has an `enable` key.

## Next
- Layer 2: bounded fetch pool, real playback rate, isolated harness in `tests/e2e/` (private `dbus-run-session` bus plus a short private runtime dir under `/run/user/$UID`, since AF_UNIX paths cap at 108 bytes), pytest E2E of the daemon against `fake_mpris.py`.
- Layers 3-7 as listed above.

## Known facts
- HyDE bugs found (candidate small PRs): `hyprlock.sh find_filepath` uses `find -type f` without `-L`, so symlinked layouts fail to load and `Encore.conf` is installed as a copy; `hyprlock.sh fn_mpris` reads the first listed player, not the playing one.
- Owner's Spicy Lyrics key lives in `~/.config/hyde/config.toml` (mode 600, not tracked by dotfiles).
- HyDE writes `~/.local/state/hyde/config` only once config.toml holds a setting beyond `$schema`. Not a HyDE bug.
- LRCLIB `/api/get` can return junk uploads (single `probe` line); synced results under 4 timed lines are rejected and search runs instead.
- Auto-lyrics spike (vocal separation + Whisper) parked; venv and recording in `~/.cache/hyde/encore/autosync/`.

## Open questions
- Final name (working name: hyde-encore).

## Ideas
- Re-survey LRCLIB `hasWordSync`; once word-synced entries are common, parse `lyricsfile` (DECISIONS #18).
- `hyde-shell encore lrc` saves the current lyrics as a local `.lrc` for offline use and hand-tuning.
- Waybar module showing the current lyric line from `encore.sock`.

verified: 52300f8 2026-11-04
