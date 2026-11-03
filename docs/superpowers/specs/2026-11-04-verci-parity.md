# Verci parity notes (frame-stepped from the 7 reels, 4 fps)

Source: `.reference/r1..r7.mp4` (local only, never committed). Sheets regenerate with ffmpeg fps=4 tiles.

## Stack ("Fisheye"-family) - measured from r3
- A ROLLING COLUMN of the last 3 sung words, newest at the BOTTOM: sizes ~1.0 / 0.72 / 0.55 of the big word, alphas ~1.0 / 0.6 / 0.35.
- A new word pops in at the bottom (fade+scale, ~100-150 ms) and pushes the column UP with an eased slide (~180 ms) that leaves MOTION-BLUR GHOSTS (2-3 echo copies, alpha-decayed) during the slide.
- Per-word typography from a small set (heavy sans / italic serif / medium sans), seeded per word; capitalization and emoji preserved.
- X positions stagger in a ragged zigzag (~±8% width, seeded).
- Line end: the whole column slides up and out with ghosts (~300 ms); the next line starts with a single word.

## Constellation - measured from r1
- A compact CHAIN, not a whole-screen scatter: each word lands NEAR the previous one (random-walk steps ~80-150 px, biased rightward then wrapping), the cluster lives in the center ~70% x 50% band.
- Consecutive words joined by thin hairlines; sparkles sit ON chain nodes, not randomly.
- Dim past words small (~0.5x), the newest word bright accent ~2.2x with glow.
- LINE CHANGE: the whole cluster FADES OUT together (~260 ms), then the new chain grows from one word.

## Visual mode - measured from r7
- The album art fills the whole screen under the rolling column.
- Words get SEMANTIC GLYPHS: "left" an arrow, "city" a building, "Started" a play triangle, drinks a glass; emoji in the lyric render inline.
- Strong shadows keep text readable on bright art; fast word runs show the same ghost trails.
- The now-playing pill controls float bottom-center.

## Now-playing card - r1/r2/r3/r5/r6
- Rounded-square art ~28-30% of screen height, deep soft shadow, bold title, dim artist.
- A row of 5 circular pill buttons under it and a "Lyrics" pill below; ours renders the row decoratively (the overlay stays click-through).

## Glow - all reels
- Thick (~120-140 px feel), steady and even around the full bezel including the notch and corners; color = album accent; subtle breathing, not strobing.

## Settings panel (r1/r5/r6)
- Style list: Ship, Fisheye, Visual, Fisheye Visual, Codestyle, Codestyle Visual, Branches, Web, Constellation.
- Fonts: SF Pro, SF Rounded, New York, Helvetica Neue, Avenir Next, Futura, Didot. Text Size slider. Color: Auto Sync, Lyric Text, Highlight, Secondary Text, Reset. Display picker.
- Our equivalent stays the rofi menu.

## Build order (parity first, then extras)
1. Stack v2 = rolling column + ghosts + per-word fonts + stagger.
2. Constellation v2 = chain placement + cluster fade on line change.
3. Card v2 = bigger art, shadow, decorative pill rows.
4. New style `visual` = full-bleed cover + rolling column + glyph dict.
5. Glow: thicker default, calmer flow at low energy.
