"""Tests for Neo4j and GDS Docker setup (T0.2)."""

import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def test_docker_compose_config():
    """Verify docker-compose.yml exists and defines the required Neo4j configuration."""
    compose_path = ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    content = compose_path.read_text(encoding="utf-8")
    assert "name: quran-graph" in content, "Top-level project name must be quran-graph"
    assert "image: neo4j:5" in content, "Neo4j image must be neo4j:5"
    assert "graph-data-science" in content, "GDS plugin must be configured"
    assert "NEO4J_server_memory_heap_initial__size=4G" in content
    assert "NEO4J_server_memory_heap_max__size=4G" in content
    assert "NEO4J_server_memory_pagecache_size=4G" in content
    assert "neo4j_data:/data" in content, "Must use named volume for /data"


def test_docker_compose_valid():
    """Verify docker compose config validates cleanly."""
    res = subprocess.run(["docker", "compose", "config"], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"docker compose config failed: {res.stderr}"
    assert "quran-graph" in res.stdout


def test_tasks_targets():
    """Verify scripts/tasks.py defines up and down targets."""
    tasks_path = ROOT / "scripts" / "tasks.py"
    assert tasks_path.exists()
    content = tasks_path.read_text(encoding="utf-8")
    assert '"up": run_up' in content
    assert '"down": run_down' in content


def test_neo4j_gds_running():
    """Verify the running Neo4j container has GDS available."""
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        return

    res = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "neo4j",
            "cypher-shell",
            "-u",
            user,
            "-p",
            password,
            "RETURN gds.version();",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"cypher-shell failed: {res.stderr}"
    assert "2.13.14" in res.stdout
