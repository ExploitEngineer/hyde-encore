"""Map each word of a lyric line to its UTF-8 byte span in the line text.

Pango's index APIs (index_to_pos, get_x_ranges) take byte offsets into the
layout text, so the overlay needs byte ranges, found in word order so that
repeated words resolve to their own occurrence.
"""

from __future__ import annotations


def word_byte_ranges(text: str, words: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    byte_cursor = 0
    for word in words:
        index = text.find(word, cursor)
        if index < 0:
            index = text.find(word)
        if index < 0:
            ranges.append((byte_cursor, byte_cursor))
            continue
        start = len(text[:index].encode("utf-8"))
        end = start + len(word.encode("utf-8"))
        ranges.append((start, end))
        cursor = index + len(word)
        byte_cursor = end
    return ranges
