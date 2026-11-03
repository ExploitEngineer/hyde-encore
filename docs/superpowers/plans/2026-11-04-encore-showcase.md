# hyde-encore Plan 3: Showcase styles and edge glow

> Deadline plan (owner: deliver tonight). Inline execution, TDD on pure logic, lean steps.

**Goal:** Three overlay styles switchable live (`line`, `stack`, `constellation`) plus a beat-pulsing screen-edge glow, matching and beating the Verci/Lumn reels.

**Spec anchors:** design doc section 2-3; reel analysis in STATE.md (constellation word-map, stacked mixed-font words, bezel glow).

## Global Constraints
- All Plan 1/2 constraints hold (tree, system python3, no gi in encorelib, commit style).
- No new per-frame work while nothing changes: constellation and stack redraw on word boundaries and short fades only; glow animates only while playing.
- Styles live in the existing overlay process; glow is its own process (`encore.py glow`, flock pidfile, `encore glow` toggle) so lyrics and glow toggle independently.
- Live style switch: `hyde-shell encore style <name|next>` writes `$XDG_RUNTIME_DIR/hyde/encore.style`; the overlay's existing runtime-dir monitor picks it up. Config default `[encore.overlay] style`.
- Glow beat source: HyDE `cava.sock` when present (attack/decay envelope over bar average), else a slow breathe; color follows the album accent from `encore.sock`.

## Tasks
1. `encorelib/constellation.py`: pure seeded placement. `place_words(words, width, height, seed, margin, min_dist) -> list[(x, y)]` deterministic, inside margins, pairwise min distance, left-to-right meander; `sparkles(seed, width, height, k)` positions. Tests: determinism, bounds, spacing, count, distinct seeds differ.
2. `encorelib/lyricview.py`: `current_word_index(view) -> int` (last word with fill > 0, -1 before first) and `next_word_boundary(state, now) -> float | None` (seconds to the next start or end, rate-aware). Tests RED→GREEN.
3. `encorelib/config.py`: `overlay_style` (`line|stack|constellation`, default line, bad value falls back) + env `ENCORE_OVERLAY_STYLE`. `stream.py`: `read_style(path) -> str | None`. Tests.
4. `encoregui/overlay.py`: style dispatch. Stack renderer (prev small dim italic serif above, current huge accent glow, next small dim below, 140 ms pop fade). Constellation renderer (full-screen window in those styles; words appear as sung at seeded positions, past words small dim, current big accent, hairlines between consecutive words, seeded sparkles, 260 ms line fade). Word-surface cache. Scheduling via `next_word_boundary` timeouts plus short fade timers. Style file watch + `encore style` CLI.
5. `encoregui/glow.py` + `encore.py glow` + `encore glow` toggle: four edge-strip layer windows (overlay layer, click-through), vertical/horizontal gradients in the accent, intensity = idle glow + beat envelope from cava.sock (reconnecting client, optional), paused = static dim, stopped/no art = wallpaper accent. ~30 fps only while playing.
6. Measure (styles swap into measure harness; glow measured playing/paused), smoke screenshots, schema/README/STATE, commit, review, merge.

## Review Focus
1. Style switch mid-song: no stale words from the previous style, no double timers.
2. Constellation on a track change mid-line: fade out, never mixed songs.
3. Glow with no cava socket: still breathes; cava appearing later gets picked up.
4. Two styles' timers never run at once; paused/hidden = zero timers in every style.
5. Stack with one-word lines and instrumental gaps.
