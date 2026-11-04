# Layer 1: Lyrics Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the engine gaps in `docs/STATE.md` (LRCLIB queries, CJK words, instrumental gaps, playback rate) and make estimated word timing measurably closer to real singing.

**Architecture:** All work stays in `encorelib/` (pure, stdlib only, no `gi`) plus its tests; the daemon and GUI only get the one-line changes the protocol needs.
A new `words.py` owns tokenizing and joining (CJK-aware), a new `query.py` owns LRCLIB search variants, and `timing.locate` learns a gap state that the protocol publishes.

**Tech Stack:** Python 3 stdlib, pytest, ruff.

**Spec:** `docs/STATE.md` (Known gaps, Next), owner brief for layer 1 (2026-11-04), design spec `docs/superpowers/specs/2026-11-03-hyde-encore-design.md` (lyrics model, protocol).

## Findings that shape this plan (measured 2026-11-04)

- LRCLIB word sync: 0 of 600 search results across 30 popular tracks (pop, rap, rock, J-pop, C-pop, K-pop) had `hasWordSync`.
  Word timing lives only in the YAML `lyricsfile` (legacy `syncedLyrics` stays line-level), and the stdlib has no YAML parser.
  Decision: do not parse `lyricsfile` now; record it as DECISIONS #18 and an Idea to re-survey.
- Empty `artist_name=` still returns results today, so that fix is hygiene; `/get` is skipped without an artist.
- `Stay (feat. Justin Bieber)` by `The Kid LAROI, Justin Bieber` returns 0 results; `Stay` by `The Kid LAROI` returns 20, so stripped retries are a real hit-rate win.
- `lrclib()` returns the first duration match even when it is plain-only and a later match is synced.
- Estimator vs real word timing (11 cached word-synced songs, 3,600 words, alternate-song train/validate split): today's `SECONDS_PER_CHAR = 0.45` gives mean word-start error 0.48 s / 0.39 s; a 0.08 s-per-letter cap with a 0.9 line fill gives 0.23 s / 0.20 s.
  Real singing runs 0.067 s per character at the median, 0.16 s at p95.
- Real gap from a line's last word to the next line: median 0.27 s, p99 6.5 s, max 84 s.
- Enhanced LRC with syllable tags (`<..>Hel<..>lo`) renders as `Hel lo`, and Spicy CJK lines render with a space between every character, because lines are rebuilt with `" ".join`.
- The daemon's 1 s resync calls `clock.sync(pos, True)`, which resets the rate to 1.0.

## Global Constraints

- `encorelib/` imports only the stdlib and its own modules; never `gi`.
- Ruff clean: `uvx ruff check Configs tests` and `uvx ruff format --check Configs tests`, line length 100.
- No lyric text from real songs in committed fixtures or tests (copyright); synthetic lines only.
- Protocol stays `"v": 1`: only additive fields.
- Commits: conventional prefix, imperative, no agent attribution.
- Markdown docs: one sentence per line, no em dash.
- Branch `layer1-engine`, cut from `main` after the layer 0 PR merges; the first commit adds this plan.

## Review Focus

- Browser players (YouTube in Brave): title `Artist - Title (Official Video)`, artist is the channel; expect lyrics found via the split variant (test in Task 5).
- Mixed scripts in one line (`Lemon 夢ならば`), Hangul (`사랑해 너를`), full-width punctuation (`夢。`); expect Latin and Hangul words kept whole, each Han/kana character its own word, punctuation glued to the previous word (tests in Task 1).
- A word missing from its line text (source typo) or repeated words; expect spans to stay in order and never crash (test in Task 1).
- Seeking backward from a gap into a line, and an outro after the last line; expect `locate` to be a pure function of time and `gap` to be null after the last line (tests in Task 3).
- Cache files written by the old key or corrupted; expect a refetch, never a crash (test in Task 6).

---

### Task 1: CJK-aware word tokens

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/words.py`
- Modify: `Configs/.local/lib/hyde/encorelib/wordrects.py` (build on `word_spans`)
- Test: `tests/test_words.py`, existing `tests/test_wordrects.py` must stay green

**Interfaces:**
- Produces:
  - `is_cjk(ch: str) -> bool`: Han (incl. ext. A, compatibility), Hiragana, Katakana (incl. half-width), CJK symbols and full-width punctuation. Hangul is NOT cjk here (Korean spaces its words).
  - `split_words(text: str) -> list[str]`: whitespace chunks; inside a chunk every CJK letter (Han, kana including `ー`) is its own token, non-CJK runs stay whole, and a run made only of punctuation (Unicode category `P*`, e.g. `。`, `！`, `」`) attaches to the previous token.
  - `join_words(tokens: list[str]) -> str`: joins with one space, no space where either side of the seam is `is_cjk`.
  - `word_units(token: str) -> int`: `CJK_UNITS` (3) per CJK letter, 0 per punctuation character, 1 per other non-space character.
  - `word_spans(text: str, words: list[str]) -> list[tuple[int, int]]`: char ranges, found in order (moved from wordrects' algorithm); a missing word gets an empty span at the cursor.

- [ ] **Step 1: Write failing tests** in `tests/test_words.py`:
  `split_words("hello world") == ["hello", "world"]`;
  `split_words("夜に駆ける") == ["夜", "に", "駆", "け", "る"]`;
  `split_words("Lemon 夢ならば") == ["Lemon", "夢", "な", "ら", "ば"]`;
  `split_words("夢。ok!") == ["夢。", "ok!"]`;
  `split_words("사랑해 너를") == ["사랑해", "너를"]`;
  `join_words(["夜", "に", "Lemon", "go"]) == "夜にLemon go"`;
  `word_units("夜") == 3 and word_units("hey") == 3`;
  `word_spans("a b a", ["a", "a"]) == [(0, 1), (4, 5)]`;
  `word_spans("ab", ["x", "b"]) == [(0, 0), (1, 2)]`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_words.py -q`; expected FAIL (module missing).
- [ ] **Step 3: Implement `words.py`**; `is_cjk` uses code-point ranges, not `unicodedata` names.
- [ ] **Step 4: Make `word_byte_ranges` convert `word_spans` to UTF-8 byte offsets.**
- [ ] **Step 5: Run** `python3 -m pytest tests/test_words.py tests/test_wordrects.py -q`; expected PASS.
- [ ] **Step 6: Commit** `feat: add CJK-aware lyric word tokens`.

### Task 2: Calibrated word-timing estimator

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/timing.py` (`estimate_words`, constants)
- Create: `tests/tools/calibrate_timing.py` (dev script, not collected by pytest)
- Test: `tests/test_timing.py`

**Interfaces:**
- Consumes: `split_words`, `word_units` (Task 1).
- Produces: constants `SECONDS_PER_UNIT = 0.08`, `LINE_FILL = 0.9`, `WORD_WEIGHT_PAD = 2`; `SECONDS_PER_CHAR` is removed.
  `estimate_words(line)`: tokens from `split_words(line.text)`, weights `word_units(t) + WORD_WEIGHT_PAD`, total duration `min((line.end - line.start) * LINE_FILL, SECONDS_PER_UNIT * sum(word_units))`.

- [ ] **Step 1: Write failing tests** (replace `test_estimate_caps_long_gap`, keep the rest):
  `test_estimate_paces_long_window`: `Line(10.0, 40.0, "hello there world")` gives 3 words, `words[1].start == approx(10.4)`, `words[-1].end == approx(11.2)`.
  `test_estimate_fills_short_window`: `Line(10.0, 11.0, "hello there world")` gives `words[-1].end == approx(10.9)`.
  `test_estimate_cjk_per_character`: `Line(0.0, 10.0, "夜に駆ける")` gives 5 words, each `0.24` s long.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_timing.py -q`; expected FAIL on the three new tests.
- [ ] **Step 3: Implement the new `estimate_words`.**
- [ ] **Step 4: Write `tests/tools/calibrate_timing.py`**: reads `$XDG_CACHE_HOME/hyde/encore/lyrics/*.json` with `sync == "word"`, re-estimates each line from its first word start and the next line start, prints mean and median word-start error and last-word-end error for the current constants, and for each song half (even/odd) separately. It prints numbers only, never lyric text.
- [ ] **Step 5: Run** the tests (PASS) and `python3 tests/tools/calibrate_timing.py`; expected mean word-start error at or under 0.25 s on both halves. Paste the output into the commit body.
- [ ] **Step 6: Commit** `feat: pace estimated words like real singing`.

### Task 3: Instrumental gaps in the cursor and the protocol

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/timing.py` (`Cursor`, `locate`, `GAP_HOLD_SECONDS`)
- Modify: `Configs/.local/lib/hyde/encorelib/protocol.py` (`build_state`, `hyprlock_markup`)
- Modify: `Configs/.local/lib/hyde/encorelib/lyricview.py` (use line text, shared hold constant)
- Modify: `docs/superpowers/plans/2026-11-03-encore-core.md` (protocol example: `line.text`, `gap`)
- Test: `tests/test_timing.py`, `tests/test_protocol.py`, `tests/test_lyricview.py`

**Interfaces:**
- Consumes: `word_spans` (Task 1).
- Produces:
  - `Cursor(line, word, progress, after: int = -1)`: `line` is the live line or -1 in any gap (intro, instrumental, explicit empty line, outro); `after` is the last line whose start has passed (equals `line` when live). `NO_CURSOR = Cursor(-1, -1, 0.0, -1)`.
  - `GAP_HOLD_SECONDS = 4.0` in `timing.py`; `lyricview.GAP_HIDE_SECONDS` becomes an alias of it.
  - A line is live from `start` until `min(end, last_word_end + GAP_HOLD_SECONDS)`; a line with blank text is never live.
  - State: `line` gains `"text"` (the source line text); `next` is the first non-blank line after `after`; new top-level `"gap": {"after": int, "until": float} | null`, non-null only when `line` is null and a non-blank line follows.
  - `hyprlock_markup` splits `line.text` at the end of the sung word's span, so CJK lines keep their spacing.
  - `build_view` renders `line["text"]` when present, else the old join.

- [ ] **Step 1: Write failing tests:**
  `test_locate_releases_line_after_hold`: words end at 12.0, next line at 60.0; `locate(l, 15.9).line == 0`, `locate(l, 16.1) == Cursor(-1, -1, 0.0, 0)`.
  `test_locate_blank_line_is_gap`: cursor on a blank-text line has `line == -1, after == index`.
  `test_locate_seek_back_from_gap`: `locate(l, 11.0).line == 0` after a call at 30.0.
  `test_build_state_gap`: in the hold-expired gap `state["line"] is None`, `state["gap"] == {"after": 0, "until": 60.0}`, `state["next"]` is line 1's text; intro gives `{"after": -1, "until": first_start}`; after the last line `state["gap"] is None`.
  `test_build_state_line_text`: `state["line"]["text"] == "夜に駆ける"`.
  `test_hyprlock_markup_cjk`: cursor on word 1 of `夜に駆ける` gives the accent span `夜に` and dim span `駆ける` with no space between them.
  `test_build_view_uses_line_text`: words `夜`,`に` with `line.text` `夜に` gives `view.text == "夜に"`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_timing.py tests/test_protocol.py tests/test_lyricview.py -q`; expected FAIL on the new tests.
- [ ] **Step 3: Implement** `Cursor.after`, the release rule in `locate`, the state fields, the span-based markup and `build_view` text.
- [ ] **Step 4: Run** the full suite `python3 -m pytest -q`; expected PASS (the daemon compares `(line, word)`, which now changes on release, so it republishes with no daemon edit).
- [ ] **Step 5: Update the protocol example** in the encore-core plan with `"text"` in `line` and `"gap": null`.
- [ ] **Step 6: Commit** `feat: publish instrumental gaps instead of a stuck last word`.

### Task 4: Keep source spacing in enhanced LRC and Spicy lines

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/lrc.py` (`_parse_words`, line text)
- Modify: `Configs/.local/lib/hyde/encorelib/providers.py` (`_parse_spicy` line text)
- Test: `tests/test_lrc.py`, `tests/test_providers.py`

**Interfaces:**
- Consumes: `is_cjk`, `join_words` (Task 1).
- Produces: enhanced LRC line text is the body with tags removed and whitespace collapsed; adjacent tag tokens with no whitespace between them and no CJK letter at the seam merge into one `Word` (start of the first, end of the last). Spicy line text is `join_words(words)`.

- [ ] **Step 1: Write failing tests:**
  `test_enhanced_syllables_merge`: `[00:01.00]<00:01.00>Hel<00:01.20>lo <00:01.50>world<00:02.00>` gives text `Hello world`, words `[("Hello", 1.0, 1.5), ("world", 1.5, 2.0)]`.
  `test_enhanced_cjk_keeps_characters`: `[00:01.00]<00:01.00>夜<00:01.30>に<00:01.60>` gives text `夜に` and two words.
  `test_spicy_cjk_line_text`: a synthetic Syllable payload with lead syllables `夜`, `に` (`IsPartOfWord` false) gives line text `夜に`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_lrc.py tests/test_providers.py -q`; expected FAIL on the new tests.
- [ ] **Step 3: Implement** the merge in `_parse_words` and `join_words` in both parsers.
- [ ] **Step 4: Run** `python3 -m pytest -q`; expected PASS.
- [ ] **Step 5: Commit** `fix: keep source spacing in word-timed lines`.

### Task 5: LRCLIB search variants and best-match selection

**Files:**
- Create: `Configs/.local/lib/hyde/encorelib/query.py`
- Modify: `Configs/.local/lib/hyde/encorelib/providers.py` (`lrclib`)
- Test: `tests/test_query.py`, `tests/test_providers.py`

**Interfaces:**
- Produces:
  - `clean_title(title: str) -> str`: drops bracketed or dash-suffixed qualifiers matching `feat|ft|featuring|with|official|video|audio|lyrics?|visuali[sz]er|remaster(ed)?|live|explicit|clean|hd|hq|4k|radio edit|version`, and a bare trailing `feat. X`; collapses whitespace; never returns empty (falls back to the input).
  - `primary_artist(artist: str) -> str`: first part split on `,`, `;`, ` & `, ` x `, ` feat. `, ` ft. `, ` featuring `, ` with `; strips a trailing ` - Topic`.
  - `search_variants(title: str, artist: str) -> list[tuple[str, str]]`: (title, artist) pairs in order, deduplicated, at most `MAX_SEARCHES = 3`: the raw pair; `(clean_title(title), primary_artist(artist))`; when the title holds ` - ` (or en dash), `(clean_title(right), left)`.
  - `lrclib(t, fetch)`: `/get` only when artist, album and length are all present; each search sends only non-empty params; within one result list the best sync rank wins (word > line > none, first wins ties); variants run in order, stop at the first synced hit, else return the best plain result seen.

- [ ] **Step 1: Write failing tests:**
  `test_clean_title`: `"Stay (feat. Justin Bieber)" -> "Stay"`, `"Song - Remastered 2011" -> "Song"`, `"Blinding Lights (Official Video)" -> "Blinding Lights"`, `"(Live)" -> "(Live)"`.
  `test_primary_artist`: `"The Kid LAROI, Justin Bieber" -> "The Kid LAROI"`, `"Artist - Topic" -> "Artist"`.
  `test_search_variants_browser`: `("The Weeknd - Blinding Lights (Official Video)", "TheWeekndVEVO")` includes `("Blinding Lights", "The Weeknd")` and has at most 3 entries.
  `test_lrclib_empty_artist_omits_param`: fake fetch records URLs; no URL contains `artist_name=` and none hits `/get`.
  `test_lrclib_feat_retry`: fake search returns `[]` for the raw pair and a synced record for `Stay`/`The Kid LAROI`; result is that record.
  `test_lrclib_prefers_synced_over_earlier_plain`: one result list, plain-only record first, synced second; result `sync == "line"`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_query.py tests/test_providers.py -q`; expected FAIL.
- [ ] **Step 3: Implement `query.py` and the new `lrclib` flow.**
- [ ] **Step 4: Run** `python3 -m pytest -q`; expected PASS.
- [ ] **Step 5: Live check** (read-only GET, no player involved): `python3 -c` calling `lrclib(TrackInfo("Stay (feat. Justin Bieber)", "The Kid LAROI, Justin Bieber", "", 141.0, "", "", "test"))` returns synced lyrics; print only the line count and sync level.
- [ ] **Step 6: Commit** `feat: retry LRCLIB with cleaned titles and artists`.

### Task 6: Cache key version and size cap

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/lookup.py` (`cache_key`), `Configs/.local/lib/hyde/encorelib/cache.py`
- Test: `tests/test_lookup.py`, `tests/test_cache.py`

**Interfaces:**
- Produces: `LOOKUP_VERSION = 2`; `cache_key` ends in `-v2`, so lyrics cached before Tasks 4-5 are refetched once.
  `LyricsCache.prune(max_files: int = MAX_FILES)` with `MAX_FILES = 2000` deletes the oldest files by mtime beyond the cap; `put` calls it; `get` touches the mtime of a hit so pruning is least-recently-used.

- [ ] **Step 1: Write failing tests:** `test_cache_key_has_version` (`cache_key(...).endswith("-v2")`); `test_prune_keeps_recent` (cap 3, five puts with increasing mtimes, a `get` of the oldest, then prune leaves that one and the two newest); `test_get_ignores_v1_key` (a file under the old key name is not returned by `lookup_lyrics`, which fetches).
- [ ] **Step 2: Run** `python3 -m pytest tests/test_cache.py tests/test_lookup.py -q`; expected FAIL.
- [ ] **Step 3: Implement**; `prune` ignores `.tmp` files and swallows `OSError` per file.
- [ ] **Step 4: Run** `python3 -m pytest -q`; expected PASS.
- [ ] **Step 5: Commit** `feat: version and cap the lyrics cache`.

### Task 7: Playback rate in the clock

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/clock.py`
- Test: `tests/test_clock.py`

**Interfaces:**
- Produces: `clean_rate(value: object) -> float` returns `float(value)` when it is finite and `0 < value <= 8`, else `1.0`.
  `PlaybackClock.sync(position, playing, rate: float | None = None)`: `None` keeps the current rate, anything else goes through `clean_rate`. Layer 2 reads MPRIS `Rate` and passes it.

- [ ] **Step 1: Write failing tests:** `test_clean_rate` (`1.5 -> 1.5`, `0 -> 1.0`, `-1 -> 1.0`, `nan -> 1.0`, `"x" -> 1.0`, `None -> 1.0`); `test_sync_keeps_rate_when_omitted` (sync with 1.5, then sync without rate; after 2 fake seconds the position advanced 3.0).
- [ ] **Step 2: Run** `python3 -m pytest tests/test_clock.py -q`; expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python3 -m pytest -q`; expected PASS.
- [ ] **Step 5: Commit** `feat: keep the playback rate across clock resyncs`.

### Task 8: Config accepts every overlay style

**Files:**
- Modify: `Configs/.local/lib/hyde/encorelib/config.py`, `Configs/.local/share/hyde/schema/config.toml`, `Configs/.local/share/hyde/schema/schema.toml`, `README.md`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `stream.STYLES`.
- Produces: `overlay_style` accepts any name in `STYLES`; schema and README list `line, stack, constellation, visual`.

- [ ] **Step 1: Write failing test** `test_overlay_style_visual`: `load_config({"ENCORE_OVERLAY_STYLE": "visual"}, env_file=missing).overlay_style == "visual"`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_config.py -q`; expected FAIL.
- [ ] **Step 3: Implement** with `_as_choice(..., STYLES, "line")`; update the two schema fragments and README.
- [ ] **Step 4: Run** `python3 -m pytest -q` and `python3 -c "import tomllib, glob; [tomllib.load(open(f, 'rb')) for f in glob.glob('Configs/.local/share/hyde/schema/*.toml')]"`; expected PASS.
- [ ] **Step 5: Commit** `fix: accept the visual style in config.toml`.

### Task 9: Docs and end-to-end check

**Files:**
- Modify: `docs/STATE.md`, `docs/DECISIONS.md`, `AGENTS.md` (encorelib module list: words, query)

- [ ] **Step 1: E2E on a private bus** (never the owner's players or daemon): a script in the scratchpad runs `dbus-run-session` with a private `XDG_RUNTIME_DIR`, `XDG_CACHE_HOME` and `ENCORE_LYRICS_DIRS`, holding a synthetic `Rick Astley - Never Gonna Give You Up.lrc` (invented lines, a 30 s instrumental gap, one CJK line); inside it start `tests/e2e/fake_mpris.py`, the repo's `encore.py daemon`, drive `playerctl -p encoretest play|position N` and read `encore.py status`.
  Expected: `line` goes null with `gap.until` set 4 s after the last word before the gap, `line` returns at the next line, and the CJK line's `line.text` has no inner spaces.
  Layer 2 turns this script into the reusable harness in `tests/e2e/`.
- [ ] **Step 2: DECISIONS** #18 LRCLIB `lyricsfile` deferred (0/600, YAML, re-survey later) and #19 estimator calibration (constants, error numbers, gap hold).
- [ ] **Step 3: STATE**: move fixed gaps out of Known gaps, add the new numbers, add the `lyricsfile` re-survey Idea, bump `verified:` after checking against the code.
- [ ] **Step 4: Full verification**: `python3 -m pytest -q`, both ruff commands; all clean.
- [ ] **Step 5: Commit** `docs: record layer 1 engine results`.
