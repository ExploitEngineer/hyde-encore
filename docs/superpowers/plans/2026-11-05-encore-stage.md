# Encore stage pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A windowed Stage page, spring motion with ghost trails, per-style typography, a color floor with a 1/2-color gradient field, and a settings pixel pass, each verified on the hidden monitor.

**Architecture:** Pure decisions live in `encorelib/` (unit-tested, no `gi`): `motion.spring`/`ghosts`, a new `typeface.py` (face per word and style, nearest installed weight), `colors.py` floors and blob colors, `stageflag.wanted`, `transport` page routing.
The GTK side (`encoregui/`) only applies them: `FullPage` gains a windowed mode that the app shows as page `stage`; `LyricsEngine` draws springs, ghosts and the picked faces; `AlbumField` takes the gradient; `popovers.py` gets the Background/Gradient rows and the pixel pass.

**Tech Stack:** Python 3 (system), GTK 4.24 via PyGObject, Pango/Cairo, pytest, ruff; lab tooling `tests/e2e/stage.py` and `tests/e2e/measure.py`.

**Spec:** `docs/superpowers/specs/2026-11-05-encore-stage-design.md` (reference notes: `docs/superpowers/specs/2026-11-04-verci-parity.md`, frames under `.reference/site/`).

**Ledger:** `.superpowers/sdd/2026-11-05-encore-stage/progress.md` (local, gitignored): one line per step done, every Ruling, every measured number.

## Global Constraints

- No new dependency; springs in pure Python; no libadwaita, WebKit or AMLL code (AGPL-3.0); no font downloads.
- HyDE conventions, GPL-3.0, upstream commit style (`feat: ...`, `fix: ...`), no agent attribution anywhere; branch `feat/encore-app` (PR #18).
- `encorelib/` never imports `gi`.
- Visual changes judged only on `tests/e2e/stage.py` stills/clips next to `.reference/site/` frames, saved under `.stage/stage-<step>/`; one lab job at a time.
- Perf: `measure.py --lab` numbers; a style may rise at most 2 points over DECISIONS #36 (Full screen playing: line 12-13%, stack 21%, constellation 15%, visual 22.6%).
- Every commit: `python3 -m pytest -q`, `uvx ruff check Configs tests`, `uvx ruff format --check Configs tests` green.
- The owner's session is never touched: no playerctl to real players, no windows on the owner's workspaces, no restart of `hyde-Hyprland-encore.service`.
- Time box: no new task starts after 16:30 PKT; everything pushed by 17:30 PKT.

## Review Focus

1. Pressing F twice fast (stage -> full -> stage) while the compositor's unfullscreen notification arrives late: the window must land on Stage, never bounce to Home. Pinned by `test_page_after_*` in Task 1 and by `_on_fullscreened` acting only when `page == "full"`.
2. A Stage window resized to something tiny (or a 0x0 allocation during map): the engine must keep a sane size and never divide by zero. Pinned by `test_stage_size_floor` in Task 1.
3. Quitting, closing to tray or crashing while Stage is up: the `encore.stage` flag must go, so desktop lyrics come back. Pinned by `test_wanted_*` in Task 1 plus the lab test.
4. A font in the look file that is no longer installed (`font = "Futura"`): every surface must fall back to an installed family and never synthesize bold. Pinned by `test_faces_unknown_family_falls_back` in Task 3.
5. Extreme covers (pure white, pure black, one saturated hue, grey): the floors must hold on every one. Pinned by `test_floor_holds_on_extreme_covers` in Task 4.

---

### Task 1: The Stage window

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/stageflag.py` (add `wanted`), `encorelib/transport.py` (W key, `page_after`), `encoregui/fullscreen.py` (windowed mode, size debounce, suspended/unmap), `encoregui/app.py` (page `stage`, routing, Home button), `encore.py` CLI help if it lists pages.
- Test: `tests/test_stageflag.py`, `tests/test_transport.py`, `tests/e2e/test_app.py` (lab)

**Interfaces:**
- Produces: `stageflag.wanted(page: str, mapped: bool, suspended: bool) -> bool`; `transport.page_after(action: str, page: str, came_from: str) -> str | None`; `fullscreen.stage_size(w: int, h: int) -> tuple[int, int]` (pure, in `encorelib/stageflag.py` as `stage_size` to stay gi-free); `FullPage.enter(windowed: bool)`, `FullPage.set_windowed(bool)`; app page names `("home", "lyrics", "stage", "full")`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_stageflag.py
def test_wanted_only_on_stage_or_full_mapped_and_awake():
    assert wanted("stage", True, False) and wanted("full", True, False)
    assert not wanted("stage", True, True)      # on another workspace / minimized
    assert not wanted("full", True, True)
    assert not wanted("stage", False, False)    # closed to tray
    assert not wanted("home", True, False) and not wanted("lyrics", True, False)

def test_stage_size_floor():
    assert stage_size(0, 0) == (320, 240)
    assert stage_size(960, 700) == (960, 700)

# tests/test_transport.py
def test_w_key_is_stage_everywhere():
    for page in ("home", "lyrics", "stage", "full"):
        assert key_action("w", False, page) == "stage"

def test_page_after_routes():
    assert page_after("stage", "home", "home") == "stage"
    assert page_after("stage", "stage", "home") == "home"
    assert page_after("stage", "full", "stage") == "stage"
    assert page_after("fullscreen", "stage", "home") == "full"
    assert page_after("fullscreen", "full", "stage") == "stage"
    assert page_after("fullscreen", "full", "home") == "home"
    assert page_after("fullscreen", "home", "home") == "full"
    assert page_after("back", "stage", "home") == "home"
    assert page_after("back", "full", "stage") == "home"
    assert key_action("l", False, "stage") is None   # Lyrics key off on the stage
```

- [ ] **Step 2: Run, expect ImportError / assertion failures**: `python3 -m pytest -q tests/test_stageflag.py tests/test_transport.py`
- [ ] **Step 3: Implement** `wanted`, `stage_size` (floor 320x240) in `stageflag.py`; `"w": "stage"` in `_KEYS`, `"stage": {"lyrics"}` in `_NOT_ON`, `page_after` in `transport.py`.
- [ ] **Step 4: GUI.** `FullPage`: `windowed` flag; in windowed mode the engine is sized from the page allocation through `do_size_allocate` with a 120 ms one-shot debounce calling `engine.set_screen(*stage_size(w, h))`; full mode keeps `_on_enter_monitor`. Flag: `_sync_flag()` writes the connector when `wanted(page, mapped, suspended)` else clears; hooked to `notify::suspended` and `map`/`unmap` of the window and to page switches. Top bar: Exit button label "Home" in windowed mode, "Exit full screen" in full; a second pill beside it, "Window" in full and "Full screen" in windowed. App: `stage` in `PAGES`; `show_page("stage")` hides header and toolbar, crossfades to the `full` stack child, `self.full.enter(windowed=True)`; stage -> full calls `fullscreen()` and `full.set_windowed(False)` without leaving; full -> stage sets `page = "stage"` before `unfullscreen()`; Home toolbar gets a window icon button "Stage window (W)"; `_on_key` uses `page_after`; `came_from` remembers the page before full.
- [ ] **Step 5: Lab test** `test_stage_flag_follows_the_window(lab)`: open the app on `stage`; assert `encore.stage` exists; move the window to the lab's special workspace (`hyprctl` dispatch, lab window selector only), wait until the flag is gone; bring it back, flag returns; `app.terminate()`.
- [ ] **Step 6: Suite, lint, lab** `python3 -m pytest -q`, ruff, `python3 -m pytest -q -m lab tests/e2e/test_app.py`.
- [ ] **Step 7: Stills** `stage.py --no-overlay --app stage --style stack --at 5.0,12.4 --out .stage/stage-1/stack` and `--style visual`, `--look stage_bg=clear`; clip `--app home --then stage --clip 4`; sheet next to `hero-1.png` with `magick montage -label`.
- [ ] **Step 8: Measure** `measure.py --lab --app stage --look style=stack` and `style=visual`; ledger.
- [ ] **Step 9: Commit** `feat: stage window, the lyrics show in the normal window`

### Task 2: Springs and ghosts

**Files:**
- Modify: `encorelib/motion.py`, `encoregui/lyrics.py` (`_pop`, `_draw_rolling`, `_draw_column`, line entry, constellation pop)
- Test: `tests/test_motion.py`

**Interfaces:**
- Produces: `motion.spring(t: float, settle: float = 0.32, zeta: float = 0.55) -> float`; `motion.ghosts(progress: float, count: int = 2) -> list[tuple[float, float]]` (lag seconds, alpha); `motion.settle_curve(age: float, motion: bool, settle: float) -> float` (spring when motion, else `ease_out(age / 0.16)`).

- [ ] **Step 1: Failing tests**

```python
def test_spring_ends():
    assert spring(0) == 0.0 and spring(-1) == 0.0
    assert spring(0.32) == 1.0 and spring(5) == 1.0

def test_spring_overshoots_then_settles():
    ts = [i / 1000 for i in range(0, 321)]
    xs = [spring(t) for t in ts]
    peak = max(xs)
    assert 1.05 <= peak <= 1.15
    assert ts[xs.index(peak)] <= 0.6 * 0.32
    assert all(-0.01 <= x <= 1.2 for x in xs)
    assert all(abs(x - 1) <= 0.01 for t, x in zip(ts, xs) if t >= 0.32 * 0.95)

def test_spring_final_approach_monotonic():
    # after the last extremum before settle the curve only closes in on 1
    ts = [0.32 * (0.87 + i / 1000) for i in range(0, 131)]
    xs = [spring(t) for t in ts]
    assert all(b >= a - 1e-9 for a, b in zip(xs, xs[1:]))

def test_ghosts():
    assert ghosts(0.0) == [] and ghosts(1.0) == [] and ghosts(1.4) == []
    mid = ghosts(0.5)
    assert [lag for lag, _ in mid] == [0.055, 0.110]
    assert mid[0][1] == pytest.approx(0.35) and mid[1][1] == pytest.approx(0.18)
    assert len(ghosts(0.5, count=1)) == 1

def test_settle_curve_without_motion_is_plain_ease():
    assert settle_curve(0.08, False, 0.24) == pytest.approx(ease_out(0.5))
    assert settle_curve(0.16, False, 0.24) == 1.0
    assert settle_curve(0.1, True, 0.24) == pytest.approx(spring(0.1, 0.24))
```

- [ ] **Step 2: Run, expect ImportError**: `python3 -m pytest -q tests/test_motion.py`
- [ ] **Step 3: Implement.** `spring`: underdamped step response `1 - e^(-zeta*w*t) (cos(wd t) + zeta/sqrt(1-zeta^2) sin(wd t))`, `wd = w sqrt(1-zeta^2)`, `w` chosen so the envelope `e^(-zeta w settle)/sqrt(1-zeta^2) = 0.01`; returns exactly 1.0 from `settle` on. `ghosts`: weight `sin(pi * progress)` on alphas (0.35, 0.18), lags (0.055, 0.110), empty outside (0, 1).
- [ ] **Step 4: Engine.** Stack/visual: current word scale `0.6 + 0.4 * spring(age)` and opacity `min(1, spring(age) * 1.6)` on top of its slot values; column slide `settle_curve(age, motion, 0.24)`; while the slide runs, draw the column twice more first at `settle_curve(age - lag)` with alpha times the ghost alpha, no Highlight block, no glyphs; the block rides the main draw. Line end: 0.30 s, eased (no overshoot) rise, with the same two ghosts lagging along its path. Constellation: `_pop` uses the spring for scale and opacity. Line: the new line's slide-in offset uses `settle_curve(age, motion, 0.32)`. `motion=false`: plain 160 ms ease-out, no ghosts.
- [ ] **Step 5: Suite and lint.**
- [ ] **Step 6: Clips** `stage.py --app stage --no-overlay --style stack --clip 6 --out .stage/stage-2/stack`, same for `visual`, `constellation`; frame-step 10 frames around one slide into a montage next to `verci-hero.mp4` frames (`ffmpeg -ss 2 -t 1 -vf fps=12`).
- [ ] **Step 7: Measure** Full screen stack, visual, constellation, line playing (`measure.py --lab --app full --look style=S`); fail the task if any rises more than 2 points over #36.
- [ ] **Step 8: Commit** `feat: spring pops and ghost trails in the lyric styles`

### Task 3: Typography

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/typeface.py`
- Modify: `encorelib/lyricview.py` (`word_style` delegates), `encoregui/lyrics.py` (`_word_surface`, `line_layout`, `serif_face`), `encoregui/popovers.py` (`PREFERRED_FONTS` -> `typeface.DISPLAY_FONTS`, tooltip aliases, size value label)
- Test: `tests/test_typeface.py`

**Interfaces:**
- Produces: `DISPLAY_FONTS: tuple[str, ...]` in the spec's order; `ALIASES = {"Newsreader": "New York", "Instrument Serif": "Didot"}`; `Face = NamedTuple(family: str, weight: int, italic: bool)`; `primary_family(font: str, have: dict[str, set[tuple[int, bool]]]) -> str` (first installed of a comma list, else first installed of `DISPLAY_FONTS`); `nearest_weight(want: int, have: set[int]) -> int` (closest, ties to the heavier); `role_for(style: str, line_key: str, index: int, on_block: bool) -> str` in `{"heavy", "serif", "medium", "semibold"}`; `face_for(role: str, primary: str, have) -> Face`; `serif_partner(have) -> str`, `mono_partner(have) -> str`.

- [ ] **Step 1: Failing tests**

```python
HAVE = {"SF Pro Display": {(400, False), (700, False)}, "Inter": {(w, False) for w in range(100, 1000, 100)},
        "Instrument Serif": {(400, False)}, "Newsreader": {(400, False), (700, False)},
        "JetBrainsMono Nerd Font": {(400, False)}, "Alfa Slab One": {(400, False)}}

def test_line_is_bold_only():
    assert {role_for("line", "k", i, False) for i in range(50)} == {"heavy"}

def test_stack_mix_is_about_half_heavy():
    roles = [role_for("stack", f"line{i}", j, False) for i in range(40) for j in range(10)]
    assert 0.42 < roles.count("heavy") / len(roles) < 0.58
    assert 0.18 < roles.count("serif") / len(roles) < 0.32

def test_highlight_word_is_never_heavy():
    assert all(role_for("visual", f"l{i}", 3, True) != "heavy" for i in range(200))

def test_constellation_one_serif_in_four():
    roles = [role_for("constellation", f"l{i}", j, False) for i in range(40) for j in range(10)]
    assert set(roles) == {"semibold", "serif"}
    assert 0.18 < roles.count("serif") / len(roles) < 0.32

def test_faces_use_what_the_family_ships():
    assert face_for("semibold", "SF Pro Display", HAVE) == Face("SF Pro Display", 700, False)
    assert face_for("semibold", "Inter", HAVE) == Face("Inter", 600, False)
    assert face_for("medium", "SF Pro Display", HAVE) == Face("SF Pro Display", 400, False)
    assert face_for("heavy", "Alfa Slab One", HAVE) == Face("Alfa Slab One", 400, False)  # never synthetic bold
    assert face_for("serif", "Inter", HAVE) == Face("Instrument Serif", 400, True)

def test_faces_unknown_family_falls_back():
    assert primary_family("Futura", HAVE) == "SF Pro Display"
    assert primary_family("SF Pro Display, Inter, sans-serif", HAVE) == "SF Pro Display"

def test_partners():
    assert serif_partner(HAVE) == "Instrument Serif"
    assert serif_partner({"Newsreader": {(400, False)}}) == "Newsreader"
    assert mono_partner({"Maple Mono": {(400, False)}}) == "Maple Mono"

def test_display_fonts_order():
    assert DISPLAY_FONTS[:3] == ("SF Pro Display", "Inter", "Newsreader")
```

- [ ] **Step 2: Run, expect ImportError**: `python3 -m pytest -q tests/test_typeface.py`
- [ ] **Step 3: Implement `typeface.py`**; the role picker reuses `lyricview._stable_unit` (move it to `typeface` if import direction needs it; `lyricview.word_style` stays for callers and delegates).
- [ ] **Step 4: GUI.** `lyrics.py`: `installed_faces()` builds `have` once per process from `PangoCairo.FontMap.get_default().list_families()` / `list_faces()` / `describe()`; `_word_surface(style=role)` builds a `Pango.FontDescription` from the `Face` (family, weight, `Pango.Style.ITALIC` when italic); line rasters use `face_for("heavy", ...)`; constellation words use `role_for("constellation", ...)`; the visual block word uses `on_block=True`. `popovers.py`: the menu lists `DISPLAY_FONTS` present in `have`, tooltips carry the alias ("Where New York would be"), the size slider shows its value.
- [ ] **Step 5: Suite and lint.**
- [ ] **Step 6: Stills** stack, visual, constellation, line at `--at 5.0,9.9,14.4`, plus `--look font=Inter` and `font=Newsreader`, under `.stage/stage-3/`; labelled sheet next to `hero-1.png`, `hero-2.png`.
- [ ] **Step 7: Measure** stack and visual Full screen (more faces = more cached textures; check no rise).
- [ ] **Step 8: Commit** `feat: per-style typography from the installed faces`

### Task 4: Colors and gradient

**Files:**
- Modify: `encorelib/colors.py` (floors, `blob_colors`), `encorelib/look.py` (`gradient` key), `encoregui/field.py` (`set_gradient`), `encoregui/app.py` and `encoregui/fullscreen.py` (pass gradient), `encoregui/popovers.py` (Background and Gradient rows)
- Test: `tests/test_colors.py`, `tests/test_look.py`

**Interfaces:**
- Produces: `colors.BASE = "141317"`; `scheme()` output obeys the floors; `colors.blob_colors(colors: Scheme, gradient: int) -> tuple[str, str, str]`; look key `gradient` in `(1, 2)`, default 2; `AlbumField.set_gradient(n: int)`.

- [ ] **Step 1: Failing tests**

```python
COVERS = {"white": "FFFFFF", "black": "000000", "red": "FF0000", "blue": "1020A0",
          "yellow": "F0E040", "grey": "808080", "teal": "1FA39A"}

@pytest.mark.parametrize("name", COVERS)
def test_floor_holds_on_extreme_covers(name):
    s = scheme(_pal(COVERS[name]), {})
    assert contrast_ratio(s.lyric, BASE) >= 7.0
    assert contrast_ratio(s.on_highlight, s.highlight) >= 4.5
    assert 2.5 <= contrast_ratio(s.secondary, BASE) <= 4.0

def test_floor_moves_text_never_the_block():
    s = scheme(_pal("1FA39A"), {})
    assert s.highlight == _block_for(s.accent)   # the derivation, untouched by the floor

@pytest.mark.parametrize("gradient", [1, 2])
def test_blob_colors_capped(gradient):
    s = scheme(_pal("F0E040"), {})
    blobs = blob_colors(s, gradient)
    assert all(relative_luminance(c) <= 0.28 for c in blobs)
    assert len(set(blobs)) == (1 if gradient == 1 else 2)

def test_gradient_look_key():  # tests/test_look.py
    assert _valid("gradient", 1) and _valid("gradient", 2)
    assert not _valid("gradient", 3) and not _valid("gradient", True)
```

- [ ] **Step 2: Run, expect failures**: `python3 -m pytest -q tests/test_colors.py tests/test_look.py`
- [ ] **Step 3: Implement.** Floors in `scheme()` only (Auto Sync); user overrides in `resolve()` are honored as picked, `on_highlight` is always floored against the block. Text on the block: start from white or ink, move toward pure white or pure black until 4.5:1 (always reachable). Secondary: lighten under 2.5, darken over 4.0, along its own hue. `blob_colors`: gradient 1 = accent x3, 2 = (accent, accent2, accent); each darkened along its hue to luminance <= 0.28.
- [ ] **Step 4: GUI.** `AlbumField` paints `blob_colors(colors, gradient)`; the window and the Full page pass `look.get("gradient", 2)`; the look menu gains "Background" (Cover, Clear) and "Gradient" (1 Color, 2 Colors) rows.
- [ ] **Step 5: Suite and lint.**
- [ ] **Step 6: Stills** `--app stage --look stage_bg=clear --look gradient=1|2`, Home, idle (`--no-player`), with two covers; sheet next to `lumn-1.png` under `.stage/stage-4/`.
- [ ] **Step 7: Commit** `feat: readable color floors and a one or two color gradient`

### Task 5: Settings and look menu pass

**Files:**
- Modify: `encoregui/ui.py` (CSS tokens), `encoregui/popovers.py` (rows, swatches, slider values, Font and Display dropdowns, Quit last)
- Test: `tests/test_ui_tokens.py` (reads the CSS string without importing GTK: tokens live in `encorelib/` or the test greps `ui.py` source)

- [ ] **Step 1: Failing test** asserting the CSS tokens: eyebrow `font-size: 11px`, `letter-spacing: 0.08em`, `text-transform: uppercase`; row `min-height: 36px`; separator `alpha(white, 0.08)`; swatch `min-width: 18px`, `border-radius: 50%`, `1px` ring.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** the tokens and widgets; Font becomes a `Gtk.DropDown` of installed `DISPLAY_FONTS`; slider rows show their value at the right; Quit stays last.
- [ ] **Step 4: Suite and lint.**
- [ ] **Step 5: Stills** `--app look` and `--app settings` at full resolution; sheet with `lumn-2.png`, `panel-crop.png`, `verci-settings.png` under `.stage/stage-5/`; fix what looks off, re-shoot.
- [ ] **Step 6: Commit** `feat: settings and look menu after the reference panels`

### Task 6: The `code` style (optional)

Only if Tasks 1-5 are committed green and the clock is before 16:30 PKT.

- [ ] Style `code` in `STYLES`; mono partner; current line typed word by word with a block caret; past lines dimmed; line numbers in Secondary at the left. Tests for the layout helper in `encorelib/`; stills; measure; commit `feat: code lyric style`.

### Finish (after 16:30 PKT at the latest)

- [ ] One fresh-context review (Sonnet, high effort, code-reviewer template, read-only); fix Critical and Important with a failing test first; Minor to the ledger.
- [ ] `docs/STATE.md` rewrite, DECISIONS entries (stage window, spring motion, typography), `AGENTS.md`, PR #18 description (CodeRabbit block verbatim), Handoff section below, push.

## Handoff

(written at the end of the pass)
