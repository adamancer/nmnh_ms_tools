"""Defines class for caching results from GeoNames matching"""

import json

from ....databases.cache import CacheDict
from ....databases.geonames import GeoNamesFeatures


class RecordCache(CacheDict):
    """Caches list of sites matching a query"""

    local = GeoNamesFeatures()

    def __init__(self, path=None):
        super(RecordCache, self).__init__()
        if path is not None:
            self.init_db(path)

    @staticmethod
    def writer(vals):
        """Stores sites as lists of integers and filters"""
        if not vals:
            return None
        assert isinstance(vals, list), "must be a list"
        try:
            loc_ids = [int(r.location_id) for r in vals]
        except TypeError:
            raise ValueError("location_id must be an integer")
        filters = [r.filter for r in vals]
        return json.dumps([loc_ids, filters])

    @staticmethod
    def reader(row):
        """Reinflates sites from location_id"""
        from ....records import Site  # lazy load to avoid import conflict

        if row.val is None:
            return []
        loc_ids, fltrs = json.loads(row.val)
        records = RecordCache.local.get_many(loc_ids)
        sites = [Site(rec) for rec in records]
        for site, fltr in zip(sites, fltrs):
            site.filter = fltr
            site.from_cache = True
        return sites
