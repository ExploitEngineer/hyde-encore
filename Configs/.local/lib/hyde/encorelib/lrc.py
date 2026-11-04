"""Parser for plain and enhanced (word-timed) LRC lyrics."""

from __future__ import annotations

import re

from .model import Line, Lyrics, Word
from .words import is_cjk

LAST_LINE_SECONDS = 5.0

_LINE_TAG = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_WORD_TAG = re.compile(r"<(\d+):(\d+(?:\.\d+)?)>")
_OFFSET = re.compile(r"^\[offset:\s*([+-]?\d+)\s*\]$", re.IGNORECASE)
_META = re.compile(r"^\[[a-zA-Z]+:.*\]$")


def _seconds(minutes: str, seconds: str) -> float:
    return int(minutes) * 60 + float(seconds)


def _parse_words(body: str, shift: float) -> tuple[list[tuple[str, float]], float | None]:
    """Split an enhanced LRC body into (word, start) tokens.

    Tags inside a word (syllable timing, `<t>Hel<t>lo`) merge into one word
    that starts at the first syllable; CJK characters stay separate words.
    Returns the tokens and the time of a trailing closing tag, if any.
    """
    marks = list(_WORD_TAG.finditer(body))
    tokens: list[tuple[str, float]] = []
    closing: float | None = None
    glued = False  # the previous token ran straight into this tag
    for i, m in enumerate(marks):
        start = _seconds(m.group(1), m.group(2)) - shift
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        raw = body[m.end() : stop]
        text = raw.strip()
        if text:
            merge = (
                tokens
                and glued
                and not raw[0].isspace()
                and not is_cjk(tokens[-1][0][-1])
                and not is_cjk(text[0])
            )
            if merge:
                tokens[-1] = (tokens[-1][0] + text, tokens[-1][1])
            else:
                tokens.append((text, start))
            glued = not raw[-1].isspace()
        else:
            if raw:
                glued = False  # only whitespace between two tags: a word break
            if i == len(marks) - 1:
                closing = start
    return tokens, closing


def parse_lrc(text: str, source: str = "lrc") -> Lyrics:
    shift = 0.0
    entries: list[tuple[float, str]] = []
    untimed: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        offset = _OFFSET.match(line)
        if offset:
            shift = int(offset.group(1)) / 1000.0
            continue
        stamps = []
        pos = 0
        while m := _LINE_TAG.match(line, pos):
            stamps.append(_seconds(m.group(1), m.group(2)))
            pos = m.end()
        if stamps:
            body = line[pos:]
            entries.extend((t, body) for t in stamps)
        elif not _META.match(line):
            untimed.append(line)

    if not entries:
        lines = tuple(Line(start=0.0, end=0.0, text=t) for t in untimed)
        return Lyrics(lines=lines, sync="none", source=source)

    entries.sort(key=lambda e: e[0])
    lines: list[Line] = []
    has_words = False
    for i, (stamp, body) in enumerate(entries):
        start = stamp - shift
        end = entries[i + 1][0] - shift if i + 1 < len(entries) else start + LAST_LINE_SECONDS
        words: tuple[Word, ...] = ()
        if _WORD_TAG.search(body):
            tokens, closing = _parse_words(body, shift)
            built = []
            for j, (wtext, wstart) in enumerate(tokens):
                if j + 1 < len(tokens):
                    wend = tokens[j + 1][1]
                else:
                    wend = closing if closing is not None else end
                built.append(Word(wtext, wstart, wend))
            words = tuple(built)
            has_words = has_words or bool(words)
            body = " ".join(_WORD_TAG.sub("", body).split())
        lines.append(Line(start=start, end=end, text=body.strip(), words=words))

    return Lyrics(lines=tuple(lines), sync="word" if has_words else "line", source=source)
