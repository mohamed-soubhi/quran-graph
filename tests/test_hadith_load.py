"""Tests for hadith interim data and Neo4j loader (T5.1).

Validates:
- Exact counts matching T5.1 facts (36,104 hadith, 10 books, 9 graders, 67,334 grades)
- Specific reference cases (muslim:7207 / 2865.01, bukhari:402.2)
- Byte-for-byte fidelity of raw text on random sample
- Idempotent loader on test fixture 'test-coll' and 'test-grader'
"""

from collections import Counter
import json
import os
from pathlib import Path
import random
import pytest
from neo4j.exceptions import ServiceUnavailable

from src.extract.normalize import normalize_with_map
from src.graph.client import get_driver
from src.graph.hadith import load_hadith
from src.ingest.parse_hadith import COLLECTIONS_META

ROOT = Path(__file__).resolve().parent.parent
INTERIM_HADITH_FILE = ROOT / "data" / "interim" / "hadith" / "hadith.jsonl"
INTERIM_BOOKS_FILE = ROOT / "data" / "interim" / "hadith" / "books.jsonl"
RAW_HADITH_DIR = ROOT / "data" / "raw" / "hadith" / "fawazahmed0"

EXPECTED_COLLECTION_COUNTS = {
    "abudawud": 5272,
    "bukhari": 7580,
    "dehlawi": 40,
    "ibnmajah": 4338,
    "malik": 1829,
    "muslim": 7360,
    "nasai": 5679,
    "nawawi": 42,
    "qudsi": 40,
    "tirmidhi": 3924,
}

EXPECTED_GRADER_COUNTS = {
    "Zubair Ali Zai": 19033,
    "Al-Albani": 18925,
    "Shuaib Al Arnaut": 6409,
    "Abu Ghuddah": 5609,
    "Muhammad Muhyi Al-Din Abdul Hamid": 5169,
    "Muhammad Fouad Abd al-Baqi": 4309,
    "Ahmad Muhammad Shakir": 3667,
    "Bashar Awad Maarouf": 2384,
    "Salim al-Hilali": 1829,
}


@pytest.fixture(scope="module")
def hadith_records():
    assert INTERIM_HADITH_FILE.exists(), f"Missing {INTERIM_HADITH_FILE}. Run parse_hadith first."
    records = []
    with open(INTERIM_HADITH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


@pytest.fixture(scope="module")
def books_records():
    assert INTERIM_BOOKS_FILE.exists(), f"Missing {INTERIM_BOOKS_FILE}. Run parse_hadith first."
    records = []
    with open(INTERIM_BOOKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


@pytest.fixture
def driver():
    """Yield a connected Neo4j driver, skipping only if the server is unreachable."""
    try:
        drv = get_driver()
    except (ServiceUnavailable, OSError) as exc:
        if os.getenv("SMOKE_STRICT") == "1":
            pytest.fail(f"Neo4j is unreachable: {exc}")
        pytest.skip(f"Neo4j is unreachable: {exc}")
    yield drv
    drv.close()


def test_hadith_counts(hadith_records, books_records):
    """Verify exact counts from T5.1 facts table."""
    # 1. Total loaded hadiths and books
    assert len(hadith_records) == 36104
    assert len(books_records) == 10

    # 2. Per collection counts
    col_counts = Counter(h["collection"] for h in hadith_records)
    assert col_counts == EXPECTED_COLLECTION_COUNTS

    # 3. Grades and Graders
    grader_counts = Counter()
    total_grades = 0
    hadiths_without_grade = 0
    null_arabic_numbers = 0
    bukhari_floats = 0
    total_floats = 0

    for h in hadith_records:
        grades = h.get("grades", [])
        if not grades:
            hadiths_without_grade += 1
        else:
            total_grades += len(grades)
            for g in grades:
                grader_counts[g["grader"]] += 1

        if h["arabic_number"] is None:
            null_arabic_numbers += 1

        if "." in h["number"]:
            total_floats += 1
            if h["collection"] == "bukhari":
                bukhari_floats += 1

    assert total_grades == 67334
    assert len(grader_counts) == 9
    assert grader_counts == EXPECTED_GRADER_COUNTS
    assert hadiths_without_grade == 15106
    assert null_arabic_numbers == 148
    assert bukhari_floats == 26
    # Total floats across all collections: 26 bukhari + 2 ibnmajah + 7 nasai + 35 tirmidhi = 70
    assert total_floats == 70


def test_hadith_books_metadata(books_records):
    """Verify books.jsonl has 10 entries with expected Arabic and English names."""
    assert len(books_records) == 10
    by_col = {b["collection"]: b for b in books_records}
    for col, meta in COLLECTIONS_META.items():
        assert col in by_col
        book = by_col[col]
        assert book["name"] == meta["name"]
        assert book["name_en"] == meta["name_en"]
        assert book["edition"] == f"ara-{col}"
        assert book["source"] == "hadith-api@df57907"


def test_hadith_muslim_2865_01(hadith_records):
    """Verify muslim hadith with arabicnumber '2865.01' is muslim:7207 with expected text."""
    matches = [h for h in hadith_records if h["collection"] == "muslim" and h.get("arabic_number") == "2865.01"]
    assert len(matches) == 1
    h = matches[0]
    assert h["hadith_id"] == "muslim:7207"
    assert h["number"] == "7207"

    norm_phrase, _ = normalize_with_map("خلقت عبادي حنفاء")
    assert norm_phrase in h["text_norm"]


def test_hadith_bukhari_402_2(hadith_records):
    """Verify bukhari:402.2 exists with float number string."""
    matches = [h for h in hadith_records if h["hadith_id"] == "bukhari:402.2"]
    assert len(matches) == 1
    h = matches[0]
    assert h["collection"] == "bukhari"
    assert h["number"] == "402.2"
    assert h["arabic_number"] == "402.2"


def test_hadith_text_byte_identical_sample(hadith_records):
    """Verify verbatim text matches raw file byte-for-byte on 20 random hadiths."""
    rnd = random.Random(42)
    sample = rnd.sample(hadith_records, 20)

    # Group sample by collection to minimize raw file loads
    by_col: dict[str, list[dict]] = {}
    for h in sample:
        by_col.setdefault(h["collection"], []).append(h)

    for col, items in by_col.items():
        raw_file = RAW_HADITH_DIR / f"ara-{col}.json"
        with open(raw_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        raw_map = {}
        for rh in raw_data["hadiths"]:
            hn = rh.get("hadithnumber")
            if hn is not None:
                num_key = str(hn) if isinstance(hn, float) and not hn.is_integer() else str(int(hn))
                raw_map[num_key] = rh["text"]

        for item in items:
            expected_text = raw_map[item["number"]]
            assert item["text"] == expected_text
            assert item["text"].encode("utf-8") == expected_text.encode("utf-8")


def test_hadith_loader_fixture(driver, tmp_path):
    """Test load_hadith on a tiny fixture (test-coll, test-grader).

    Verifies idempotency (counts unchanged on reload), provenance on all edges,
    and cleanly deletes only test nodes. Real data is never touched.
    """
    fixture_books = tmp_path / "books.jsonl"
    fixture_hadith = tmp_path / "hadith.jsonl"

    book_entry = {
        "collection": "test-coll",
        "edition": "ara-test-coll",
        "name": "كتاب تجريبي",
        "name_en": "Test Collection",
        "source": "hadith-api@df57907",
    }
    with open(fixture_books, "w", encoding="utf-8") as f:
        f.write(json.dumps(book_entry, ensure_ascii=False) + "\n")

    hadith_entries = [
        {
            "arabic_number": "1",
            "book_number": 1,
            "collection": "test-coll",
            "grades": [{"grade": "Sahih", "grader": "test-grader"}],
            "hadith_id": "test-coll:1",
            "number": "1",
            "number_in_book": 1,
            "text": "نص تجريبي 1",
            "text_norm": "نص تجريبي 1",
        },
        {
            "arabic_number": "2",
            "book_number": 1,
            "collection": "test-coll",
            "grades": [{"grade": "Hasan", "grader": "test-grader"}],
            "hadith_id": "test-coll:2",
            "number": "2",
            "number_in_book": 2,
            "text": "نص تجريبي 2",
            "text_norm": "نص تجريبي 2",
        },
        {
            "arabic_number": "3",
            "book_number": 1,
            "collection": "test-coll",
            "grades": [],
            "hadith_id": "test-coll:3",
            "number": "3",
            "number_in_book": 3,
            "text": "نص تجريبي 3",
            "text_norm": "نص تجريبي 3",
        },
    ]
    with open(fixture_hadith, "w", encoding="utf-8") as f:
        for entry in hadith_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _cleanup():
        with driver.session() as s:
            s.run("MATCH (h:Hadith {collection: 'test-coll'}) DETACH DELETE h").consume()
            s.run("MATCH (b:HadithBook {collection: 'test-coll'}) DETACH DELETE b").consume()
            s.run("MATCH (g:Grader {name: 'test-grader'}) DETACH DELETE g").consume()

    _cleanup()
    try:
        # Load 1
        counts1 = load_hadith(driver, hadith_path=fixture_hadith, books_path=fixture_books)
        assert counts1 == {
            "hadith_books": 1,
            "hadiths": 3,
            "graders": 1,
            "in_book": 3,
            "graded": 2,
        }

        with driver.session() as s:
            # Check nodes
            n_books = s.run("MATCH (b:HadithBook {collection: 'test-coll'}) RETURN count(b) AS c").single()["c"]
            n_hadiths = s.run("MATCH (h:Hadith {collection: 'test-coll'}) RETURN count(h) AS c").single()["c"]
            n_graders = s.run("MATCH (g:Grader {name: 'test-grader'}) RETURN count(g) AS c").single()["c"]
            assert n_books == 1
            assert n_hadiths == 3
            assert n_graders == 1

            # Check relationships and provenance
            in_books = s.run("""
                MATCH (h:Hadith {collection: 'test-coll'})-[r:IN_BOOK]->(b:HadithBook {collection: 'test-coll'})
                RETURN r.source AS src, r.method AS meth, r.confidence AS conf
            """).data()
            assert len(in_books) == 3
            for r in in_books:
                assert r["src"] == "hadith-api@df57907"
                assert r["meth"] == "dataset"
                assert r["conf"] == 1.0

            gradeds = s.run("""
                MATCH (h:Hadith {collection: 'test-coll'})-[r:GRADED]->(g:Grader {name: 'test-grader'})
                RETURN r.grade AS grade, r.source AS src, r.method AS meth, r.confidence AS conf
            """).data()
            assert len(gradeds) == 2
            grades_set = {r["grade"] for r in gradeds}
            assert grades_set == {"Sahih", "Hasan"}
            for r in gradeds:
                assert r["src"] == "hadith-api@df57907"
                assert r["meth"] == "dataset"
                assert r["conf"] == 1.0

        # Load 2 (idempotency check)
        counts2 = load_hadith(driver, hadith_path=fixture_hadith, books_path=fixture_books)
        assert counts2 == counts1

        with driver.session() as s:
            n_books2 = s.run("MATCH (b:HadithBook {collection: 'test-coll'}) RETURN count(b) AS c").single()["c"]
            n_hadiths2 = s.run("MATCH (h:Hadith {collection: 'test-coll'}) RETURN count(h) AS c").single()["c"]
            n_graders2 = s.run("MATCH (g:Grader {name: 'test-grader'}) RETURN count(g) AS c").single()["c"]
            assert n_books2 == 1
            assert n_hadiths2 == 3
            assert n_graders2 == 1

            n_in_books = s.run("""
                MATCH (h:Hadith {collection: 'test-coll'})-[r:IN_BOOK]->(b:HadithBook {collection: 'test-coll'})
                RETURN count(r) AS c
            """).single()["c"]
            n_gradeds = s.run("""
                MATCH (h:Hadith {collection: 'test-coll'})-[r:GRADED]->(g:Grader {name: 'test-grader'})
                RETURN count(r) AS c
            """).single()["c"]
            assert n_in_books == 3
            assert n_gradeds == 2

    finally:
        _cleanup()
        with driver.session() as s:
            # Confirm deletion of only test fixture
            rem_books = s.run("MATCH (b:HadithBook {collection: 'test-coll'}) RETURN count(b) AS c").single()["c"]
            rem_hadiths = s.run("MATCH (h:Hadith {collection: 'test-coll'}) RETURN count(h) AS c").single()["c"]
            rem_graders = s.run("MATCH (g:Grader {name: 'test-grader'}) RETURN count(g) AS c").single()["c"]
            assert rem_books == 0
            assert rem_hadiths == 0
            assert rem_graders == 0
