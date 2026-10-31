"""Task runner replacing Makefile for the project.

Targets: up, down, test, smoke, schema
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get_venv_python() -> str:
    """Return path to the virtual environment Python executable."""
    if sys.platform == "win32":
        venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT / ".venv" / "bin" / "python"

    if venv_py.exists():
        return str(venv_py)
    print("Error: .venv not found. Create it with: python -m venv .venv", file=sys.stderr)
    sys.exit(1)


def run_test(args=None) -> None:
    """Run pytest suite using venv Python."""
    py = get_venv_python()
    cmd = [py, "-m", "pytest"]
    if args:
        cmd.extend(args)
    res = subprocess.run(cmd, cwd=ROOT)
    sys.exit(res.returncode)


def run_up() -> None:
    """Start services with docker compose."""
    res = subprocess.run(["docker", "compose", "up", "-d"], cwd=ROOT)
    sys.exit(res.returncode)


def run_down() -> None:
    """Stop services with docker compose."""
    res = subprocess.run(["docker", "compose", "down"], cwd=ROOT)
    sys.exit(res.returncode)


def run_smoke(args=None) -> None:
    """Run Neo4j smoke test followed by extraction smoke test."""
    py = get_venv_python()
    env = {**os.environ, "SMOKE_STRICT": "1"}
    res = subprocess.run([py, "-m", "pytest", "tests/test_neo4j.py"], cwd=ROOT, env=env)
    if res.returncode != 0:
        sys.exit(res.returncode)

    smoke_args = args if args else ["--runs", "1"]
    res = subprocess.run([py, "scripts/extract_smoke.py", *smoke_args], cwd=ROOT)
    sys.exit(res.returncode)


def run_schema() -> None:
    """Apply Neo4j constraints and indexes from src/graph/schema.cypher."""
    py = get_venv_python()
    res = subprocess.run([py, "src/graph/apply_schema.py"], cwd=ROOT)
    sys.exit(res.returncode)


TARGETS = {
    "test": run_test,
    "up": run_up,
    "down": run_down,
    "smoke": run_smoke,
    "schema": run_schema,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        print(f"Usage: python scripts/tasks.py <{'|'.join(TARGETS.keys())}>")
        sys.exit(1)

    target = sys.argv[1]
    extra_args = sys.argv[2:]
    if target in ("test", "smoke"):
        TARGETS[target](extra_args)
    else:
        TARGETS[target]()


if __name__ == "__main__":
    main()
