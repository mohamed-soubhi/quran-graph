"""Deterministic locator: anchor phrases to exact original character offsets (T2.3)."""

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


def locate(
    text: str,
    anchor: HadithSpanAnchor,
    window_start: int = 0,
) -> tuple[int, int] | None:
    """Locate a hadith anchor in the original text and return exact character offsets.

    Following x-locator-rules in docs/extraction_schema.json:
    1. Normalize text and both anchors; s = first match of start_anchor at or after window_start;
       e = first match of end_anchor at or after s; either missing -> return None with warning.
    2. start = index[s]; end = index[e + len(norm_end) - 1] + 1.
    3. Extend end over following Mn characters (diacritics), then over following closing marks:
       " ” » ) ] ﴾
    4. Anchor matches inside [[ ... ]] footnotes are skipped; if no match outside remains -> None.

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

    # Map window_start (original text offset) to the corresponding normalized index
    norm_window_start = bisect.bisect_left(index, window_start) if window_start > 0 else 0

    # Footnote ranges in original offsets; anchor matches inside them are skipped (x-locator-rules)
    footnotes = [m.span() for m in FOOTNOTE_RE.finditer(text)]

    def in_footnote(pos: int) -> bool:
        return any(fn_start <= pos < fn_end for fn_start, fn_end in footnotes)

    def find_outside(needle: str, from_pos: int) -> int:
        """First normalized match at or after from_pos whose whole range lies outside footnotes."""
        k = norm.find(needle, from_pos)
        while k != -1:
            if not in_footnote(index[k]) and not in_footnote(index[k + len(needle) - 1]):
                return k
            logger.warning("Anchor %r match at offset %d is inside a [[...]] footnote; skipped", needle, index[k])
            k = norm.find(needle, k + 1)
        return -1

    s = find_outside(norm_start, norm_window_start)
    if s == -1:
        logger.warning(
            "Start anchor %r not found outside footnotes at or after window_start %d",
            anchor.start_anchor,
            window_start,
        )
        return None

    e = find_outside(norm_end, s)
    if e == -1:
        logger.warning(
            "End anchor %r not found outside footnotes at or after start match position %d",
            anchor.end_anchor,
            s,
        )
        return None

    start = index[s]
    end = index[e + len(norm_end) - 1] + 1

    # Extend end over following Mn characters (diacritics of the last letter)
    while end < len(text) and unicodedata.category(text[end]) == "Mn":
        end += 1

    # Extend end over directly following closing marks
    while end < len(text) and text[end] in CLOSING_MARKS:
        end += 1

    return start, end
