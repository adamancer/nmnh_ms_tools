"""Defines global configuration for package"""

from .. import _ImportClock

with _ImportClock("config"):
    from .config import CONFIG, CONFIG_DIR, DATA_DIR, GEOCONFIG, TEST_DIR
    from .downloader import download
