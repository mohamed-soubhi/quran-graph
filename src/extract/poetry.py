"""Poetry extraction: detect poetry verse lines and group into OTHER spans (T4.6).

Pure functions for deterministic regex-based poetry extraction.
Output: data/interim/spans/poetry.jsonl
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.log import get_logger

logger = get_logger("poetry")

DIACRITICS_RE: re.Pattern[str] = re.compile(r"[\u064B-\u0652\u0670]")
FOOTNOTE_INLINE_RE: re.Pattern[str] = re.compile(r"\[\[.*?\]\]")
FOOTNOTE_DOTALL_RE: re.Pattern[str] = re.compile(r"\[\[.*?\]\]", re.DOTALL)

DEFAULT_SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "interim" / "spans" / "poetry.jsonl"
DEFAULT_HADITH_PATH = ROOT / "data" / "interim" / "spans" / "hadith.jsonl"
DEFAULT_SOURCE = "run:20261117-1414-poetry"


def is_verse_line(line: str) -> bool:
    """Return True if line is a verse line according to T4.6 rules.

    A line (maximal run of non-\\n characters) is a verse line when, after
    removing [[...]] footnotes and Arabic diacritics (U+064B-U+0652, U+0670) and
    stripping spaces, it contains ' ... ' or ends with ' ...', and is at most
    100 characters long.
    """
    if not line:
        return False
    cleaned = FOOTNOTE_INLINE_RE.sub("", line)
    cleaned = DIACRITICS_RE.sub("", cleaned).strip()
    if not cleaned:
        return False
    has_ellipsis = (" ... " in cleaned) or cleaned.endswith(" ...")
    return has_ellipsis and (len(cleaned) <= 100)


def extract_poetry_from_text(
    text: str,
    segment_id: str,
    fn_spans: list[tuple[int, int]] | None = None,
    source: str = DEFAULT_SOURCE,
    hadith_spans: list[tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    """Extract poetry spans (OTHER) from a segment's text.

    - Consecutive verse lines separated only by whitespace form one poem.
    - Span start = start of the first line.
    - Span end = end of the last line, then trim backwards:
      trailing whitespace, then a trailing [[...]] footnote and whitespace
      before it (repeated while one ends the span).
    - Skip any verse line that lies inside a FOOTNOTE span.
    - Drop a candidate poem that contains a HADITH span: it is a narration line
      with an ellipsis («"بينما رجل ... " إلى آخره»), not verse (T4.6 review).
    """
    if not text:
        return []

    if fn_spans is None:
        fn_spans = [(m.start(), m.end()) for m in FOOTNOTE_DOTALL_RE.finditer(text)]

    def _is_inside_fn(start: int, end: int) -> bool:
        for fs, fe in fn_spans:
            if fs <= start and end <= fe:
                return True
        return False

    # Extract lines: maximal runs of non-\n characters
    lines: list[tuple[int, int, str]] = []
    curr = 0
    for chunk in text.split("\n"):
        lines.append((curr, curr + len(chunk), chunk))
        curr += len(chunk) + 1  # for the \n

    verse_lines: list[tuple[int, int, str]] = []
    for l_start, l_end, chunk in lines:
        if _is_inside_fn(l_start, l_end):
            continue
        if is_verse_line(chunk):
            verse_lines.append((l_start, l_end, chunk))

    if not verse_lines:
        return []

    poems: list[dict[str, Any]] = []
    i = 0
    while i < len(verse_lines):
        group = [verse_lines[i]]
        j = i + 1
        while j < len(verse_lines):
            prev_end = group[-1][1]
            next_start = verse_lines[j][0]
            gap = text[prev_end:next_start]
            if gap.strip() == "":
                group.append(verse_lines[j])
                j += 1
            else:
                break

        p_start = group[0][0]
        p_end = group[-1][1]

        # Trim backwards: trailing whitespace, then trailing footnote and whitespace before it
        while True:
            sub = text[p_start:p_end]
            sub_r = sub.rstrip()
            p_end = p_start + len(sub_r)

            matched_fn = None
            for fs, fe in fn_spans:
                # Footnote ends at p_end, or p_end cut into a multiline footnote starting >= p_start
                if fs >= p_start and ((fe == p_end) or (fs < p_end <= fe)):
                    matched_fn = (fs, fe)
                    break
            if matched_fn:
                p_end = matched_fn[0]
                continue
            break

        if hadith_spans and any(p_start <= hs and he <= p_end for hs, he in hadith_spans):
            i = j
            continue

        poems.append({
            "span_id": f"{segment_id}#{p_start}-{p_end}",
            "segment_id": segment_id,
            "start": p_start,
            "end": p_end,
            "type": "OTHER",
            "method": "regex",
            "confidence": 1.0,
            "source": source,
            "parent": None,
            "lines": len(group),
        })
        i = j

    return poems


def extract_poetry(
    segments_path: Path | str | None = None,
    output_path: Path | str | None = None,
    source: str = DEFAULT_SOURCE,
    hadith_path: Path | str | None = None,
) -> Path:
    """Extract poetry spans for all segments and write data/interim/spans/poetry.jsonl."""
    in_path = Path(segments_path) if segments_path else DEFAULT_SEGMENTS_PATH
    out_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH

    if not in_path.exists():
        raise FileNotFoundError(f"Missing segments file: {in_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    poems: list[dict[str, Any]] = []
    total_verse_lines = 0

    hadith_by_seg: dict[str, list[tuple[int, int]]] = {}
    h_path = Path(hadith_path) if hadith_path else DEFAULT_HADITH_PATH
    if h_path.exists():
        with h_path.open("r", encoding="utf-8") as hf:
            for hline in hf:
                if hline.strip():
                    h = json.loads(hline)
                    hadith_by_seg.setdefault(h["segment_id"], []).append((h["start"], h["end"]))

    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            seg_id = row["segment_id"]
            text = row["text"]
            seg_poems = extract_poetry_from_text(
                text, seg_id, source=source, hadith_spans=hadith_by_seg.get(seg_id)
            )
            for p in seg_poems:
                total_verse_lines += p["lines"]
            poems.extend(seg_poems)

    with out_path.open("w", encoding="utf-8") as out:
        for p in poems:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")

    logger.info("Extracted %d poems (%d lines) -> %s", len(poems), total_verse_lines, out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract poetry spans (OTHER) from segments.")
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_PATH, help="Path to segments.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output path for poetry.jsonl")
    parser.add_argument("--source", type=str, default=DEFAULT_SOURCE, help="Provenance source string")
    args = parser.parse_args()

    out = extract_poetry(args.segments, args.output, source=args.source)
    print(f"Poetry spans written to {out}")


if __name__ == "__main__":
    main()
