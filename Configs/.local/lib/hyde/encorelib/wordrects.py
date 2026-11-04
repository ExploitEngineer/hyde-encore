"""Map each word of a lyric line to its UTF-8 byte span in the line text.

Pango's index APIs (index_to_pos, get_x_ranges) take byte offsets into the
layout text, so the overlay needs byte ranges, found in word order so that
repeated words resolve to their own occurrence.
"""

from __future__ import annotations

from .words import word_spans


def word_byte_ranges(text: str, words: list[str]) -> list[tuple[int, int]]:
    def to_bytes(index: int) -> int:
        return len(text[:index].encode("utf-8"))

    return [(to_bytes(a), to_bytes(b)) for a, b in word_spans(text, words)]
