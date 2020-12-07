"""Initializes databases required by tests in this folder"""
import os

from nmnh_ms_tools.bots import Bot
from nmnh_ms_tools.config import DATA_DIR, TEST_DIR
from nmnh_ms_tools.databases.admin import (
    AdminFeatures,
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
from nmnh_ms_tools.databases.georef_data import init_db as init_georef_data_db
from nmnh_ms_tools.databases.georef_job import init_db as init_georef_job_db



import datetime as dt
start = dt.datetime.now()
# Cache queries from bots
Bot.install_cache()

# Initialize geonames feature database
init_geonames_db(':memory')
geonames_db = GeoNamesFeatures()
geonames_db.keys = None
geonames_db.delim = '|'
geonames_db.csv_kwargs = {'dialect': 'excel'}
geonames_db.from_csv(os.path.join(TEST_DIR, 'test_geonames.csv'))

# Initialize admin feature database
init_admin_db(':memory')
admin_db = AdminFeatures()
admin_db.keys = None
admin_db.delim = '|'
admin_db.csv_kwargs = {'dialect': 'excel'}
admin_db.from_csv(os.path.join(TEST_DIR, 'test_geonames.csv'))

# Initialize custom feature database
init_custom_db(':memory')
CustomFeatures().from_csv(os.path.join(TEST_DIR, 'test_custom.csv'))

# Initialize georeferencing databases
init_georef_data_db(os.path.join(DATA_DIR, 'downloads', 'georef_data.sqlite'))
init_georef_job_db(':memory')
