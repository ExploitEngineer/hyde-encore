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

## Official assets (public site, verci.xyz / trylumn.xyz, 2026-11-04)
Pulled with REA browser capture + curl into `.reference/site/` (gitignored): verci-hero.mp4 (1600x900, 12 s), verci-styles.png, verci-settings.png, lumn-demo.mp4 (3024x1964, 64 s). We study their public site and videos only; their paid app binary is not decompiled (EULA, and we must not copy their code).

### Three separate UIs (we had merged them - wrong)
1. **Verci menu** (menu-bar dropdown, native NSMenu look): Style list with checks, Keep Screen Awake, Non-lockscreen Visibility, Font list (SF Pro, SF Rounded, New York, Helvetica Neue, Avenir Next, Futura, Didot), Text Size slider + Reset, Display (monitor with check), Color: Auto Sync, **Lyric Text... / Highlight... / Secondary Text...** each with a swatch, Reset Colors, Check for Updates, License, Quit. Dark #1d1a1b, grey section headers, white items, thin separators.
2. **Player window** (Lumn main window, an ordinary app window): dark, rounded art (~240 px) with a thin light ring and an album-tinted radial glow behind it, bold title, dim artist, round controls (15 s back, prev, big play/pause, next, 15 s forward), a "Lyrics" pill + history button, bottom toolbar (palette, waveform, bulb, **Settings** pill, display, lock-screen, window). Hovering the art expands it and tints the window. Lyrics mode: card with art + controls on the left, scrolling lyric list on the right (current line bold white, others dim, fade at the bottom).
3. **Lumn settings popover**: Gradient (1 Color / 2 Colors), Animation (Music Sync / ...), Notch compatibility, Thickness slider, Glow slider, Override album color with **Primary 60% / Secondary 40% color wheels + brightness**, Display picker, Lock screen player, Show in Dock, version/updates, Quit.

### Visual-style column semantics (hero video at 6 fps)
- Three slots scrolling upward: top = word two back (small, often italic), **middle = the word just sung (big)**, **bottom = the word being sung now, on a skewed Highlight-colored marker block**, with an SF-Symbol-like icon beside some words (person, eye, car, play, runner, speech bubble, dice, wind, phone, hourglass, clock).
- Slight 3D drum tilt; ghost overlap during the scroll.
- Three colors: Lyric Text (light pink), Highlight (magenta block), Secondary (mauve); Auto Sync derives all three from the cover.
