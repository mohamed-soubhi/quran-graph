"""Tests for logging configuration (T0.6)."""

import logging
from pathlib import Path
from src.log import get_logger

ROOT = Path(__file__).resolve().parent.parent


def test_get_logger_creates_handlers_and_file(tmp_path):
    test_name = "test_module_logger"
    logger = get_logger(test_name)

    assert isinstance(logger, logging.Logger)
    assert logger.name == test_name
    assert len(logger.handlers) == 2

    handler_types = {type(h) for h in logger.handlers}
    assert logging.FileHandler in handler_types
    assert logging.StreamHandler in handler_types

    log_path = ROOT / "logs" / f"{test_name}.log"
    assert log_path.exists()

    # Log a message and verify it is written to the file
    msg = "Test log entry with Arabic: الحمد لله"
    logger.info(msg)

    # Flush handlers
    for h in logger.handlers:
        h.flush()

    content = log_path.read_text(encoding="utf-8")
    assert msg in content


def test_get_logger_idempotent():
    logger1 = get_logger("idempotent_test")
    handler_count = len(logger1.handlers)
    logger2 = get_logger("idempotent_test")
    assert logger1 is logger2
    assert len(logger2.handlers) == handler_count
