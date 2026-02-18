"""
Centralised logging configuration for Financial Mapper.

Every module obtains its logger via ``get_logger(__name__)``.
The pipeline calls ``configure_logging`` once at startup so that all
downstream loggers share the same handler, format, and level.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


_CONFIGURED = False

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> None:
    """Set up root logger for the ``financial_mapper`` namespace.

    Parameters
    ----------
    level:
        Minimum severity to emit.
    log_file:
        If provided, a ``FileHandler`` is added alongside the console handler.
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    root = logging.getLogger("financial_mapper")
    root.setLevel(level)
    root.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``financial_mapper`` namespace."""
    return logging.getLogger(f"financial_mapper.{name}")
