"""Initializes bots and databases required by tests in this folder"""

import datetime as dt
import os

import pytest

from nmnh_ms_tools.bots import (
    AdamancerBot,
    GeoGalleryBot,
    GeoNamesBot,
    GNRDBot,
    ITISBot,
    MacrostratBot,
    MetBullBot,
    PLSSBot,
    xDDBot,
)
from nmnh_ms_tools.config import TEST_DIR
from nmnh_ms_tools.databases.helpers import from_csv
from nmnh_ms_tools.databases.admin import (
    Session as AdminSession,
    AdminNames,
    init_db as init_admin_db,
)
from nmnh_ms_tools.databases.custom import (
    CustomFeatures,
    init_db as init_custom_db,
)
from nmnh_ms_tools.databases.geonames import (
    GeoNamesFeatures,
    init_db as init_geonames_db,
)
from nmnh_ms_tools.databases.geohelper import (
    Session as GeoHelperSession,
    init_db as init_geohelper_db,
    AlternativePolygons,
    OceanTiles,
    PreferredLocalities,
)
from nmnh_ms_tools.databases.georef_job import init_db as init_georef_job_db

start = dt.datetime.now()

# Initialize helper database
init_geohelper_db(":memory:")
from_csv(
    GeoHelperSession,
    AlternativePolygons,
    os.path.join(TEST_DIR, "db_alt_polygons.csv"),
    comment="#",
)
from_csv(
    GeoHelperSession,
    OceanTiles,
    os.path.join(TEST_DIR, "db_oceans.csv"),
    comment="#",
)
from_csv(
    GeoHelperSession,
    PreferredLocalities,
    os.path.join(TEST_DIR, "db_preferred.csv"),
    comment="#",
)

# Initialize geonames feature database
init_geonames_db(":memory:")
geonames_db = GeoNamesFeatures()
geonames_db.keys = None
geonames_db.delim = "|"
geonames_db.csv_kwargs = {"dialect": "excel"}
geonames_db.from_csv(os.path.join(TEST_DIR, "db_geonames.csv"))

# Initialize admin feature database
init_admin_db(":memory:")
from_csv(
    AdminSession,
    AdminNames,
    os.path.join(TEST_DIR, "db_admin.csv"),
    comment="#",
    dtype=str,
)

# Initialize custom feature database
init_custom_db(":memory:")
CustomFeatures().from_csv(os.path.join(TEST_DIR, "db_custom.csv"))

# Initialize georeferencing database
init_georef_job_db(":memory:")


@pytest.fixture(scope="session")
def adamancerbot():
    bot = AdamancerBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def geogallerybot():
    bot = GeoGalleryBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def geonamesbot():
    bot = GeoNamesBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def gnrdbot():
    bot = GNRDBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def itisbot():
    bot = ITISBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def macrostratbot():
    bot = MacrostratBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def metbullbot():
    bot = MetBullBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def plssbot():
    bot = PLSSBot()
    bot.install_cache("bot.sqlite")
    return bot


@pytest.fixture(scope="session")
def xddbot():
    bot = xDDBot()
    bot.install_cache("bot.sqlite")
    return bot
