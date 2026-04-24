# core/logger.py

import logging
from core.config import LOG_LEVEL


def setup_logger():
    """
    Configure the root logger so every child logger (get_logger(__name__))
    inherits the same handler and formatter via propagation.
    Returns the 'ai_agent' logger for backward-compatibility with
    `from core.logger import logger` imports across the codebase.
    """
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            "%H:%M:%S",
        ))
        root.addHandler(handler)

    # Named logger kept for modules that import it directly
    named = logging.getLogger("ai_agent")
    named.setLevel(level)
    return named


def get_logger(name: str = "ai_agent") -> logging.Logger:
    """Return a named logger. Inherits root handler/formatter via propagation."""
    return logging.getLogger(name)


logger = setup_logger()
