import csv
import logging
import os

from .database import Base, Session, AllCustom, AlternateNames
from ..geonames import GeoNamesFeatures
from ...config import DATA_DIR
from ...records import Site
from ...utils import as_str, skip_hashed, to_attribute


logger = logging.getLogger(__name__)


class CustomFeatures(GeoNamesFeatures):
    """Fills and searches a SQLite db based on the user-provided gazetteers"""

    def __init__(self):
        super(CustomFeatures, self).__init__()
        self.features = AllCustom
        self.names = AlternateNames
        self.base = Base
        self.session = Session
        self.keys = None  # overrides attribute in base class
        self.csv_kwargs = {"dialect": "excel"}
        self.delim = "|"

    def mapper(self, rowdict, reverse=False):
        """Maps dict to format used by GeoNames"""
        keymap = {
            "location_id": "geonameId",
            "continent": "continentCode",
            "country": "countryName",
            "state_province": "adminName1",
            "county": "adminName2",
            "country_code": "countryCode",
            "admin_code_1": "adminCode1",
            "admin_code_2": "adminCode2",
            "footprint_wkt": "bbox",
            "verbatim_latitude": "lat",
            "verbatim_longitude": "lng",
            "site_names": "name",
            "site_kind": "fcode",
            "synonyms": "alternateNames",
            # The keys below are not part of the GeoNames API
            "site_source": "source",
            "url": "_url",
        }
        if reverse:
            keymap = {v: k for k, v in keymap.items()}
            rowdict = {keymap[k]: v for k, v in rowdict.items() if k in keymap}
            synonyms = [s["name"] for s in rowdict["synonyms"]]
            rowdict["synonyms"] = as_str(synonyms)
            return rowdict
        site = Site(rowdict)
        site.map_admin_from_names()
        sitedict = site.to_dict()
        row = {}
        for src_key, gn_key in keymap.items():
            try:
                if sitedict[src_key]:
                    row[gn_key] = as_str(sitedict[src_key])
            except KeyError:
                pass
        # Manually map the url attribute, which does not show up in attributes
        row["url"] = site.url if site.url else None
        # Namespace the identifier based on the source field
        source = to_attribute(row["source"])
        try:
            row["alternateNames"] = row["alternateNames"].replace(" | ", ",")
        except KeyError:
            pass
        return {to_attribute(k): v for k, v in row.items()}

    def from_csv(self, fp):
        """Reads custom features into database from file"""
        # Clear existing records from the sources represented by this file
        sources = []
        with open(fp, "r", encoding="utf-8-sig", newline="") as f:
            rows = csv.reader(skip_hashed(f), dialect="excel")
            keys = next(rows)
            for row in rows:
                rowdict = dict(zip(keys, row))
                assert rowdict["site_source"]
                sources.append(rowdict["site_source"])
        for source in set(sources):
            self.delete_existing_records(source)
        return super(CustomFeatures, self).from_csv(fp, delete_existing=False)

    def fill_record(self, *args, **kwargs):
        raise NotImplementedError

    def from_included_gazetteer(self, source):
        """Loads data from one of the included gazetteers"""
        gazetteers = {
            "GVP": "global_volcanism_program_volcanoes.csv",
            #'MRDS': 'usgs_mineral_resources_data_system_mines.csv'
        }
        try:
            fn = gazetteers[source]
        except KeyError:
            raise KeyError("Name must be one of {}".format(list(gazetteers)))
        self.from_csv(os.path.join(DATA_DIR, "gazetteers", fn))
