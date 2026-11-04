"""Deterministic locator: anchor phrases to exact original character offsets (T2.3, T4.5b)."""

import bisect
import re
import unicodedata

from src.extract.models import HadithSpanAnchor
from src.extract.normalize import normalize_with_map
from src.log import get_logger

logger = get_logger("locate")

# Closing punctuation marks to extend over (from docs/extraction_schema.json x-locator-rules)
CLOSING_MARKS: set[str] = {'"', "”", "»", ")", "]", "﴾"}

# Editor footnotes enclosed in [[...]]
FOOTNOTE_RE: re.Pattern[str] = re.compile(r"\[\[.*?\]\]", re.DOTALL)


def is_word_char(c: str) -> bool:
    """Return True if character is part of an Arabic/alphanumeric word (T4.5b F4)."""
    cat = unicodedata.category(c)
    return cat.startswith("L") or cat.startswith("M") or cat.startswith("N") or c == "\u0640"


class LocateResult(tuple):
    """(start, end) offsets in original text, with fallback usage indicator."""
    used_fallback: bool

    def __new__(cls, start: int, end: int, used_fallback: bool = False):
        obj = super().__new__(cls, (start, end))
        obj.used_fallback = used_fallback
        return obj


def locate(
    text: str,
    anchor: HadithSpanAnchor,
    window_start: int = 0,
) -> tuple[int, int] | None:
    """Locate a hadith anchor in the original text and return exact character offsets.

    Following x-locator-rules in docs/extraction_schema.json and T4.5b review fixes:
    1. Normalize text and both anchors; search normalized text with footnote characters
       removed (whitespace collapsed, offset map kept), so a match can cross a [[...]]
       footnote but can never start or end inside one (F3). An anchor found only inside
       a footnote returns None. A match crossing a footnote is not a fallback.
    2. s = first match of start_anchor at or after window_start;
       e = first match of end_anchor at or after s; either missing -> return None.
    3. start = fn_index[s]; end = fn_index[e + len(norm_end) - 1] + 1.
    4. Move start back to word boundary; move end forward to word boundary (F4).
    5. Extend end over following Mn characters (diacritics), then over following closing marks:
       " ” » ) ] ﴾

    Args:
        text: Verbatim original Arabic text.
        anchor: HadithSpanAnchor with start_anchor and end_anchor.
        window_start: Optional starting offset in original text coordinates (default 0).

    Returns:
        tuple[int, int] of (start, end) offsets in the original text, or None.
    """
    if not text:
        logger.warning("Empty text passed to locate")
        return None

    norm, index = normalize_with_map(text)
    if not norm:
        logger.warning("Normalized text is empty")
        return None

    norm_start, _ = normalize_with_map(anchor.start_anchor)
    norm_end, _ = normalize_with_map(anchor.end_anchor)

    if not norm_start:
        logger.warning("Empty normalized start anchor: %r", anchor.start_anchor)
        return None
    if not norm_end:
        logger.warning("Empty normalized end anchor: %r", anchor.end_anchor)
        return None

    # Collapse whitespace in anchors
    norm_start = re.sub(r"\s+", " ", norm_start).strip()
    norm_end = re.sub(r"\s+", " ", norm_end).strip()

    # Footnote ranges in original offsets (F3: search fn-stripped normalized text)
    footnotes = [m.span() for m in FOOTNOTE_RE.finditer(text)]
    in_fn = [False] * (len(text) + 1)
    for fs, fe in footnotes:
        in_fn[fs:fe] = [True] * (fe - fs)

    # Build footnote-stripped normalized text with collapsed whitespace and offset map
    fn_chars: list[str] = []
    fn_index: list[int] = []
    prev_space = False
    for i, c in enumerate(norm):
        if in_fn[index[i]]:
            continue
        if c.isspace():
            if not prev_space:
                fn_chars.append(" ")
                fn_index.append(index[i])
                prev_space = True
        else:
            fn_chars.append(c)
            fn_index.append(index[i])
            prev_space = False

    fn_norm = "".join(fn_chars)
    if not fn_norm:
        logger.warning("Footnote-stripped normalized text is empty")
        return None

    # Map window_start (original text offset) to the corresponding fn_norm index
    fn_window_start = bisect.bisect_left(fn_index, window_start) if window_start > 0 else 0

    s = fn_norm.find(norm_start, fn_window_start)
    used_fallback = False
    if s == -1:
        words = norm_start.split()
        for k in range(len(words) - 1, 2, -1):
            sub_needle = " ".join(words[:k])
            s = fn_norm.find(sub_needle, fn_window_start)
            if s != -1:
                used_fallback = True
                logger.info("Start anchor %r matched with prefix %r", anchor.start_anchor, sub_needle)
                break

    if s == -1:
        logger.warning(
            "Start anchor %r not found outside footnotes at or after window_start %d",
            anchor.start_anchor,
            window_start,
        )
        return None

    e = fn_norm.find(norm_end, s)
    match_end_len = len(norm_end)
    if e == -1:
        words = norm_end.split()
        for k in range(len(words) - 1, 2, -1):
            sub_needle = " ".join(words[-k:])
            e = fn_norm.find(sub_needle, s)
            if e != -1:
                used_fallback = True
                match_end_len = len(sub_needle)
                logger.info("End anchor %r matched with suffix %r", anchor.end_anchor, sub_needle)
                break

    if e == -1:
        logger.warning(
            "End anchor %r not found outside footnotes at or after start match position %d",
            anchor.end_anchor,
            s,
        )
        return None

    start = fn_index[s]
    end = fn_index[e + match_end_len - 1] + 1

    # Move start back to word boundary (F4)
    while start > 0 and is_word_char(text[start - 1]):
        start -= 1

    # Move end forward to word boundary (F4)
    while end < len(text) and is_word_char(text[end]):
        end += 1

    # Extend end over following Mn characters (diacritics of the last letter)
    while end < len(text) and unicodedata.category(text[end]) == "Mn":
        end += 1

    # Extend end over directly following closing marks
    while end < len(text) and text[end] in CLOSING_MARKS:
        end += 1

    return LocateResult(start, end, used_fallback=used_fallback)
