# State

Goal: match, then beat, Verci (lyrics) and Lumn (glow, player), polished enough to show publicly; upstream PRs to HyDE after.
Current shape: Encore is an app (DECISIONS #29); the next project is lyric animation polish on top of it.

## Shipped (main through PR #17, plus branch feat/encore-app)
- The Encore app (`org.hyde.encore`, launcher entry and icon, one window): Home (HD cover with hover halo, title, artist, seek bar, back 15 s / previous / play / next / forward 15 s, volume when the player has one, a chip to pick the player it follows), Lyrics page (synced lines, click a line to seek; "Looking for lyrics", "No synced lyrics found", plain lyrics as a list), Full screen (any style over the cover or clear black; top bar Exit / style / background / glow / look and bottom bar cover / song / seek / transport / volume fade in on mouse motion and out after 3 s; Esc, Exit and the compositor dropping fullscreen return to Home; the desktop overlay on that output hides meanwhile). Idle: drifting album-colored light with buttons for the music apps installed. Keys: Space, Left/Right, Up/Down, N/P, L, F, Esc, Ctrl+Q. Launching again raises the window; `encore app --open home|lyrics|full|look|settings`.
- Closing the window keeps Encore in the tray (StatusNotifierItem: Open, Play/Pause, Next, Desktop lyrics, Glow, Quit) while desktop lyrics or glow run; otherwise it quits. Quit stops the overlay and glow; the engine stays for the lock screen.
- Settings: glow (gradient, animation, thickness, glow, override colors, display), lock screen lyrics with Preview (`encore lock on|off|preview|status`, restores the previous hyprlock layout), HD covers, start at login, which players to follow, Quit. The look and these settings persist in `$XDG_STATE_HOME/hyde/encore.look` (DECISIONS #32).
- HD covers (DECISIONS #30): Spotify's 1500 px CDN size always; Apple's catalog (2000 px) for other players with a strict artist and album (or song) match, on by default; `track.cover` beside the 512 px `track.art`.
- Engine (`encorelib/`): LRC and enhanced LRC, CJK-aware word tokens, calibrated word-timing estimator, gap-aware cursor, playback clock, providers (local `.lrc`, LRCLIB with search variants, Spicy Lyrics word sync), LRU lyrics cache, album palette, protocol v1 with `players`, `volume`, `lookup` (pending or done) and `track.cover` added.
- Daemon: follows the most recently started player or a pin (`encore follow <player|auto>`), honors the app's player list and HD switch live, publishes `encore.sock`, hyprlock line, track and cover files; `--if-enabled` honors the app's start-at-login switch and brings back desktop lyrics and glow that were on.
- One lyric renderer (`encoregui/lyrics.py`, DECISIONS #31) for the desktop overlay (click-through, never a full-screen cover) and Full screen; styles line, stack, constellation, visual; frames are GPU render nodes.
- One album color scheme for every surface; glow (one full-screen window, cava beat envelope); hyprlock `Encore.conf`.
- 410 tests (unit and e2e on a private bus) plus 5 opt-in lab tests (`-m lab`) that drive the window on the hidden monitor; ruff clean. `tests/e2e/stage.py` renders every surface and app page on the hidden monitor; `measure.py` measures them.

## Measured (this laptop, 2026-11-04, hidden stage, `measure.py --lab`)
- Window: playing 3%, paused 1.4%, idle 2-3% of a core (8 fps idle field); entering idle costs a one-off ~0.6 s of CPU (full-window crossfades).
- Full screen playing: line 12%, stack 19%, constellation 4%, visual 24.5%; paused 0.5-1.6%. About 2-5 points over the overlay-only numbers: the whole window repaints per engine frame (the cover texture itself costs ~1 point).
- Desktop overlay playing (dense lyrics): line 9-10%, stack 17%; paused and hidden under 1%. Daemon playing ~1%.
- Glow playing 6-7.5%, paused 0.25%.

## Verified with the owner
- 2026-11-04 (before the app): real Spotify, Spicy Lyrics word sync, the `Encore` hyprlock preview.

## Unverified on screen
- The app end to end on the owner's screen: launcher, Spotify, full screen, close to tray, tray in waybar, lock switch. Every page is verified on the hidden monitor only.
- Covers from Apple on a real browser track; HD Spotify covers in Home (lab used a 1500 px file).

## Broken or placebo
- Perf over budget while Full screen plays (above); the remaining cost is the per-frame pipeline (DECISIONS #28), which needs a native profiler.
- GTK 4.24 logs harmless "GtkImage reported baselines" warnings when Settings opens (GtkDropDown internals).

## Not built
- Multi-monitor copies of the overlay and glow; a second monitor's Full screen hides only that output's overlay.
- Wallbash template for encore and the opt-in `follow_album` full-theme recolor.
- The standalone (non-HyDE) app; built so it stays possible.

## Next
- Owner's verdict on the branch (2026-11-05): a base, not the final product; "we have to improve a lot of things". The next project is the look-and-feel pass on Home and Full screen (spacing, type, the bars' glass look, the idle light) and then lyric animation polish (timing against the official videos, emoji and glyphs beside words, lyric typefaces). Start it in a fresh session with a brainstorm from the owner's own list of what is off.
- Owner check on the real screen is still pending (launcher, Spotify, full screen, tray in waybar, lock preview).
- Per-frame pipeline cut with a native profiler (owner's OK to install perf or sysprof).
- Upstream: Discussion, then small PRs (hyprlock.sh symlink and player fixes, start_up.lua hc.start iteration, encore).

## Known facts
- HyDE bugs found (candidate small PRs): `hyprlock.sh find_filepath` does not follow symlinked layouts; `hyprlock.sh fn_mpris` reads the first listed player; `start_up.lua` runs only the `hc.start` keys it names.
- Hyprland 0.56 moves a workspace back to the monitor it was last on, so a reused headless monitor name pulls one of the owner's workspaces onto it; `stage.py` names its lab monitor per run and refuses to run if that happens. Its Lua `window.close` dispatcher accepted a selector without closing the window; the lab tests use the app's `close` GTK action instead.
- PyGObject: `Gsk.RoundedRect().init_from_rect()` does not return the initialized struct (DECISIONS #34).
- Owner's Spicy Lyrics key lives in `~/.config/hyde/config.toml` (mode 600, not tracked).
- LRCLIB `/api/get` can return junk uploads; synced results under 4 timed lines are rejected and search runs instead.

## Open questions
- Final name (working name: hyde-encore).

## Ideas
- Push the state over the socket to the window instead of polling every 400 ms (paused window from 1.4% toward 0).
- Full screen on a second monitor while Home stays on the first (a `--display` for Full screen).
- Waybar module showing the current lyric line from `encore.sock`.

verified: b0be574 2026-11-04
