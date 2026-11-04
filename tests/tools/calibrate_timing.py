#!/usr/bin/env python3
"""Score the word-timing estimator against real word-synced lyrics.

Reads the word-synced songs in the local encore cache
($XDG_CACHE_HOME/hyde/encore/lyrics), strips their word timing, re-estimates
each line from its first word and the next line's start, and prints how far
the estimate lands from the real timing. Prints numbers only, never lyrics.

Usage: python3 tests/tools/calibrate_timing.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "Configs" / ".local" / "lib" / "hyde"
sys.path.insert(0, str(LIB))

from encorelib import timing
from encorelib.model import Line
from encorelib.words import join_words


def load_songs(root: Path) -> list[dict]:
    songs = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("sync") == "word":
            songs.append(data)
    return songs


def score(songs: list[dict]) -> tuple[float, float, float, int]:
    """(mean, median word-start error, mean last-word-end error, words scored)."""
    starts: list[float] = []
    tails: list[float] = []
    for song in songs:
        lines = song["lines"]
        for i, line in enumerate(lines):
            real = line["words"]
            if len(real) < 2:
                continue
            nxt = lines[i + 1]["start"] if i + 1 < len(lines) else line["end"]
            text = join_words([w[0] for w in real])
            guess = timing.estimate_words(Line(real[0][1], nxt, text)).words
            if len(guess) != len(real):
                continue  # tokenization differs from the source's words
            starts += [abs(g.start - r[1]) for g, r in zip(guess, real)]
            tails.append(abs(guess[-1].end - real[-1][2]))
    if not starts:
        return 0.0, 0.0, 0.0, 0
    return statistics.mean(starts), statistics.median(starts), statistics.mean(tails), len(starts)


def main() -> int:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    songs = load_songs(cache / "hyde" / "encore" / "lyrics")
    if not songs:
        print("no word-synced songs in the cache yet; play some with Spicy Lyrics on")
        return 1
    print(
        f"constants: SECONDS_PER_UNIT={timing.SECONDS_PER_UNIT} "
        f"LINE_FILL={timing.LINE_FILL} WORD_WEIGHT_PAD={timing.WORD_WEIGHT_PAD}"
    )
    for name, subset in (("all", songs), ("even", songs[::2]), ("odd", songs[1::2])):
        mean, median, tail, n = score(subset)
        print(
            f"{name:4} songs={len(subset):2} words={n:4}  word-start err mean {mean:.3f}s "
            f"median {median:.3f}s  last-word-end err {tail:.3f}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
