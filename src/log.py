"""Logging configuration for project modules (T0.6)."""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a logger configured with console and file handlers.

    Logs to logs/<name>.log and the console. One logger per module.
    """
    LOGS_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        safe_name = name.replace("/", "_").replace("\\", "_")
        log_file = LOGS_DIR / f"{safe_name}.log"

        formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(name)s: %(message)s")

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        logger.propagate = False

    return logger
