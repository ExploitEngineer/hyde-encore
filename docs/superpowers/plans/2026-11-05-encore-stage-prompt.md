# Prompt for the stage pass session (2026-11-05)

Paste everything below the line into a fresh session started in `~/Documents/dev/products/hyde-encore`.

---

You are finishing Encore's stage pass on your own. I am away until the evening and cannot answer questions; my Claude limit resets at 18:00 PKT, so everything must be committed, pushed and documented by 17:30 PKT at the latest, whatever state the work is in.

Context: branch `feat/encore-app` (PR #18), `docs/STATE.md` is the current truth, `docs/DECISIONS.md` #35-#38 the recent calls. The design for this pass is `docs/superpowers/specs/2026-11-05-encore-stage-design.md`; read it whole first, then `docs/superpowers/specs/2026-11-04-verci-parity.md` and the reference frames it names under `.reference/site/`.

Process:
1. Use superpowers:writing-plans to turn the spec into `docs/superpowers/plans/2026-11-05-encore-stage.md`: one task per scope step in the spec's order (1 Stage window, 2 springs and ghosts, 3 typography, 4 colors and gradient, 5 settings pass, 6 code style optional), each with its tests, stills or clips, measure runs and commit. Do not ask me anything: the spec rules; where it is silent, decide, and record the decision in the plan's ledger as a Ruling.
2. Execute with superpowers:executing-plans inline (no per-task subagents), test-driven: write the failing test, watch it fail, make it pass, run `python3 -m pytest -q`, `uvx ruff check Configs tests`, `uvx ruff format --check Configs tests`. Commit each task when green, in upstream style, no attribution of any kind.
3. Verify every visual change on the hidden monitor only: `python3 tests/e2e/stage.py ...` stills and `--clip` clips next to the reference frames, `python3 tests/e2e/measure.py --lab ...` for the styles you touch; one lab job at a time, never two measure or stage runs together. Never open anything on my screen, never send playerctl commands to real players, never restart `hyde-Hyprland-encore.service`.
4. At the end: one fresh-context review of the whole pass by a single subagent (`model: "sonnet"`, `effort: "high"`, the code-reviewer template from superpowers:requesting-code-review, read-only, no lab runs), fix its Critical and Important findings with a failing test first, defer Minor to the ledger. Then rewrite `docs/STATE.md` (shipped, measured, verified sha), add DECISIONS entries for the stage window, the spring motion and the typography, update `AGENTS.md` and the PR #18 description (keep CodeRabbit's auto-generated block verbatim), add a Handoff section to the plan, push.

Context hygiene (your context will auto-compact; make sure nothing is lost when it does):
- Keep the plan's ledger (`.superpowers/sdd/<plan>/progress.md`) current: one line per step done, every ruling, every measured number, before moving on. After compaction, trust the ledger and `git log`, not memory.
- Redirect test and measure output to files under the ledger's directory and read only the tail. Never read a large file whole; grep then read the range. Look at images only as a labelled sheet (`magick montage`) or one full-size still when a detail matters.
- Do not poll background jobs; wait for their notification.

Time box: stop starting new tasks at 16:30 PKT. From then on only finish the current task, run the review, write the docs and push. If a task cannot be finished green by 17:30, revert its uncommitted changes, record why in the Handoff, and push what is green.

Rules that stand no matter what: user-level CLAUDE.md and the repo's AGENTS.md; subagents only Haiku or Sonnet; no crews; no fan-out of three or more agents; never `pkill -f`/`pgrep -f` with a pattern that appears in the same shell command; worktrees are not needed (one task at a time on this checkout).

Final message: what shipped per task with the still or clip paths, the measured numbers, every Ruling you made with its cost if wrong, deferred minors, and what I should look at on my screen first.
