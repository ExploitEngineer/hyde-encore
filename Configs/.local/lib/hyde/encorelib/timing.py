"""Word timing estimation and playback cursor lookup."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace

from .model import Line, Lyrics, Word

SECONDS_PER_CHAR = 0.45
WORD_WEIGHT_PAD = 2


@dataclass(frozen=True)
class Cursor:
    line: int
    word: int
    progress: float


NO_CURSOR = Cursor(-1, -1, 0.0)


def estimate_words(line: Line) -> Line:
    """Spread a line's words over its duration, weighted by word length."""
    texts = line.text.split()
    if not texts:
        return replace(line, words=())
    stop = min(line.end, line.start + SECONDS_PER_CHAR * len(line.text))
    weights = [len(t) + WORD_WEIGHT_PAD for t in texts]
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


def locate(lyrics: Lyrics, t: float) -> Cursor:
    """Return the line and word being sung at playback time t (seconds)."""
    if lyrics.sync == "none" or not lyrics.lines:
        return NO_CURSOR
    li = bisect_right(lyrics.lines, t, key=lambda ln: ln.start) - 1
    if li < 0:
        return NO_CURSOR
    line = lyrics.lines[li]
    if t >= line.end or not line.words:
        return Cursor(li, -1, 0.0)
    wi = bisect_right(line.words, t, key=lambda w: w.start) - 1
    if wi < 0:
        return Cursor(li, -1, 0.0)
    word = line.words[wi]
    if t >= word.end:
        return Cursor(li, wi, 1.0)
    span = word.end - word.start
    progress = (t - word.start) / span if span > 0 else 1.0
    return Cursor(li, wi, progress)
