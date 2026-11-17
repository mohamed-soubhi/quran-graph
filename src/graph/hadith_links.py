"""Neo4j graph loader for hadith links (T5.2).

Writes CITES relationships between Span (type HADITH) and Hadith nodes:
(:Span)-[:CITES]->(:Hadith)
with evidence, ref_text, number_kind, outcome, method, source, confidence, and text_sim.
"""

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

logger = get_logger("hadith_links")

DEFAULT_BATCH_SIZE = 2000
DEFAULT_LINKS_PATH = ROOT / "data" / "interim" / "links" / "footnote_links.jsonl"


def chunked(items: list[Any], size: int = DEFAULT_BATCH_SIZE) -> Iterable[list[Any]]:
    """Yield successive chunks from items with maximum size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def write_cites(
    driver: Driver,
    path: Path | str = DEFAULT_LINKS_PATH,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Write CITES edges from HADITH spans to Hadith nodes from JSONL file.
    
    Refuses missing or empty files, and refuses rows whose span or hadith does not exist.
    Deletes existing CITES edges with method='regex' and source starting with 'run:'
    and containing 'footnote-links' prior to write.
    Does not touch CITES from QURAN spans.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                rows.append(json.loads(line_str))

    if not rows:
        raise ValueError(f"Input file is empty: {p}")

    with driver.session() as session:
        # 1. Validate that all referenced Span and Hadith nodes exist in Neo4j
        span_ids = list({r["span_id"] for r in rows})
        hadith_ids = list({r["hadith_id"] for r in rows})

        found_spans = set()
        for chunk in chunked(span_ids, 5000):
            res = session.run(
                "UNWIND $ids AS sid MATCH (s:Span {span_id: sid}) RETURN s.span_id AS sid",
                ids=chunk,
            )
            for record in res:
                found_spans.add(record["sid"])

        found_hadiths = set()
        for chunk in chunked(hadith_ids, 5000):
            res = session.run(
                "UNWIND $ids AS hid MATCH (h:Hadith {hadith_id: hid}) RETURN h.hadith_id AS hid",
                ids=chunk,
            )
            for record in res:
                found_hadiths.add(record["hid"])

        missing_spans = set(span_ids) - found_spans
        missing_hadiths = set(hadith_ids) - found_hadiths

        if missing_spans or missing_hadiths:
            err_msg = (
                f"Refusing write: {len(missing_spans)} spans and {len(missing_hadiths)} hadiths "
                "do not exist in Neo4j database."
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

        # 2. Delete existing footnote CITES edges from HADITH spans (idempotent reload)
        # Note: explicitly preserves CITES from QURAN spans (which point to Ayah).
        del_query = """
        MATCH (s:Span)-[r:CITES]->(:Hadith)
        WHERE (s.type = 'HADITH' OR s.span_id STARTS WITH 'test:')
          AND r.method = 'regex'
          AND r.source STARTS WITH 'run:'
          AND r.source CONTAINS 'footnote-links'
        DELETE r
        """
        session.run(del_query).consume()

        # 3. Write CITES relationships in UNWIND batches
        merge_query = """
        UNWIND $batch AS row
        MATCH (s:Span {span_id: row.span_id})
        MATCH (h:Hadith {hadith_id: row.hadith_id})
        MERGE (s)-[r:CITES]->(h)
        SET r.evidence = row.evidence,
            r.ref_text = row.ref_text,
            r.number_kind = row.number_kind,
            r.outcome = row.outcome,
            r.method = row.method,
            r.source = row.source,
            r.confidence = row.confidence,
            r.text_sim = row.text_sim
        """
        for batch in chunked(rows, batch_size):
            session.run(merge_query, batch=batch).consume()

        # Count total created CITES edges from these spans to Hadith
        count_query = """
        UNWIND $rows AS row
        MATCH (s:Span {span_id: row.span_id})-[r:CITES]->(h:Hadith {hadith_id: row.hadith_id})
        RETURN count(r) AS count
        """
        count_res = session.run(count_query, rows=[{"span_id": r["span_id"], "hadith_id": r["hadith_id"]} for r in rows]).single()
        total_written = count_res["count"] if count_res else 0

        logger.info(f"Successfully loaded {total_written} CITES edges from {p}")
        return total_written


def main() -> None:
    driver = get_driver()
    try:
        count = write_cites(driver, DEFAULT_LINKS_PATH)
        print(f"Loaded {count} CITES relationships into Neo4j.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
