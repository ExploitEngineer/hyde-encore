# State

## Shipped (branch feat/encore-core, Plan 1)
- `encorelib/`: LRC and enhanced LRC parser, word-timing estimator, cursor lookup, playback clock, config loader (verified against HyDE's real `config.lua` output), providers (local `.lrc`, LRCLIB with junk-upload filter, Spicy Lyrics), lyrics cache, album palette via `wallbash.sh` on a 256px cover, JSON-lines state protocol, hyprlock markup.
- `encore.py` daemon plus `encore.sh` hyde-shell entry: follows the most recently started MPRIS player, worker-thread fetches guarded against stale results, `daemon [--if-enabled]`, `status`, `hyprlock`.
- `Encore.conf` hyprlock layout; schema, config and `hc.start` autostart fragments for upstream.
- 114 unit tests; `tests/e2e/fake_mpris.py` scriptable MPRIS player for end-to-end runs.

## Measured (fake MPRIS player, this laptop, 2026-11-03)
- Playing: about 0.4% of one core, about 40 MB RSS.
- Paused: 0 CPU ticks over 10 s, 0 to 1.4 context switches per second across runs (target under 1, recheck with the overlay).
- E2E verified: word-by-word line follows playback, seek forward and back lands within 0.3 s, three fast skips end on the right song, two players hand over correctly, clean shutdown removes runtime files.

## In progress
- Owner checks still open: real Spotify session, and the `Encore` hyprlock layout on screen (preview and real lock).

## Next
- Final whole-branch review of Plan 1, then merge.
- Plan 2: lyrics overlay (GTK4 layer-shell, click-through, keybind toggle).
- Plan 3: edge glow from HyDE's `cava.py` socket. Plan 4: `follow_album` spike and full-theme recolor.

## Known facts
- This laptop's `~/.config/hyde/config.toml` only has `$schema`, so `config.lua` writes no `~/.local/state/hyde/config`; that file appears once any setting (such as `[encore]`) is added. Not a HyDE bug.
- LRCLIB `/api/get` can return junk uploads (single `probe` line); encore rejects synced results under 4 timed lines and falls back to search.
- Spicy Lyrics schema read from the OpenAPI document embedded in its docs page; parser unverified against a live response until the owner adds a key.

## Open questions
- Final name (working name: hyde-encore).

## Ideas
- LRCLIB now exposes `hasWordSync` and a `lyricsfile` payload; parsing it could give word-level timing without a Spotify-only key.
- A `hyde-shell encore lrc` command to save the current lyrics as a local `.lrc` for offline use and hand-tuning.
- Waybar module showing the current lyric line from `encore.sock`.

verified: 1579d06 2026-11-03
