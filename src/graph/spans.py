"""Neo4j span writer: write Span nodes, HAS_SPAN, INSIDE, and ayah links (T4.2, T4.4).

Reusable for all Phase 4 spans (4a Quran, 4b Hadith, 4c Commentary & Footnotes).
Idempotent UNWIND batches using MERGE on span_id and relationships:
- (TafsirSegment)-[:HAS_SPAN]->(Span)
- (Span)-[:INSIDE]->(Span)
- (Span)-[:EXPLAINS]->(Ayah)
- (Span)-[:CITES]->(Ayah)
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neo4j import Driver, Session

from src.graph.client import get_driver
from src.log import get_logger

logger = get_logger("spans")

DEFAULT_BATCH_SIZE = 5000
DEFAULT_SPANS_PATH = ROOT / "data" / "interim" / "spans" / "footnotes.jsonl"
DEFAULT_QURAN_SPANS_PATH = ROOT / "data" / "interim" / "spans" / "quran.jsonl"


def chunked(items: list[Any], size: int = DEFAULT_BATCH_SIZE) -> Iterable[list[Any]]:
    """Yield successive chunks from items with maximum size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def write_ayah_links(
    links: list[dict[str, Any]],
    driver: Driver | None = None,
    session: Session | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Write ayah link relationships (EXPLAINS or CITES) into Neo4j using idempotent UNWIND batches.

    For each link record:
    - (s:Span)-[r:EXPLAINS|CITES]->(a:Ayah)
    Sets r.source, r.method, r.confidence, and r.ref_text (if present).

    Returns actual DB count of links: {"explains": N, "cites": M}.
    """
    if not links:
        return {"explains": 0, "cites": 0}

    explains_links = [l for l in links if l.get("rel") == "EXPLAINS"]
    cites_links = [l for l in links if l.get("rel") != "EXPLAINS"]

    merge_explains_query = """
    UNWIND $batch AS link
    MATCH (s:Span {span_id: link.span_id})
    MATCH (a:Ayah {ayah_id: link.ayah_id})
    MERGE (s)-[r:EXPLAINS]->(a)
    SET r.source = link.source,
        r.method = link.method,
        r.confidence = link.confidence
    FOREACH (_ IN CASE WHEN link.ref_text IS NOT NULL THEN [1] ELSE [] END | SET r.ref_text = link.ref_text)
    """

    merge_cites_query = """
    UNWIND $batch AS link
    MATCH (s:Span {span_id: link.span_id})
    MATCH (a:Ayah {ayah_id: link.ayah_id})
    MERGE (s)-[r:CITES]->(a)
    SET r.source = link.source,
        r.method = link.method,
        r.confidence = link.confidence
    FOREACH (_ IN CASE WHEN link.ref_text IS NOT NULL THEN [1] ELSE [] END | SET r.ref_text = link.ref_text)
    """

    def _execute(sess: Session) -> dict[str, int]:
        if explains_links:
            logger.info("Writing EXPLAINS relationships (%d edges)...", len(explains_links))
            for chunk in chunked(explains_links, batch_size):
                sess.run(merge_explains_query, batch=chunk).consume()

        if cites_links:
            logger.info("Writing CITES relationships (%d edges)...", len(cites_links))
            for chunk in chunked(cites_links, batch_size):
                sess.run(merge_cites_query, batch=chunk).consume()

        # Query actual counts written
        explains_count = 0
        if explains_links:
            exp_span_ids = list({l["span_id"] for l in explains_links})
            explains_count = sess.run(
                "MATCH (s:Span)-[r:EXPLAINS]->(a:Ayah) WHERE s.span_id IN $ids RETURN count(r) AS cnt",
                ids=exp_span_ids,
            ).single()["cnt"]

        cites_count = 0
        if cites_links:
            cites_span_ids = list({l["span_id"] for l in cites_links})
            cites_count = sess.run(
                "MATCH (s:Span)-[r:CITES]->(a:Ayah) WHERE s.span_id IN $ids RETURN count(r) AS cnt",
                ids=cites_span_ids,
            ).single()["cnt"]

        return {"explains": explains_count, "cites": cites_count}

    if session is not None:
        return _execute(session)

    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    try:
        with driver.session() as sess:
            return _execute(sess)
    finally:
        if close_driver:
            driver.close()


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
    4. If row has links:
       Write EXPLAINS and CITES relationships to Ayah nodes.

    Returns dict of actual DB counts: {"spans": N, "has_span": N, "inside": M, "explains": E, "cites": C}.
    """
    if not rows:
        return {"spans": 0, "has_span": 0, "inside": 0, "explains": 0, "cites": 0}

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

    # Flatten links
    all_links: list[dict[str, Any]] = []
    for r in rows:
        span_id = r["span_id"]
        row_source = r.get("source", "")
        for l in r.get("links", []):
            all_links.append({
                "span_id": span_id,
                "ayah_id": l["ayah_id"],
                "rel": l.get("rel", "CITES"),
                "source": l.get("source") or row_source,
                "method": l.get("method", "ngram"),
                "confidence": l.get("confidence", 1.0),
                "ref_text": l.get("ref_text") or r.get("ref_text"),
            })

    span_ids = [r["span_id"] for r in rows]

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

            # 4. Remove old ayah links for QURAN spans in rows, then write new links
            quran_span_ids = [r["span_id"] for r in rows if r.get("type") == "QURAN"]
            if quran_span_ids:
                logger.info("Clearing previous ayah links for %d QURAN spans...", len(quran_span_ids))
                for chunk in chunked(quran_span_ids, batch_size):
                    session.run(
                        """
                        UNWIND $batch AS id
                        MATCH (s:Span {span_id: id})-[r:EXPLAINS|CITES]->(:Ayah)
                        DELETE r
                        """,
                        batch=chunk,
                    ).consume()

            # Write ayah link relationships (if any links present)
            link_counts = {"explains": 0, "cites": 0}
            if all_links:
                link_counts = write_ayah_links(
                    all_links, session=session, batch_size=batch_size
                )

            # 5. Query actual counts verified in DB
            span_count = session.run(
                "MATCH (s:Span) WHERE s.span_id IN $ids RETURN count(s) AS cnt",
                ids=span_ids,
            ).single()["cnt"]

            has_span_count = session.run(
                "MATCH (:TafsirSegment)-[r:HAS_SPAN]->(s:Span) WHERE s.span_id IN $ids RETURN count(r) AS cnt",
                ids=span_ids,
            ).single()["cnt"]

            inside_count = 0
            if parent_rows:
                inside_count = session.run(
                    "MATCH (c:Span)-[r:INSIDE]->(:Span) WHERE c.span_id IN $ids RETURN count(r) AS cnt",
                    ids=[r["span_id"] for r in parent_rows],
                ).single()["cnt"]

        return {
            "spans": span_count,
            "has_span": has_span_count,
            "inside": inside_count,
            "explains": link_counts["explains"],
            "cites": link_counts["cites"],
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
        default=None,
        help="Path to spans JSONL file (default: footnotes.jsonl and quran.jsonl)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Batch size for UNWIND",
    )
    args = parser.parse_args()

    files_to_load = [args.file] if args.file else [DEFAULT_SPANS_PATH, DEFAULT_QURAN_SPANS_PATH]
    total_spans = 0
    total_has_span = 0
    total_inside = 0
    total_explains = 0
    total_cites = 0

    for f in files_to_load:
        if f.exists():
            logger.info("Loading %s...", f)
            counts = load_spans_file(f, batch_size=args.batch_size)
            total_spans += counts["spans"]
            total_has_span += counts["has_span"]
            total_inside += counts["inside"]
            total_explains += counts.get("explains", 0)
            total_cites += counts.get("cites", 0)
            print(
                f"Loaded {f.name}: {counts['spans']} spans, {counts['has_span']} HAS_SPAN, "
                f"{counts['inside']} INSIDE, {counts.get('explains', 0)} EXPLAINS, {counts.get('cites', 0)} CITES."
            )
        else:
            logger.warning("Spans file not found: %s", f)

    print(
        f"Total: {total_spans} spans, {total_has_span} HAS_SPAN, {total_inside} INSIDE, "
        f"{total_explains} EXPLAINS, {total_cites} CITES in Neo4j."
    )


if __name__ == "__main__":
    main()
