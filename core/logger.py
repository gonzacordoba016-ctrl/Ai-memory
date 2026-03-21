# core/logger.py

import logging
from core.config import LOG_LEVEL

def setup_logger():

    logger = logging.getLogger("ai_agent")

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    logger.setLevel(level)

    if not logger.handlers:

        handler = logging.StreamHandler()

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            "%H:%M:%S"
        )

        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


logger = setup_logger()