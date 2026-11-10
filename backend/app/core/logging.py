"""Consistently formatted logging.

What we log: request lifecycle, domain events (conversation created,
message received, ticket created, status changed), unexpected errors.
What we never log: API keys, secrets, full contact details, prompts.
"""

import logging
import sys

from app.core.config import get_settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. tests)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
