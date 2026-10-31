"""Apply Neo4j graph schema constraints and indexes (T2.2)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neo4j import Driver

from src.graph.client import get_driver
from src.log import get_logger

logger = get_logger("apply_schema")

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.cypher"
NAME_PATTERN = re.compile(
    r"CREATE\s+(?:FULLTEXT\s+)?(?:CONSTRAINT|INDEX)\s+([A-Za-z0-9_]+)",
    re.IGNORECASE,
)


def extract_statement_name(stmt: str) -> str:
    """Extract constraint or index name from a Cypher statement."""
    match = NAME_PATTERN.search(stmt)
    if match:
        return match.group(1)
    return stmt.strip().split()[2] if len(stmt.strip().split()) > 2 else "unknown"


def apply_schema(driver: Driver | None = None, schema_path: Path | None = None) -> list[str]:
    """Execute each statement in schema.cypher using the driver and log each name.

    Returns the list of applied constraint and index names.
    """
    path = schema_path or SCHEMA_FILE
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")

    content = path.read_text(encoding="utf-8")
    statements = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]

    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    applied_names: list[str] = []
    try:
        with driver.session() as session:
            for stmt in statements:
                name = extract_statement_name(stmt)
                session.run(stmt)
                logger.info("Applied schema statement: %s", name)
                applied_names.append(name)
    finally:
        if close_driver:
            driver.close()

    return applied_names


def main() -> None:
    try:
        names = apply_schema()
        print(f"Successfully applied {len(names)} schema statements.")
    except Exception as exc:
        logger.error("Failed to apply schema: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
