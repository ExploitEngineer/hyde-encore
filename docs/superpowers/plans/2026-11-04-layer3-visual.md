# Layer 3+: Visual Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Visual tasks iterate (capture, compare, refine) instead of strict RED/GREEN; pure logic stays test-first.

**Goal:** Make every surface look finished: the four overlay styles, the edge glow, the player window and the lock screen, judged by eye against `.reference/` and by numbers on the isolated harness.

**Owner brief (2026-11-04):** "work on each thing with your creativity, without following anything, and deliver the final product." The references are a bar to clear, not a template; no questions back, decisions are mine and get recorded.

**Architecture:** A capture stage (`tests/e2e/stage.py`) adds a virtual monitor `encore-lab` to the running Hyprland (parked at 20000,20000, removed afterwards), runs the private harness, starts the real GTK surfaces on that monitor, seeks the fake player to scripted positions and saves `grim -o encore-lab` stills (and optional `wf-recorder` clips). Nothing appears on the owner's screen.

## Global Constraints
- Never show windows on the owner's screen; every GUI run targets `encore-lab`.
- Never control the owner's players; the harness fake player only.
- Perf budget per style on `measure.py --overlay --monitor encore-lab`: about 6.5% of one core animating, 0 paused or hidden.
- `encorelib/` stays gi-free and test-first; GTK changes are verified by stage captures.
- Ruff clean, conventional commits without attribution, Markdown one sentence per line, no em dash.

## Tasks
1. Output targeting: `encoregui/outputs.py` places a layer window on a connector; the overlay (text and art windows) and the glow use it; config gains `[encore.glow] monitor` (ENCORE_GLOW_MONITOR).
2. Stage: `tests/e2e/stage.py` (lab monitor lifecycle, surfaces, stills, clips, side-by-side sheets with reference frames); `measure.py --monitor`.
3. Visual passes, one surface at a time, each ending with before/after stills in the commit message and a perf check: line, stack, constellation, visual, glow, player window, lock screen.
4. Docs: DECISIONS for the stage and every visual direction I choose, STATE rewritten, README screenshots list.
