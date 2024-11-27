"""Tests geographic name parsers"""

import pytest

from nmnh_ms_tools.databases.geonames import (
    GeoNamesFeatures,
    AllCountries,
    to_geonames_api,
)
from nmnh_ms_tools.records import Site
from nmnh_ms_tools.tools.geographic_names.caches import (
    LocalityCache,
    RecordCache,
)
from nmnh_ms_tools.tools.geographic_names.parsers.simple import SimpleParser


def test_locality_cache():
    cache = LocalityCache(":memory:")
    cache.max_recent = 5
    records = []
    for i in range(0, 10):
        records.append(([SimpleParser("Fake Name")], "leftovers {}".format(i)))
    # Separating set/get item allows max_recent to kick in
    for i, rec in enumerate(records):
        cache[i] = rec
    for i, rec in enumerate(records):
        assert cache[i] == rec


# @pytest.mark.skip("Does not restore records correctly")
def test_record_cache():
    cache = RecordCache(":memory:")
    cache.max_recent = 5
    # Use the geonames test data to guarantee that sites exist
    records = []
    for row in GeoNamesFeatures().session.query(AllCountries).limit(10):
        rec = Site(to_geonames_api(row))
        rec.filter = {"name": "fake site {}".format(row.geoname_id)}
        records.append([rec])
    # Separating set/get item allows max_recent to kick in
    for i, rec in enumerate(records):
        cache[i] = rec
    from nmnh_ms_tools.utils import get_attrs

    import pandas as pd
    from shapely.geometry.base import BaseGeometry

    for i, rec in enumerate(records):
        for inst, other in zip(rec, cache[i]):
            assert inst == other
