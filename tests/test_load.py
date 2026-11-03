"""Unit and integration tests for Neo4j L0+L1 loader (T3.5).

Tests loading of Surah 1, verifying:
- 1 Surah, 7 Ayah, 29 Word, 7 COVERS
- Idempotency: running it twice changes no count
- Provenance on all relationships
"""

from pathlib import Path
import pytest
from neo4j.exceptions import ServiceUnavailable

from src.graph.client import get_driver
from src.graph.load import load_l0_l1

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def neo4j_driver():
    """Provide a Neo4j driver if reachable, otherwise skip."""
    try:
        driver = get_driver()
    except (ServiceUnavailable, Exception) as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")

    yield driver
    driver.close()


def test_load_surah_1_counts(neo4j_driver):
    """Loading surah 1 must produce 1 Surah, 7 Ayah, 29 Word, 7 COVERS."""
    counts = load_l0_l1(surah=1, driver=neo4j_driver)

    assert counts["Node:Surah"] >= 1
    assert counts["Node:Ayah"] >= 7
    assert counts["Node:Word"] >= 29
    assert counts["Rel:COVERS"] >= 7

    with neo4j_driver.session() as session:
        # Directly verify in DB for surah 1 specifically
        surah_res = session.run(
            "MATCH (s:Surah {surah_id: 1}) RETURN count(s) AS cnt"
        ).single()["cnt"]
        assert surah_res == 1

        ayah_res = session.run(
            "MATCH (a:Ayah {surah_id: 1}) RETURN count(a) AS cnt"
        ).single()["cnt"]
        assert ayah_res == 7

        word_res = session.run(
            "MATCH (a:Ayah {surah_id: 1})-[:HAS_WORD]->(w:Word) RETURN count(w) AS cnt"
        ).single()["cnt"]
        assert word_res == 29

        covers_res = session.run(
            "MATCH (s:TafsirSegment {surah_id: 1})-[:COVERS]->(a:Ayah) RETURN count(a) AS cnt"
        ).single()["cnt"]
        assert covers_res == 7


def test_load_surah_1_idempotent(neo4j_driver):
    """Running load on surah 1 twice produces strictly identical counts."""
    counts1 = load_l0_l1(surah=1, driver=neo4j_driver)
    counts2 = load_l0_l1(surah=1, driver=neo4j_driver)

    assert counts1 == counts2


def test_provenance_properties(neo4j_driver):
    """Every relationship must carry source, method='dataset', and confidence=1.0."""
    with neo4j_driver.session() as session:
        invalid_res = session.run(
            """
            MATCH ()-[r]->()
            WHERE r.source IS NULL
               OR r.method <> 'dataset'
               OR r.confidence <> 1.0
            RETURN count(r) AS cnt
            """
        ).single()["cnt"]
        assert invalid_res == 0
