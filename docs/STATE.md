# State

## Shipped (branch feat/encore-core, Plan 1)
- `encorelib/`: LRC and enhanced LRC parser, word-timing estimator, cursor lookup, playback clock, config loader (verified against HyDE's real `config.lua` output), providers (local `.lrc`, LRCLIB with junk-upload filter, Spicy Lyrics), lyrics cache, album palette via `wallbash.sh` on a 256px cover, JSON-lines state protocol, hyprlock markup.
- `encore.py` daemon plus `encore.sh` hyde-shell entry: follows the most recently started MPRIS player, worker-thread fetches guarded against stale results, `daemon [--if-enabled]`, `status`, `hyprlock`.
- `Encore.conf` hyprlock layout; schema, config and `hc.start` autostart fragments for upstream.
- Lookup rules (`encorelib/lookup.py`): local `.lrc` always wins and is never cached; provider errors are never cached; cache key includes enabled sources.
- 134 unit tests; `tests/e2e/fake_mpris.py` scriptable MPRIS player for end-to-end runs.

## Measured (fake MPRIS player, this laptop, 2026-11-03)
- Playing: about 0.4% of one core, about 40 MB RSS.
- Paused: 0 CPU ticks over 10 s; 0 to 1.4 context switches per second across runs, 0 on the latest run.
- E2E verified: word-by-word line follows playback, seek forward and back lands within 0.3 s, three fast skips end on the right song, two players hand over correctly, clean shutdown removes runtime files.

## Verified with the owner (2026-11-04)
- Real Spotify: follows Spotify over a stopped Brave tab; Spicy Lyrics word sync on "LEGACY (slowed down)" lights word by word in time.
- `Encore` hyprlock preview on screen: real cover, title, artist, word-by-word line, readable colors.

## In progress
- Branch `feat/encore-overlay` (Plan 2): lyrics overlay done, under final review. 167 tests.
- Overlay measured: animating 6.5% of one core at a 30 fps sweep, paused and hidden 0%; see DECISIONS #10-#11.
- Owner reference study (2026-11-04): 7 Verci/Lumn Instagram reels decoded to contact sheets; signature looks are bezel glow, constellation word-map, stacked mixed-font words, full-bleed album art. Drives Plans 3-5.
- Auto-lyrics (vocal separation + Whisper) spike parked: owner confirmed the target song has no lyrics anywhere; revisit later. Venv and recording live in `~/.cache/hyde/encore/autosync/`.

## Known gaps (deferred from review)
- Empty artist still sends `artist_name=` to LRCLIB search; no `feat.`-stripped retry.
- Fast skipping spawns one fetch and palette thread per track (results are discarded safely).
- Last sung word stays lit through long unmarked instrumental gaps; CJK lines light as one word.
- Playback rate fixed at 1.0; no automated test of the GLib daemon class.

## Next
- Owner checks, then merge `feat/encore-core`.
- Plan 3: overlay style system (constellation and stack modes, live switch).
- Plan 4: edge glow from HyDE's `cava.py` socket, beat-reactive. Plan 5: `follow_album` spike, full-theme recolor, showcase video.

## Known facts
- HyDE upstream bugs found (candidate small PRs): `hyprlock.sh find_filepath` uses `find -type f` without `-L`, so symlinked layouts are listed but fail to load; `hyprlock.sh fn_mpris` reads the first listed player, not the playing one.
- Owner's Spicy Lyrics key lives in `~/.config/hyde/config.toml` (mode 600, not tracked by dotfiles).
- This laptop's `~/.config/hyde/config.toml` only has `$schema`, so `config.lua` writes no `~/.local/state/hyde/config`; that file appears once any setting (such as `[encore]`) is added. Not a HyDE bug.
- LRCLIB `/api/get` can return junk uploads (single `probe` line); encore rejects synced results under 4 timed lines and falls back to search.
- Spicy Lyrics schema read from the OpenAPI document embedded in its docs page; parser unverified against a live response until the owner adds a key.

## Open questions
- Final name (working name: hyde-encore).

## Ideas
- LRCLIB now exposes `hasWordSync` and a `lyricsfile` payload; parsing it could give word-level timing without a Spotify-only key.
- A `hyde-shell encore lrc` command to save the current lyrics as a local `.lrc` for offline use and hand-tuning.
- Waybar module showing the current lyric line from `encore.sock`.

verified: 61abec8 2026-11-04
