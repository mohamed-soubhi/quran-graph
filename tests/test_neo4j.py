"""Smoke tests for Neo4j driver (T0.3)."""

import pytest
from neo4j.exceptions import ServiceUnavailable

from src.graph.client import get_driver


@pytest.fixture
def driver():
    """Yield a connected Neo4j driver, skipping only if the server is unreachable.

    Auth and other errors are not caught, so a wrong password fails the test.
    """
    try:
        drv = get_driver()
    except (ServiceUnavailable, OSError) as exc:
        pytest.skip(f"Neo4j is unreachable: {exc}")
    yield drv
    drv.close()


def test_neo4j_smoke(driver):
    """Write and read a smoke node, verifying round-trip and teardown."""
    try:
        with driver.session() as session:
            result = session.run("MERGE (n:Smoke {id:'t1'}) RETURN n.id")
            record = result.single()
            assert record is not None, "Expected a record to be returned"
            assert record["n.id"] == "t1"
    finally:
        with driver.session() as session:
            session.run("MATCH (n:Smoke) DELETE n")
