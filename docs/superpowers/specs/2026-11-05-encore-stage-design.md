# Encore, the stage pass: design

Builder-authored on 2026-11-05 from the owner's verdict after the first run on the real screen; the owner is away during the build and opted out of questions, so every open choice is ruled here or in the plan's ledger.

## Intent (the owner's words, 2026-11-05)

- "The animations, when I change my workspace it keeps on that": the desktop overlay is a layer-shell surface and follows every workspace.
- "In the video they use the animations in a separate window which turns black and gradient, and their animations have popping and everything properly, which we don't have."
- "There are not a lot of different fonts right now, they all look the same."
- "Everything perfect: animations, windows, settings, fonts, colors."

## Direction

- The reference is Verci's hero (`.reference/site/hero-1.png`, `hero-2.png`, `verci-hero.mp4`): a pure black field, a three-slot column, the word being sung on a skewed Highlight block, glyphs beside some words, three faces mixed per word (heavy sans, italic serif, medium sans), pops with overshoot and ghost trails on every slide (`docs/superpowers/specs/2026-11-04-verci-parity.md`).
- Lumn's window (`lumn-1.png`, `lumn-2.png`) is the reference for the dark window with an album gradient and for the settings panel.
- No open-source engine fits: AMLL (Apple Music-like Lyrics) is a web renderer under AGPL-3.0, waylyrics a Rust GTK app under MIT with plain text motion. Nothing is borrowed; the motion is a damped spring written in `encorelib/motion.py`.
- Fonts come from what this machine has (`fc-list`): SF Pro Display (Regular, Bold), Inter (variable, with 18/24/28 pt optical sizes), Instrument Serif (Regular, Italic), Newsreader, Alfa Slab One, Anurati, Electrolize, JetBrainsMono Nerd Font, Maple Mono, Miracode, Monocraft. No font is downloaded.

## Scope, in order of value (stop at the budget, never half-ship a step)

1. The Stage window.
2. Springs and ghosts in the stack and visual styles, pops everywhere.
3. Per-style typography and a Font menu that only lists what is installed.
4. The gradient background and the color floor.
5. Settings and look menu pixel pass against the Lumn and Verci panels.
6. The `code` style (Verci's Codestyle), only if 1-5 are done and within budget.

## 1. The Stage window

- A page `stage`: the Full screen page's content hosted in the normal window, never fullscreened. `encore app --open stage`, key `W` from any page, a window button in Home's bottom bar, and in the Full screen top bar a "Window" button beside "Exit full screen"; `F` toggles stage <-> full, `Esc` from stage returns to Home.
- The window keeps its size; the engine sizes to the window (`set_screen(w, h)` on size changes, debounced 120 ms).
- Backgrounds as today (`stage_bg`): `art` fills with the cover; `clear` is black light: the album field at full strength over `#141317`.
- The desktop overlay hides while the stage window is mapped and not suspended on its output (the `encore.stage` flag, as for Full screen) and comes back the moment the window is on another workspace or minimized (flag cleared on suspend and unmap). Lab test: the flag exists while mapped, is gone after `window.suspended` flips (the lab can move the window to another workspace with hyprctl).
- Bars: the same glass bars as Full screen, with the pointer-hide rule; the Exit button says "Home".

## 2. Motion: springs and ghosts

- `motion.spring(t, settle=0.32, zeta=0.55) -> float`: the closed-form underdamped oscillator, 0 at t=0, overshoots to about 1.08 near t=0.55*settle, settles within 1% by `settle`; `motion.ghosts(progress, count=2) -> list[(lag, alpha)]` gives the lagged copies drawn during a slide (alphas 0.35, 0.18; lag 55 and 110 ms of the slide's own path). Both unit-tested (monotonic after the last crossing, bounded, zero and one at the ends, ghosts vanish once the slide settles).
- Stack and visual: a new word pops in with `spring` on scale (0.6 -> 1.0, overshoot visible) and opacity; the column pushes up with a spring slide (settle 240 ms) and each moving word draws its ghosts behind it along the slide; the line end slides the whole column up and out with ghosts (300 ms); visual's Highlight block rides the spring with its word.
- Constellation: the new word pops with the spring; the hairline draw-in and the sparkle breath stay.
- Line: unchanged except the pop.
- `motion=false`: no springs (plain 160 ms ease-out), no ghosts.
- Cost: ghosts are extra draws of textures already cached; springs are arithmetic. Measured per style on the hidden stage; a style may not rise more than 2 points over the numbers in DECISIONS #36.

## 3. Typography

- The Font menu chooses the primary sans; the serif partner is always Instrument Serif Italic (Newsreader Italic if missing), the mono partner JetBrainsMono Nerd Font (Maple Mono if missing).
- Per style, faces are picked per word with the seeded picker that chooses serif words today (`glyphs`/`lyrics.py`): line uses primary Bold only; stack and visual mix primary Bold (heavy), Instrument Serif Italic and primary Regular (medium) about 50/25/25; the word on the Highlight block in visual is Regular or serif Italic, never Bold; constellation uses primary Semibold (Bold when the family has no Semibold) with one serif Italic word in four.
- Weights come from what the family ships (`fc-list :family=... style`); SF Pro Display has Regular and Bold here, Inter every weight. A face the family lacks falls to the nearest it has; never a synthetic bold.
- `PREFERRED_FONTS` becomes the installed display set, in this order: SF Pro Display, Inter, Newsreader, Instrument Serif, Alfa Slab One, Electrolize, Anurati, JetBrainsMono Nerd Font, Maple Mono; the menu lists only families present. Verci's names map to ours where a user might look for them (New York -> Newsreader, Didot -> Instrument Serif) in the tooltip, not in the list.
- Text size slider and Reset stay; the slider's value is shown.
- UI type stays SF Pro Display with tabular figures; the idle title stays Instrument Serif Italic.

## 4. Colors

- Auto Sync derives Lyric Text, Highlight and Secondary from the cover as today; add a floor: Lyric Text at least 7:1 against `#141317`, the text on the Highlight block at least 4.5:1 against the block (lighten or darken the text, never the block), Secondary between 2.5:1 and 4:1 (readable, clearly behind). Unit-tested in `encorelib/colors.py`.
- The gradient background (`gradient` look key: `1` or `2`, default `2`): the field's blobs use accent only (`1`) or accent and accent2 (`2`); both capped at 28% luminance so type reads. The look menu's Background row gets the Gradient choice beside Cover/Clear.
- Glow override colors unchanged.

## 5. Settings and look menu

- Compared at full resolution with `lumn-2.png`, `panel-crop.png`, `verci-settings.png`: eyebrows 11 px uppercase, 0.08 em tracking, 36 px rows, separators 8% white, 18 px round swatches with a 1 px light ring, sliders with their value at the right, dropdowns for Font and Display, the Gradient choice, Quit at the bottom. The sheet is saved under `.stage/stage-5/`.
- GTK 4.24's "GtkImage reported baselines" warnings are not ours; leave them.

## 6. The `code` style (optional)

- Verci's Codestyle: the mono partner, the current line typed in word by word with a block caret, past lines dimmed like comments, line numbers at the left in Secondary; the same lead and timing as every style. Only after 1-5 are green and measured.

## Constraints

- No new dependency: springs in pure Python; no libadwaita, no WebKit, no AMLL code (AGPL-3.0).
- HyDE conventions, GPL-3.0, commits in upstream style, no agent attribution; branch `feat/encore-app` (PR #18 grows).
- Every visual change is judged on stills or clips from the hidden monitor next to the reference frames; never on the owner's screen; perf claims come from `measure.py --lab`; budgets in DECISIONS #36 plus at most 2 points per style for the ghosts.
- Tests green, lab tests green, ruff clean, at every commit.
- The owner's session is never touched: no playerctl to real players, no windows on the owner's workspaces, no restarts of the owner's units.

## Verification

- Per step: stills (and clips where motion changed) under `.stage/stage-<step>/` with a side-by-side sheet against the reference; `measure.py` numbers for the styles touched; the suite and the lab tests.
- At the end: one fresh-context review (Sonnet, high effort) of the whole pass, its Critical and Important findings fixed with a failing test first; STATE.md rewritten, DECISIONS entries for the stage window, the spring motion and the typography, AGENTS.md map and commands updated, PR #18 description updated, a Handoff section in the plan.

## Out of scope

- Multi-monitor copies, the standalone app, the wallbash template, new lyric sources, the Lens style, downloading fonts.
