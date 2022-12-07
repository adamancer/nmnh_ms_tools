"""Defines class to match feature names to custom locality records"""
import logging
logger = logging.getLogger(__name__)

import csv
import pickle
import os

from .core import Georeference
from .match_geonames import MatchGeoNames
from ....databases.custom import CustomFeatures, init_db




class MatchCustom(MatchGeoNames):
    """Matches feature names to custom locality records"""
    cache = {}

    def __init__(self, fp=None, url_mask=None, **kwargs):
        super(MatchCustom, self).__init__(**kwargs)
        if fp:
            init_db(fp)
        self.url_mask = url_mask
        self.use_cache = False
        self.use_local = True
        self.local = CustomFeatures()


    def get_preferred(self, name):
        return


    @staticmethod
    def enable_sqlite_cache(path=None):
        MatchCustom.cache = RecordCache(path)
