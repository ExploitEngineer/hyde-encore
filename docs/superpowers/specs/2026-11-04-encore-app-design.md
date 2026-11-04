# Encore as an app: design

Date: 2026-11-04.
Status: flow approved by the owner in the brainstorm (mockup `.superpowers/brainstorm/*/content/flow.html`); builder check done, open questions answered.

## Why

The owner tried Encore as a user and could not use it.
Everything starts from Hyprland keybinds, so there is no obvious way in.
The Visual style fills the screen as a click-through layer, so once it is up there is nothing to click: no close, no style switch, only a keybind gets you out.
The full-screen cover looks blurry and murky next to the reference apps and Spotify.
The reference apps (Verci, Lumn) open as a normal window, keep their options reachable in full screen, and show the cover sharp.

Encore has to work like a proper Linux app first.
Polishing the lyric animations comes after this project, on top of it.

## Goals

- Encore opens from the app launcher like any app; no keybind is needed for anything.
- One window with clear places to be (below), every control visible, labelled by tooltip, and working.
- Full screen is always escapable: Esc and a visible Exit button, on every style and background.
- Covers are sharp: HD source when one exists, never stretched past the source size.
- Every state a user can hit (nothing playing, no lyrics, no cover, two players, crash) shows something deliberate.

## Non-goals (this project)

- Lyric animation polish: style motion, lyric typefaces (the italic serif falls back to Noto Serif), emoji and glyph additions next to words. That is the next project.
- Keybinds; the existing SUPER+ALT bindings keep working but nothing depends on them.
- Multi-monitor copies of the overlay or glow.
- Being a music player (local files, playlists, library). Encore remotes whatever MPRIS player is playing.

## Anti-goals (failure even if it technically works)

- Any full-screen surface without a visible way out.
- A stretched, blurry or muddy cover.
- A button that does nothing, or does something its icon does not say (today: the display button cycles styles, the lock button previews hyprlock).
- Regressions in the desktop overlay, glow, hyprlock layout or their perf numbers.
- A window that looks like a GTK demo instead of the Lumn reference.

## The flow (decided with the owner)

Start: "Encore" in the app launcher (rofi drun, any launcher reading `.desktop` files).
Launching again raises the open window instead of starting a second one.
The daemon starts on demand as today (DECISIONS #20).

1. **Home**, the Now Playing window: HD cover with the album-tinted halo, title, artist, seek bar with elapsed and total time, back 15 s, previous, play/pause, next, forward 15 s, volume, which player it follows, and a bottom bar with Lyrics, Look (style, font, size, colors), Glow, Full screen, Desktop lyrics, Lock screen, Settings.
2. **Lyrics**, a panel inside Home (the existing Lyrics page): cover card with controls on the left, synced lines scrolling on the right, current line bright; clicking a line seeks there. Esc returns.
3. **Stage**, full screen: any style (Line, Stack, Constellation, Visual) over a background of either the album art or clear black (only the words and the glow, as in the reels). Moving the mouse fades in a top bar (Exit, style, background, Glow, Look) and a bottom bar (cover thumb, title, seek, transport, volume); 3 s without movement fades them out and hides the pointer. Esc always returns to Home.
4. **Desktop lyrics**: today's see-through, click-through overlay above windows. It never draws the cover, in any style, so it can never cover the screen. Turned off from Home or the tray.
5. **Lock screen**: the existing hyprlock layout. The Home switch "Lock screen lyrics" on selects `Encore.conf` as the HyDE hyprlock layout (today's `hyprlock.sh --select` path) after saving the previous layout name in encore's state; off restores that saved layout. Preview runs `hyprlock.sh --test Encore`. (My call.)

Glow is a switch, not a place: it runs with any of the above or alone.

### Look, styles and backgrounds (my call)

- One shared look (`encore.look`: style, font, size, colors) for Desktop lyrics and Stage, as Verci has one style setting. Changing the style on Stage changes it on the desktop too.
- Visual is a style (the rolling column with the Highlight block and glyphs), not a background. The verci-hero video shows it on black.
- Stage has its own background key, `stage_bg` = `art` or `clear`, valid for every style. Default `art`.
- The desktop overlay ignores the background and never draws the cover; `style=visual` there renders the column only.
- The `show` profile and `encore show` workspace are retired; existing look files stay valid.

### Lifecycle and tray (my call)

- The app is the supervisor while it runs. Closing Home with Desktop lyrics or Glow on keeps the app running in the background with a tray icon (Open Encore, Play/Pause, Next, Desktop lyrics, Glow, Quit). With neither on, closing quits the app.
- With no StatusNotifier watcher (no tray in the bar), closing behaves the same; the way back is the launcher, which presents the existing window.
- Overlay or glow started by keybind with no app running get no tray; launching Encore later picks them up (it reads their pidfiles).
- Quit (tray, Ctrl+Q, Settings) stops the app, the overlay and the glow, whoever started them. The daemon keeps running for hyprlock, as today.
- While Stage is up, the desktop overlay hides itself on that monitor (runtime flag file the overlay already watches for), so lyrics never double up, and comes back when Stage exits. Glow stays on (it is click-through and part of the look in the reels); the Stage bars sit inside the glow band.

### Settings (my call, matches Lumn)

The Settings pill opens the existing popover (glow gradient, animation, thickness, glow, override colors, display, lock screen lyrics, Quit) plus an Encore section: HD covers switch, followed players, start at login.

### Player chip and protocol (my call)

- Picking a player in the chip pins it until that player closes or the user picks again; it is not written to config.
- The app asks the daemon through a runtime file the daemon watches; commands to the player keep going through playerctl with `-p <player>`.
- Protocol v1 grows additive fields: `players` (names of the MPRIS players present) and `volume` (0-1, or null when the player rejects it). Old clients ignore them.

### States every place handles

| State | Behaviour |
|---|---|
| Nothing playing | Home: idle screen, a slow drifting gradient in the theme colors, "Nothing playing", buttons to open the music apps that are installed. Stage: the same drift, no frozen word. |
| Paused | Everything holds and dims slightly; animation timers stop (0% CPU paused, as today). |
| No lyrics | Plain message with the reason from the lookup journal; Stage shows cover, title and artist. |
| Plain lyrics only | Lyrics panel shows them as a static list; Stage shows cover and title. |
| Instrumental or long gap | A soft pulsing note until the next line. |
| Cover small or missing | HD fetch; if still small, the sharp cover at most 1.25x its pixel size, centered on a blurred, color-washed copy of itself; no cover: theme-colored gradient. |
| Two players | Follow the most recently started (as today); the player chip in Home switches. |
| Song change | Words fade out, new cover crossfades in. |
| Volume not supported by the player | Volume control hidden, not dead. |
| Daemon stopped or crashed | The window restarts it and shows "Reconnecting" briefly. |
| Two monitors | Stage goes full screen on the monitor the window is on. |

## Findings that shape the build

- Blur root cause, from the code: `palette.cover_png` shrinks the cover to `512x512>` for hyprlock, the daemon publishes that copy as `track.art`, and `overlay._update_background` scales it to the screen (3.75x on 1920x1080), then dims it 42%, soft-light washes it, pools and vignettes it. Spotify's MPRIS `artUrl` itself is 640x640.
- The overlay process mixes window setup (layer-shell) with rendering (`Overlay.render`, rasters, socket client, look reload). The renderer has to be shareable between the desktop overlay and Stage.
- The player window uses `NON_UNIQUE` plus a pidfile for single instance; a unique `Gtk.Application` gives launcher activation and raising for free.
- The state stream already carries `player`, `status`, `position`, `track.length` and `track.art`, enough for the seek bar.
- Waybar in HyDE has a `tray` module, so a StatusNotifierItem shows up there.

## How (builder's calls, marked as such; owner may override)

- **Entry point** (my call): `Configs/.local/share/applications/org.hyde.encore.desktop` running `hyde-shell encore app`, plus a scalable icon under `Configs/.local/share/icons/hicolor/scalable/apps/`. Unique `Gtk.Application` with id `org.hyde.encore`; activation presents the existing window.
- **One app process** (my call): Home, Lyrics and Stage are pages of one window; Full screen calls `fullscreen()` on that window and swaps to the Stage page, Esc unfullscreens and swaps back. The desktop overlay and glow stay separate processes (DECISIONS #11).
- **Shared renderer** (my call): extract the lyric renderer from `overlay.py` into a widget module with no layer-shell import, used by the desktop overlay (layer-shell host) and by Stage. Stage composites cover, words and controls in its own window, so Visual needs no second TOP-layer window there.
- **HD covers** (verify first): check whether Spotify's `i.scdn.co` serves a size above 640 px (reviewer believes 640 is its maximum); else Apple's public iTunes Search API (artwork up to 3000 px, no key) by artist and album, cached like other art. Match policy (my call): a wrong cover is worse than a small one, so accept Apple's result only when the normalized artist matches and the album or track title matches; otherwise keep the source cover with the small-cover display. Publish the full-resolution cover and the 512 px lock copy as separate fields. On by default (owner, 2026-11-04), with a switch in Settings. Needs a DECISIONS entry.
- **Cover display** (my call): GPU scaling with mipmaps; blur via `snapshot.push_blur` for the backdrop; dimming only where text sits, not a global 42%.
- **Toolkit** (my call): plain GTK4 with our CSS, no libadwaita, to keep the Lumn look and HyDE theming.
- **Tray** (my call): StatusNotifierItem plus `com.canonical.dbusmenu` over `Gio` D-Bus in the app process, no new dependency.
- **Volume and seek**: MPRIS `Volume` and `SetPosition` through the existing playerctl path; hide volume when the player rejects it.
- **Keyboard**: Space play/pause, Left/Right seek 5 s, Up/Down volume, N/P next/previous, L lyrics, F or F11 full screen, Esc back, Ctrl+Q quit.
- **Retired**: the `show` workspace toggle and its toolbar button (Stage replaces it); `visual` as a desktop-overlay style (it moves to Stage).

## Constraints

- Scope (owner, 2026-11-04): HyDE on Hyprland only for this project. Built so a standalone Linux app stays possible later; the upstream-to-HyDE plan stands.
- Hard rules in `AGENTS.md`: HyDE tree layout, `hyde-shell` entry, system `python3`, `encorelib` without `gi`, GPL-3.0, no playerctl commands to the owner's real players during tests.
- New dependencies need a DECISIONS entry; none are expected.
- Perf: Stage animating within the overlay budget (~6.5% of a core target, today's per-style numbers as the ceiling), 0 when paused or hidden; the Home window idle under 1%.

## Verification

- Unit tests for the pure parts: CDN size upgrade, HD candidate choice, idle and no-lyrics state selection, keyboard map.
- E2E on the private bus with `fake_mpris.py`: launch, single instance, seek, volume (supported and not), player switch, close-to-tray, quit.
- `tests/e2e/stage.py` stills of Home, Lyrics, Stage (art and clear, every style), idle, no lyrics, small cover; side by side with `.reference/` frames at full resolution.
- `measure.py --lab` numbers for Stage and Home.
- Owner check on the real screen at the end: open from the launcher, play, go full screen, leave it, close to tray.

## Left to the builder

Widget structure, file split inside `encoregui/`, CSS details, animation curves for the bar fades, the exact idle gradient, test harness extensions.
