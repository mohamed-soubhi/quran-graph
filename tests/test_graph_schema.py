"""Tests for Neo4j schema constraints and indexes (T2.2)."""

import os
from pathlib import Path
import pytest
from neo4j.exceptions import ConstraintError, ServiceUnavailable

from src.graph.apply_schema import apply_schema
from src.graph.client import get_driver

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_UNIQUE_CONSTRAINTS = {
    ("Surah", "surah_id"),
    ("Ayah", "ayah_id"),
    ("Word", "word_id"),
    ("Root", "root_id"),
    ("Lemma", "lemma_id"),
    ("Mufassir", "mufassir_id"),
    ("TafsirBook", "book_id"),
    ("TafsirSegment", "segment_id"),
    ("Span", "span_id"),
    ("HadithBook", "collection"),
    ("Hadith", "hadith_id"),
    ("Grader", "name"),
    ("Narrator", "narrator_id"),
}


@pytest.fixture
def driver():
    """Yield a connected Neo4j driver, skipping only if the server is unreachable.

    With SMOKE_STRICT=1 (e.g. from `tasks.py smoke`), an unreachable server fails instead of skipping.
    """
    try:
        drv = get_driver()
    except (ServiceUnavailable, OSError) as exc:
        if os.getenv("SMOKE_STRICT") == "1":
            pytest.fail(f"Neo4j is unreachable: {exc}")
        pytest.skip(f"Neo4j is unreachable: {exc}")
    yield drv
    drv.close()


def test_schema_idempotency(driver):
    """Applying schema twice should execute without error (idempotent)."""
    first_names = apply_schema(driver)
    second_names = apply_schema(driver)
    assert len(first_names) == 18
    assert first_names == second_names


def test_schema_constraints(driver):
    """SHOW CONSTRAINTS contains exactly the 13 unique constraints of the schema."""
    apply_schema(driver)
    with driver.session() as session:
        records = session.run("SHOW CONSTRAINTS").data()

    unique_constraints = [r for r in records if r["type"] == "UNIQUENESS"]
    assert len(unique_constraints) == 13, (
        f"Expected 13 unique constraints, found {len(unique_constraints)}: "
        f"{[c['name'] for c in unique_constraints]}"
    )

    actual_pairs = {
        (r["labelsOrTypes"][0], r["properties"][0])
        for r in unique_constraints
        if r.get("labelsOrTypes") and r.get("properties")
    }
    assert actual_pairs == EXPECTED_UNIQUE_CONSTRAINTS


def test_schema_indexes(driver):
    """SHOW INDEXES contains the 3 range indexes and the 2 full-text indexes."""
    apply_schema(driver)
    with driver.session() as session:
        indexes = session.run("SHOW INDEXES").data()

    index_map = {idx["name"]: idx for idx in indexes}

    # 3 Range indexes
    range_expected = {
        "span_type_idx": ("Span", "type"),
        "hadith_arabic_number_idx": ("Hadith", "arabic_number"),
        "hadith_collection_idx": ("Hadith", "collection"),
    }
    for name, (label, prop) in range_expected.items():
        assert name in index_map, f"Missing index {name}"
        idx = index_map[name]
        assert idx["type"] == "RANGE"
        assert label in idx["labelsOrTypes"]
        assert prop in idx["properties"]

    # 2 Full-text indexes
    ft_expected = {
        "ayah_text_norm_ft": ("Ayah", "text_norm"),
        "segment_text_norm_ft": ("TafsirSegment", "text_norm"),
    }
    for name, (label, prop) in ft_expected.items():
        assert name in index_map, f"Missing full-text index {name}"
        idx = index_map[name]
        assert idx["type"] == "FULLTEXT"
        assert label in idx["labelsOrTypes"]
        assert prop in idx["properties"]


def test_ayah_unique_constraint(driver):
    """Creating two Ayah nodes with the same ayah_id fails with ConstraintError."""
    apply_schema(driver)
    with driver.session() as session:
        try:
            session.run("MATCH (a:Ayah {ayah_id: '0:0'}) DELETE a")
            session.run("CREATE (:Ayah {ayah_id: '0:0'})").consume()

            with pytest.raises(ConstraintError):
                session.run("CREATE (:Ayah {ayah_id: '0:0'})").consume()
        finally:
            session.run("MATCH (a:Ayah {ayah_id: '0:0'}) DELETE a")
