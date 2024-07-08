"""Defines null handler for module"""

import datetime as dt
import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class _ImportClock:
    """Defines the context manager used to clock snippets"""

    def __init__(self, name):
        self.name = name
        self.start = None

    def __enter__(self):
        logger.debug(f"Started importing {self.name}")
        self.start = dt.datetime.now()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = dt.datetime.now() - self.start
        logger.debug(f"Finished importing {self.name} (t={elapsed})")
