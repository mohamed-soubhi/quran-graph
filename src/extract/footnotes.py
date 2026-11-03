"""Footnote extraction: detect editor notes [[...]] and generate interim spans (T4.2).

Deterministic regex extraction over Ibn Kathir segments.
Output: data/interim/spans/footnotes.jsonl
"""

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.log import get_logger

logger = get_logger("footnotes")

FOOTNOTE_RE: re.Pattern[str] = re.compile(r"\[\[.*?\]\]", re.DOTALL)

DEFAULT_SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "interim" / "spans" / "footnotes.jsonl"
DEFAULT_SOURCE = "run:20261103-0000-footnotes"
METHOD_REGEX = "regex"
CONFIDENCE_EXACT = 1.0
SPAN_TYPE_FOOTNOTE = "FOOTNOTE"


def find_footnotes(text: str) -> list[tuple[int, int]]:
    """Return all [[...]] footnote spans in text as (start, end) tuples.

    Offsets are in the original text, end exclusive, markers included.
    Uses regex pattern '\\[\\[.*?\\]\\]' with re.DOTALL.
    """
    if not text:
        return []
    return [(m.start(), m.end()) for m in FOOTNOTE_RE.finditer(text)]


def extract_footnotes(
    segments_path: Path | str | None = None,
    output_path: Path | str | None = None,
    source: str = DEFAULT_SOURCE,
) -> Path:
    """Extract all footnote spans from tafsir segments into interim JSONL.

    Preserves deterministic segment order, then start offset.
    Each span record contains:
    - span_id: <segment_id>#<start>-<end>
    - segment_id: segment identifier
    - start: int (start offset)
    - end: int (end exclusive offset)
    - type: "FOOTNOTE"
    - parent: None (null in JSON)
    - source: provenance source string
    - method: "regex"
    - confidence: 1.0

    Returns the written Path.
    """
    in_path = Path(segments_path) if segments_path else DEFAULT_SEGMENTS_PATH
    out_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH

    if not in_path.exists():
        raise FileNotFoundError(
            f"Missing segments file: {in_path}. Run 'python scripts/tasks.py parse' first."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_spans = 0
    with in_path.open("r", encoding="utf-8") as in_f, out_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as out_f:
        for line in in_f:
            line = line.strip()
            if not line:
                continue
            seg = json.loads(line)
            segment_id = seg["segment_id"]
            text = seg.get("text", "")
            matches = find_footnotes(text)
            for start, end in matches:
                span_record = {
                    "confidence": CONFIDENCE_EXACT,
                    "end": end,
                    "method": METHOD_REGEX,
                    "parent": None,
                    "segment_id": segment_id,
                    "source": source,
                    "span_id": f"{segment_id}#{start}-{end}",
                    "start": start,
                    "type": SPAN_TYPE_FOOTNOTE,
                }
                out_f.write(json.dumps(span_record, ensure_ascii=False, sort_keys=True) + "\n")
                total_spans += 1

    logger.info("Extracted %d footnote spans into %s", total_spans, out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract [[...]] footnotes from Ibn Kathir segments.")
    parser.add_argument(
        "--segments",
        type=Path,
        default=DEFAULT_SEGMENTS_PATH,
        help="Path to segments.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to output footnotes.jsonl",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE,
        help="Provenance source tag",
    )
    args = parser.parse_args()
    out = extract_footnotes(args.segments, args.output, args.source)
    print(f"Footnotes written to {out}")


if __name__ == "__main__":
    main()
