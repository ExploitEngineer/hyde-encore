# hyde-encore design

Date: 2026-11-03.
Status: original design, built through Plans 1-3 and later branches.
Where it differs, `docs/DECISIONS.md` wins: the player window and look menu replace the no-settings-GUI non-goal (#15, #16), the glow runs in its own process (#13, #14), and there are four overlay styles (#12, #17).
Working name: hyde-encore (final name still open, rename is cheap).

## Intent

macOS users pay $9.99 each for Verci (word-by-word lyrics on the lock screen) and Lumn (screen-edge glow that pulses with the beat, colored from the album art).
Linux has the raw pieces scattered across small projects and nothing that feels like part of the desktop.
hyde-encore makes music a first-class part of HyDE: lyrics that light up word by word over your work, a glow around the screen that breathes with the beat, a lock screen that keeps singing, and colors that follow the album cover.

Two audiences:

1. The owner, who wants it daily and wants a jaw-drop Instagram video of it.
2. HyDE users, through pull requests to HyDE-Project/HyDE that maintainers will merge.

The second audience sets the engineering bar: everything must look like HyDE wrote it.

## Goals

- Word-by-word synced lyrics overlay for any MPRIS player (Spotify, mpv, browsers, YouTube Music in a browser).
- Beat-reactive glow on the screen edges, per monitor.
- Album-art palette driving the overlay, glow and lock screen.
- Opt-in mode where the whole HyDE theme (waybar, borders, kitty, rofi, everything wallbash touches) recolors per track.
- A hyprlock layout with album art, track info and a live lyric line.
- Configurable through HyDE's own `config.toml`, controllable through `hyde-shell encore ...`.
- Upstreamable as 3-4 focused PRs.

## Non-goals

- Being a music player or controlling playback beyond what playerctl already does.
- A settings GUI. Config lives in `config.toml` like the rest of HyDE.
- Supporting compositors other than Hyprland in the first version (layer-shell code will happen to work on others, but nobody tests it).
- Translating or romanizing lyrics.
- Shipping outside HyDE (AUR package, Flatpak) for now.

## Anti-goals (it fails even if it works, if...)

- It drops frames or makes the desktop stutter on the owner's NVIDIA Quadro P1000 laptop.
- It burns CPU or GPU while music is paused or nothing is playing (must idle at roughly zero).
- The overlay ever takes focus, eats clicks, or shows up in alt-tab, screenshots tools' window pickers, or the taskbar.
- Full-theme mode makes every track change visibly reload apps and flicker, or thrashes when skipping through songs.
- It uses lyric sources that break a service's terms (no Musixmatch scraping), which would also get the PR rejected.
- It looks or reads like a foreign project bolted onto HyDE.

## Constraints

- Target: Hyprland 0.56 with HyDE's Lua configuration (`~/.local/share/hypr/hyde.lua`, keybinds in `lua/key_binds.lua`, user overrides in `~/.config/hypr/hyprland.lua`).
- Repo layout mirrors upstream exactly:
  - scripts in `Configs/.local/lib/hyde/`
  - hyprlock layouts in `Configs/.config/hypr/hyprlock/`
  - wallbash templates in `Configs/.config/hyde/wallbash/{always,theme}/` with scripts in `.../wallbash/scripts/`
  - config defaults in `Configs/.local/share/hyde/schema/config.toml` and `schema.toml`
- Languages: Python 3 (PyGObject) for the daemon and overlay, Bash for glue, Lua only where Hyprland config needs it.
  This matches HyDE's `cava.py` and `mediaplayer.py`.
- Python uses HyDE's `pyutils` (`logger`, `xdg_base_dirs`) the way `mediaplayer.py` does.
- Dependencies, preferring what HyDE already ships:
  - existing: `playerctl` (core), `cava` (extra), `hyprlock`, `imagemagick` (wallbash), `python-gobject`.
  - new: `gtk4-layer-shell` (official Arch repo, already installed on the owner's machine). Needs a DECISIONS.md entry and an entry in HyDE's `Scripts/pkg_extra.lst` in the PR.
  - HTTP via Python stdlib `urllib` to avoid adding `python-requests` as a hard dependency.
- Known gotcha: gtk4-layer-shell from Python requires `libgtk4-layer-shell.so` to be loaded before `libwayland-client`.
  The launcher must handle this (for example by `LD_PRELOAD` in the wrapper that starts the overlay), not the user.
- Upstream contribution rules: PRs target the `dev` branch, must pass `pre-commit run --all-files` (luacheck, markdownlint, file hygiene), and user-facing changes add a `CHANGELOG.md` entry.
  The owner's global rule forbids hand-editing changelogs; the agreed exception is HyDE's `CHANGELOG.md` inside upstream PR branches only.
- License GPL-3.0. Any code adapted from MIT projects (LyricsMPRIS-Rust, Undertone, DSAlyrik) keeps its notice.

## Decisions made by the owner (2026-11-03)

1. The lyrics overlay sits above windows, click-through, toggled by a keybind.
2. Word timing comes from a clean source chain: local `.lrc` files and LRCLIB (enhanced LRC when it has word tags), then the Spicy Lyrics API when the user adds a free key, else estimated word timing.
   No Musixmatch.
3. Album-art colors always drive encore's own pieces (overlay, glow, lock screen).
   Recoloring the whole HyDE theme per track is opt-in.
4. Upstream path: open a GitHub Discussion on HyDE first to gauge interest (owner approves before anything is posted), then 3-4 small PRs to `dev`.

## How it fits together

```text
 MPRIS players ──playerctl──► encore.py daemon ◄── cava.sock (HyDE cava.py manager)
                                │  lyrics fetch + cache, word clock, beat energy,
                                │  cover art -> palette (wallbash.sh)
                                ▼
                     $XDG_RUNTIME_DIR/hyde/encore.sock  (JSON lines)
              ┌─────────────────┼────────────────────┬──────────────────────┐
              ▼                 ▼                    ▼                      ▼
     overlay process     edge glow (same      hyprlock label         opt-in full theme
     (GTK4 layer-shell)  process, per-monitor  `hyde-shell encore     (HyDE color pipeline
     lyrics              layer surfaces)       hyprlock`              fed the cover art)
```

### 1. `encore.py` daemon

One long-running process, modelled on `cava.py`'s manager/client pattern and `mediaplayer.py`'s Playerctl handling.

- Follows the active MPRIS player via `gi.repository.Playerctl`, including player switches, seeks, pause and track changes.
- Keeps a smooth playback clock: player position plus monotonic interpolation, resynced on seek and periodically.
- Fetches lyrics through the provider chain in Decision 2, caches results under `$XDG_CACHE_HOME/hyde/encore/`, never refetches a cached track, and handles "no lyrics found" and instrumental tracks gracefully.
- Parses plain LRC, enhanced LRC (`<mm:ss.xx>` word tags) and the Spicy Lyrics response into one internal model: lines, each with words and start/end times.
- Spicy Lyrics provider (ships in v1, Claude's call): `GET api.spicylyrics.org/v1/lyrics/{spotifyTrackId}` with a Bearer key the user creates at developers.spicylyrics.org.
  It is keyed by Spotify track ID, so it only applies when the MPRIS player is Spotify (track ID from `mpris:trackid`).
  The response `Type` is `Syllable` (word-level), `Line` or `Static`.
  When `source` is the Spicy community catalogue, its terms require crediting the uploader and maker, so the overlay shows a small credit line.
  The docs site renders client-side and could not be read during design; the builder confirms the exact JSON field names from the live docs or a real response before writing the parser and its fixture tests.
  This is the user's own key against an official developer API, so it does not carry the Musixmatch terms problem.
- When only line timing exists, estimates word timing inside each line (weighted by word length or syllables; the builder picks the heuristic and tunes it by eye).
- Reads beat/energy from HyDE's existing `cava.sock` instead of running its own audio capture, and starts the cava manager if it is not running.
- Fetches the cover art (MPRIS `mpris:artUrl`, local file or http), runs HyDE's `wallbash.sh <cover> <cache-prefix>` to get a palette, and caches it per album.
- Broadcasts state over `$XDG_RUNTIME_DIR/hyde/encore.sock` as JSON lines: track metadata, current line and word with progress, next line, palette, beat energy, playing/paused.
- Runs the `hyde-shell encore` subcommands: `daemon`, `toggle` (overlay on/off), `glow` (on/off), `hyprlock` (prints one formatted line for hyprlock), `status`.

### 2. Lyrics overlay

- GTK4 window made a layer surface on the overlay layer via gtk4-layer-shell: no keyboard interactivity, empty input region (click-through), not in any window list.
- Shows the current line with a progressive fill across each word as it is sung, plus a dimmer next line; lines transition with a short fade or slide.
- Colors from the album palette, font from HyDE's configured font, position and size configurable (default bottom-center, above waybar).
- Draws only while playing; when paused or idle it stops its frame clock (no busy loop).
- Hidden automatically when no lyrics are available, with an optional "no lyrics" hint.

### 3. Edge glow

- Lives in the same process as the overlay (one GTK app, shared frame clock and socket connection).
- Per-monitor layer surfaces that draw a soft glow along the screen edges, intensity and color driven by beat energy and the palette.
- Modes: `beat` (pulses with the music) and `idle` (steady low glow), plus thickness, intensity and per-monitor enable.
- Must respect rounded corners and not cover waybar unreadably.

### 4. hyprlock layout

- New layout `Configs/.config/hypr/hyprlock/Encore.conf`, selectable through HyDE's existing `hyde-shell hyprlock.sh` layout picker.
- Shows the background, time, album art (from encore's cache), track and artist, and a lyric label using `cmd[update:<ms>] hyde-shell encore hyprlock` that prints Pango markup with sung words highlighted.
- Falls back to a normal clean lock screen when nothing is playing.
- Must still lock correctly if the encore daemon is not running.

### 5. Album-art colors

- Default: encore's own pieces take their colors from the cover palette.
- Opt-in `follow_album` mode recolors the whole HyDE theme from the cover, reusing HyDE's own color pipeline rather than reimplementing it.
  - Debounced: only applies after a track has played for a few seconds, so skipping through songs does not thrash.
  - Restores the wallpaper-derived colors when playback stops for a configurable time.
  - Never overwrites the user's persistent theme or wallpaper state; the wallpaper colors must come back exactly.
  - Starts with a timeboxed spike (Claude's call): measure what `color.set.sh` driven by a cover image reloads and how visible it is.
    If the full path flickers, ship a lighter in-place update of the pieces that can recolor live (Hyprland borders via `hyprctl`, kitty via remote control, encore itself) and leave the rest to the next wallpaper change.
    The spike result is recorded in DECISIONS.md before PR 4 is built.
- A wallbash template for encore itself lives under `wallbash/always/` so encore also follows normal wallpaper changes when no music is playing.

### 6. Configuration and control

- New `[encore]` section (and subsections such as `[encore.overlay]`, `[encore.glow]`, `[encore.lyrics]`) in HyDE's `config.toml` defaults and `schema.toml`, mirroring how `[cava.*]` and `[mediaplayer]` are done.
- Spicy Lyrics key read from config or an environment variable, never committed.
- Autostart only when `[encore] enable = true`, through HyDE's existing startup mechanism.
- No default keybind in the upstream PR, to avoid collisions; this repo documents a suggested bind for `~/.config/hypr/hyprland.lua`.

## Quality bar

- Measured targets (Claude's call) on the owner's laptop (eDP-1, 1920x1080 at 60 Hz, scale 1, NVIDIA Quadro P1000):
  - while playing with overlay and glow on: no dropped frames at 60 Hz, overlay+glow process under 5% of one CPU core on average;
  - paused or nothing playing: no frame clock running, under 1 wakeup per second, effectively 0% CPU;
  - measured with `top`/`pidstat` and `nvidia-smi` and recorded in STATE.md.
- The cava manager shuts down when it has no clients; the daemon holds one client connection only while playing, so cava also stops when music stops.
- Glow starts with the cheapest technique that meets the targets; switch to a GL area only if measurements demand it.
- Lyrics never drift visibly from the singer on a normal track; seeking resyncs within a fraction of a second.
- Pixel-clean in screen recordings: no clipped glyphs, no flicker on line change, no hard edges on the glow.
- Unit tests for the LRC/enhanced LRC/Spicy parsers, the word-timing estimator and the playback clock (fake clock).
- End-to-end checks on the owner's real desktop with Spotify and one browser player before each PR.
  HydeVM is optional upstream and needs Nix, which is not installed here; it is skipped unless the owner wants Nix installed (Claude's call).
- Passes HyDE's pre-commit hooks.

## Build order and module split (builder-review resolution, Claude's call)

Build daemon-first in this repo, because the owner uses the full feature set daily and the video needs all of it.
Keep the logic in small library modules with no daemon or GTK dependency, so the upstream PRs can be carved out cleanly afterwards:

- lyrics: providers, parsers, cache, word-timing estimator
- clock: playback clock with interpolation and resync
- palette: cover art fetch and `wallbash.sh` palette, cached per album
- the daemon wires these together; the overlay and glow process only consumes the socket

Every consumer degrades without the daemon: `hyde-shell encore hyprlock` prints track and artist straight from playerctl (no lyrics) when the socket is absent.

## Upstream PR plan (revised after builder review, Claude's call)

1. hyprlock `Encore.conf` layout: album art, track and artist via `hyde-shell encore hyprlock`, works with no daemon. Smallest and standalone.
2. `encore.py` daemon with lyrics, clock and palette modules, the lyrics overlay, the lyric line in the hyprlock layout, config schema, and the `gtk4-layer-shell` dependency.
3. Edge glow.
4. `follow_album` full-theme recolor.

The earlier idea of a waybar media palette PR is dropped: waybar CSS is static and recoloring it per track means reloads, which fights the no-flicker anti-goal.
Each PR stands on its own and includes its CHANGELOG entry.
This repo keeps the full feature set and is the source for the PR branches.

## Success

- The owner keeps it on daily.
- A 15-30 second clip where a song changes and the lyrics, glow, lock screen and (in full mode) the whole desktop shift to the new album's colors.
- At least the first upstream PR merged into HyDE `dev`.

## Left to the builder

- Internal module split inside `Configs/.local/lib/hyde/` (single `encore.py` or a small `encore/` package next to `pyutils`).
- Rendering technique for the glow (Cairo, GL area, or snapshot API) as long as the performance anti-goal holds; measure it.
- Exact word-timing estimation heuristic.
- JSON line schema on `encore.sock`.
- Animation curves, fonts sizes and default colors within HyDE's look.
- Cache eviction policy.

## Open

- Final project name.
