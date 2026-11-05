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


## 35. 2026-11-05 - The identity: the album field, glass and lyric depth - Active
The window's light is the cover itself: `encoregui/field.py` (AlbumField) blurs it large once per cover and size into a texture, darkens it, and lays three album-colored blobs over it that drift at 1 fps while music plays or while nothing plays at all (the idle light) and hold still when paused, hidden, suspended or `motion=false` (the idle screen was meant to run at 3 fps; a timer that never re-armed kept it at 1, no still faulted it, and a real 3 fps doubled the idle cost, so 1 it is).
A fine grain is baked into a tiled texture (brightest speck alpha 14) because GTK 4.24 ignores an opacity node over a repeat node and drew the 4.5% grain at full strength.
The same field is the idle screen and Full screen's Clear background, so Clear is black light rather than a void; `idle.py` is gone.
Bars and popovers are glass (`glass.py`): a clipped crop of the backdrop's already-blurred texture, a dark tint and a 1 px light edge, so a panel costs one texture node and never a live blur.
The Lyrics page is a snapshot widget (`lyriclist.py`): every line a cached `LineRaster` (heights come from bare Pango layouts, so a 200-line song lays out at once and only the lines in view rasterise), depth by distance from the current line (scale 1 / 0.94 / 0.9, opacity 1 / 0.55 / 0.32, blur 0 / 1.5 / 3 px, each blurred once into a texture), the current line held at 38% of the view and the last lines allowed to rise past the end as in Apple Music; the wheel browses the song and following resumes 4 s later; plain lyrics show every line sharp, scrollable, with nothing to seek.
Type: SF Pro Display for the UI and lyrics; Instrument Serif Italic for the column styles' serif words and the idle title when installed, else the system serif (no new dependency).
The window opens at 960x760 so the Home column breathes.
Design: `docs/superpowers/specs/2026-11-05-encore-finish-design.md`.

## 36. 2026-11-05 - Frames are the cost: what the window may draw each frame - Active
Every full-window repaint costs 8-16 ms of CPU on this laptop's NVIDIA driver, GL and Vulkan alike (cairo measured 97%), bisected on the Lyrics page: the base tree 12 ms, a list mask 6 points, live gradients 4 points.
Frames, not nodes, are the cost, so the window follows these rules: no blur or mask node is built per frame (the field's and backdrop's blurs, the depth steps' blurs and the line style's next-line blur are rendered once into textures and reused); glass crops a cached blur; the Lyrics list brightens each word over 140 ms instead of sweeping a feathered mask at 30 fps; the album field drifts at 1 fps while playing (3 on the idle screen) and holds when paused; entering Full screen cuts (a Gtk.Stack crossfade painted two full-HD offscreens per frame at about 10 fps) and the hero animation's clock starts at its first painted frame; the backdrop pre-blurs and warms the renderer so the first full-HD frame costs about 250 ms once per session (was 360-790 ms); the field redraws on a new scheme only (the 400 ms poll used to repaint Full screen while paused).
Measured 2026-11-05 on the hidden stage, 8 s phases: Home 2.4-3.1% playing, 1.5-1.9% paused, 1.1-1.5% idle; Lyrics page 10-11% while words fill, 1.9-2.0% paused; Full screen line 12-13% (11.4% over Clear), stack 21%, constellation 15%, visual 22.6% playing, 0.75-1.4% paused, 1.4% on the idle field at full HD; desktop overlay line 9.6-11.3%, stack 20.5-20.9%, under 0.7% paused.
Earlier runs in the same pass read lower on the same code (overlay line 7.75%, stack 14.1%; Full screen constellation 6.6% before the sparkle breath and the hairline draw-in), so the run-to-run spread on this machine is about 40% and the plan's budgets (line 12, stack 19, constellation 4, visual 24.5) are not all met while words fill.
With `motion=false` Full screen constellation drops to 9.1% playing and 0.75% idle, so the 30 fps word drift that every style runs while playing costs about 6 points and the 20 fps soft pulse through lyric gaps about 5 (the idle field at full HD cost 4 more at 3 fps and 1.4 at the 1 fps it runs now): the first cuts are lower rates for those two loops, and the rest needs a native profiler (#28).

## 37. 2026-11-05 - Words lead by 120 ms; held words are set larger - Active
Every surface lights a word 120 ms before its timestamp (`lyricview.LEAD_SECONDS`), as the ear expects and as Verso's ~160 ms lead does; the lead is a parameter so the exact-clock tests pin the pure clock with `lead=0`.
In the stack and visual styles a word held longer is drawn bigger: `motion.held_scale` grows from 1.0 at 0.3 s to 1.18 at 1.2 s and caps there, so a long note never overflows its slot.
Judged frame by frame next to `verci-hero.mp4`: the same three-slot rhythm, block, glyphs and serif words, and the big word spans about the same share of the frame.
The optional Lens style was skipped: the plan allowed it only within budget, and animated pages already sit above it (#36).

## 38. 2026-11-05 - Runtime files are a courtesy: a full tmpfs never hides a surface - Active
The owner's first run on the real screen showed nothing: `/run/user/1000` was full (HyDE's update checker had leaked 254 pacman db dirs), `single.claim` crashed writing the overlay's pid, `encore toggle` died with its stderr in `/dev/null`, and the daemon logged a traceback twenty times a second while leaking a `.tmp` per attempt.
Now the flock is the lock and the pid text is best effort (`single._record`), every runtime file goes through `encorelib/files.py` (temp beside the target, renamed in, removed on failure), the daemon's `publish` keeps serving the socket when the lock-screen files cannot be written and says so once a minute (`session.Quiet`), and detached surfaces and the app's commands write their stderr to `$XDG_CACHE_HOME/hyde/encore/logs/<name>.log`.
The leak itself is HyDE's (`checkupdates` under waybar); Encore reports it, never sweeps it.
The state socket is the one thing that must not die: an `accept` that fails for lack of descriptors drops hung-up pollers, then the oldest client, and the GLib watch behind it is guarded, so no error removes the listener (the 2026-11-04 crash on `EMFILE` was the same lesson one step earlier).

## 39. 2026-11-05 - The Stage: the show in the normal window - Active
The owner's verdict on the real screen: the desktop overlay is a layer surface and follows every workspace, while the reference runs its animation in a separate window.
The Full screen page now has a windowed mode, the app page `stage` (`encore app --open stage`, W from any page, a window button in Home's bar, Window and Full screen buttons in the show's top bar): one `FullPage`, one engine, one set of glass bars; the Exit button reads Home there and the bottom bar narrows (seek 240 px) so it fits 960 px.
The engine lays its type out for the page, re-laid 120 ms after a resize settles; the size comes from a `Gtk.DrawingArea` probe's `resize` signal because overriding `do_size_allocate` on the `Gtk.Overlay` subclass never fires under PyGObject (the first stills had the type laid out for the 320x240 floor), and in the Stage the canvas fills the page with no size request so the window can always shrink.
Keys: W toggles Home or Lyrics and the Stage and takes Full screen back to the Stage; F goes to Full screen from anywhere and leaves it to where it came from; Esc goes Home (`transport.page_after`).
The `encore.stage` flag is held only while the show is in sight (`stageflag.wanted`: page stage or full, the window mapped and not suspended), so the window on another workspace, minimized or in the tray lets the desktop lyrics back; the rule covers Full screen too.
Hyprland 0.56 marks a window on a hidden special workspace suspended; the lab test moves the window there and back and watches the flag.
Measured (960x760, 8 s): stack 18.1% playing, visual 12.5%, both 1.1% paused.

## 40. 2026-11-05 - Motion: a damped spring, pops and ghost trails - Active
`motion.spring` is the closed-form underdamped oscillator (zeta 0.55, natural frequency chosen so the envelope is 1% at the settle time); it peaks at 1.13 near 0.43 of the settle and is exactly 1 from the settle on, so animations end; `motion.ghosts` gives two lagged copies (55 and 110 ms behind, alphas 0.35 and 0.18) swelling with a sine over the slide.
A sung word pops in from 0.6 scale on the spring in every style (`motion.pop_in`); the stack and visual columns push up on a 240 ms spring; a finished column rises out over 300 ms with its ghosts; the line style's new line rises on the spring; `motion=false` keeps a plain 160 ms ease-out and no ghosts.
Full ghosting (every moving word, the whole slide) cost about 6 points on Full screen stack against a 2-point budget, all of it in GSK per textured node (Python's render time moved 0.3 ms a frame), so ghosts trail only the two words that travel farthest (the sung word and the one just sung), only through the fast first 160 ms of a slide, and a copy within 6 px of its word or under 5% alpha is not drawn; the spring's slow tail runs at the 15 fps drift rate.
Measured (Full screen, 16 s phases, same session): stack 24.9% playing against 22.4% for the previous commit, visual 22.6-26.4% against 20.6-24.4%; the same code read 22.6% and 26.0% back to back, so the cost is about 2 to 3 points inside a run spread of several.
The `code` style (#41) stands still and redraws once per word: 3.75% in Full screen, 4.1% on the desktop.

## 41. 2026-11-05 - Typography: a face per word from what is installed - Active
The owner found every font looking the same; `encorelib/typeface.py` now picks each word's face per style with the seeded picker: the line style sets the font's heavy face only; stack and visual mix heavy, serif italic and regular about 50/25/25 and never set the word on visual's Highlight block heavy; constellation sets semibold with one serif italic word in four; the new `code` style sets the mono partner.
The look's font chooses the primary sans; the serif partner is Instrument Serif (Newsreader when missing), the mono partner JetBrainsMono Nerd Font (Maple Mono when missing).
A weight comes from what the family ships, the nearest (ties to the heavier), read from Pango once per process for the display set, the partners and the look's families only (19 ms; every family took 184 ms), so a one-weight family such as Alfa Slab One is never emboldened.
Neither installed serif ships an italic face, so the serif words keep Pango's slant as before; a true italic is used automatically when one is installed.
The Font menu is a dropdown of the installed display set (SF Pro Display, Inter, Newsreader, Instrument Serif, Alfa Slab One, Electrolize, Anurati, JetBrainsMono Nerd Font, Maple Mono) with the reference's names (New York, Didot) in its tooltip; this replaces the type line of #35.
The code style (Verci's Codestyle): line numbers in Secondary, the lines already sung as `//` comments, the current line typed word by word with a steady block caret (`encorelib/codeview.py`); the block shrinks as one so its widest row, the whole current line included, fits the window.

## 42. 2026-11-05 - Color floors, the gradient field and the settings pass - Active
Auto Sync floors what it derives against the black light #141317: Lyric Text at least 7:1, Secondary between 2.5:1 and 4:1, and the text on the Highlight block at least 4.5:1 by moving the text toward white or black, never the block (one of the two always reaches 4.58:1); the block is derived at HLS lightness 0.42 so saturated blues, magentas and violets carry light text as in the reference, while luminous hues such as teal carry ink.
User-picked colors stand as picked; only the text on a picked block is floored.
Secondary words are drawn at full fill now, since the floored color already sits behind (the old 0.55 fill on top made them near invisible).
The `gradient` look key (1 or 2, default 2) colors every album field's blobs from the accent alone or the accent and the second hue, each capped at 28% luminance; the look menu has Background (Cover, Clear) and Gradient (1 Color, 2 Colors) rows.
Settings and the look menu follow the reference panels: 11 px uppercase eyebrows tracked 0.08 em, 36 px rows, 8% white separators, 18 px round swatches with a 1 px light ring (drawn, since GtkColorDialogButton's swatch keeps a 32 px natural width), slider values at the right, Quit last.
