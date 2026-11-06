# Encore Finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Encore app its visual identity and motion: the album field, glass, Apple-like lyric depth, orchestrated transitions, polished lyric styles.

**Architecture:** New snapshot widgets in `encoregui/` (`field.py` album field, `lyriclist.py`, `glass.py`) reuse `scene.py` nodes and `lyrics.LineRaster`; CSS tokens in `ui.py`; motion constants in `lyrics.py` tuned against the hero video; pure helpers in `encorelib` (`motion.py` for easing and held-word scale, `depth.py` for list depth) unit-tested.

**Tech Stack:** GTK4 snapshot nodes (textures, blur, opacity, masks), Pango rasters, cairo for one-time rasters, pytest, ruff; stage.py and measure.py on the hidden monitor.

**Spec:** `docs/superpowers/specs/2026-11-05-encore-finish-design.md`

## Global Constraints

- Budgets: window playing under 4%, paused under 1.5%, idle under 3%; full screen line <= 12%, stack <= 19%, constellation <= 4%, visual <= 24.5%; paused and hidden 0 ticks; desktop overlay numbers unchanged (line 9-10%, stack 17%).
- Every visual task ends with stills (and clips where motion changed) on the hidden monitor, compared at full resolution with the reference frames; the comparison sheet is saved under `.stage/finish-<task>/`.
- `motion=false` disables drift, grain motion and decorative pulses.
- No new dependencies; GPL-3.0; commits in upstream style; no agent attribution; branch `feat/encore-app` (PR #18 grows).
- Lint and tests green at every commit: `uvx ruff check Configs tests`, `uvx ruff format --check Configs tests`, `python3 -m pytest -q`; `-m lab` at the end of Tasks 3 and 7.

## Review Focus

1. A song with no cover (podcast, local file): the album field and glass fall back to the theme palette without a blank or black window (Task 1: `test_field_palette_without_cover`).
2. A 200-line song in the Lyrics list: scrolling stays smooth and memory bounded (rasters are a byte-bounded LRU, Task 2: `test_depth_steps_cap`, lab still with the long LRC).
3. Full screen entered while paused: no drift, no pulse, 0 ticks after the entry animation (Task 3: measure paused).
4. A word held for 8 s (a long note): the big word's scale caps at 1.18 and the pulse does not start inside a live word (Task 4: `test_held_scale_caps`).
5. Reduced motion (`motion=false`): the field holds, the list still scrolls to the current line (Task 1 and 2 lab stills with `--look motion=false`).

---

### Task 1: Album field, tokens and Home identity

**Files:**
- Create: `encoregui/field.py`, `encorelib/motion.py`
- Modify: `encoregui/ui.py` (tokens and CSS), `encoregui/app.py` (background stack uses `AlbumField`), `encoregui/home.py` (sizes, scrubber, play button), `encoregui/idle.py` (grain, serif title)
- Test: `tests/test_motion.py`, lab stills `.stage/finish-1/`

**Interfaces:**
- `motion.ease_out(t: float) -> float` (cubic), `motion.ease_in_out(t) -> float`, `motion.lerp(a, b, t)`, `motion.blob_center(t, orbit, period, phase)` (moved from idle.py), `motion.grain_texture_bytes(size: int = 128, seed: int = 7) -> bytes` (BGRA premultiplied, white noise alpha 0-255).
- `field.AlbumField(Gtk.Widget)`: `set_cover(path: str)`, `set_colors(colors: Scheme)`, `set_playing(playing: bool)`, `set_motion(motion: bool)`, `set_grain(on: bool)`; draws the blurred cover (cached texture via the renderer, 80 px blur, 0.55 black wash) under three blobs from `colors` (accent, accent2, highlight) and the grain; ticks at 6 fps only while mapped, not suspended, playing and motion on.
- `ui.CSS` tokens as CSS custom properties are not available in GTK CSS, so tokens are Python constants (`UI_BASE`, `UI_FG`, `UI_DIM`, `GLASS_FILL`, `GLASS_EDGE`) rendered into the CSS string once.

- [ ] **Step 1: Write the failing tests**

```python
def test_ease_out_is_monotonic_and_bounded():
    xs = [ease_out(i / 20) for i in range(21)]
    assert xs[0] == 0 and xs[-1] == 1 and all(b >= a for a, b in zip(xs, xs[1:]))
    assert ease_out(0.5) > 0.5  # eases out: fast start

def test_blob_center_stays_inside():
    for t in range(0, 120, 7):
        x, y = blob_center(t, (0.22, 0.16), (41.0, 29.0), 0.0)
        assert 0.28 <= x <= 0.72 and 0.34 <= y <= 0.66

def test_grain_texture_is_fine_and_faint():
    data = grain_texture_bytes(128, seed=7)
    assert len(data) == 128 * 128 * 4
    alphas = data[3::4]
    assert 20 < sum(alphas) / len(alphas) < 60  # faint on average
    assert grain_texture_bytes(128, seed=7) == data  # stable
```

- [ ] **Step 2:** Run `python3 -m pytest -q tests/test_motion.py`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `encorelib/motion.py`; move `blob_center` out of `idle.py` (idle imports it).
- [ ] **Step 4:** Implement `field.AlbumField`; `app.py` replaces the cairo `backdrop` DrawingArea and the idle stack with one `AlbumField` (idle = no cover: blobs in the scheme's colors plus grain; playing = cover under blobs at 0.6 strength); hover expansion raises blob strength through `set_hover(0..1)`.
- [ ] **Step 5:** `ui.py`: type scale (title 24/800, artist 15), scrubber 6 px with a glowing 14 px knob, play button 60 px filled (`button.round.play`), hover and press transitions (`transition: background-color 120ms, box-shadow 120ms`), glass pills (fill `rgba(28,26,34,0.62)`, edge `rgba(255,255,255,0.12)` top, shadow), section eyebrows.
- [ ] **Step 6:** `home.py`: cover 256 / hover 320; play button class `play`; volume slider 140 px; `idle.py`: Instrument Serif Italic 40 px title via CSS `font-family: "Instrument Serif"; font-style: italic`.
- [ ] **Step 7:** `python3 -m pytest -q` and ruff. Expected: PASS.
- [ ] **Step 8:** Stills: `stage.py --app home` playing, `--no-player` idle, `--look motion=false`; sheet next to `.reference/site/frame-7.png` at full resolution. Judge: the field reads as the album's light, type sizes match the reference within 10%, nothing clipped.
- [ ] **Step 9:** `measure.py --lab --app home --seconds 8`: playing under 4%, paused under 1.5%, idle under 3%.
- [ ] **Step 10:** Commit `feat: the album field and the Home identity`.

### Task 2: The Lyrics list with depth

**Files:**
- Create: `encoregui/lyriclist.py`, `encorelib/depth.py`
- Modify: `encoregui/home.py` (LyricsPage uses `LyricList`)
- Test: `tests/test_depth.py`, lab stills `.stage/finish-2/`

**Interfaces:**
- `depth.step(distance: int) -> int` (0, 1, 2 capped), `depth.DEPTH = ((1.0, 1.0, 0.0), (0.94, 0.55, 1.5), (0.9, 0.32, 3.0))` as (scale, opacity, blur), `depth.scroll_target(line_tops: list[float], current: int, view_h: float, anchor: float = 0.38) -> float`.
- `lyriclist.LyricList(Gtk.Widget)`: `set_lines(lines: list[dict], key: str)`, `set_state(state: dict)` (current line, words, position for the sweep), `set_colors(colors)`, `on_seek: Callable[[float], None]`; rasters through a byte-bounded LRU (`ByteLRU`, 24 MB); eased scroll 420 ms; hover row at 0.7.

- [ ] **Step 1: Write the failing tests**

```python
def test_depth_steps_cap():
    assert [step(d) for d in (0, 1, 2, 3, 40)] == [0, 1, 2, 2, 2]
    assert DEPTH[0] == (1.0, 1.0, 0.0) and DEPTH[2][2] == 3.0

def test_scroll_target_keeps_current_at_anchor():
    tops = [0, 60, 120, 180, 240, 300]
    assert scroll_target(tops, 3, 400) == 180 - 0.38 * 400 + 30  # line center at 38%
    assert scroll_target(tops, 0, 400) == 0  # never above the top
```

- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement `depth.py` and `lyriclist.py`: a line's raster is the dim copy of `LineRaster(text, words, font, 26 px...)`; the current line draws the bright copy clipped to the sweep (`Scene.fade_out_right` as the overlay does); depth via `push_opacity`, `push_blur` (only for steps 1-2) and a scale transform around the line's center; the list draws only lines inside the viewport plus one; top and bottom 90 px alpha masks.
- [ ] **Step 4:** `LyricsPage` swaps the label column for `LyricList`; click -> `win.seek_to(start)`; messages (waiting, none, plain) stay labels.
- [ ] **Step 5:** `python3 -m pytest -q` and ruff. Expected: PASS.
- [ ] **Step 6:** Stills `--app lyrics` at 5.0 and 12.4, plus a 200-line LRC (stage `--long-lyrics` flag added here) and `--look motion=false`; sheet next to `.reference/site/frame-16.5.png` and `lyrics-crop.png`.
- [ ] **Step 7:** `measure.py --lab --app lyrics` (add `lyrics` to the app pages measure accepts): playing under 4%.
- [ ] **Step 8:** Commit `feat: a lyrics list with depth`.

### Task 3: Full screen glass and the entry moment

**Files:**
- Create: `encoregui/glass.py`
- Modify: `encoregui/cover.py` (`CoverBackdrop.blurred_texture()` for the bars; the field under `clear`), `encoregui/fullscreen.py` (glass bars, slide, entry animation), `encoregui/app.py` (entry/exit timeline)
- Test: lab stills and a clip `.stage/finish-3/`, `-m lab`

**Interfaces:**
- `glass.GlassPanel(Gtk.Widget)` wraps a child: draws the backdrop's blurred texture clipped to its own bounds (`set_backdrop(texture, offset_x, offset_y)`), a tint and a top edge, then the child.
- `cover.CoverBackdrop.blurred_texture() -> Gdk.Texture | None` (the cached blur of the whole view, built once per cover and size, in both fill and framed modes).
- Full screen entry: `app.show_page("full")` starts a 320 ms timeline: the Home cover's side grows 256 -> 400 while the page stack crossfades; `fullscreen.FullPage.enter()` runs after it. Leaving reverses over 240 ms.

- [ ] **Step 1:** Implement `GlassPanel` and the backdrop texture; the two bars become `GlassPanel`s; revealers use slide (`SLIDE_DOWN` for the top, `SLIDE_UP` for the bottom) at 200 ms with the crossfade of their opacity.
- [ ] **Step 2:** Entry and exit timelines in `app.py` (GLib timeouts at 16 ms, `ease_out`).
- [ ] **Step 3:** `clear` background: `AlbumField` (no cover, motion) under the engine.
- [ ] **Step 4:** Stills: line on cover with bars, constellation on clear, bars hidden; clip `stage.py --app full --clip 4` of the entry (from `--open home` then `encore app --open full` launched 1 s later: stage gains `--then full`).
- [ ] **Step 5:** `measure.py --lab --app full --style S` for the four styles; `-m lab` tests pass.
- [ ] **Step 6:** Commit `feat: glass bars and the full screen entry`.

### Task 4: Lyric style motion against the hero video

**Files:**
- Modify: `encoregui/lyrics.py` (depth for the line style, held-word scale, serif face, glyph pop, sparkle pulse, sync lead), `encorelib/lyricview.py` (`LEAD_SECONDS`), `encorelib/motion.py` (`held_scale`)
- Test: `tests/test_motion.py`, `tests/test_lyricview.py`, clips `.stage/finish-4/`

**Interfaces:**
- `motion.held_scale(duration: float) -> float`: 1.0 at <= 0.3 s rising linearly to 1.18 at >= 1.2 s.
- `lyricview.LEAD_SECONDS = 0.12`; `build_view` and `next_word_boundary` apply it (position + lead).

- [ ] **Step 1: Write the failing tests**

```python
def test_held_scale_caps():
    assert held_scale(0.1) == 1.0 and held_scale(0.3) == 1.0
    assert abs(held_scale(0.75) - 1.09) < 0.01
    assert held_scale(1.2) == 1.18 and held_scale(8.0) == 1.18

def test_lead_lights_words_early():
    # a word starting at 10.0 is live at 9.9 with the lead
    state = {...position 9.9...}
    assert current_word_index(build_view(state, now)) == 0
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement; line style: next line raster drawn at 0.72 opacity under `push_blur(1.5)`; column styles: serif words use `Instrument Serif Italic` when installed (`Pango` family check once), else `Serif Italic`; the big slot's scale multiplies by `held_scale(word duration)`; glyphs pop (0.6 -> 1 over 150 ms); constellation sparkle on the current node pulses at 1 Hz.
- [ ] **Step 4:** Clips: `stage.py --style S --clip 6` for each style on the desktop and `--app full --style S --clip 6`; frame-step (`ffmpeg fps=10`) and lay next to `verci-hero.mp4` frames at the same beats; judge pop/slide/exit timing, type weights, the held-word growth.
- [ ] **Step 5:** `measure.py --lab --overlay --style S` and `--app full --style S`: within budgets.
- [ ] **Step 6:** Commit `feat: lyric motion against the reference`.

### Task 5: Lens style (optional, only if Tasks 1-4 are within budget and on time)

**Files:**
- Create: `encorelib/lens.py` (`project(slot_y: float, height: float) -> tuple[float, float]` scale and shift)
- Modify: `encorelib/stream.py` (`STYLES` gains `lens`), `encoregui/lyrics.py` (`_draw_column` with lens projection), popovers and full screen buttons (style list is data-driven already)
- Test: `tests/test_lens.py`, stills and clip

- [ ] Project the rolling column on a convex surface: scale = 0.72 + 0.28 * cos(angle), angle = (y - center) / (height * 0.6) * pi/2; shift toward the center by 12% of the distance; the current word nearest and largest. Commit `feat: the lens style`.

### Task 6: Settings and look menu glass, idle grain

**Files:**
- Modify: `encoregui/popovers.py` (eyebrows, separators, glass), `encoregui/idle.py` (grain, title face)
- Test: stills

- [ ] Stills of both popovers and idle; commit `feat: frosted panels and the idle screen`.

### Task 7: Final gate, docs, PR

- [ ] `python3 -m pytest -q`, `-m lab`, ruff; `measure.py` for home, lyrics, full (4 styles), overlay (line, stack); stills sheet of every screen under `.stage/finish-final/`.
- [ ] STATE.md rewritten (shipped, measured), DECISIONS #35 (the identity: album field, glass, depth) and #36 (lead and held-word scale), AGENTS.md module map, PR #18 description updated.
- [ ] Commit `docs: record the finish`, push.

## Handoff (2026-11-05, session ended on context)
- Done and committed on `feat/encore-app` (PR #18): Task 1 (album field, identity, 1d6cf3e), Task 2 (lyrics list with depth, 8ee0c1f), Task 3 (glass bars, hero entry, shared textures, a79be9d), Task 4 (lyric motion, lead, serif, fd7948b). Task 5 (Lens) skipped by ruling. Task 6 needed no code (popovers already restyled in Task 1; stills in `.stage/finish-6`).
- Remaining, Task 7: DECISIONS #35 (identity: album field, glass, lyric depth; Instrument Serif) and #36 (frames are the cost: 8-16 ms per full-window repaint on this NVIDIA GL/Vulkan; no per-frame blur or mask nodes; cached blurs; per-word brighten; hero cut instead of crossfade; warm-up; numbers below); AGENTS.md module map (`field.py`, `lyriclist.py`, `glass.py`, `motion.py`, `depth.py`, `ENCORE_TRACE`, stage `--then`, `--long-lyrics`); STATE.md rewrite; update PR #18 text; push.
- Measured (8 s lab runs): Home playing 2%, paused 1.75%, idle 1.25%; Lyrics page 13% while words fill; full screen line 8.5%, stack 15-22%, constellation 6.6%, visual 15-20%, paused 0.75-1.6%; overlay line 7.75%, stack 14.1%. First full-screen frame ~250 ms once per session.
- Owner must know: `/run/user/1000` (1.6 GB tmpfs) was 100% full of ~130 `checkupdates_db_*` dirs left by HyDE's waybar update checker; the test harness now falls back to /tmp; the dirs were not touched.
- Verified only on the hidden monitor; the owner's run on the real screen is still pending.
