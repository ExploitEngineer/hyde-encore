# hyde-encore

Music-reactive ambience for [HyDE](https://github.com/HyDE-Project/HyDE): word-by-word synced lyrics over your desktop, a beat-reactive screen-edge glow, a player window, and a lyrics lock screen, all colored from the album art.

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
- `hyde-shell encore menu` opens the player window: album art, transport controls, a Lyrics view with the whole song scrolling, a look menu (style, font, size, lyric colors) and a Settings popover for the glow (gradient, animation, thickness, glow, override colors).
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
# copy, not link: hyprlock.sh does not follow symlinked layouts
cp Configs/.config/hypr/hyprlock/Encore.conf ~/.config/hypr/hyprlock/Encore.conf

hyde-shell encore daemon          # run in a terminal, play a song
hyde-shell encore toggle          # lyrics overlay on or off
hyde-shell encore menu            # player window
hyde-shell hyprlock.sh --select   # pick the "Encore" lock screen layout
```

Suggested binds and the player window rule are in `Configs/.local/share/hypr/lua/key_binds.encore.lua` and `window_rules.encore.lua`; copy them into `~/.config/hypr/hyprland.lua`.
The binds are SUPER+ALT+L (overlay), SUPER+ALT+K (next style), SUPER+ALT+M (player) and SUPER+ALT+E (show workspace).

To start it with your session, add to `~/.config/hyde/config.toml`:

```toml
[encore]
enable = true

[desktop.start]
encore = "hyde-shell app -u hyde-$XDG_SESSION_DESKTOP-encore.service -t service -- encore.sh daemon --if-enabled"
```

## Configuration

All keys live in `~/.config/hyde/config.toml`; see `Configs/.local/share/hyde/schema/config.toml` for the full list.
Changes made live through `encore look`, `encore style` or the player window sit on top of these and reset on reboot.

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
style = "line"          # line, stack or constellation
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
