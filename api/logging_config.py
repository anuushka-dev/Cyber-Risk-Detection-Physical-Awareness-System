# api/logging_config.py

import logging
import sys

from .config import LOG_LEVEL

try:
    from pythonjsonlogger import jsonlogger
except Exception:
    jsonlogger = None


def setup_logging():

    log_handler = logging.StreamHandler(sys.stdout)

    if jsonlogger:

        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z"
        )

    else:

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

    log_handler.setFormatter(formatter)

    logger = logging.getLogger("ids_api")

    logger.setLevel(LOG_LEVEL)

    if not logger.handlers:
        logger.addHandler(log_handler)

    logger.propagate = False

    return logger


logger = setup_logging()