# hyde-encore

Music-reactive ambience for [HyDE](https://github.com/HyDE-Project/HyDE): an app with word-by-word synced lyrics (in a window, full screen, or over your desktop), a beat-reactive screen-edge glow, and a lyrics lock screen, all colored from the album art.

The tree under `Configs/` mirrors HyDE's own layout so the work can be proposed upstream as pull requests.

## Status

Everything below is in `main`.
A layer-by-layer quality pass is under way (engine, daemon, overlay, glow, player, lock screen); see `docs/STATE.md` for what is verified, what is still rough and what comes next.

## What works today

- `hyde-shell encore daemon` follows the most recently started MPRIS player (Spotify, browsers, anything with MPRIS).
- Lyrics come from local `.lrc` files, then [LRCLIB](https://lrclib.net), then the [Spicy Lyrics API](https://developers.spicylyrics.org) for word-level sync on Spotify when you add a key.
  Lines without word timing get estimated word timing.
- The album cover is run through HyDE's `wallbash.sh` to get the palette for lyrics, glow and lock screen.
- `hyde-shell encore toggle` floats the lyrics above your windows, click-through, in one of four styles:
  - `line`: the current line with a feathered word-by-word fill, the next line dimmed below.
  - `stack`: a rolling column of the last sung words in mixed fonts, with ghost trails as it scrolls.
  - `constellation`: the line grows as a chain of words joined by hairlines, then fades as one cluster.
  - `visual`: the album art fills the screen under the rolling column, the sung word sits on a Highlight marker, some words get a glyph.
- `hyde-shell encore style next` cycles the styles; `hyde-shell encore look font|size|color|next-line|motion|reset` changes the look live.
- `hyde-shell encore glow` toggles a screen-edge glow in the album colors: two comets circle the frame and speed up on the beat when HyDE's cava is running, and it breathes softly without it.
- **Encore** in the app launcher opens the window: HD album art, seek, transport and volume, which player to follow, a Lyrics page, Full screen (lyrics over the cover or clear black, with controls that fade in on mouse motion and Esc always returning), a look menu (style, font, size, lyric colors) and Settings (glow, lock screen, HD covers, players, start at login). Closing it keeps Encore in the tray while desktop lyrics or the glow run.
- `hyde-shell encore profile working|show` applies a sound setup; `hyde-shell encore show` toggles an empty `encore` workspace running the full show.
- `hyde-shell encore status` prints the live state as JSON; the same JSON lines stream on `$XDG_RUNTIME_DIR/hyde/encore.sock`.
- The `Encore` hyprlock layout shows the album art, title, artist and the lyric line with sung words highlighted.

## Try it from this checkout

Requirements: HyDE, `python-gobject`, `playerctl`, `imagemagick` (all present on a HyDE install) and `gtk4-layer-shell` for the overlay and glow.

```sh
# link encore into your HyDE install (nothing is overwritten)
for f in encore.py encore.sh encorelib encoregui; do
  ln -s "$PWD/Configs/.local/lib/hyde/$f" ~/.local/lib/hyde/$f
done
# "Encore" in the app launcher, with its icon
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
ln -s "$PWD/Configs/.local/share/applications/org.hyde.encore.desktop" ~/.local/share/applications/
ln -s "$PWD/Configs/.local/share/icons/hicolor/scalable/apps/org.hyde.encore.svg" \
  ~/.local/share/icons/hicolor/scalable/apps/
# copy, not link: hyprlock.sh does not follow symlinked layouts
cp Configs/.config/hypr/hyprlock/Encore.conf ~/.config/hypr/hyprlock/Encore.conf
```

Then open **Encore** from the app launcher, like any app.
From a terminal the same commands are:

```sh
hyde-shell encore app             # the Encore window (again: brings it forward)
hyde-shell encore toggle          # lyrics on the desktop, on or off
hyde-shell hyprlock.sh --select   # pick the "Encore" lock screen layout
```

Optional binds and the window rule are in `Configs/.local/share/hypr/lua/key_binds.encore.lua` and `window_rules.encore.lua`; copy them into `~/.config/hypr/hyprland.lua`.
The binds are SUPER+ALT+L (lyrics on the desktop), SUPER+ALT+K (next style) and SUPER+ALT+M (open Encore).
In the window: Space play, Left and Right seek, Up and Down volume, N and P next and previous, L lyrics, F full screen, Esc back, Ctrl+Q quit.

Opening Encore, the desktop lyrics or the glow starts the `encore` service when it is not running; "Start at login" in Settings keeps it running from the next login.
To start it with your session too, set `enable = true` under `[encore]` in `~/.config/hyde/config.toml` and add this to `~/.config/hypr/hyprland.lua`:

```lua
hl.on("hyprland.start", function()
  hl.exec_cmd("hyde-shell app -u hyde-" .. (os.getenv("XDG_SESSION_DESKTOP") or "Hyprland")
    .. "-encore.service -t service -- encore.sh daemon --if-enabled")
end)
```

HyDE's `start_up.lua` runs only the `hc.start` keys it names, so a `[desktop.start] encore` entry alone never starts it; the upstream change adds `check_exec(hs.encore)` there (`Configs/.local/share/hypr/lua/start_up.encore.lua`).

## Configuration

All keys live in `~/.config/hyde/config.toml`; see `Configs/.local/share/hyde/schema/config.toml` for the full list.
Changes made live through `encore look`, `encore style` or the window sit on top of these and are kept across reboots.

```toml
[encore]
enable = false
players = []            # e.g. ["spotify"]; empty follows any player

[encore.lyrics]
lrclib = true
spicy_key = ""          # sl_sk_... from developers.spicylyrics.org, Spotify only
dirs = []               # extra folders with "Artist - Title.lrc" files

[encore.hyprlock]
color = ""              # sung words; empty uses the album accent
dim = ""                # unsung words; empty uses album text at 50%

[encore.overlay]
enable = false          # start the overlay with the service
style = "line"          # line, stack, constellation or visual
position = "bottom"     # top, center or bottom
margin = 120
font = "SF Pro Display, Inter, Cantarell, sans-serif"
size = 30
next_line = true
color = ""              # sung words; empty uses the album accent
monitor = ""            # e.g. "eDP-1"
```

## Development

```sh
python3 -m pytest -q
uvx ruff check Configs tests && uvx ruff format --check Configs tests
python3 tests/e2e/fake_mpris.py --art /path/cover.png &   # scriptable MPRIS player
playerctl -p encoretest play
```

## License

GPL-3.0, same as HyDE.
