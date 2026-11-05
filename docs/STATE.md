# State

Goal: match, then beat, Verci (lyrics) and Lumn (glow, player), polished enough to show publicly; upstream PRs to HyDE after.
Current shape: Encore is an app (DECISIONS #29) with its own identity (#35); the stage pass (#39-#42) and the smoothness pass (#43-#44) are done on the hidden monitor and wait for the owner's eyes; a demo reel is rendered for Instagram.

## Shipped (main through PR #17, plus branch feat/encore-app = PR #18)
- The Encore app (`org.hyde.encore`, launcher entry and icon, one 960x760 window; Home's cover and the Lyrics card grow with a bigger or tiled window): Home (HD cover with hover halo, title, artist, seek bar, back 15 s / previous / play / next / forward 15 s, volume when the player has one, a chip to pick the player it follows), Lyrics page (a list with depth; click a line to seek; the wheel browses and following resumes 4 s later), Stage window and Full screen (below). Keys: Space, Left/Right, Up/Down, N/P, L, W, F, Esc, Ctrl+Q. Launching again raises the window; `encore app --open home|lyrics|stage|full|look|settings`.
- The show (DECISIONS #39): any style over the cover, or over the album field when Clear or when the track has no cover, with glass bars (Home or Exit, Window or Full screen, five styles, background, glow, look; cover, song, seek, transport, volume) that fade on mouse motion. The Stage runs it in the normal window, sized to the window and re-laid after a resize; Full screen fills the output. W and F move between them without stopping the show; Esc and the compositor dropping fullscreen never trap. The desktop overlay on that output hides only while the show is in sight: another workspace, minimized or the tray brings it back.
- Lyric motion (#37, #40, #43, #44): words light 120 ms ahead; a sung word pops in on a damped spring in every style; the stack and visual columns push up on a spring with ghost echoes that read as motion blur; the word just sung hands its sung color, face and block over to its resting look across the slide; a finished column rises out with its echoes, a finished chain rises and draws back; held words grow; glyphs pop beside 145 words. Fast motion draws from the display's frame clock at up to 60 fps, slow motion on a 30 fps timer. `motion=false` keeps plain eases and no ghosts.
- Typography (#41): a face per word and style from what is installed (line heavy; stack and visual heavy / serif italic / regular, never heavy on the Highlight block; constellation semibold with serif words; code mono); weights only from what a family ships; the Font menu is a dropdown of the installed display set.
- Five styles: line (centred, sized for the show), stack, constellation, visual (proportions read off Verci's hero) and code (line numbers, past lines as comments, the current word typed letter by letter with a block caret, the block centred and shrunk to fit).
- Colors (#42): one album scheme for every surface, floored on #141317 (Lyric Text 7:1, Secondary 2.5-4:1, text on the block 4.5:1); the `gradient` look key paints the album field from one or two album colors.
- The identity (#35): the album field is the window's light, the idle screen and Clear; frosted glass bars and popovers; SF Pro Display UI; `motion=false` stops every decorative drift.
- Settings and the look menu after the reference panels (#42): style, background, gradient, font, text size with its value, Auto Sync and three color swatches; glow (gradient, animation, thickness, glow with values, override colors, display), lock screen lyrics with Preview, HD covers, start at login, players to follow, Quit. Persisted in `$XDG_STATE_HOME/hyde/encore.look` (#32).
- Closing the window keeps Encore in the tray (StatusNotifierItem) while desktop lyrics or glow run; otherwise it quits. Quit stops the overlay and glow; the engine stays for the lock screen.
- HD covers (#30), the engine (`encorelib/`), the daemon, one lyric renderer for the overlay and the show (#31), glow, hyprlock `Encore.conf`: as before this pass.
- 537 tests (unit and e2e on a private bus) plus 9 opt-in lab tests (`-m lab`) on the hidden monitor; ruff clean. `tests/e2e/stage.py` and `measure.py` take `--app stage` and `--style code`; `tests/e2e/showreel.py` records the demo take. Stills: `.stage/stage-1` to `.stage/stage-6`, `.stage/polish/`; takes `.stage/showreel*/`.
- Demo reel (outside this repo, in the owner's content repo): `~/Documents/dev/0xExploit-Labs/site/experiments/reels/encore-synced-lyrics/reel.mp4` (1080x1920, 60 fps, silent, built with `pnpm reel`).

## Measured (this laptop, 2026-11-05, hidden stage, `measure.py --lab`, 8 s phases)
- After the smoothness pass (#43), with HyDE's `checkupdates` and a crashing process loading the machine, read back to back: desktop line strip 10.8-15.0% playing (14.75% at the start of the stage pass under the same load), 0.5% paused; Full screen line 16.3%, visual 39%, stack 47-55%, code about 8%; paused 1.1-2.4%.
- Before it (stage pass, quieter machine): the Stage 960x760 stack 18.1%, visual 12.5%; Full screen stack 24.9-25.6%, visual 22.6-26.4%, constellation 15.8%, code 3.75%; desktop code 4.1%.
- Frame pacing on a playing Full screen stack clip: paint intervals p10/p50/p90 14/28/65 ms before, 5/16/22 ms after; a recorded take shows 60 fps during springs.
- Spread: the same code reads several points apart run to run; treat single runs as +-40%. Every full-window repaint costs 8-16 ms here (#36).

## Verified with the owner
- 2026-11-04 (before the app): real Spotify, Spicy Lyrics word sync, the `Encore` hyprlock preview.
- 2026-11-05: desktop lyrics running on the real screen (the verdict that started the stage pass).

## Unverified on screen
- Everything the stage pass built: the Stage window, springs and ghosts, the faces, the floors and gradient, the panels, the code style. All judged on the hidden monitor only.
- That the desktop lyrics come back when the Stage sits on another ordinary workspace (the lab proved it for a hidden special workspace only).
- Full screen, tray in waybar, the lock switch, Apple covers on a real browser track, plain lyrics or no cover on a real track.

## Broken or placebo
- Full screen column styles cost about twice what they did before 60 fps springs (#43), well above the plan's budgets while words fall; `motion=false` is the low-cost setting.
- The Settings popover once failed to open in a lab capture (`--app settings`; a re-run opened it); not reproduced.
- Known small gaps from the final review: `code` is missing from the style lists in `schema.toml`, `config.toml` and the `encore style` help; the Font dropdown shows a stale family when the look's font is installed but outside the display set; holding F down can bounce Full screen back; a box with none of the look's families nor a display font asks fontconfig for Bold on a substitute.
- GTK 4.24 logs harmless "GtkImage reported baselines" warnings when Settings opens (GtkDropDown internals).

## Not built
- Multi-monitor copies of the overlay and glow; the Lens style; the wallbash template and `follow_album`; the standalone (non-HyDE) app.

## Next
- Owner's run on the real screen: Stage window first (W) in the visual style, then Full screen (F), the code style, the look menu and Settings; then watch the reel and post it (the GitHub repo is private: make it public before asking for contributors).
- Per-frame pipeline cut: lower rates for the drift loop and the gap pulse, then a native profiler (owner's OK to install perf or sysprof).
- Upstream: Discussion, then small PRs (hyprlock.sh symlink and player fixes, start_up.lua hc.start iteration, encore).

## Known facts
- HyDE's waybar update checker can fill `/run/user/1000` with `checkupdates_db_*` dirs; Encore survives a full runtime dir (#38).
- Detached surfaces and the app's commands log to `$XDG_CACHE_HOME/hyde/encore/logs/<name>.log`; the daemon logs to the journal under `hyde-Hyprland-encore.service`.
- GTK 4.24 ignores an opacity node over a repeat node; PyGObject never calls a `do_size_allocate` override on a `Gtk.Overlay` subclass (use a `Gtk.DrawingArea` probe's `resize`); GtkColorDialogButton's swatch cannot be narrowed below 32 px.
- Hyprland 0.56 moves a workspace back to the monitor it was last on (`stage.py` names its lab monitor per run), marks windows on hidden special workspaces suspended, and its Lua `window.close` accepts a selector without closing; HyDE's waybar also draws on the lab monitor.
- Fonts here: SF Pro Display ships 400/500/700 uprights, Inter every weight, Instrument Serif and Newsreader no italic.
- HyDE bugs found (candidate small PRs): `hyprlock.sh find_filepath` does not follow symlinked layouts; `hyprlock.sh fn_mpris` reads the first listed player; `start_up.lua` runs only the `hc.start` keys it names.
- Owner's Spicy Lyrics key lives in `~/.config/hyde/config.toml` (mode 600, not tracked). LRCLIB `/api/get` can return junk uploads; synced results under 4 timed lines are rejected.

## Open questions
- Final name (working name: hyde-encore).

## Ideas
- Push the state over the socket to the window instead of polling every 400 ms (paused window from 1.5% toward 0).
- Full screen on a second monitor while Home stays on the first (a `--display` for Full screen).
- Waybar module showing the current lyric line from `encore.sock`.
- The Stage as a small always-on-top mini player (a compact size preset for the window).
- A Codestyle Visual variant: the code rows over the cover, like Verci's.

verified: 27aef22 2026-11-05
