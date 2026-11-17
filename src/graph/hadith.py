"""Neo4j graph loader for Hadith collections (T5.1).

Loads HadithBook, Hadith, Grader, IN_BOOK, and GRADED into Neo4j using
idempotent UNWIND batches with MERGE.
"""

import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neo4j import Driver

from src.graph.apply_schema import apply_schema
from src.graph.client import get_driver
from src.log import get_logger

logger = get_logger("load_hadith")

BATCH_SIZE = 5000

SOURCE_HADITH = "hadith-api@df57907"
METHOD_DATASET = "dataset"
CONFIDENCE_EXACT = 1.0

DEFAULT_HADITH_PATH = ROOT / "data" / "interim" / "hadith" / "hadith.jsonl"
DEFAULT_BOOKS_PATH = ROOT / "data" / "interim" / "hadith" / "books.jsonl"


def chunked(items: list[Any], size: int = BATCH_SIZE) -> Iterable[list[Any]]:
    """Yield successive chunks from items with maximum size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Load JSONL file returning list of dicts."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing required file: {p}")
    with p.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def execute_batch(session, query: str, batch: list[dict[str, Any]], **kwargs: Any) -> None:
    """Execute a cypher query over an unwound batch."""
    if not batch:
        return
    session.run(query, batch=batch, **kwargs).consume()


def load_hadith(
    driver: Driver,
    hadith_path: Path | str = DEFAULT_HADITH_PATH,
    books_path: Path | str = DEFAULT_BOOKS_PATH,
) -> dict[str, int]:
    """Load hadith collections, hadiths, graders, and relationships into Neo4j.

    Idempotent: running multiple times does not duplicate any node or edge.
    """
    logger.info("Applying Neo4j schema before hadith load...")
    apply_schema(driver)

    logger.info("Reading interim hadith files: %s, %s", books_path, hadith_path)
    books_data = load_jsonl(books_path)
    hadiths_data = load_jsonl(hadith_path)

    # Collect distinct graders
    graders_set: set[str] = set()
    grades_edges: list[dict[str, Any]] = []
    in_book_edges: list[dict[str, Any]] = []

    for h in hadiths_data:
        hid = h["hadith_id"]
        col = h["collection"]
        in_book_edges.append({"hadith_id": hid, "collection": col})

        for g in h.get("grades", []):
            grader_name = g["grader"]
            graders_set.add(grader_name)
            grades_edges.append({
                "hadith_id": hid,
                "grader": grader_name,
                "grade": g["grade"],
            })

    graders_data = [{"name": name} for name in sorted(graders_set)]

    with driver.session() as session:
        # 1. HadithBook
        logger.info("Loading HadithBook nodes (%d)...", len(books_data))
        book_query = """
        UNWIND $batch AS row
        MERGE (b:HadithBook {collection: row.collection})
        SET b.name = row.name,
            b.name_en = row.name_en,
            b.edition = row.edition,
            b.source = row.source
        """
        for chunk in chunked(books_data):
            execute_batch(session, book_query, chunk)

        # 2. Hadith nodes
        logger.info("Loading Hadith nodes (%d)...", len(hadiths_data))
        hadith_query = """
        UNWIND $batch AS row
        MERGE (h:Hadith {hadith_id: row.hadith_id})
        SET h.collection = row.collection,
            h.number = row.number,
            h.arabic_number = row.arabic_number,
            h.book_number = row.book_number,
            h.number_in_book = row.number_in_book,
            h.text = row.text,
            h.text_norm = row.text_norm
        """
        for chunk in chunked(hadiths_data):
            execute_batch(session, hadith_query, chunk)

        # 3. Grader nodes
        logger.info("Loading Grader nodes (%d)...", len(graders_data))
        grader_query = """
        UNWIND $batch AS row
        MERGE (g:Grader {name: row.name})
        """
        for chunk in chunked(graders_data):
            execute_batch(session, grader_query, chunk)

        # 4. IN_BOOK relationships
        logger.info("Writing IN_BOOK relationships (%d)...", len(in_book_edges))
        in_book_query = """
        UNWIND $batch AS row
        MATCH (h:Hadith {hadith_id: row.hadith_id})
        MATCH (b:HadithBook {collection: row.collection})
        MERGE (h)-[r:IN_BOOK]->(b)
        SET r.source = $source,
            r.method = $method,
            r.confidence = $confidence
        """
        for chunk in chunked(in_book_edges):
            execute_batch(
                session,
                in_book_query,
                chunk,
                source=SOURCE_HADITH,
                method=METHOD_DATASET,
                confidence=CONFIDENCE_EXACT,
            )

        # 5. GRADED relationships
        logger.info("Writing GRADED relationships (%d)...", len(grades_edges))
        graded_query = """
        UNWIND $batch AS row
        MATCH (h:Hadith {hadith_id: row.hadith_id})
        MATCH (g:Grader {name: row.grader})
        MERGE (h)-[r:GRADED {grade: row.grade}]->(g)
        SET r.source = $source,
            r.method = $method,
            r.confidence = $confidence
        """
        for chunk in chunked(grades_edges):
            execute_batch(
                session,
                graded_query,
                chunk,
                source=SOURCE_HADITH,
                method=METHOD_DATASET,
                confidence=CONFIDENCE_EXACT,
            )

    counts = {
        "hadith_books": len(books_data),
        "hadiths": len(hadiths_data),
        "graders": len(graders_data),
        "in_book": len(in_book_edges),
        "graded": len(grades_edges),
    }
    logger.info("Loaded hadith counts: %s", counts)
    return counts


def main() -> None:
    driver = get_driver()
    try:
        counts = load_hadith(driver)
        print("Successfully loaded hadith into Neo4j:")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
