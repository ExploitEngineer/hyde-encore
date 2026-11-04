"""Word timing estimation and playback cursor lookup."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace

from .model import Line, Lyrics, Word
from .words import split_words, word_units

# Calibrated against real word-synced songs (DECISIONS #19): singers run
# about 0.07 s per letter, so cap the pace there and leave a short tail
# before the next line instead of stretching words across instrumentals.
SECONDS_PER_UNIT = 0.08
LINE_FILL = 0.9
WORD_WEIGHT_PAD = 2
# A line stays on screen this long after its last word, then the cursor
# reports a gap, so an instrumental never shows a stale, fully lit line.
GAP_HOLD_SECONDS = 4.0


@dataclass(frozen=True)
class Cursor:
    """Where playback is in the lyrics.

    line is the live line, or -1 in any gap (intro, instrumental, blank
    line, outro); after is the last line whose start has passed, so a gap
    still knows where it sits.
    """

    line: int
    word: int
    progress: float
    after: int = -1


NO_CURSOR = Cursor(-1, -1, 0.0, -1)


def estimate_words(line: Line) -> Line:
    """Spread a line's words at a singing pace, weighted by word length."""
    texts = split_words(line.text)
    if not texts:
        return replace(line, words=())
    units = [word_units(t) for t in texts]
    duration = min((line.end - line.start) * LINE_FILL, SECONDS_PER_UNIT * sum(units))
    stop = line.start + max(0.0, duration)
    weights = [u + WORD_WEIGHT_PAD for u in units]
    scale = (stop - line.start) / sum(weights)
    words = []
    t = line.start
    for i, (text, weight) in enumerate(zip(texts, weights)):
        end = stop if i == len(texts) - 1 else t + weight * scale
        words.append(Word(text, t, end))
        t = end
    return replace(line, words=tuple(words))


def with_words(lyrics: Lyrics) -> Lyrics:
    """Estimate word timing for every timed line that lacks it."""
    if lyrics.sync == "none":
        return lyrics
    lines = tuple(ln if ln.words else estimate_words(ln) for ln in lyrics.lines)
    return replace(lyrics, lines=lines)


def release_time(line: Line) -> float:
    """When a line stops being live: its end, or the hold after its last word."""
    if line.words:
        return min(line.end, line.words[-1].end + GAP_HOLD_SECONDS)
    return line.end


def locate(lyrics: Lyrics, t: float) -> Cursor:
    """Return the line and word being sung at playback time t (seconds)."""
    if lyrics.sync == "none" or not lyrics.lines:
        return NO_CURSOR
    li = bisect_right(lyrics.lines, t, key=lambda ln: ln.start) - 1
    if li < 0:
        return NO_CURSOR
    line = lyrics.lines[li]
    if not line.text.strip() or t >= release_time(line):
        return Cursor(-1, -1, 0.0, li)
    if not line.words:
        return Cursor(li, -1, 0.0, li)
    wi = bisect_right(line.words, t, key=lambda w: w.start) - 1
    if wi < 0:
        return Cursor(li, -1, 0.0, li)
    word = line.words[wi]
    if t >= word.end:
        return Cursor(li, wi, 1.0, li)
    span = word.end - word.start
    progress = (t - word.start) / span if span > 0 else 1.0
    return Cursor(li, wi, progress, li)
