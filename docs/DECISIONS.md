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

## 9. 2026-11-03 - Autostart through HyDE's hc.start / [desktop.start] - Active
encore starts like HyDE's other services: `hyde-shell app -u hyde-$XDG_SESSION_DESKTOP-encore.service -t service -- encore.sh daemon --if-enabled`.
The daemon exits at once unless `[encore] enable = true`, so the entry can ship enabled-by-config without starting anything by default.

## 10. 2026-11-04 - Overlay renders with the cairo GSK renderer and cached line rasters - Active
Measured on the owner's laptop at a steady 60 fps fill: cairo 6.8%, vulkan 11.8%, gl 15.0% of one core; cached dim/bright surfaces then halve the python cost.
Animation runs on a 30 fps GLib timer because an active GTK tick callback forces the full frame cycle at 60 Hz; the feathered fill edge hides the half rate.

## 11. 2026-11-04 - Overlay is a separate process from the daemon - Active
`encore.sh overlay` needs LD_PRELOAD of gtk4-layer-shell and a GTK main loop; the daemon stays GTK-free and serves every client over encore.sock.
A crash or toggle of the overlay never touches playback tracking.
