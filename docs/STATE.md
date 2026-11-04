# State

Goal: match, then beat, Verci (lyrics) and Lumn (glow, player), polished enough to show publicly; upstream PRs to HyDE after.
Quality pass runs one layer at a time: 0 docs, 1 engine, 2 daemon, 3 overlay, 4 glow, 5 player, 6 lock screen and HyDE integration, 7 review.

## Shipped (main, PRs #1-#12, plus branch layer3-visual)
- Engine (`encorelib/`): LRC and enhanced LRC parser (syllable tags merge into words), CJK-aware word tokens, word-timing estimator calibrated on real word sync, gap-aware cursor, playback clock that keeps the rate across resyncs, config loader, providers (local `.lrc` always wins and is never cached, LRCLIB with junk-upload filter and up to three search variants for feat. credits, release qualifiers and browser "Artist - Title" videos, Spicy Lyrics syllable sync with a user key), versioned LRU lyrics cache (2000 tracks, errors never cached), album palette via `wallbash.sh`, JSON-lines protocol v1 (`lyrics.lines`, `line.text`, `gap` whenever no line is live).
- Daemon (`encore daemon`): follows the most recently started MPRIS player or `[encore] players` (a same-song switch updates the player), follows the player's MPRIS `Rate`, bounded latest-wins lyric and palette workers with stale results discarded, publishes `encore.sock` plus hyprlock line, track and cover files.
- Overlay (`encore toggle`, `encore style`): GTK4 layer-shell, click-through, pinned with its art layer to `overlay.monitor`; styles `line` (screen-scaled type, soft shadow, accent bloom, tinted next line), `stack` (rolling column, ghost trails, mixed fonts), `constellation` (centered word chain scaled to the screen, accent hairlines and sparkles), `visual` (art dimmed, accent-washed, pooled and vignetted under a column with glyphs and a Highlight block).
- One album color scheme (`encorelib/colors.py`) for overlay, glow, player and lock screen: the cover's first colorful wallbash family, else the HyDE theme's wallpaper palette, else a curated violet; block text by contrast.
- Live look (`encore look`, runtime `encore.look`): style, font, size, Lyric Text / Highlight / Secondary colors, next line, motion.
- Glow (`encore glow`, `[encore.glow] monitor`): one full-screen click-through window, 1/4-res texture scaled on the GPU, two comets circling over a soft light-like falloff (`encorelib/glowfield.py`), cava beat envelope or breathe fallback, 12.5 fps; look keys for gradient, animation, thickness, intensity, override colors. Before layer 3 every paint crashed (undefined helpers), so it never drew.
- Player window (`encore menu`, SUPER+ALT+M): art with an album-tinted halo and hover-expand, transport, Lyrics pill with scrolling list, bottom toolbar, look menu, glow Settings popover; its accents follow the scheme.
- Profiles `working` and `show` (`encore profile`); `encore show` toggles the empty `encore` workspace.
- The overlay, glow and player start the daemon on demand when it is not answering (DECISIONS #20).
- hyprlock `Encore.conf`: art, title, artist, word-highlighted line.
- Upstream fragments: schema and config toml, `variables.encore.lua` (hc.start), `key_binds.encore.lua` (SUPER+ALT+{L,K,M,E}), `window_rules.encore.lua` (player floats).
- 301 tests, ruff clean, including 18 end-to-end tests of the daemon on a private bus (`tests/e2e/harness.py`, marker `e2e`); `tests/e2e/fake_mpris.py` scriptable MPRIS player with a writable `Rate`; `tests/tools/calibrate_timing.py` scores the estimator against cached word sync.
- `tests/e2e/stage.py`: renders the real overlay, glow and player on a hidden Hyprland monitor (`encore-lab`) and saves stills and clips; `measure.py --lab` measures them there.

## Measured (this laptop, 2026-11-03/04)
- Daemon (isolated harness, `tests/e2e/measure.py`, 10 s phases): playing 0.60%, paused 0 ticks, playing with no lyric line 0.40% of one core.
- Overlay playing (hidden stage, `measure.py --lab --overlay`, dense test lyrics: a word every 0.3-0.5 s): line 7.6-9.1%, stack ~16%, constellation ~9%, visual ~19% of a core; paused and no lyric line under 1%. Pre-layer-3 code on the same content: line 5.9%, stack 15.4%, visual 18.9%.
- Glow (hidden stage): playing 6.1-7.5%, paused 0.25% of a core.
- Estimated word timing: mean word-start error 0.21 s against 11 real word-synced songs (was 0.43 s); see DECISIONS #19.
- LRCLIB: feat. titles, browser video titles and empty-artist lookups that found nothing now return synced lyrics (live check 2026-11-04).

## Verified with the owner (2026-11-04)
- Real Spotify: follows Spotify over a stopped Brave tab; Spicy Lyrics word sync on "LEGACY (slowed down)" lights word by word in time.
- `Encore` hyprlock preview: real cover, title, artist, word-by-word line, readable colors.

## Unverified on screen
- Player lyrics list with a real synced song, art hover-expand, glow following the Settings popover live.
- Overlay click-through press test; every style checked on the hidden stage with test lyrics, not yet with a real song on the owner's screen.
- Login autostart: the `hl.on("hyprland.start", ...)` hook from README sits in the owner's `~/.config/hypr/hyprland.lua` (2026-11-04); first proof is the next login.

## Broken or placebo
- Glow popover Display picker only posts a notification; nothing moves.
- Player bottom bar: the display button cycles the style and the lock button previews hyprlock; neither matches the reference.
- Polish, parity, setup and player branches shipped without an independent review.
- Perf over the ~6.5% overlay budget on dense lyrics: stack, visual and constellation (CPU rescaling of big type on slide frames, DECISIONS #27), line slightly over; glow over the 5% design target. Measure only on a quiet machine.

## Not built
- Multi-monitor: overlay and glow each pin to one output (`overlay.monitor`, `glow.monitor`); no per-monitor copies yet.
- Grey covers already follow the HyDE theme's palette; a wallbash template for encore and the opt-in `follow_album` full-theme recolor are not built.
- Glow autostart; only the overlay has an `enable` key.

## Next
- Overlay perf: move drawing to snapshot texture nodes so the renderer scales words on the GPU (DECISIONS #27), then re-measure on a quiet machine.
- Motion timing against the official videos (clips via `stage.py --clip`), player bottom-bar behaviour, multi-monitor copies, lock screen, independent review.

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

verified: e99465e 2026-11-04
