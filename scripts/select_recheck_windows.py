#!/usr/bin/env python3
"""Select candidate windows for second-pass hadith extraction (T4.5c).

Reads hadith-raw.jsonl (latest 'ok' per key), keeps keys where:
- GLM found 0 spans
- Window text outside segment-level footnotes contains narration cue:
  حدثن|اخبرن|سمعت|رواه|اخرجه|اخرجا

Writes sorted keys, one per line, to data/interim/spans/recheck-keys.txt.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.extract.footnotes import find_footnotes
from src.extract.glm_client import parse_anchor_response
from src.extract.normalize import normalize_with_map

RAW_PATH = ROOT / "data" / "interim" / "spans" / "hadith-raw.jsonl"
SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "spans" / "recheck-keys.txt"

CUE_RE = re.compile(r"حدثن|اخبرن|سمعت|رواه|اخرجه|اخرجا")


def extract_window_outside_footnotes(
    seg_text: str,
    w_start: int,
    w_end: int,
    fn_spans: list[tuple[int, int]],
) -> str:
    """Extract window text removing characters that fall inside segment-level footnotes.

    Handles windows starting or ending strictly inside footnotes.
    """
    clamped_fns = []
    for s, e in fn_spans:
        if e > w_start and s < w_end:
            clamped_fns.append((max(s, w_start), min(e, w_end)))
    clamped_fns.sort()

    curr = w_start
    pieces = []
    for cs, ce in clamped_fns:
        if cs > curr:
            pieces.append(seg_text[curr:cs])
        curr = max(curr, ce)
    if curr < w_end:
        pieces.append(seg_text[curr:w_end])

    return "".join(pieces)


def select_recheck_keys(
    raw_path: Path = RAW_PATH,
    segments_path: Path = SEGMENTS_PATH,
    output_path: Path = DEFAULT_OUTPUT,
) -> list[str]:
    """Select windows with 0 spans and narration cue outside segment-level footnotes."""
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")
    if not segments_path.exists():
        raise FileNotFoundError(f"Segments file not found: {segments_path}")

    # Load segments
    segments: dict[str, str] = {}
    with open(segments_path, "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            segments[d["segment_id"]] = d["text"]

    # Precompute footnote positions for each segment
    segment_footnotes: dict[str, list[tuple[int, int]]] = {
        seg_id: find_footnotes(text) for seg_id, text in segments.items()
    }

    # Load latest ok per key from raw file
    latest_ok: dict[str, dict] = {}
    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                k = rec.get("key")
                if k and rec.get("status") == "ok":
                    latest_ok[k] = rec
            except json.JSONDecodeError:
                continue

    selected_keys: list[str] = []

    for key, rec in latest_ok.items():
        raw_text = rec.get("raw_text", "")
        try:
            parsed = parse_anchor_response(raw_text)
        except Exception:
            continue

        if len(parsed.spans) != 0:
            continue

        seg_id = rec["segment_id"]
        w_s = rec["window_start"]
        w_e = rec["window_end"]

        seg_text = segments.get(seg_id, "")
        if not seg_text:
            continue

        fn_spans = segment_footnotes.get(seg_id, [])
        clean_text = extract_window_outside_footnotes(seg_text, w_s, w_e, fn_spans)
        norm_text, _ = normalize_with_map(clean_text)

        if CUE_RE.search(norm_text):
            selected_keys.append(key)

    selected_keys.sort()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for k in selected_keys:
            f.write(f"{k}\n")

    print(f"Selected {len(selected_keys)} recheck windows (written to {output_path})")
    return selected_keys


def main():
    parser = argparse.ArgumentParser(description="Select recheck windows for Phase 4 second pass.")
    parser.add_argument("--raw-path", type=Path, default=RAW_PATH, help="Path to hadith-raw.jsonl")
    parser.add_argument("--segments-path", type=Path, default=SEGMENTS_PATH, help="Path to segments.jsonl")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT, help="Output keys file")
    args = parser.parse_args()

    select_recheck_keys(
        raw_path=args.raw_path,
        segments_path=args.segments_path,
        output_path=args.output_path,
    )


if __name__ == "__main__":
    main()
