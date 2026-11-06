# Product

## Who and why
HyDE users who listen to music while they work.
macOS has paid apps for this (Verci: word-by-word lyrics on the desktop and lock screen, Lumn: beat-synced edge glow and a player window, both $9.99).
Linux has scattered pieces and nothing integrated with a desktop theme.
Also a showcase for an Instagram video.

## Positioning
Match Verci and Lumn look for look and motion for motion, then beat them: free, any MPRIS player, colors that belong to the HyDE theme, no scraped lyric sources.

## Pieces
1. The Encore app (`org.hyde.encore`, in the launcher): Home (HD cover, seek, transport, volume, which player to follow), a Lyrics page, and Full screen with the lyrics over the cover or clear black and controls that fade in on mouse motion.
2. Word-by-word synced lyrics (any MPRIS player) in four styles: line, stack, constellation, visual; the same renderer draws them on the desktop (click-through, never covering the screen) and in Full screen.
3. Beat-reactive glow around the screen edges, with its settings in the app.
4. hyprlock layout with live lyrics, switched on and off from the app.
5. Album art drives encore's colors; the whole HyDE theme following the song is opt-in (not built yet).

## Non-goals
- Being a music player; the window remotes whatever MPRIS player is playing.
- Shipping as a standalone app outside HyDE (for now); the app is built so that stays possible.

## Quality bar
Side by side with the reference frames in `.reference/`, ours holds up at full resolution: same layout and motion timing, no clipped glyphs, no flicker.
Smooth on NVIDIA Wayland within the perf budget, idle at zero when paused.
Mergeable upstream: HyDE code style, no new heavy deps without reason.

## Prior art
- Word-level lyrics: BEST8OY/LyricsMPRIS-Rust (MIT, Musixmatch richsync), dd1o7/DSAlyrik (MIT, Verci-like styles, Spicy Lyrics), wshowlyrics (Wayland overlay, LRCX), Mohit-Aasirwal/undertone (MIT, Python/GTK lyrics + audio ring).
- Edge glow: stefanomainardi/hypr-ringlight (GPL-3, Rust layer-shell, no audio).
- Audio capture: slastra/hyprglaze (PipeWire), HyDE's own `cava.py`.
- Timing sources: LRCLIB is mostly line-level (its `hasWordSync` / `lyricsfile` fields are under evaluation); word-level needs Musixmatch richsync (rejected) or the Spicy Lyrics API, else estimated.
