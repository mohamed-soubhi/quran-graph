"""Tests for Neo4j and GDS Docker setup (T0.2)."""

import os
import re
import subprocess
from pathlib import Path
import pytest
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
    """Verify the running Neo4j container has GDS available.

    Skips when the Docker daemon is not running, unless SMOKE_STRICT=1 (set by `tasks.py smoke`).
    The password reaches cypher-shell through the environment, never the command line,
    so it cannot appear in a failure message.
    """
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        pytest.skip("NEO4J_PASSWORD not set in .env")

    daemon = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if daemon.returncode != 0:
        if os.getenv("SMOKE_STRICT") == "1":
            pytest.fail("Docker daemon is not running")
        pytest.skip("Docker daemon is not running")

    res = subprocess.run(
        ["docker", "compose", "exec", "-T", "-e", "NEO4J_USERNAME", "-e", "NEO4J_PASSWORD",
         "neo4j", "cypher-shell", "RETURN gds.version();"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password},
    )
    code, out, err = res.returncode, res.stdout, res.stderr.replace(password, "***")
    assert code == 0, f"cypher-shell failed: {err}"
    assert re.search(r"\d+\.\d+\.\d+", out), f"no GDS version in output: {out}"
