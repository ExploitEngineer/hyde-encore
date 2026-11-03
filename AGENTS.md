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
None yet.
