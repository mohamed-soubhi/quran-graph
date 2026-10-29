"""Task runner replacing Makefile for the project.

Targets: up, down, test, smoke
"""

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
    return sys.executable


def run_test(args=None) -> None:
    """Run pytest suite using venv Python."""
    py = get_venv_python()
    cmd = [py, "-m", "pytest"]
    if args:
        cmd.extend(args)
    res = subprocess.run(cmd, cwd=ROOT)
    sys.exit(res.returncode)


def run_up() -> None:
    print("not implemented yet")


def run_down() -> None:
    print("not implemented yet")


def run_smoke() -> None:
    print("not implemented yet")


TARGETS = {
    "test": run_test,
    "up": run_up,
    "down": run_down,
    "smoke": run_smoke,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        print(f"Usage: python scripts/tasks.py <{'|'.join(TARGETS.keys())}>")
        sys.exit(1)

    target = sys.argv[1]
    extra_args = sys.argv[2:]
    if target == "test":
        TARGETS[target](extra_args)
    else:
        TARGETS[target]()


if __name__ == "__main__":
    main()
