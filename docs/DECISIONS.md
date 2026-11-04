# Decisions

## 1. 2026-11-03 - Build as HyDE-native add-on, mirror upstream tree - Active
Target is a PR to HyDE-Project/HyDE, so the repo mirrors `Configs/` layout and HyDE's language mix (Python/shell/Lua) instead of a separate Rust app.
Forking the external projects wholesale was rejected: mixed languages, not mergeable upstream.

## 2. 2026-11-03 - GPL-3.0 - Active
Matches HyDE.

## 3. 2026-11-03 - Lyrics overlay above windows, click-through - Active
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

## 10. 2026-11-04 - Overlay renders with the cairo GSK renderer and cached line rasters - Active
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
Kept from #13: own process toggled by `hyde-shell encore glow`, cava attack/release envelope when `cava.sock` exists, else a slow breathe.

## 15. 2026-11-04 - Settings window and sound-setup profiles - Superseded by #16
A GTK4 panel (`hyde-shell encore menu`, SUPER+ALT+M) modelled on the reference app replaces the rofi menu (kept as `menu --rofi`); profiles `working` and `show` set look keys and the glow state; `encore show` (SUPER+ALT+E) toggles an empty `encore` workspace running the show profile.

## 16. 2026-11-04 - Three reference UIs, built separately - Active
RE of the public reference assets showed three different UIs: the lyrics look menu, the player window, and the glow settings popover.
`hyde-shell encore menu` (SUPER+ALT+M) now opens the player window; its palette button opens the look menu (styles, fonts, size, Lyric Text / Highlight / Secondary colors), its Settings pill opens the glow popover (gradient, animation, thickness, glow, override colors, display).
Kept from #15: the `working` and `show` profiles and the `encore show` workspace; the rofi menu stays as `menu --rofi`.

## 17. 2026-11-04 - Column styles render for steady 1:1 blits; visual art is its own layer - Active
Visual cost 85% of a core: words re-typeset at interpolated sizes every frame and big bitmaps went through cairo's convolution filter with skew.
Words now rasterize per target slot with the drum tilt baked in, steady frames blit 1:1 at integer positions, slides use bilinear, and the album art sits in a separate TOP-layer window that never redraws: visual 11%, stack 9%.

## 20. 2026-11-04 - The daemon starts on demand; login autostart needs a start_up.lua line - Active
HyDE's `start_up.lua` runs a fixed list of `hc.start` keys in its `hyprland.start` handler and never iterates the table, so `hc.start.encore` and `[desktop.start] encore` were never executed: encore had never autostarted, and after a fresh login every surface stayed empty while Spotify played.
`toggle`, `glow` and the player now start the daemon when its socket does not answer, as the same `hyde-<desktop>-encore.service` unit (not gated on `enable`, since the user asked for a surface), falling back to a detached `encore.py daemon` when `hyde-shell` or the unit fails.
Login autostart is a `hl.on("hyprland.start", ...)` line in the user's `hyprland.lua` here, and `check_exec(hs.encore)` in `start_up.lua` in the upstream PR.
