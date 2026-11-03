"""Neo4j span writer: write Span nodes, HAS_SPAN, and INSIDE relationships (T4.2).

Reusable for all Phase 4 spans (4a Quran, 4b Hadith, 4c Commentary & Footnotes).
Idempotent UNWIND batches using MERGE on span_id and relationships.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neo4j import Driver

from src.graph.client import get_driver
from src.log import get_logger

logger = get_logger("spans")

DEFAULT_BATCH_SIZE = 5000
DEFAULT_SPANS_PATH = ROOT / "data" / "interim" / "spans" / "footnotes.jsonl"


def chunked(items: list[Any], size: int = DEFAULT_BATCH_SIZE) -> Iterable[list[Any]]:
    """Yield successive chunks from items with maximum size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def write_spans(
    rows: list[dict[str, Any]],
    driver: Driver | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Write span records into Neo4j using idempotent UNWIND batches.

    For each span record:
    1. MERGE (s:Span {span_id: row.span_id})
       SET s.segment_id, s.start, s.end, s.type, and optional hints (cue, collection_hint, number_hint)
    2. MATCH (seg:TafsirSegment {segment_id: row.segment_id})
       MATCH (s:Span {span_id: row.span_id})
       MERGE (seg)-[r:HAS_SPAN]->(s)
       SET r.source = row.source, r.method = row.method, r.confidence = row.confidence
    3. If row.parent is not null:
       MATCH (child:Span {span_id: row.span_id})
       MATCH (parent:Span {span_id: row.parent})
       MERGE (child)-[r:INSIDE]->(parent)
       SET r.source = row.source, r.method = row.method, r.confidence = row.confidence

    Returns dict of counts processed: {"spans": N, "has_span": N, "inside": M}.
    """
    if not rows:
        return {"spans": 0, "has_span": 0, "inside": 0}

    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    merge_span_query = """
    UNWIND $batch AS row
    MERGE (s:Span {span_id: row.span_id})
    SET s.segment_id = row.segment_id,
        s.start = row.start,
        s.end = row.end,
        s.type = row.type
    FOREACH (_ IN CASE WHEN row.cue IS NOT NULL THEN [1] ELSE [] END | SET s.cue = row.cue)
    FOREACH (_ IN CASE WHEN row.collection_hint IS NOT NULL THEN [1] ELSE [] END | SET s.collection_hint = row.collection_hint)
    FOREACH (_ IN CASE WHEN row.number_hint IS NOT NULL THEN [1] ELSE [] END | SET s.number_hint = row.number_hint)
    """

    merge_has_span_query = """
    UNWIND $batch AS row
    MATCH (seg:TafsirSegment {segment_id: row.segment_id})
    MATCH (s:Span {span_id: row.span_id})
    MERGE (seg)-[r:HAS_SPAN]->(s)
    SET r.source = row.source,
        r.method = row.method,
        r.confidence = row.confidence
    """

    merge_inside_query = """
    UNWIND $batch AS row
    MATCH (child:Span {span_id: row.span_id})
    MATCH (parent:Span {span_id: row.parent})
    MERGE (child)-[r:INSIDE]->(parent)
    SET r.source = row.source,
        r.method = row.method,
        r.confidence = row.confidence
    """

    parent_rows = [r for r in rows if r.get("parent")]

    try:
        with driver.session() as session:
            # 1. Write Span nodes
            logger.info("Writing Span nodes (%d records)...", len(rows))
            for chunk in chunked(rows, batch_size):
                session.run(merge_span_query, batch=chunk).consume()

            # 2. Write HAS_SPAN relationships
            logger.info("Writing HAS_SPAN relationships (%d edges)...", len(rows))
            for chunk in chunked(rows, batch_size):
                session.run(merge_has_span_query, batch=chunk).consume()

            # 3. Write INSIDE relationships (if any parent set)
            if parent_rows:
                logger.info("Writing INSIDE relationships (%d edges)...", len(parent_rows))
                for chunk in chunked(parent_rows, batch_size):
                    session.run(merge_inside_query, batch=chunk).consume()

        return {
            "spans": len(rows),
            "has_span": len(rows),
            "inside": len(parent_rows),
        }
    finally:
        if close_driver:
            driver.close()


def load_spans_file(
    path: Path | str = DEFAULT_SPANS_PATH,
    driver: Driver | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Read spans JSONL file and write records into Neo4j."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Spans JSONL file not found: {p}")

    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    return write_spans(rows, driver=driver, batch_size=batch_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load spans JSONL into Neo4j.")
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=DEFAULT_SPANS_PATH,
        help="Path to spans JSONL file (default: data/interim/spans/footnotes.jsonl)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Batch size for UNWIND",
    )
    args = parser.parse_args()
    counts = load_spans_file(args.file, batch_size=args.batch_size)
    print(f"Loaded {counts['spans']} spans, {counts['has_span']} HAS_SPAN, {counts['inside']} INSIDE into Neo4j.")


if __name__ == "__main__":
    main()
