"""Lyric word tokens that work for scripts written without spaces.

Chinese and Japanese lines carry no spaces between words, so each Han or
kana character becomes its own token (roughly one sung syllable). Korean
spaces its words, so Hangul stays grouped like Latin text. Punctuation
never stands alone inside a chunk: it rides on the neighbouring token.
"""

from __future__ import annotations

import unicodedata

CJK_UNITS = 3  # one CJK character sings like about three Latin letters

_CJK_RANGES = (
    (0x3000, 0x303F),  # CJK symbols and punctuation (incl. iteration mark)
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3100, 0x312F),  # Bopomofo
    (0x31A0, 0x31BF),  # Bopomofo extended
    (0x31F0, 0x31FF),  # Katakana phonetic extensions
    (0x3400, 0x4DBF),  # Han extension A
    (0x4E00, 0x9FFF),  # Han unified
    (0xF900, 0xFAFF),  # Han compatibility
    (0xFF00, 0xFF9F),  # full-width forms and half-width katakana
    (0x20000, 0x2FA1F),  # Han extensions B-F and compatibility supplement
    (0x30000, 0x3134F),  # Han extension G
)


def is_cjk(ch: str) -> bool:
    """True for Chinese and Japanese characters and their punctuation (not Hangul)."""
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def _is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P")


def _chunk_tokens(chunk: str) -> list[str]:
    out: list[str] = []
    lead = run = ""
    for ch in chunk:
        if _is_punct(ch):
            if run:
                run += ch
            elif out:
                out[-1] += ch
            else:
                lead += ch
        elif is_cjk(ch):
            if run:
                out.append(lead + run)
                lead = run = ""
            out.append(lead + ch)
            lead = ""
        else:
            run += ch
    if run:
        out.append(lead + run)
    elif lead:
        out.append(lead)
    return out


def split_words(text: str) -> list[str]:
    """Words of a lyric line; each Han or kana character is its own word."""
    tokens: list[str] = []
    for chunk in text.split():
        tokens.extend(_chunk_tokens(chunk))
    return tokens


def join_words(tokens: list[str]) -> str:
    """Join words with spaces, except where either side of the seam is CJK."""
    out = ""
    for token in tokens:
        if out and token and not (is_cjk(out[-1]) or is_cjk(token[0])):
            out += " "
        out += token
    return out


def word_units(token: str) -> int:
    """Singing length of a word: CJK_UNITS per CJK character, 1 per other letter."""
    units = 0
    for ch in token:
        if ch.isspace() or _is_punct(ch):
            continue
        units += CJK_UNITS if is_cjk(ch) else 1
    return units


def word_spans(text: str, words: list[str]) -> list[tuple[int, int]]:
    """Character range of each word in text, matched in order.

    Repeated words resolve to their own occurrence; a word found only
    earlier in the line falls back to that occurrence; a word that is not
    in the line gets an empty range at the cursor.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for word in words:
        index = text.find(word, cursor)
        if index < 0:
            index = text.find(word)
        if index < 0:
            spans.append((cursor, cursor))
            continue
        spans.append((index, index + len(word)))
        cursor = index + len(word)
    return spans
