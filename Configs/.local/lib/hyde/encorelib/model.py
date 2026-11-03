"""Lyrics data model shared by every encore component."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Sync = Literal["word", "line", "none"]


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Line:
    start: float
    end: float
    text: str
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class Lyrics:
    lines: tuple[Line, ...]
    sync: Sync
    source: str
    credit: str | None = None

    def to_dict(self) -> dict:
        return {
            "sync": self.sync,
            "source": self.source,
            "credit": self.credit,
            "lines": [
                {
                    "start": ln.start,
                    "end": ln.end,
                    "text": ln.text,
                    "words": [[w.text, w.start, w.end] for w in ln.words],
                }
                for ln in self.lines
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Lyrics:
        return cls(
            lines=tuple(
                Line(
                    start=ln["start"],
                    end=ln["end"],
                    text=ln["text"],
                    words=tuple(Word(t, s, e) for t, s, e in ln.get("words", ())),
                )
                for ln in d["lines"]
            ),
            sync=d["sync"],
            source=d["source"],
            credit=d.get("credit"),
        )
