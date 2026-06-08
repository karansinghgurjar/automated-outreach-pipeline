"""Logging helpers."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logger(name: str, log_path: Path, level: str = "INFO") -> logging.Logger:
    """Create a file-backed logger for pipeline audit logs."""
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
