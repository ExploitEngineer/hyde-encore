# Product

## Who and why
HyDE users who listen to music while they work.
macOS has paid apps for this (Verci: word-by-word lock screen lyrics, Lumn: beat-synced edge glow, both $9.99).
Linux has scattered pieces and nothing integrated with a desktop theme.
Also a showcase for an Instagram video.

## Pieces
1. Word-by-word synced lyrics overlay (any MPRIS player).
2. Beat-reactive glow around the screen edges.
3. Album art drives wallbash, so the whole theme follows the song.
4. hyprlock layout with live lyrics.

## Non-goals
- Being a music player.
- Shipping as a standalone app outside HyDE (for now).

## Quality bar
Mergeable upstream: HyDE code style, no new heavy deps without reason, smooth on NVIDIA Wayland, pixel-clean in the video.

## Prior art
- Word-level lyrics: BEST8OY/LyricsMPRIS-Rust (MIT, Musixmatch richsync), dd1o7/DSAlyrik (MIT, Verci-like styles, Spicy Lyrics), wshowlyrics (Wayland overlay, LRCX), Mohit-Aasirwal/undertone (MIT, Python/GTK lyrics + audio ring).
- Edge glow: stefanomainardi/hypr-ringlight (GPL-3, Rust layer-shell, no audio).
- Audio capture: slastra/hyprglaze (PipeWire), HyDE's own `cava.py`.
- Timing sources: LRCLIB is line-level only; word-level needs Musixmatch richsync or Spicy Lyrics API, else estimated.
