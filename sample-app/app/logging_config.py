"""Structured JSON logging configuration."""

import logging
import sys

from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured JSON logging to stdout."""
    logger = logging.getLogger("sample_app")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "timestamp"},
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
