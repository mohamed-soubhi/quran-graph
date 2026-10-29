"""Neo4j client and connection management (T0.3)."""

import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")


def get_driver(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> Driver:
    """Create and return a connected Neo4j driver instance.

    Reads NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD from the environment
    (loaded from .env via python-dotenv) if not explicitly provided.
    Calls verify_connectivity() before returning the driver.
    """
    load_dotenv(ROOT / ".env")
    uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = user or os.getenv("NEO4J_USER", "neo4j")
    password = password if password is not None else os.getenv("NEO4J_PASSWORD")

    auth = (user, password) if user and password is not None else None
    driver = GraphDatabase.driver(uri, auth=auth)
    try:
        driver.verify_connectivity()
    except Exception:
        driver.close()
        raise
    return driver
