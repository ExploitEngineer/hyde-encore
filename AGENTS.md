# hyde-encore agent guide

## What this is
HyDE add-on: synced word-level lyrics overlay, beat-reactive edge glow, album-art wallbash, hyprlock lyrics layout.
Goal is an upstream PR to HyDE-Project/HyDE, so everything must look like HyDE wrote it.

## Hard rules
- Mirror HyDE's tree: scripts in `Configs/.local/lib/hyde/`, hyprlock layouts in `Configs/.config/hypr/hyprlock/`, wallbash templates in `Configs/.config/hyde/wallbash/`.
- Follow HyDE conventions: Python via its `pyutils`, shell via `globalcontrol.sh`, invoked through `hyde-shell`. Read the matching upstream file before writing a new one.
- Prefer deps HyDE already ships (playerctl, cava, hyprlock, wallbash). A new dependency needs a DECISIONS.md entry.
- Read `CONTRIBUTING.md` and `COMMIT_MESSAGE_GUIDELINES.md` in the upstream clone before the first commit of feature code.
- License GPL-3.0. Code borrowed from MIT projects keeps its notice.

## Paths
- Upstream reference clone (read-only, shallow): `~/Documents/dev/reference/HyDE`
- Prior art: see `docs/PRODUCT.md`.

## Commands
- Tests: `python3 -m pytest -q`
- Lint: `uvx ruff check Configs tests` and `uvx ruff format --check Configs tests`
- Python runs on system `python3` (DECISIONS #8); `encorelib/` must not import `gi`.
- E2E: `python3 tests/e2e/fake_mpris.py --art <cover> &` then drive with `playerctl -p encoretest play|pause|next|position N` and read `hyde-shell encore status`.
- Never `pkill -f`/`pgrep -f` with a pattern that also appears in the same shell command; it matches and kills that shell. Anchor patterns (`^python3 ...$`) or run from a script file.

## Architecture
- `Configs/.local/lib/hyde/encorelib/`: pure logic (model, lrc, timing, clock, config, providers, cache, palette, protocol, session). Unit-tested, no `gi`.
- `Configs/.local/lib/hyde/encore.py`: GLib/Playerctl daemon and CLI; `encore.sh` is the hyde-shell entry.
- State protocol: JSON lines on `$XDG_RUNTIME_DIR/hyde/encore.sock`, schema in `docs/superpowers/plans/2026-11-03-encore-core.md`. Plans 2-3 consume it.
- Upstream fragments: `Configs/.local/share/hyde/schema/*.toml` and `Configs/.local/share/hypr/lua/variables.encore.lua` hold only encore's additions, to merge into HyDE's files.
