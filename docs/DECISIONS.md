# Decisions

## 1. 2026-11-03 - Build as HyDE-native add-on, mirror upstream tree - Active
Target is a PR to HyDE-Project/HyDE, so the repo mirrors `Configs/` layout and HyDE's language mix (Python/shell/Lua) instead of a separate Rust app.
Forking the external projects wholesale was rejected: mixed languages, not mergeable upstream.

## 2. 2026-11-03 - GPL-3.0 - Active
Matches HyDE.

## 3. 2026-11-03 - Lyrics overlay above windows, click-through - Active (amended by #31: it never draws a full-screen cover)
Overlay layer, no input region, keybind toggle. Visible while working, which is the video shot.

## 4. 2026-11-03 - Clean word-timing chain, no Musixmatch - Active
Local .lrc and LRCLIB (enhanced LRC when present), then Spicy Lyrics API with a user-supplied free key, else estimated word timing.
Musixmatch anonymous-token scraping rejected: ToS gray and would block the upstream PR.

## 5. 2026-11-03 - Album colors drive encore pieces, full-theme recolor opt-in - Active
Overlay, glow and hyprlock always follow the cover palette. Whole-HyDE recolor per track is a `follow_album` option, debounced.

## 6. 2026-11-03 - Upstream via Discussion first, then 3-4 small PRs to dev - Active
Owner approves before anything is posted to HyDE-Project.
HyDE's CHANGELOG.md gets edited in upstream PR branches only, an agreed exception to the owner's no-changelog-edits rule.

## 7. 2026-11-03 - New dependency gtk4-layer-shell - Active
HyDE has no overlay surface mechanism; gtk4-layer-shell is in official Arch repos and lightest option from Python. Needs pkg_extra.lst entry upstream.

## 8. 2026-11-03 - encore runs on system python3, not HyDE's venv - Active
HyDE's venv (`$XDG_STATE_HOME/hyde/python_env`) is built with `include-system-site-packages = false` and cannot import `gi`, which encore needs for Playerctl and GTK4 layer-shell.
System `python3` has `python-gobject`, `playerctl` and `gtk4-layer-shell` typelibs on Arch.
`encore.sh` is the `hyde-shell` entry (hyde-shell prefers `.sh` over `.py`) and execs system `python3 encore.py`.
`encorelib/` stays free of `gi` and third-party imports so it runs on either interpreter.

## 9. 2026-11-03 - Autostart through HyDE's hc.start / [desktop.start] - Superseded by #20
encore starts like HyDE's other services: `hyde-shell app -u hyde-$XDG_SESSION_DESKTOP-encore.service -t service -- encore.sh daemon --if-enabled`.
The daemon exits at once unless `[encore] enable = true`, so the entry can ship enabled-by-config without starting anything by default.

## 10. 2026-11-04 - Overlay renders with the cairo GSK renderer and cached line rasters - Superseded by #28
Measured on the owner's laptop at a steady 60 fps fill: cairo 6.8%, vulkan 11.8%, gl 15.0% of one core; cached dim/bright surfaces then halve the python cost.
Animation runs on a 30 fps GLib timer because an active GTK tick callback forces the full frame cycle at 60 Hz; the feathered fill edge hides the half rate.

## 11. 2026-11-04 - Overlay is a separate process from the daemon - Active
`encore.sh overlay` needs LD_PRELOAD of gtk4-layer-shell and a GTK main loop; the daemon stays GTK-free and serves every client over encore.sock.
A crash or toggle of the overlay never touches playback tracking.

## 12. 2026-11-04 - Overlay styles are one process with a live style file - Active
`line`, `stack`, `constellation` and later `visual` (#17) share the overlay process, socket client and caches; `hyde-shell encore style` writes `$XDG_RUNTIME_DIR/hyde/encore.look`, which the existing runtime-dir monitor picks up.
Stack and constellation redraw on word boundaries plus 160 ms pops only.

## 13. 2026-11-04 - Edge glow is four layer strips in its own process - Superseded by #14
`hyde-shell encore glow` toggles it independently of lyrics; intensity rides a cava attack/release envelope when `cava.sock` exists, else a slow breathe; repaints skip when the intensity change is imperceptible.

## 14. 2026-11-04 - Glow is one full-screen window with a GPU-scaled texture - Active
Circling comets need continuous repaint; four strip windows at 20 fps cost 23% of a core (CPU raster) and still 9-12% after downscaling, because GTK's per-window frame overhead dominated.
One click-through window composes all four edges into a 1/4-resolution frame texture that GSK stretches on the GPU: 2.5% of a core at 20 fps, compositor +1%.
The tick later dropped to 80 ms (12.5 fps), which reads smooth for slow comets.
Correction (2026-11-04, layer 3): the 2.5% was measured while every paint raised (undefined helpers), so nothing was drawn; drawing for real costs 6.1-7.5% of a core playing on the hidden stage.
Kept from #13: own process toggled by `hyde-shell encore glow`, cava attack/release envelope when `cava.sock` exists, else a slow breathe.

## 15. 2026-11-04 - Settings window and sound-setup profiles - Superseded by #16
A GTK4 panel (`hyde-shell encore menu`, SUPER+ALT+M) modelled on the reference app replaces the rofi menu (kept as `menu --rofi`); profiles `working` and `show` set look keys and the glow state; `encore show` (SUPER+ALT+E) toggles an empty `encore` workspace running the show profile.

## 16. 2026-11-04 - Three reference UIs, built separately - Active (the `menu` window and the `show` workspace are superseded by #29)
RE of the public reference assets showed three different UIs: the lyrics look menu, the player window, and the glow settings popover.
`hyde-shell encore menu` (SUPER+ALT+M) now opens the player window; its palette button opens the look menu (styles, fonts, size, Lyric Text / Highlight / Secondary colors), its Settings pill opens the glow popover (gradient, animation, thickness, glow, override colors, display).
Kept from #15: the `working` and `show` profiles and the `encore show` workspace; the rofi menu stays as `menu --rofi`.

## 17. 2026-11-04 - Column styles render for steady 1:1 blits; visual art is its own layer - Superseded by #31
Visual cost 85% of a core: words re-typeset at interpolated sizes every frame and big bitmaps went through cairo's convolution filter with skew.
Words now rasterize per target slot with the drum tilt baked in, steady frames blit 1:1 at integer positions, slides use bilinear, and the album art sits in a separate TOP-layer window that never redraws: visual 11%, stack 9%.

## 18. 2026-11-04 - LRCLIB lyricsfile word sync deferred - Active
LRCLIB exposes `hasWordSync` and a YAML `lyricsfile` (LRCGET's Lyricsfile format); word timing lives only there, its `syncedLyrics` stays line-level.
A survey of 30 popular tracks across pop, rap, rock, J-pop, C-pop and K-pop found 0 of 600 search results with word sync, and the stdlib has no YAML parser.
Parsing it now would add a hand-written YAML subset for almost no tracks; re-survey later and build it once word-synced entries are common.

## 19. 2026-11-04 - Estimated word timing calibrated on real word sync; lines release 4 s after the last word - Active
Scored against 11 word-synced songs in the local cache (3,589 words, `tests/tools/calibrate_timing.py`, numbers only): the old 0.45 s-per-character cap gave a 0.43 s mean word-start error.
Capping the pace at 0.08 s per letter (3 units per CJK character, which is split per character) and filling at most 90% of the gap to the next line gives 0.21 s overall, 0.25 s and 0.20 s on the two song halves.
Real gaps from a line's last word to the next line: median 0.27 s, p99 6.5 s, so a line stays live 4 s after its last word; then the state reports `gap` instead of a stuck, fully lit line.

## 20. 2026-11-04 - The daemon starts on demand; login autostart needs a start_up.lua line - Active
HyDE's `start_up.lua` runs a fixed list of `hc.start` keys in its `hyprland.start` handler and never iterates the table, so `hc.start.encore` and `[desktop.start] encore` were never executed: encore had never autostarted, and after a fresh login every surface stayed empty while Spotify played.
`toggle`, `glow` and the player now start the daemon when its socket does not answer, as the same `hyde-<desktop>-encore.service` unit (not gated on `enable`, since the user asked for a surface), falling back to a detached `encore.py daemon` when `hyde-shell` or the unit fails.
Login autostart is a `hl.on("hyprland.start", ...)` line in the user's `hyprland.lua` here, and `check_exec(hs.encore)` in `start_up.lua` in the upstream PR.
On-demand starts run from `$HOME` (HyDE's `app2unit` uses `--same-dir`, and a vanished working directory made every restart fail at CHDIR) and clear a failed unit of the same name first.

## 21. 2026-11-04 - Daemon fetches run on latest-wins workers - Active
Every track change started a lyrics thread and a palette thread; six fast skips with slow palette work took the daemon from 4 to 10 threads.
`encorelib.jobs.LatestJobs` runs at most N jobs (2 lyric, 1 palette) and keeps one queued slot that a newer submit replaces; `FetchGate` still discards results of work that had already begun.
A `ThreadPoolExecutor` was rejected: its queue would still run every stale job.

## 22. 2026-11-04 - Playback rate comes from a D-Bus proxy on the followed player - Active
Playerctl exposes no `Rate`, so the daemon keeps a `Gio.DBusProxy` on `org.mpris.MediaPlayer2.<instance>` (built asynchronously when the followed player changes), reads `Rate` through `clean_rate` on every playback refresh and resyncs on `PropertiesChanged`.

## 23. 2026-11-04 - End-to-end tests run on a private bus and runtime dir - Active
`tests/e2e/harness.py` starts a private `dbus-daemon`, a short runtime dir under `/run/user/$UID` (AF_UNIX paths cap at 108 bytes), private cache, state and lyrics dirs, fake players and the repo daemon; tests read `encore.sock` without importing `gi`.
They run in the default pytest invocation, never start GUI processes and never touch the owner's players or runtime files; `tests/e2e/measure.py` uses the same harness for every perf claim.

## 24. 2026-11-04 - One album color scheme for every surface - Active
`encorelib/colors.py` derives accent, second hue, highlight block, text on the block, resting lyric and secondary colors once per palette; overlay, glow, player and lock screen all use it.
The first wallbash family with real color (HLS saturation >= 0.22) drives the accent, lightened along its hue until it reads on dark; a grey cover hands over to the HyDE theme's wallpaper palette, and only then a curated violet (`B48CFF`).
Text on the highlight block is white or ink by contrast: a black-and-white cover used to give a white block under white text.

## 25. 2026-11-04 - Visual work is judged on a hidden Hyprland monitor - Active
Hyprland has no headless mode, and running nested opens a visible window, so `tests/e2e/stage.py` adds a virtual monitor `encore-lab` to the live session, parks it at 20000,20000 out of the mouse's reach, runs the real surfaces there on the private harness and captures them with `grim -o encore-lab`; the monitor is removed afterwards.
The player reaches it through a window rule for a stage-only app id and is killed at once if it ever maps on the owner's screen; the harness pins `WAYLAND_DISPLAY` and drops `DISPLAY` so GTK can never fall back to an X11 window there.

## 26. 2026-11-04 - Overlay type and motion are paid for with cheaper rasters, not a GPU renderer - Active
The redesigned line type (about 4% of the screen height), soft shadow and accent bloom are baked once per line: the shadow comes from shifted blits of a glyph mask shared by the dim and lit copies, and the lit copy is built lazily.
Frames whose only movement is the idle drift run at 15 fps; pops, slides and exits keep 30.
The GL, NGL and Vulkan renderers were measured again on these full-screen surfaces and cost 2-3x more than cairo, so #10 stands; the column styles stay over budget on dense lyrics until drawing is limited to the damaged region.

## 27. 2026-11-04 - Column-style cost is CPU rescaling of big type; the way out is GPU texture nodes - Active
Measured on the hidden stage: with the column's draw function emptied, the same frame rhythm costs 3.4% of a core, so about 13 of stack's ~17 points are painting.
GTK replays the cairo drawing at render time, so the Python profiler cannot see it; the cost is bilinear rescaling of the big middle word (about 207 px type, ~270k pixels) on every slide frame.
Shrinking the canvas width to the line's widest word did not help (painting, not canvas area, dominates), and frame-skipping slides gave no measurable gain on a loaded machine.
A prototype that draws word textures through snapshot texture nodes and lets the renderer scale them cost 20% (NGL) against 70% (cairo) in a worst case of four giant words rescaled every frame; NGL alone carries a high per-frame cost on this NVIDIA setup, so the switch only pays once the whole overlay draws texture nodes.
Perf numbers need a quiet machine: with a browser video, Hyprland and a build running, runs varied by 3-4 points.

## 28. 2026-11-04 - Overlay frames are GPU render nodes; CPU is now the frame pipeline, not painting - Active
`encoregui/scene.py` turns every frame into snapshot nodes (textures, transforms, opacity, clips, an alpha-mask feather, GPU shadows); cairo and Pango only rasterise text once into cached textures, and the overlay runs on GTK's default renderer.
Gains: big words scale with mipmapped filtering and only ever downward (crisp slides), and shadows are GPU blurs.
An interleaved A/B on identical code and load (stack, dense lyrics, browser video running) measured cairo 17.5-20.0% against NGL 17.3-18.3% of a core, so the port is cost-neutral rather than the 4x the worst-case prototype suggested: painting is no longer the cost, and what remains is per-frame Python, GTK's frame cycle and the Wayland commit.
Finding the next cut needs a native profiler (perf or sysprof), which is not installed.

## 29. 2026-11-04 - Encore is a launcher app with one window: Home, Lyrics, Full screen - Active
The owner could not use Encore as a user: everything started from keybinds and the visual style covered the screen with a click-through layer that had no way out.
Encore is now `org.hyde.encore`, a unique `Gtk.Application` with a desktop entry and icon: launching it again raises the window, `encore app --open <page>` switches it.
Home carries the cover, seek, transport, volume, the player chip and a bottom bar; Lyrics is a page; Full screen is the window itself fullscreened, with bars that fade in on mouse motion and Esc, an Exit button and the compositor dropping fullscreen all returning to Home.
The `show` workspace, its profile and SUPER+ALT+E are retired; `player` and `menu` are aliases of `app`.
Scope: HyDE on Hyprland (owner's call); standalone later.

## 30. 2026-11-04 - HD covers: Spotify's CDN size, then Apple's catalog with a strict match - Active
Spotify's MPRIS cover is the 640 px size (`ab67616d0000b273`) of an image the same CDN serves at 1500 px under `ab67616d000082c1`; that swap sends nothing new anywhere and is always on.
Other players fall back to Apple's public iTunes Search API (2000 px artwork; 3000 px timed out on a slow link), on by default (owner's call) with a Settings switch, matched strictly: the primary artist must match and the album must, or the song title when the player sends no album (browser videos).
A wrong cover is worse than a small one: no match means the player's own cover, shown sharp and framed, never stretched past 1.35x.
The state carries `track.cover` (best full size) beside `track.art` (the 512 px lock copy); colors publish first and the HD download runs on its own worker.

## 31. 2026-11-04 - One lyric renderer (LyricsEngine) hosted by the desktop overlay and the full-screen page - Active
`encoregui/lyrics.py` owns the socket client, the live look and every style's drawing with no layer-shell import; `overlay.py` is a thin layer-shell host that hides while `encore.stage` names its output, and `fullscreen.py` hosts the same engine in the window over `CoverBackdrop`.
The desktop never draws a full-screen cover again (the trap behind this project); the visual style on the desktop is the column alone.
Pixel-compared before and after the split on the hidden stage: at most 0.03% of pixels differ, the run-to-run noise.

## 32. 2026-11-04 - The look and the app's settings persist in $XDG_STATE_HOME/hyde/encore.look - Active
Every look writer also keeps the merged look there and every entry point restores the runtime copy after a reboot; the daemon honors `autostart`, restarts desktop lyrics and glow that were on, and applies `players` and `hd_covers` live.

## 33. 2026-11-04 - Close to tray through a StatusNotifierItem; Quit stops every surface - Active
Closing the window with desktop lyrics or glow running keeps Encore in the tray (StatusNotifierItem and dbusmenu exported with plain Gio, registered whenever a watcher appears); with neither on, closing quits.
Quit stops the overlay and glow, records both as off and clears the full-screen flag (which names the app's pid, so a crashed app never keeps the desktop overlay hidden); the daemon keeps running for the lock screen.
The app also exposes `close` and `quit` as GTK app actions, which the lab tests drive over D-Bus (Hyprland's Lua `window.close` dispatcher accepted the call without closing the window).

## 34. 2026-11-04 - Pre-existing fix: rounded clips and shadows were empty - Active
PyGObject's return value of `Gsk.RoundedRect().init_from_rect()` is not the initialized struct, so every rounded clip built from it came out empty and every GPU shadow sat at the origin (pixman logged invalid rectangles). `scene.rounded()` builds the rect in place; `tests/test_scene.py` pins it.

