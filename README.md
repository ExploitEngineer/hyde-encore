# hyde-encore

Music-reactive ambience for [HyDE](https://github.com/HyDE-Project/HyDE): word-by-word synced lyrics, a beat-reactive screen-edge glow, and album-art driven wallbash colors, plus a lyrics layout for hyprlock.

The tree under `Configs/` mirrors HyDE's own layout so the work can be proposed upstream as pull requests.

## Status

Plan 1 is done: the `encore` service, the lyrics engine and the `Encore` hyprlock layout.
The lyrics overlay, edge glow and full-theme recolor come next.
See `docs/STATE.md`.

## What works today

- `hyde-shell encore daemon` follows the most recently started MPRIS player (Spotify, browsers, anything with MPRIS).
- Lyrics come from local `.lrc` files, then [LRCLIB](https://lrclib.net), then the [Spicy Lyrics API](https://developers.spicylyrics.org) for word-level sync on Spotify when you add a key.
  Lines without word timing get estimated word timing.
- The album cover is run through HyDE's `wallbash.sh` to get a palette for the lyric highlight.
- `hyde-shell encore status` prints the live state as JSON; the same JSON lines stream on `$XDG_RUNTIME_DIR/hyde/encore.sock`.
- The `Encore` hyprlock layout shows the album art, title, artist and the lyric line with sung words highlighted.

## Try it from this checkout

Requirements: HyDE, `python-gobject`, `playerctl`, `imagemagick` (all present on a HyDE install).

```sh
# link encore into your HyDE install (nothing is overwritten)
for f in encore.py encore.sh encorelib; do
  ln -s "$PWD/Configs/.local/lib/hyde/$f" ~/.local/lib/hyde/$f
done
ln -s "$PWD/Configs/.config/hypr/hyprlock/Encore.conf" ~/.config/hypr/hyprlock/Encore.conf

hyde-shell encore daemon          # run in a terminal, play a song
hyde-shell encore hyprlock        # current lyric line as Pango markup
hyde-shell hyprlock.sh --select   # pick the "Encore" lock screen layout
```

To start it with your session, add to `~/.config/hyde/config.toml`:

```toml
[encore]
enable = true

[desktop.start]
encore = "hyde-shell app -u hyde-$XDG_SESSION_DESKTOP-encore.service -t service -- encore.sh daemon --if-enabled"
```

## Configuration

All keys live in `~/.config/hyde/config.toml`; see `Configs/.local/share/hyde/schema/config.toml` for the full list.

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
