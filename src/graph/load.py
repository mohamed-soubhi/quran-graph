"""Neo4j graph loader for L0 (Text) and L1 (Tafsir) data (T3.5).

Loads interim JSONL data into Neo4j using idempotent UNWIND batches with MERGE.
Applies schema constraints and indexes first (T2.2).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neo4j import Driver

from src.graph.apply_schema import apply_schema
from src.graph.client import get_driver
from src.log import get_logger

logger = get_logger("load")

BATCH_SIZE = 5000

SOURCE_TANZIL = "tanzil-1.1"
SOURCE_CORPUS = "quranic-corpus-0.4"
SOURCE_IBN_KATHIR = "spa5k@eb82bb6"
METHOD_DATASET = "dataset"
CONFIDENCE_EXACT = 1.0

INTERIM_DIR = ROOT / "data" / "interim"


def chunked(items: list[Any], size: int = BATCH_SIZE) -> Iterable[list[Any]]:
    """Yield successive chunks from items with maximum size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL file returning list of dicts."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing required interim file: {path}. Run 'python scripts/tasks.py parse' first."
        )
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def execute_batch(session, query: str, batch: list[dict[str, Any]]) -> None:
    """Execute a cypher query over an unwound batch."""
    if not batch:
        return
    session.run(query, batch=batch).consume()


def load_l0_l1(
    surah: int | None = None,
    driver: Driver | None = None,
) -> dict[str, int]:
    """Load L0 (Quran text, morphology) and L1 (Ibn Kathir tafsir) data into Neo4j.

    If surah is provided (1-114), only data for that surah is loaded.
    Returns a dictionary of node and relationship counts.
    """
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    try:
        # Step 1: Ensure schema constraints and indexes are applied
        logger.info("Applying Neo4j schema constraints and indexes...")
        apply_schema(driver)

        logger.info(
            "Loading interim data (surah=%s)...",
            surah if surah is not None else "ALL",
        )

        # Load raw data from data/interim/
        surahs_data = load_jsonl(INTERIM_DIR / "quran" / "surahs.jsonl")
        ayat_data = load_jsonl(INTERIM_DIR / "quran" / "ayat.jsonl")
        words_data = load_jsonl(INTERIM_DIR / "corpus" / "words.jsonl")
        lemmas_data = load_jsonl(INTERIM_DIR / "corpus" / "lemmas.jsonl")
        roots_data = load_jsonl(INTERIM_DIR / "corpus" / "roots.jsonl")
        word_lemmas_data = load_jsonl(INTERIM_DIR / "corpus" / "word_lemmas.jsonl")
        word_roots_data = load_jsonl(INTERIM_DIR / "corpus" / "word_roots.jsonl")
        lemma_roots_data = load_jsonl(INTERIM_DIR / "corpus" / "lemma_roots.jsonl")

        mufassir_data = load_jsonl(INTERIM_DIR / "tafsir" / "ibn-kathir" / "mufassir.jsonl")
        book_data = load_jsonl(INTERIM_DIR / "tafsir" / "ibn-kathir" / "book.jsonl")
        segments_data = load_jsonl(INTERIM_DIR / "tafsir" / "ibn-kathir" / "segments.jsonl")

        # Filter by surah if requested
        if surah is not None:
            surahs_data = [s for s in surahs_data if s["surah_id"] == surah]
            ayat_data = [a for a in ayat_data if a["surah_id"] == surah]
            words_data = [w for w in words_data if int(w["ayah_id"].split(":")[0]) == surah]
            surah_word_ids = {w["word_id"] for w in words_data}
            word_lemmas_data = [wl for wl in word_lemmas_data if wl["word_id"] in surah_word_ids]
            word_roots_data = [wr for wr in word_roots_data if wr["word_id"] in surah_word_ids]

            relevant_lemma_ids = {wl["lemma_id"] for wl in word_lemmas_data}
            relevant_root_ids = {wr["root_id"] for wr in word_roots_data}
            lemma_roots_data = [
                lr
                for lr in lemma_roots_data
                if lr["lemma_id"] in relevant_lemma_ids or lr["root_id"] in relevant_root_ids
            ]
            relevant_root_ids.update(lr["root_id"] for lr in lemma_roots_data)

            lemmas_data = [l for l in lemmas_data if l["lemma_id"] in relevant_lemma_ids]
            roots_data = [r for r in roots_data if r["root_id"] in relevant_root_ids]

            segments_data = [s for s in segments_data if s["surah_id"] == surah]

        # Prepare adjacent pairs for Ayah NEXT
        all_ayat = load_jsonl(INTERIM_DIR / "quran" / "ayat.jsonl")
        all_ayah_pairs = [
            {"from_id": all_ayat[i]["ayah_id"], "to_id": all_ayat[i + 1]["ayah_id"]}
            for i in range(len(all_ayat) - 1)
        ]
        if surah is not None:
            ayah_pairs = [
                p
                for p in all_ayah_pairs
                if int(p["from_id"].split(":")[0]) == surah
                or int(p["to_id"].split(":")[0]) == surah
            ]
        else:
            ayah_pairs = all_ayah_pairs

        # Prepare adjacent pairs for TafsirSegment NEXT
        all_segs = load_jsonl(INTERIM_DIR / "tafsir" / "ibn-kathir" / "segments.jsonl")
        all_seg_pairs = [
            {"from_id": all_segs[i]["segment_id"], "to_id": all_segs[i + 1]["segment_id"]}
            for i in range(len(all_segs) - 1)
        ]
        if surah is not None:
            seg_pairs = [
                p
                for p in all_seg_pairs
                if int(p["from_id"].split(":")[1]) == surah
                or int(p["to_id"].split(":")[1]) == surah
            ]
        else:
            seg_pairs = all_seg_pairs

        # Prepare covers pairs
        covers_data = [
            {"segment_id": s["segment_id"], "ayah_id": c}
            for s in segments_data
            for c in s["covers"]
        ]

        with driver.session() as session:
            # 1. Surah nodes
            logger.info("Writing Surah nodes (%d)...", len(surahs_data))
            surah_query = """
            UNWIND $batch AS row
            MERGE (s:Surah {surah_id: row.surah_id})
            SET s.name = row.name,
                s.tname = row.tname,
                s.type = row.type,
                s.revelation_order = row.revelation_order,
                s.ayah_count = row.ayah_count,
                s.has_basmala = row.has_basmala
            """
            for chunk in chunked(surahs_data):
                execute_batch(session, surah_query, chunk)

            # 2. Ayah nodes
            logger.info("Writing Ayah nodes (%d)...", len(ayat_data))
            ayah_query = """
            UNWIND $batch AS row
            MERGE (a:Ayah {ayah_id: row.ayah_id})
            SET a.surah_id = row.surah_id,
                a.number = row.number,
                a.text = row.text,
                a.text_simple = row.text_simple,
                a.text_norm = row.text_norm,
                a.word_count = row.word_count
            """
            for chunk in chunked(ayat_data):
                execute_batch(session, ayah_query, chunk)

            # 3. HAS_AYAH (Surah -> Ayah)
            logger.info("Writing HAS_AYAH relationships (%d)...", len(ayat_data))
            has_ayah_query = """
            UNWIND $batch AS row
            MATCH (s:Surah {surah_id: row.surah_id})
            MATCH (a:Ayah {ayah_id: row.ayah_id})
            MERGE (s)-[r:HAS_AYAH]->(a)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(ayat_data):
                session.run(
                    has_ayah_query,
                    batch=chunk,
                    source=SOURCE_TANZIL,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 4. NEXT (Ayah -> Ayah)
            logger.info("Writing Ayah NEXT relationships (%d pairs)...", len(ayah_pairs))
            next_ayah_query = """
            UNWIND $batch AS row
            MATCH (a1:Ayah {ayah_id: row.from_id})
            MATCH (a2:Ayah {ayah_id: row.to_id})
            MERGE (a1)-[r:NEXT]->(a2)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(ayah_pairs):
                session.run(
                    next_ayah_query,
                    batch=chunk,
                    source=SOURCE_TANZIL,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 5. Word nodes
            logger.info("Writing Word nodes (%d)...", len(words_data))
            word_query = """
            UNWIND $batch AS row
            MERGE (w:Word {word_id: row.word_id})
            SET w.ayah_id = row.ayah_id,
                w.position = row.position,
                w.text = row.text,
                w.bw = row.bw,
                w.pos = row.pos
            """
            for chunk in chunked(words_data):
                execute_batch(session, word_query, chunk)

            # 6. HAS_WORD (Ayah -> Word)
            logger.info("Writing HAS_WORD relationships (%d)...", len(words_data))
            has_word_query = """
            UNWIND $batch AS row
            MATCH (a:Ayah {ayah_id: row.ayah_id})
            MATCH (w:Word {word_id: row.word_id})
            MERGE (a)-[r:HAS_WORD]->(w)
            SET r.position = row.position,
                r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(words_data):
                session.run(
                    has_word_query,
                    batch=chunk,
                    source=SOURCE_CORPUS,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 7. Lemma nodes
            logger.info("Writing Lemma nodes (%d)...", len(lemmas_data))
            lemma_query = """
            UNWIND $batch AS row
            MERGE (l:Lemma {lemma_id: row.lemma_id})
            SET l.text = row.text,
                l.sense = row.sense,
                l.bw = row.bw
            """
            for chunk in chunked(lemmas_data):
                execute_batch(session, lemma_query, chunk)

            # 8. Root nodes
            logger.info("Writing Root nodes (%d)...", len(roots_data))
            root_query = """
            UNWIND $batch AS row
            MERGE (r:Root {root_id: row.root_id})
            SET r.text = row.text,
                r.bw = row.bw
            """
            for chunk in chunked(roots_data):
                execute_batch(session, root_query, chunk)

            # 9. HAS_LEMMA (Word -> Lemma)
            logger.info("Writing HAS_LEMMA relationships (%d)...", len(word_lemmas_data))
            has_lemma_query = """
            UNWIND $batch AS row
            MATCH (w:Word {word_id: row.word_id})
            MATCH (l:Lemma {lemma_id: row.lemma_id})
            MERGE (w)-[r:HAS_LEMMA {segment: row.segment}]->(l)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(word_lemmas_data):
                session.run(
                    has_lemma_query,
                    batch=chunk,
                    source=SOURCE_CORPUS,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 10. HAS_ROOT (Word -> Root)
            logger.info("Writing HAS_ROOT relationships (%d)...", len(word_roots_data))
            has_root_query = """
            UNWIND $batch AS row
            MATCH (w:Word {word_id: row.word_id})
            MATCH (rt:Root {root_id: row.root_id})
            MERGE (w)-[rel:HAS_ROOT]->(rt)
            SET rel.source = $source,
                rel.method = $method,
                rel.confidence = $confidence
            """
            for chunk in chunked(word_roots_data):
                session.run(
                    has_root_query,
                    batch=chunk,
                    source=SOURCE_CORPUS,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 11. LEMMA_OF_ROOT (Lemma -> Root)
            logger.info("Writing LEMMA_OF_ROOT relationships (%d)...", len(lemma_roots_data))
            lemma_of_root_query = """
            UNWIND $batch AS row
            MATCH (l:Lemma {lemma_id: row.lemma_id})
            MATCH (rt:Root {root_id: row.root_id})
            MERGE (l)-[rel:LEMMA_OF_ROOT]->(rt)
            SET rel.source = $source,
                rel.method = $method,
                rel.confidence = $confidence
            """
            for chunk in chunked(lemma_roots_data):
                session.run(
                    lemma_of_root_query,
                    batch=chunk,
                    source=SOURCE_CORPUS,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 12. Mufassir node
            logger.info("Writing Mufassir nodes (%d)...", len(mufassir_data))
            mufassir_query = """
            UNWIND $batch AS row
            MERGE (m:Mufassir {mufassir_id: row.mufassir_id})
            SET m.name = row.name,
                m.death_hijri = row.death_hijri
            """
            for chunk in chunked(mufassir_data):
                execute_batch(session, mufassir_query, chunk)

            # 13. TafsirBook node
            logger.info("Writing TafsirBook nodes (%d)...", len(book_data))
            book_query = """
            UNWIND $batch AS row
            MERGE (b:TafsirBook {book_id: row.book_id})
            SET b.title = row.title,
                b.source = row.source
            """
            for chunk in chunked(book_data):
                execute_batch(session, book_query, chunk)

            # 14. WROTE (Mufassir -> TafsirBook)
            logger.info("Writing WROTE relationships (%d)...", len(book_data))
            wrote_query = """
            UNWIND $batch AS row
            MATCH (m:Mufassir {mufassir_id: row.mufassir_id})
            MATCH (b:TafsirBook {book_id: row.book_id})
            MERGE (m)-[r:WROTE]->(b)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(book_data):
                session.run(
                    wrote_query,
                    batch=chunk,
                    source=SOURCE_IBN_KATHIR,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 15. TafsirSegment nodes
            logger.info("Writing TafsirSegment nodes (%d)...", len(segments_data))
            segment_query = """
            UNWIND $batch AS row
            MERGE (s:TafsirSegment {segment_id: row.segment_id})
            SET s.book_id = row.book_id,
                s.surah_id = row.surah_id,
                s.first_ayah = row.first_ayah,
                s.last_ayah = row.last_ayah,
                s.n = row.n,
                s.text = row.text,
                s.text_norm = row.text_norm,
                s.char_count = row.char_count
            """
            for chunk in chunked(segments_data):
                execute_batch(session, segment_query, chunk)

            # 16. HAS_SEGMENT (TafsirBook -> TafsirSegment)
            logger.info("Writing HAS_SEGMENT relationships (%d)...", len(segments_data))
            has_segment_query = """
            UNWIND $batch AS row
            MATCH (b:TafsirBook {book_id: row.book_id})
            MATCH (s:TafsirSegment {segment_id: row.segment_id})
            MERGE (b)-[r:HAS_SEGMENT]->(s)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(segments_data):
                session.run(
                    has_segment_query,
                    batch=chunk,
                    source=SOURCE_IBN_KATHIR,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 17. COVERS (TafsirSegment -> Ayah)
            logger.info("Writing COVERS relationships (%d)...", len(covers_data))
            covers_query = """
            UNWIND $batch AS row
            MATCH (s:TafsirSegment {segment_id: row.segment_id})
            MATCH (a:Ayah {ayah_id: row.ayah_id})
            MERGE (s)-[r:COVERS]->(a)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(covers_data):
                session.run(
                    covers_query,
                    batch=chunk,
                    source=SOURCE_IBN_KATHIR,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # 18. NEXT (TafsirSegment -> TafsirSegment)
            logger.info("Writing TafsirSegment NEXT relationships (%d pairs)...", len(seg_pairs))
            next_seg_query = """
            UNWIND $batch AS row
            MATCH (s1:TafsirSegment {segment_id: row.from_id})
            MATCH (s2:TafsirSegment {segment_id: row.to_id})
            MERGE (s1)-[r:NEXT]->(s2)
            SET r.source = $source,
                r.method = $method,
                r.confidence = $confidence
            """
            for chunk in chunked(seg_pairs):
                session.run(
                    next_seg_query,
                    batch=chunk,
                    source=SOURCE_IBN_KATHIR,
                    method=METHOD_DATASET,
                    confidence=CONFIDENCE_EXACT,
                ).consume()

            # Count and log summary per label and per relationship type
            counts = get_db_counts(session)
            log_db_counts(counts)
            return counts

    finally:
        if close_driver:
            driver.close()


def get_db_counts(session) -> dict[str, int]:
    """Retrieve node counts per label and relationship counts per type."""
    counts: dict[str, int] = {}

    labels = [
        "Surah",
        "Ayah",
        "Word",
        "Lemma",
        "Root",
        "Mufassir",
        "TafsirBook",
        "TafsirSegment",
    ]
    for lbl in labels:
        res = session.run(f"MATCH (n:{lbl}) RETURN count(n) AS cnt").single()
        counts[f"Node:{lbl}"] = res["cnt"] if res else 0

    rel_types = [
        "HAS_AYAH",
        "HAS_WORD",
        "HAS_LEMMA",
        "HAS_ROOT",
        "LEMMA_OF_ROOT",
        "WROTE",
        "HAS_SEGMENT",
        "COVERS",
    ]
    for rtype in rel_types:
        res = session.run(f"MATCH ()-[r:{rtype}]->() RETURN count(r) AS cnt").single()
        counts[f"Rel:{rtype}"] = res["cnt"] if res else 0

    # NEXT is polymorphic (Ayah->Ayah and TafsirSegment->TafsirSegment)
    res_ayah_next = session.run(
        "MATCH (:Ayah)-[r:NEXT]->(:Ayah) RETURN count(r) AS cnt"
    ).single()
    counts["Rel:NEXT_Ayah"] = res_ayah_next["cnt"] if res_ayah_next else 0

    res_seg_next = session.run(
        "MATCH (:TafsirSegment)-[r:NEXT]->(:TafsirSegment) RETURN count(r) AS cnt"
    ).single()
    counts["Rel:NEXT_TafsirSegment"] = res_seg_next["cnt"] if res_seg_next else 0

    return counts


def log_db_counts(counts: dict[str, int]) -> None:
    """Log counts formatted clearly."""
    logger.info("=== Database Counts ===")
    for k, v in counts.items():
        logger.info("  %-25s: %d", k, v)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Quran and Tafsir data into Neo4j.")
    parser.add_argument(
        "--surah",
        type=int,
        default=None,
        help="Surah number to load (1-114). If omitted, loads all.",
    )
    args = parser.parse_args()

    if args.surah is not None and not (1 <= args.surah <= 114):
        print("Error: --surah must be an integer between 1 and 114.", file=sys.stderr)
        sys.exit(1)

    try:
        counts = load_l0_l1(surah=args.surah)
        print("Load finished successfully.")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    except Exception as exc:
        logger.error("Load failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
