"""Structured logging configuration for SmartScrapeV8."""

from __future__ import annotations

import logging
import sys


_CONFIGURED = False

LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(verbose: bool = False) -> None:
    """Configure root logger with console handler.

    Call once at application startup.  Subsequent calls are no-ops so that
    library code that defensively calls this does not clobber the config.
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level = logging.DEBUG if verbose else logging.INFO

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root = logging.getLogger("smart_scrape")
    root.setLevel(level)
    root.addHandler(console_handler)
    # Prevent duplicate output if the root logger already has handlers.
    root.propagate = False
