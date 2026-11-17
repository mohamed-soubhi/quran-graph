"""Structure extraction and loader: parents (INSIDE), COMMENTARY gaps, and coverage (T4.6).

Pure deterministic functions for Phase 4c span layer completion.
Generates:
- data/interim/spans/poetry.jsonl (via src.extract.poetry)
- data/interim/spans/parents.jsonl
- data/interim/spans/commentary.jsonl
And optionally loads to Neo4j via write_spans / write_inside_edges.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.poetry import DEFAULT_SOURCE as DEFAULT_POETRY_SOURCE, extract_poetry
from src.graph.spans import (
    DEFAULT_BATCH_SIZE,
    delete_spans_by_type,
    load_spans_file,
    write_inside_edges,
    write_spans,
)
from src.log import get_logger

logger = get_logger("structure")

DEFAULT_SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_FOOTNOTES_PATH = ROOT / "data" / "interim" / "spans" / "footnotes.jsonl"
DEFAULT_QURAN_PATH = ROOT / "data" / "interim" / "spans" / "quran.jsonl"
DEFAULT_HADITH_PATH = ROOT / "data" / "interim" / "spans" / "hadith.jsonl"
DEFAULT_POETRY_PATH = ROOT / "data" / "interim" / "spans" / "poetry.jsonl"
DEFAULT_PARENTS_PATH = ROOT / "data" / "interim" / "spans" / "parents.jsonl"
DEFAULT_COMMENTARY_PATH = ROOT / "data" / "interim" / "spans" / "commentary.jsonl"

DEFAULT_COMMENTARY_SOURCE = "run:20261117-1414-commentary"
DEFAULT_PARENTS_SOURCE = "run:20261117-1414-parents"

# Parent tie-breaking order for identical offsets: HADITH > QURAN > OTHER > FOOTNOTE
TYPE_RANK = {"HADITH": 4, "QURAN": 3, "OTHER": 2, "FOOTNOTE": 1}


def check_partial_overlaps(spans: list[dict[str, Any]]) -> None:
    """Verify that no two spans in spans partially overlap.

    Any partial overlap raises ValueError with the offending span IDs.
    Full nesting is allowed; disjoint spans are allowed.
    """
    n = len(spans)
    for i in range(n):
        s1 = spans[i]
        for j in range(i + 1, n):
            s2 = spans[j]
            # Overlap exists if not disjoint
            if not (s1["end"] <= s2["start"] or s2["end"] <= s1["start"]):
                # Must be full nesting
                nested = (
                    (s1["start"] <= s2["start"] and s2["end"] <= s1["end"])
                    or (s2["start"] <= s1["start"] and s1["end"] <= s2["end"])
                )
                if not nested:
                    raise ValueError(
                        f"Partial overlap detected between span {s1['span_id']!r} "
                        f"[{s1['start']}:{s1['end']}] and {s2['span_id']!r} "
                        f"[{s2['start']}:{s2['end']}]."
                    )


def find_parent_for_span(
    child: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find the smallest enclosing parent span for child among candidates.

    Smallest = minimum length (p.end - p.start).
    Tie breaker if lengths are equal: HADITH > QURAN > OTHER > FOOTNOTE.
    """
    enclosing: list[dict[str, Any]] = []
    c_start = child["start"]
    c_end = child["end"]
    c_id = child["span_id"]

    for p in candidates:
        if p["span_id"] != c_id and p["start"] <= c_start and c_end <= p["end"]:
            enclosing.append(p)

    if not enclosing:
        return None

    enclosing.sort(
        key=lambda p: (p["end"] - p["start"], -TYPE_RANK.get(p.get("type", ""), 0))
    )
    return enclosing[0]


def build_parents(
    spans_by_segment: dict[str, list[dict[str, Any]]],
    output_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Build parents for all nested spans across segments and write parents.jsonl.

    Validates that no partial overlaps exist anywhere.
    Returns list of parent records:
    {"span_id": ..., "parent": ..., "type": ..., "parent_type": ...}
    sorted by span_id.
    """
    out_path = Path(output_path) if output_path else DEFAULT_PARENTS_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    parents_list: list[dict[str, Any]] = []

    for seg_id, spans in spans_by_segment.items():
        check_partial_overlaps(spans)
        for child in spans:
            p = find_parent_for_span(child, spans)
            if p is not None:
                parents_list.append({
                    "span_id": child["span_id"],
                    "parent": p["span_id"],
                    "type": child["type"],
                    "parent_type": p["type"],
                })

    parents_list.sort(key=lambda r: r["span_id"])

    with out_path.open("w", encoding="utf-8") as out:
        for r in parents_list:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info("Wrote %d nested span records -> %s", len(parents_list), out_path)
    return parents_list


def build_commentary(
    segments: list[dict[str, Any]],
    spans_by_segment: dict[str, list[dict[str, Any]]],
    nested_span_ids: set[str],
    output_path: Path | str | None = None,
    source: str = DEFAULT_COMMENTARY_SOURCE,
) -> list[dict[str, Any]]:
    """Generate COMMENTARY spans for all gaps between top-level spans in segments.

    Every gap [pos, next.start) and the tail [pos, len(text)) becomes one COMMENTARY span.
    blank: true when the gap text contains no letter (str.isalpha() is False for all chars).
    """
    out_path = Path(output_path) if output_path else DEFAULT_COMMENTARY_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    commentary_spans: list[dict[str, Any]] = []

    for seg in segments:
        seg_id = seg["segment_id"]
        text = seg["text"]
        all_spans = spans_by_segment.get(seg_id, [])

        top_level = [s for s in all_spans if s["span_id"] not in nested_span_ids]
        top_level.sort(key=lambda s: (s["start"], s["end"]))

        pos = 0
        for s in top_level:
            if s["start"] > pos:
                gap_text = text[pos : s["start"]]
                is_blank = not any(ch.isalpha() for ch in gap_text)
                commentary_spans.append({
                    "span_id": f"{seg_id}#{pos}-{s['start']}",
                    "segment_id": seg_id,
                    "start": pos,
                    "end": s["start"],
                    "type": "COMMENTARY",
                    "method": "regex",
                    "confidence": 1.0,
                    "source": source,
                    "parent": None,
                    "blank": is_blank,
                })
            pos = s["end"]

        if pos < len(text):
            gap_text = text[pos : len(text)]
            is_blank = not any(ch.isalpha() for ch in gap_text)
            commentary_spans.append({
                "span_id": f"{seg_id}#{pos}-{len(text)}",
                "segment_id": seg_id,
                "start": pos,
                "end": len(text),
                "type": "COMMENTARY",
                "method": "regex",
                "confidence": 1.0,
                "source": source,
                "parent": None,
                "blank": is_blank,
            })

    with out_path.open("w", encoding="utf-8") as out:
        for c in commentary_spans:
            out.write(json.dumps(c, ensure_ascii=False) + "\n")

    logger.info("Wrote %d COMMENTARY spans -> %s", len(commentary_spans), out_path)
    return commentary_spans


def load_structure_to_neo4j(
    poetry_path: Path | str | None = None,
    commentary_path: Path | str | None = None,
    parents_path: Path | str | None = None,
    driver: Any = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Write OTHER and COMMENTARY spans with HAS_SPAN, and INSIDE edges to Neo4j.

    - Removes old COMMENTARY and OTHER spans first (only those two types).
    - Writes OTHER spans with lines property.
    - Writes COMMENTARY spans with blank property.
    - Writes INSIDE edges for every row in parents.jsonl with provenance.
    - Idempotent: repeated runs produce identical counts.
    """
    poet_p = Path(poetry_path) if poetry_path else DEFAULT_POETRY_PATH
    comm_p = Path(commentary_path) if commentary_path else DEFAULT_COMMENTARY_PATH
    par_p = Path(parents_path) if parents_path else DEFAULT_PARENTS_PATH

    for p in (poet_p, comm_p, par_p):
        if not p.exists():
            raise FileNotFoundError(f"Required interim file not found: {p}")

    # Read rows
    poetry_rows: list[dict[str, Any]] = [
        json.loads(line) for line in poet_p.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    commentary_rows: list[dict[str, Any]] = [
        json.loads(line) for line in comm_p.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    parent_rows: list[dict[str, Any]] = [
        json.loads(line) for line in par_p.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    close_driver = False
    if driver is None:
        from src.graph.client import get_driver

        driver = get_driver()
        close_driver = True

    try:
        # 1. Remove old COMMENTARY and OTHER spans first (never delete FOOTNOTE, QURAN, HADITH)
        logger.info("Removing old COMMENTARY and OTHER spans before write...")
        del_comm = delete_spans_by_type("COMMENTARY", driver=driver)
        del_other = delete_spans_by_type("OTHER", driver=driver)
        logger.info("Deleted %d old COMMENTARY, %d old OTHER spans", del_comm, del_other)

        # 2. Write OTHER spans
        logger.info("Writing %d OTHER spans...", len(poetry_rows))
        other_counts = write_spans(poetry_rows, driver=driver, batch_size=batch_size)

        # 3. Write COMMENTARY spans
        logger.info("Writing %d COMMENTARY spans...", len(commentary_rows))
        comm_counts = write_spans(commentary_rows, driver=driver, batch_size=batch_size)

        # 4. Write INSIDE edges from parents.jsonl
        logger.info("Writing %d INSIDE edges...", len(parent_rows))
        inside_count = write_inside_edges(parent_rows, driver=driver, batch_size=batch_size)

        return {
            "other_spans": other_counts["spans"],
            "commentary_spans": comm_counts["spans"],
            "inside_edges": inside_count,
        }
    finally:
        if close_driver:
            driver.close()


def run_pipeline(
    segments_path: Path | str | None = None,
    write: bool = False,
    run_gate: bool = True,
) -> dict[str, Any]:
    """Execute Phase 4c pipeline steps 1-4 (and optionally step 5 with write=True)."""
    seg_p = Path(segments_path) if segments_path else DEFAULT_SEGMENTS_PATH
    if not seg_p.exists():
        raise FileNotFoundError(f"Segments file not found: {seg_p}")

    # Load segments
    with seg_p.open("r", encoding="utf-8") as f:
        segments = [json.loads(line) for line in f if line.strip()]

    # 1. Poetry -> poetry.jsonl
    poet_p = extract_poetry(segments_path=seg_p)

    # Load all typed spans: FOOTNOTE, QURAN, HADITH, OTHER
    spans_by_seg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    span_files = [DEFAULT_FOOTNOTES_PATH, DEFAULT_QURAN_PATH, DEFAULT_HADITH_PATH, poet_p]
    for sf in span_files:
        if not sf.exists():
            raise FileNotFoundError(f"Spans file missing: {sf}")
        with sf.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    spans_by_seg[r["segment_id"]].append(r)

    # 2. Nesting -> parents.jsonl
    parents = build_parents(spans_by_seg)
    nested_span_ids = {r["span_id"] for r in parents}

    # 3. COMMENTARY -> commentary.jsonl
    commentary = build_commentary(segments, spans_by_seg, nested_span_ids)

    # 4. Gate 4c
    gate_passed = True
    if run_gate:
        from scripts.gate_4c import evaluate_gate_4c

        gate_passed = evaluate_gate_4c(
            segments=segments,
            spans_by_segment=spans_by_seg,
            parents=parents,
            commentary=commentary,
        )
        if not gate_passed:
            raise RuntimeError("Gate 4c failed!")

    write_result = None
    if write:
        write_result = load_structure_to_neo4j(
            poetry_path=poet_p,
            commentary_path=DEFAULT_COMMENTARY_PATH,
            parents_path=DEFAULT_PARENTS_PATH,
        )

    return {
        "poetry_count": sum(1 for line in poet_p.open("r", encoding="utf-8") if line.strip()),
        "parents_count": len(parents),
        "commentary_count": len(commentary),
        "gate_passed": gate_passed,
        "write_result": write_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 4c span structure (poetry, parents, commentary).")
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_PATH, help="Path to segments.jsonl")
    parser.add_argument("--write", action="store_true", help="Write structure to Neo4j (Step 5)")
    parser.add_argument("--no-gate", action="store_true", help="Skip gate 4c validation")
    args = parser.parse_args()

    res = run_pipeline(segments_path=args.segments, write=args.write, run_gate=not args.no_gate)
    print(
        f"Structure built: {res['poetry_count']} OTHER, {res['parents_count']} INSIDE, "
        f"{res['commentary_count']} COMMENTARY spans."
    )
    if res["write_result"]:
        print(f"Loaded to Neo4j: {res['write_result']}")


if __name__ == "__main__":
    main()
