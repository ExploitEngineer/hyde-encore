# State

Goal: match, then beat, Verci (lyrics) and Lumn (glow, player), polished enough to show publicly; upstream PRs to HyDE after.
Quality pass runs one layer at a time: 0 docs, 1 engine, 2 daemon, 3 overlay, 4 glow, 5 player, 6 lock screen and HyDE integration, 7 review.

## Shipped (main, PRs #1-#8)
- Engine (`encorelib/`): LRC and enhanced LRC parser (syllable tags merge into words), CJK-aware word tokens, word-timing estimator calibrated on real word sync, gap-aware cursor, playback clock that keeps the rate across resyncs, config loader, providers (local `.lrc` always wins and is never cached, LRCLIB with junk-upload filter and up to three search variants for feat. credits, release qualifiers and browser "Artist - Title" videos, Spicy Lyrics syllable sync with a user key), versioned LRU lyrics cache (2000 tracks, errors never cached), album palette via `wallbash.sh`, JSON-lines protocol v1 (`lyrics.lines`, `line.text`, `gap` whenever no line is live).
- Daemon (`encore daemon`): follows the most recently started MPRIS player or `[encore] players` (a same-song switch updates the player), follows the player's MPRIS `Rate`, bounded latest-wins lyric and palette workers with stale results discarded, publishes `encore.sock` plus hyprlock line, track and cover files.
- Overlay (`encore toggle`, `encore style`): GTK4 layer-shell, click-through, styles `line` (karaoke strip), `stack` (rolling column, ghost trails, mixed fonts), `constellation` (word chain, hairlines, cluster fade), `visual` (full-bleed art layer, column with glyphs and a Highlight marker).
- Live look (`encore look`, runtime `encore.look`): style, font, size, Lyric Text / Highlight / Secondary colors, next line, motion.
- Glow (`encore glow`): one full-screen click-through window, 1/4-res texture scaled on the GPU, two comets circling, cava beat envelope or breathe fallback, 12.5 fps; look keys for gradient (1 or 2 colors), animation (music, breathe, static), thickness, intensity, override colors.
- Player window (`encore menu`, SUPER+ALT+M): art with tinted glow and hover-expand, transport, Lyrics pill with scrolling list, bottom toolbar, look menu, glow Settings popover.
- Profiles `working` and `show` (`encore profile`); `encore show` toggles the empty `encore` workspace.
- The overlay, glow and player start the daemon on demand when it is not answering (DECISIONS #20).
- hyprlock `Encore.conf`: art, title, artist, word-highlighted line.
- Upstream fragments: schema and config toml, `variables.encore.lua` (hc.start), `key_binds.encore.lua` (SUPER+ALT+{L,K,M,E}), `window_rules.encore.lua` (player floats).
- 283 tests, ruff clean, including 16 end-to-end tests of the daemon on a private bus (`tests/e2e/harness.py`, marker `e2e`); `tests/e2e/fake_mpris.py` scriptable MPRIS player with a writable `Rate`; `tests/tools/calibrate_timing.py` scores the estimator against cached word sync.

## Measured (this laptop, 2026-11-03/04)
- Daemon (isolated harness, `tests/e2e/measure.py`, 10 s phases): playing 0.60%, paused 0 ticks, playing with no lyric line 0.40% of one core.
- Overlay animating: line ~6%, stack 9%, visual 11% of a core; paused and hidden 0.
- Glow: 2.5% of a core at 20 fps, measured before the drop to 12.5 fps.
- Estimated word timing: mean word-start error 0.21 s against 11 real word-synced songs (was 0.43 s); see DECISIONS #19.
- LRCLIB: feat. titles, browser video titles and empty-artist lookups that found nothing now return synced lyrics (live check 2026-11-04).
- Caveat: the overlay and glow numbers came from the retired `measure_overlay.sh` or a scratchpad harness; re-measure with `measure.py --overlay` / `--glow` (they draw on the real screen, owner's OK first) before quoting them.

## Verified with the owner (2026-11-04)
- Real Spotify: follows Spotify over a stopped Brave tab; Spicy Lyrics word sync on "LEGACY (slowed down)" lights word by word in time.
- `Encore` hyprlock preview: real cover, title, artist, word-by-word line, readable colors.

## Unverified on screen
- Player lyrics list with a real synced song, art hover-expand, glow following the Settings popover live.
- Overlay click-through press test; a full-resolution pixel pass of each style against `.reference/`.
- Login autostart: the `hl.on("hyprland.start", ...)` hook from README sits in the owner's `~/.config/hypr/hyprland.lua` (2026-11-04); first proof is the next login.

## Broken or placebo
- Glow popover Display picker only posts a notification; nothing moves.
- Player bottom bar: the display button cycles the style and the lock button previews hyprlock; neither matches the reference.
- Polish, parity, setup and player branches shipped without an independent review.

## Not built
- Multi-monitor: overlay picks one output (`overlay.monitor`), glow takes the compositor's choice.
- Colors following the active HyDE theme (wallbash template for encore) and the opt-in `follow_album` full-theme recolor.
- Glow autostart; only the overlay has an `enable` key.

## Next
- Layer 3: overlay, one style at a time (line, stack, constellation, visual): pixel pass against `.reference/` frames, motion timing from the official videos, perf on `measure.py --overlay`.
- Layers 4-7 as listed above.

## Known facts
- HyDE bugs found (candidate small PRs): `hyprlock.sh find_filepath` uses `find -type f` without `-L`, so symlinked layouts fail to load and `Encore.conf` is installed as a copy; `hyprlock.sh fn_mpris` reads the first listed player, not the playing one.
- HyDE's `start_up.lua` runs only the `hc.start` keys it names, so `[desktop.start]` entries for add-ons never start (candidate small PR: iterate `hc.start`).
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

verified: 7ff9a3c 2026-11-04
