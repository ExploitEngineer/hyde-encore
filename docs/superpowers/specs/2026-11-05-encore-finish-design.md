# Encore, finished: design

Date: 2026-11-05.
Owner's brief: "make this product the finest thing I have ever seen; I want the final product; get the design and animation ideas from Pinterest, Awwwards, software"; no further questions.
Every call below is the builder's; the owner reviews the result on screen.

## Intent

The app (spec 2026-11-04) is the skeleton: launcher, one window, escapable full screen, sharp covers.
This pass gives it a visual identity and motion worth showing: the album lights the room.
Every surface takes its light, color and rhythm from the cover and the words; nothing is decorated for its own sake.

## Direction (from the research, 2026-11-05)

- Apple Music lyrics: the active line floats (bright, slightly larger), past and future lines recede (dimmer, softer), words reveal left to right from their own timestamps.
- Verso / Cotodama: typography as the picture; words held longer are set larger; two faces in one line; sync leads by about 160 ms; hover dims the words.
- Verci: timings stay the same across styles; a convex "lens" stack with the current word closest to the glass; symbols pop in beside words.
- Lumn: the dark window, the album halo, round controls, the Lyrics card with a fade at the bottom (reference frames `.reference/site/frame-7.png`, `frame-16.5.png`).
- 2026 player redesigns: bigger art, thicker scrubber, fewer labels; frosted panels over blurred art; album-color mesh gradients; spring-like easing.

## Identity

- Dark first. Base `#141317`; every tint comes from the album scheme (`encorelib/colors.py`): accent, accent2, highlight, lyric, secondary.
- Type: SF Pro Display for UI and lyrics (as the references); Instrument Serif Italic for the serif words of the column styles and for one display moment (the idle title); tabular figures everywhere digits align.
- Light: the window's background is the cover, blurred large and darkened, with three album-colored blobs drifting over it (the "album field"); it breathes at 6 fps while playing and holds still when paused or hidden.
- Glass: bars and popovers sit on frosted panels (a blurred crop of what is behind them, tinted), with a 1 px light edge on top and a soft shadow.
- Motion: everything eases out (cubic, 200-320 ms); one orchestrated moment per transition; the words set the rhythm; `motion=false` in the look turns every decorative drift off.

## Screens

### Home
- Cover 256 px, radius 9%, ring, soft shadow; hover grows it to 320 px over 220 ms and the field brightens.
- Title 24 px / 800, artist 15 px / 500 secondary; both ellipsized at 34 / 40 chars.
- Scrubber 6 px thick, rounded, accent fill with a 14 px knob that glows in the accent; elapsed and total in 12 px tabular figures.
- Transport: five round buttons; play 60 px filled lyric-color with a dark glyph; hover lifts (background brightens, 120 ms), press darkens.
- Lyrics pill + volume (speaker + 140 px slider) in one row.
- Chip (player) top left, status top center, both quiet (12 px, secondary).
- Bottom bar: round glass buttons; `on` state is an accent ring + tint; tooltips unchanged.
- Page change Home <-> Lyrics: slide left/right 280 ms with crossfade.

### Lyrics (the list)
- A snapshot widget (`LyricList`), not labels: each line a cached raster (`LineRaster`, SF Pro Display 26 px / 700), laid out in a column with 18 px gaps.
- Depth by distance from the current line: scale 1.0 / 0.94 / 0.9, opacity 1.0 / 0.55 / 0.32, blur 0 / 1.5 / 3 px (capped at two steps; farther lines share the last step).
- The current line fills word by word with the same feathered sweep as the overlay's line style, in the lyric color over secondary.
- Scroll eases to keep the current line at 38% of the card height (cubic, 420 ms); top and bottom fade out over 90 px.
- Click a line to seek; hover lifts a line to opacity 0.7.
- States (waiting, no lyrics, plain, idle) keep today's wording, set in the same type.

### Full screen
- Backdrop as today (fill or framed) plus the album field drifting under a `clear` background, so Clear is black light, not a void.
- Bars: glass over the blurred backdrop crop; top bar slides down 12 px and fades in (200 ms), bottom bar slides up; both hide after 3 s; the pointer hides with them.
- Entering: the Home cover grows toward the backdrop over 320 ms while the page crossfades (the window fullscreens at once); leaving reverses it.
- Style change: the current words exit as the style's own exit, the new style enters on the next word (no blank frame).

### Idle (nothing playing)
- The field in the last cover's colors with a fine static grain (a tiled 128 px texture at 4% opacity), "Nothing playing" in Instrument Serif Italic 40 px, the hint and the app buttons as today.

### Settings and look menu
- Frosted panel, section eyebrows 11 px uppercase with letter-spacing, 1 px separators at 8% white, controls as today.

## Lyric styles (motion)

Targets from `docs/superpowers/specs/2026-11-04-verci-parity.md` and the hero video, judged on clips (`stage.py --clip`) against `.reference/site/verci-hero.mp4` frames:
- Common: timings constant across styles; pop 150 ms, slide 200 ms, exit 260 ms (today's values stand unless the clips show otherwise); sync lead 120 ms (words light a touch early, as the ear expects).
- Line: the current line floats (full lyric color, 1.0), the next line recedes (secondary, 0.72, blurred 1.5 px); the word sweep keeps its feathered edge.
- Stack and Visual: the big word's scale follows its held duration (1.0 at 0.3 s to 1.18 at 1.2 s and above); serif words set in Instrument Serif Italic; emoji in the lyric render inline (Noto Color Emoji); glyphs pop in with the word (scale 0.6 -> 1 over 150 ms).
- Constellation: sparkles pulse on the current node (1 Hz, 0.6-1.0); hairlines draw in over 120 ms.
- Lens (new, optional): the stack projected on a convex surface: each slot scaled by cos of its angle from the center and shifted toward it, the current word largest and nearest; no shaders.

## Constraints

- No new dependencies; fonts and emoji already installed are used, with fallbacks (serif -> Noto Serif Italic).
- Perf budgets hold: window playing under 4%, paused under 1.5%, idle under 3% of a core; full screen at or under today's per-style numbers (line 12%, stack 19%, constellation 4%, visual 24.5%), 0 when paused or hidden; desktop overlay unchanged.
- Every visual change is judged on stills or clips from the hidden monitor, side by side with the reference at full resolution; perf claims come from `measure.py --lab`.
- Tests stay green; lab tests stay green; ruff clean; no agent attribution.

## Out of scope

- New lyric sources, multi-monitor copies, the standalone app, the wallbash template, sound.

## Verification

- Stills: Home (playing, paused, hover), Lyrics, Full screen (every style on cover and clear, bars up and down), Settings, idle; each next to its reference frame.
- Clips: 6 s of each style in full screen and on the desktop, frame-stepped against the hero video.
- `measure.py --lab --app home` and `--app full --style S` for every style; `python3 -m pytest -q`; `-m lab`.
