"""Hadith span extractor: regex cues + GLM anchors + deterministic locator (T4.5)."""

import re
from typing import Sequence

from src.extract.footnotes import FOOTNOTE_RE, find_footnotes
from src.extract.glm_client import extract_hadith_anchors
from src.extract.locate import locate
from src.extract.models import HadithSpanAnchor
from src.extract.normalize import normalize_with_map
from src.extract.quran_spans import QUOTE_RE, find_quotes
from src.log import get_logger

logger = get_logger("hadith_spans")

# Cue regex on v2-normalized Arabic text (outside [[...]] footnotes)
# Groups:
# 1. isnad verbs (حدثنا / أخبرنا / سمعت / أنبأنا)
# 2. takhrij verbs (رواه / أخرجه / أخرجاه / روى / خرجه / علقه البخاري)
# 3. Prophet attributions & hadith formulas (قال رسول الله / عن النبي / في الصحيح / في الحديث / صح الحديث)
CUE_REGEX: re.Pattern[str] = re.compile(
    r"(?:"
    r"[وف]?(?:حدثنا|حدثني|حدثت|حدث|اخبرنا|اخبرني|اخبر|انبانا|انباني|سمعت)"
    r"|"
    r"[وف]?(?:رواه|روى|روي|روينا|اخرجه|اخرجاه|اخرجوه|خرجه|علقه البخاري)"
    r"|"
    r"(?:قال رسول الله|عن رسول الله|عن النبي|[وف]?في الصحيح|[وف]?في الحديث|صح الحديث|[وف]?ثبت في صحيح)"
    r")"
)

# Sentence end pattern for splitting long paragraphs (dot or colon followed by space or newline)
SENTENCE_END_RE: re.Pattern[str] = re.compile(r"([.:])(?:\s+|\n|$)")


def find_cue_paragraphs(text: str) -> list[tuple[int, int]]:
    """Find paragraphs (original offsets, split on \\n\\n) matching the hadith cue list.

    Matching runs on v2-normalized text outside [[...]] footnotes.
    Logs which cue fired for each matched paragraph.

    Args:
        text: Original verbatim Arabic text of a TafsirSegment.

    Returns:
        List of (start, end) offsets in original text coordinates.
    """
    if not text:
        return []

    paras = []
    start = 0
    parts = text.split("\n\n")
    for part in parts:
        end = start + len(part)
        if part.strip():
            # Mask footnotes by replacing with spaces to preserve character offsets exactly
            masked_part = FOOTNOTE_RE.sub(lambda m: " " * len(m.group(0)), part)
            norm_part, _ = normalize_with_map(masked_part)
            match = CUE_REGEX.search(norm_part)
            if match:
                cue_word = match.group(0)
                logger.debug(
                    "Cue %r fired in paragraph [%d, %d)",
                    cue_word,
                    start,
                    end,
                )
                paras.append((start, end))
        start = end + 2  # skip \n\n

    return paras


def split_long_paragraph(
    para_text: str,
    para_start: int,
    max_len: int = 3000,
) -> list[tuple[int, int]]:
    """Split a paragraph longer than max_len chars into windows <= max_len.

    Splits at sentence ends ('.' or ':' followed by space or newline)
    never inside [[...]] footnotes or ﴿...﴾ Quran quotes.
    Overlaps one sentence between consecutive windows.

    Args:
        para_text: The verbatim text of the paragraph.
        para_start: Original start offset of this paragraph in the segment.
        max_len: Maximum window length in characters (default 3,000).

    Returns:
        List of (window_start, window_end) in original text coordinates.
    """
    n = len(para_text)
    if n <= max_len:
        return [(para_start, para_start + n)]

    fn_spans = [m.span() for m in FOOTNOTE_RE.finditer(para_text)]
    q_spans = [m.span() for m in QUOTE_RE.finditer(para_text)]

    def is_inside(pos: int) -> bool:
        for s, e in fn_spans:
            if s < pos < e:
                return True
        for s, e in q_spans:
            if s < pos < e:
                return True
        return False

    boundaries = [0]
    for m in SENTENCE_END_RE.finditer(para_text):
        pos = m.end()
        if not is_inside(pos):
            boundaries.append(pos)
    if boundaries[-1] != n:
        boundaries.append(n)

    windows = []
    i = 0
    while i < len(boundaries) - 1:
        win_s = boundaries[i]
        j = i + 1
        while j < len(boundaries) and (boundaries[j] - win_s) <= max_len:
            j += 1

        actual_j = j - 1 if j > i + 1 else j
        win_e = boundaries[actual_j]
        windows.append((para_start + win_s, para_start + win_e))

        if actual_j >= len(boundaries) - 1:
            break

        # Overlap one sentence: next window starts at previous boundary
        next_i = max(i + 1, actual_j - 1)
        i = next_i

    return windows


def locate_and_check_anchors(
    text: str,
    anchors: Sequence[HadithSpanAnchor],
    window_start: int = 0,
    segment_id: str = "",
    run_id: str = "run0",
    model: str = "",
) -> list[dict]:
    """Locate anchors in the segment text and apply rejection checks (Step 4).

    Rejection criteria:
    - Anchor not found by locate();
    - start or end falls strictly inside a [[...]] footnote;
    - start or end falls strictly inside a ﴿...﴾ quote;
    - span length > 6,000 characters;
    - duplicates (same start and end) are merged.

    Args:
        text: Full verbatim text of the TafsirSegment.
        anchors: List of HadithSpanAnchor returned by GLM.
        window_start: Offset where the window starts in segment text.
        segment_id: ID of the segment (e.g. 'ibn-kathir:2:255-255:1').
        run_id: Identifier for the extraction run.
        model: Model name/tag used.

    Returns:
        List of span dicts with keys matching gold set and schema:
        span_id, segment_id, start, end, type ('HADITH'), kind, cue,
        collection_hint, number_hint, method ('glm'), source ('run:<run_id>'), model.
    """
    fn_spans = find_footnotes(text)
    q_spans = find_quotes(text)

    def strictly_inside_fn(pos: int) -> bool:
        return any(s < pos < e for s, e in fn_spans)

    def strictly_inside_q(pos: int) -> bool:
        return any(s < pos < e for s, e in q_spans)

    results: list[dict] = []
    seen: set[tuple[int, int]] = set()

    for anchor in anchors:
        offsets = locate(text, anchor, window_start=window_start)
        if offsets is None:
            logger.warning(
                "Run %s: Anchor not found in text: start=%r, end=%r",
                run_id,
                anchor.start_anchor,
                anchor.end_anchor,
            )
            continue

        start, end = offsets

        # Check strictly inside footnote
        if strictly_inside_fn(start) or strictly_inside_fn(end):
            logger.warning(
                "Run %s: Anchor rejected (inside footnote): [%d, %d)",
                run_id,
                start,
                end,
            )
            continue

        # Check strictly inside quote
        if strictly_inside_q(start) or strictly_inside_q(end):
            logger.warning(
                "Run %s: Anchor rejected (inside quote): [%d, %d)",
                run_id,
                start,
                end,
            )
            continue

        # Check max length
        if (end - start) > 6000:
            logger.warning(
                "Run %s: Anchor rejected (too long %d > 6000 chars): [%d, %d)",
                run_id,
                end - start,
                start,
                end,
            )
            continue

        # De-duplicate
        if (start, end) in seen:
            logger.debug("Run %s: Duplicate span [%d, %d) merged", run_id, start, end)
            continue
        seen.add((start, end))

        span_id = f"{segment_id}#{start}-{end}"
        record = {
            "span_id": span_id,
            "segment_id": segment_id,
            "start": start,
            "end": end,
            "type": "HADITH",
            "kind": anchor.kind,
            "cue": anchor.cue,
            "collection_hint": anchor.collection_hint,
            "number_hint": anchor.number_hint,
            "method": "glm",
            "source": f"run:{run_id}",
            "model": model,
            "fallback_used": getattr(offsets, "used_fallback", False),
        }
        results.append(record)

    return results


def extract_hadith_spans_for_segment(
    segment_id: str,
    text: str,
    run_id: str = "run0",
    model: str | None = None,
) -> list[dict]:
    """Extract hadith spans across an entire segment text."""
    cue_paras = find_cue_paragraphs(text)
    spans: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()

    for p_start, p_end in cue_paras:
        para_text = text[p_start:p_end]
        windows = split_long_paragraph(para_text, p_start, max_len=3000)
        for w_start, w_end in windows:
            w_text = text[w_start:w_end]
            anchor_list = extract_hadith_anchors(w_text, model=model)
            located = locate_and_check_anchors(
                text,
                anchor_list.spans,
                window_start=w_start,
                segment_id=segment_id,
                run_id=run_id,
                model=model or "glm-5.3-flash:cloud",
            )
            for sp in located:
                key = (sp["start"], sp["end"])
                if key not in seen_spans:
                    seen_spans.add(key)
                    spans.append(sp)

    # Sort spans by start offset
    spans.sort(key=lambda s: (s["start"], s["end"]))
    return spans


def compute_iou(s1: int, e1: int, s2: int, e2: int) -> float:
    """Compute Intersection-over-Union (IoU) of two character ranges."""
    inter = max(0, min(e1, e2) - max(s1, s2))
    union = max(e1, e2) - min(s1, s2)
    return inter / union if union > 0 else 0.0


def match_spans_one_to_one(
    predicted_spans: list[dict],
    gold_spans: list[dict],
    min_iou: float = 0.5,
) -> tuple[list[tuple[dict, dict, float]], list[dict], list[dict]]:
    """Match predicted and gold spans one-to-one by best IoU >= min_iou.

    Returns:
        tuple of (matched_pairs, false_positives, misses)
        where matched_pairs is list of (pred_span, gold_span, iou).
    """
    candidates = []
    for pi, p in enumerate(predicted_spans):
        for gi, g in enumerate(gold_spans):
            iou = compute_iou(p["start"], p["end"], g["start"], g["end"])
            if iou >= min_iou:
                candidates.append((iou, pi, gi))

    # Sort descending by IoU
    candidates.sort(key=lambda x: x[0], reverse=True)

    matched_p: set[int] = set()
    matched_g: set[int] = set()
    pairs: list[tuple[dict, dict, float]] = []

    for iou, pi, gi in candidates:
        if pi not in matched_p and gi not in matched_g:
            matched_p.add(pi)
            matched_g.add(gi)
            pairs.append((predicted_spans[pi], gold_spans[gi], iou))

    false_positives = [p for i, p in enumerate(predicted_spans) if i not in matched_p]
    misses = [g for i, g in enumerate(gold_spans) if i not in matched_g]

    return pairs, false_positives, misses
