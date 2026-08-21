from __future__ import annotations

import logging
import sys


_LOGGING_CONFIGURED = False


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure a simple process-wide logger once."""

    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger."""

    configure_logging()
    return logging.getLogger(name)
