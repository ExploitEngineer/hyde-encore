# State

Goal: match, then beat, Verci (lyrics) and Lumn (glow, player), polished enough to show publicly; upstream PRs to HyDE after.
Current shape: Encore is an app (DECISIONS #29) with its own identity (#35); the finish pass is done on the hidden monitor and waits for the owner's eyes.

## Shipped (main through PR #17, plus branch feat/encore-app = PR #18)
- The Encore app (`org.hyde.encore`, launcher entry and icon, one 960x760 window): Home (HD cover with hover halo, title, artist, seek bar, back 15 s / previous / play / next / forward 15 s, volume when the player has one, a chip to pick the player it follows), Lyrics page (a list with depth: the current line sharp and full, neighbours a step back, farther lines two; words brighten as sung; click a line to seek; the wheel browses the song and following resumes 4 s later or on the back-to-line button; "Looking for lyrics", "No synced lyrics found", plain lyrics as a readable, scrollable list), Full screen (any style over the cover, over the album field when Clear or when the track has no cover; glass top bar Exit / style / background / glow / look and glass bottom bar cover / song / seek / transport / volume fade in on mouse motion and out after 3 s; Esc, Exit and the compositor dropping fullscreen return to Home; the desktop overlay on that output hides meanwhile). Keys: Space, Left/Right, Up/Down, N/P, L, F, Esc, Ctrl+Q. Launching again raises the window; `encore app --open home|lyrics|full|look|settings`.
- The identity (DECISIONS #35): the album field (the cover blurred large and darkened under three album-colored blobs that drift while playing and hold when paused) is the window's light, the idle screen and Clear in Full screen; frosted glass bars and popovers cropped from a cached blur; SF Pro Display for UI and lyrics, Instrument Serif Italic for serif words and the idle title when installed; `motion=false` in the look stops every decorative drift.
- Lyric motion (DECISIONS #37): every surface lights a word 120 ms ahead; stack and visual set a held word larger (1.0 at 0.3 s to 1.18 at 1.2 s); glyphs pop in with their word; the constellation's newest hairline draws in and its sparkle breathes; the line style's next line recedes (blurred once). Judged frame by frame next to `verci-hero.mp4`.
- Closing the window keeps Encore in the tray (StatusNotifierItem: Open, Play/Pause, Next, Desktop lyrics, Glow, Quit) while desktop lyrics or glow run; otherwise it quits. Quit stops the overlay and glow; the engine stays for the lock screen.
- Settings: glow (gradient, animation, thickness, glow, override colors, display), lock screen lyrics with Preview (`encore lock on|off|preview|status`, restores the previous hyprlock layout), HD covers, start at login, which players to follow, Quit. The look and these settings persist in `$XDG_STATE_HOME/hyde/encore.look` (DECISIONS #32).
- HD covers (DECISIONS #30): Spotify's 1500 px CDN size always; Apple's catalog (2000 px) for other players with a strict artist and album (or song) match, on by default; `track.cover` beside the 512 px `track.art`.
- Engine (`encorelib/`): LRC and enhanced LRC, CJK-aware word tokens, calibrated word-timing estimator, gap-aware cursor, playback clock, providers (local `.lrc`, LRCLIB with search variants, Spicy Lyrics word sync), LRU lyrics cache, byte-bounded texture cache, album palette, protocol v1 with `players`, `volume`, `lookup` and `track.cover`.
- Daemon: follows the most recently started player or a pin (`encore follow <player|auto>`), honors the app's player list and HD switch live, publishes `encore.sock`, hyprlock line, track and cover files; `--if-enabled` honors start-at-login and brings back desktop lyrics and glow that were on.
- One lyric renderer (`encoregui/lyrics.py`, DECISIONS #31) for the desktop overlay (click-through, never a full-screen cover) and Full screen; styles line, stack, constellation, visual; frames are GPU render nodes.
- One album color scheme for every surface; glow (one full-screen window, cava beat envelope); hyprlock `Encore.conf`.
- 440 tests (unit and e2e on a private bus) plus 6 opt-in lab tests (`-m lab`) that drive the window on the hidden monitor; ruff clean. `tests/e2e/stage.py` renders every surface and app page (stills, clips, `--then` page switches, `--long-lyrics`, `--plain-lyrics`, `--no-cover`, `ENCORE_TRACE` paint timing) on the hidden monitor; `measure.py` measures them. Stills of every screen: `.stage/finish-final/sheet.png`.

## Measured (this laptop, 2026-11-05, hidden stage, `measure.py --lab --seconds 8`; DECISIONS #36)
- Window: Home 2.4-3.1% playing, 1.5-1.9% paused, 1.1-1.5% idle (the field at 1 fps); Lyrics page 10-11% while words fill, 1.9-2.0% paused.
- Full screen playing: line 12-13% (11.4% over Clear), stack 21%, constellation 15%, visual 22.6%; paused 0.75-1.4%; the idle field at full HD 1.4%. First full-HD frame about 250 ms once per session.
- Desktop overlay playing: line 9.6-11.3%, stack 20.5-20.9%; paused and no lyric line under 0.7%. Daemon playing about 1%.
- Spread: runs earlier in the same pass read 7.75% (overlay line), 14.1% (overlay stack) and 6.6% (Full screen constellation, before the sparkle and hairline motion) on the same code; treat single runs as +-40%.
- Where it goes (Full screen constellation with `--look motion=false`: 9.1% playing, 0.75% idle): the 30 fps drift loop every style runs while playing is about 6 points, the 20 fps soft pulse through lyric gaps about 5 (the "no lyric line" phase); the idle field at full HD cost 4-4.6% at 3 fps and 1.4% at the 1 fps it runs now.
- Glow playing 6-7.5%, paused 0.25% (2026-11-04).

## Verified with the owner
- 2026-11-04 (before the app): real Spotify, Spicy Lyrics word sync, the `Encore` hyprlock preview.

## Unverified on screen
- Everything the finish pass built, and the app end to end: launcher, Spotify, Home, Lyrics list, Full screen entry and bars, idle screen, close to tray, tray in waybar, lock switch. Every page is verified on the hidden monitor only.
- Covers from Apple on a real browser track; HD Spotify covers in Home (lab used a 1500 px file).
- A real track with plain (unsynced) lyrics or no cover: both only as lab stills (`.stage/finish-final/plain`, `full-nocover`).

## Broken or placebo
- Perf over the plan's budgets while lyrics animate (above): the cost is the 8-16 ms full-window repaint per frame on this driver, and the 30 fps drift loop and the 20 fps gap pulse buy 11 of constellation's 15 points; a native profiler is the tool for the rest (DECISIONS #28, #36).
- The optional Lens style was not built (skipped by ruling: over budget already).
- GTK 4.24 logs harmless "GtkImage reported baselines" warnings when Settings opens (GtkDropDown internals).

## Not built
- Multi-monitor copies of the overlay and glow; a second monitor's Full screen hides only that output's overlay.
- Wallbash template for encore and the opt-in `follow_album` full-theme recolor.
- The standalone (non-HyDE) app; built so it stays possible.

## Next
- Owner's run on the real screen (launcher, Spotify, Home, Lyrics, Full screen, idle, tray in waybar, lock preview) and the owner's verdict on the identity; fix what is off before anything new.
- Per-frame pipeline cut: lower rates for the drift loop and the gap pulse first, then a native profiler (owner's OK to install perf or sysprof).
- Upstream: Discussion, then small PRs (hyprlock.sh symlink and player fixes, start_up.lua hc.start iteration, encore).

## Known facts
- `/run/user/1000` (1.6 GB tmpfs) is 100% full of `checkupdates_db_*` dirs left by HyDE's waybar update checker, with dozens of `checkupdates`/`pacman -Sy` processes asleep behind them (not ours, not swept); the test harness falls back to /tmp.
- GTK 4.24 ignores an opacity node over a repeat node: the grain's strength is baked into its texture.
- HyDE bugs found (candidate small PRs): `hyprlock.sh find_filepath` does not follow symlinked layouts; `hyprlock.sh fn_mpris` reads the first listed player; `start_up.lua` runs only the `hc.start` keys it names.
- Hyprland 0.56 moves a workspace back to the monitor it was last on, so a reused headless monitor name pulls one of the owner's workspaces onto it; `stage.py` names its lab monitor per run and refuses to run if that happens. Its Lua `window.close` dispatcher accepted a selector without closing the window; the lab tests use the app's `close` GTK action instead.
- PyGObject: `Gsk.RoundedRect().init_from_rect()` does not return the initialized struct (DECISIONS #34).
- Owner's Spicy Lyrics key lives in `~/.config/hyde/config.toml` (mode 600, not tracked).
- LRCLIB `/api/get` can return junk uploads; synced results under 4 timed lines are rejected and search runs instead.

## Open questions
- Final name (working name: hyde-encore).

## Ideas
- Push the state over the socket to the window instead of polling every 400 ms (paused window from 1.5% toward 0).
- Full screen on a second monitor while Home stays on the first (a `--display` for Full screen).
- Waybar module showing the current lyric line from `encore.sock`.
- The Lens style (the stack on a convex surface, no shaders) once a frame is cheap enough to afford it.

verified: fd7948b 2026-11-05
