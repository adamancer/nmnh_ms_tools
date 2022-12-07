import csv
import datetime as dt
import json
import logging
import os
import re
from collections import OrderedDict

from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import Index

from .database import Base, Session, AdminNames, AdminThesaurus
from ..cache import CacheDict
from ..geonames import GeoNamesFeatures
from ...config import DATA_DIR
from ...utils import (
    LocStandardizer,
    as_list,
    as_str,
    combine,
    dedupe,
    dictify,
    skip_hashed,
    std_names,
    to_attribute,
)


logger = logging.getLogger(__name__)


class AdminCache(CacheDict):
    @staticmethod
    def keyer(key):
        names, kind, admin = key
        admin = {k: v for k, v in admin.items() if k}
        return json.dumps([names, kind, admin], sort_keys=True).lower()


class AdminFeatures(GeoNamesFeatures):
    """Fills and searches a SQLite db based on the user-provided gazetteers"""

    cache = AdminCache()

    def __init__(self):
        super().__init__()
        self.names = AdminNames
        # self.names = self.names
        self.base = Base
        self.session = Session
        self.keys = [
            "geoname_id",
            "name",
            "ascii_name",
            "alternate_names",
            "lat",
            "lng",
            "fcl",
            "fcode",
            "country_code",
            "cc2",
            "admin_code_1",
            "admin_code_2",
            "admin_code_3",
            "admin_code_4",
            "population",
            "elevation",
            "dem",
            "timezone",
            "mod_date",
        ]
        self.csv_kwargs = {"delimiter": "\t", "quotechar": '"'}
        self.delim = ","
        self.code_fields = ["country_code", "admin_code_1", "admin_code_2"]
        self.name_fields = ["country", "state_province", "county"]
        self.fields = self.name_fields + self.code_fields
        self.kinds = OrderedDict(
            [
                ("country", "country_code"),
                ("state_province", "admin_code_1"),
                ("county", "admin_code_2"),
            ]
        )
        self.update_thesaurus = True
        self._std = LocStandardizer()

    def std(self, val):
        return val if val.isnumeric() else self._std.std_admin(val)

    def std_names(self, names, std_func=None):
        return std_names(names, std_func=std_func if std_func else self.std)

    def get(self, *args, **kwargs):
        return self.get_admin(*args, **kwargs)

    def get_admin(self, country, state_province=None, county=None, **kwargs):
        if not country:
            raise ValueError("country is required")

        if county and not state_province:
            raise ValueError("state_province is required when resolving a county")

        result = {}
        # Get country info
        resolved = self.resolve_admin(country, "country")
        for key, vals in resolved.items():
            result.setdefault(key, []).extend(vals)
        # Get state_province/province info
        if state_province and "state_province" in result:
            logger.warning("state_province from thesaurus supersedes kwarg")
        elif state_province:
            resolved = self.resolve_admin(state_province, "state_province", **result)
            for key, vals in resolved.items():
                result.setdefault(key, []).extend(vals)
        # Get county info
        if county and "county" in result:
            logger.warning("county from thesaurus supersedes kwarg")
        elif county:
            resolved = self.resolve_admin(county, "county", **result)
            for key, vals in resolved.items():
                result.setdefault(key, []).extend(vals)
        result.update(kwargs)
        result = {k: dedupe(v) for k, v in result.items()}
        # Remove the 00 state/province code that GeoNames provides for countries
        try:
            result["admin_code_1"] = [c for c in result["admin_code_1"] if c != "00"]
        except KeyError:
            pass
        return result

    def resolve_admin(self, names, kind, **admin):
        assert names, "no names provided"
        try:
            return self.cache[(names, kind, admin)]
        except KeyError:
            pass
        # Do not map names that indicate uncertainty
        if "?" in str(names):
            raise ValueError("Names uncertain: {}".format(names))
        rows = self._query(names, kind, **admin)
        unresolved = self.unresolved(names, kind, rows)
        if unresolved:
            args = []
            keys = ["country", "state_province", "county"]
            for key in keys:
                args.append(admin.get(key, []))
            i = keys.index(kind)
            if not args[i]:
                args[i] = unresolved
                while not args[-1]:
                    args = args[:-1]
                admin.update(self.map_deprecated(*args))
                return self.get_admin(**admin)
            raise ValueError("{}={} superseded by thesaurus".format(kind, unresolved))
        resolved = combine(*[dictify(r) for r in rows])
        # Make result specific to the current division type
        resolved[kind] = resolved["name"]
        del resolved["name"]
        del resolved["st_name"]
        self.cache[(names, kind, admin)] = resolved
        return resolved

    def get_admin_codes(self, *args, **kwargs):
        admin = self.get_admin(*args, **kwargs)
        return {k: v for k, v in admin.items() if k in self.code_fields}

    def get_admin_names(self, *args, **kwargs):
        admin = self.get_admin(*args, **kwargs)
        return {k: v for k, v in admin.items() if k in self.name_fields}

    def unresolved(self, names, kind, rows):
        """Finds unresolved names"""
        names = as_list(names)
        st_names = self.std_names(names)
        name_map = dict(zip(st_names, names))
        resolved = []
        for row in rows:
            for attr in ("st_name", self.kinds[kind]):
                val = self.std(getattr(row, attr))
                if val in name_map:
                    resolved.append(val)
                    break
        return sorted([name_map[k] for k in st_names - set(resolved)])

    def remove_unwanted_names(self):
        """Removes synonyms that confuse matching

        See the corresponding function in the parent class for more info
        about the rationale behind this function. A query to find records to
        research for the unwanted synonym list is:

        SELECT * FROM admin_names
        WHERE
        (name like "North %" AND st_name = substr(name, length("North ") + 1))
            OR (name like "South %" AND st_name = substr(name, length("South ") + 1))
            OR (name like "East %" AND st_name = substr(name, length("East ") + 1))
            OR (name like "West %" AND st_name = substr(name, length("West ") + 1))
        """
        session = self.session()
        for geoname_id, st_name in self.unwanted_names.items():
            for row in session.query(self.names).filter(
                self.names.geoname_id == geoname_id, self.names.st_name == st_name
            ):
                session.delete(row)
        session.commit()
        session.close()

    def remove_geoname_ids(self, geoname_ids):
        """Removes list of GeoNames features from the database"""
        session = self.session()
        session.query(self.names).filter(
            self.names.geoname_id.in_(geoname_ids)
        ).delete()
        session.commit()
        session.close()

    def map_deprecated(self, country, state_province=None, county=None):
        vals = [dedupe(as_list(n)) for n in [country, state_province, county]]
        fltr = []
        vals = []
        mapping = {}
        update_key = "county"
        for key, names in (
            ("country", country),
            ("state_province", state_province),
            ("county", county),
        ):
            names = dedupe(as_list(names))
            if names:
                update_key = key
                mapping[key] = names
            field = getattr(AdminThesaurus, key)
            fltr.append(field.in_(names) if names else field == None)
            vals.append(names)
        session = self.session()
        rows = session.query(AdminThesaurus).filter(*fltr).all()
        mappings = []
        for row in rows:
            try:
                obj = json.loads(row.mapping)
            except TypeError:
                raise ValueError("{} resolves to empty mapping".format(vals))
            except json.decoder.JSONDecodeError:
                obj = {update_key: row.mapping}
            else:
                if not isinstance(obj, dict):
                    obj = {update_key: obj}
            mappings.append(obj)
        if not mappings:
            vals = [dedupe(as_list(n)) for n in [country, state_province, county]]
            while not vals[-1]:
                vals = vals[:-1]
            # Exclude amibiguous names like multiple states/multiple counties
            if self.update_thesaurus and not any([len(s) > 1 for s in vals[:-1]]):
                vals = [s[0].title().replace("'S", "'s") if s else None for s in vals]
                session.add(AdminThesaurus(**dict(zip(self.name_fields, vals))))
                session.commit()
            raise ValueError("{} does not resolve".format(vals))
        session.close()
        mapping.update(combine(*mappings))
        # Check if mapping points to another row in the thesaurus
        update_thesaurus = self.update_thesaurus
        self.update_thesaurus = False
        try:
            remapping = self.map_deprecated(**mapping)
            while mapping != remapping:
                mapping = remapping
        except (IndexError, TypeError, ValueError):
            pass
        self.update_thesaurus = update_thesaurus
        return mapping

    def delete_unmapped_synonyms(self):
        """Deletes thesaurus records that haven't been mapped"""
        update_thesaurus = self.update_thesaurus
        self.update_thesaurus = False
        session = self.session()
        for i, row in enumerate(session.query(AdminThesaurus)):
            if not row.mapping:
                session.delete(row)
        session.commit()
        session.close()
        self.update_thesaurus = update_thesaurus

    def delete_mappable_synonyms(self):
        """Deletes thesaurus records that can be mapped to known admin divs"""

        def disable_map_deprecated(*args, **kwargs):
            raise ValueError("map_deprecated disabled")

        update_thesaurus = self.update_thesaurus
        self.update_thesaurus = False
        admin = AdminFeatures()
        self.update_thesaurus = False
        self.map_deprecated = disable_map_deprecated
        session = self.session()
        for i, row in enumerate(session.query(AdminThesaurus)):
            divs = [d for d in [row.country, row.state_province, row.county] if d]
            try:
                self.get_admin(*divs)
            except ValueError:
                pass  # print(divs, 'does not resolve')
            else:
                session.delete(row)
            if i and not i % 100:
                logger.debug("{} records checked".format(i))
                # break
        session.commit()
        session.close()
        self.update_thesaurus = update_thesaurus

    def verify_mapped(self):
        """Verifies that mapped thesaurus records resolve to a known admin div"""
        update_thesaurus = self.update_thesaurus
        self.update_thesaurus = False
        session = self.session()
        rows = (
            session.query(AdminThesaurus)
            .filter(AdminThesaurus.mapping != None, AdminThesaurus.id == 197)
            .order_by(AdminThesaurus.id)
        )
        for i, row in enumerate(rows):
            vals = [row.country, row.state_province, row.county]
            mapping = self.map_deprecated(*vals)
            admin = {k: v for k, v in mapping.items() if k in self.name_fields}
            if admin["country"]:
                try:
                    self.get_admin(**admin)
                except ValueError:
                    raise
                    print("Failed to map {}".format(admin))
        session.close()
        self.update_thesaurus = update_thesaurus

    def from_csv(self, fp):
        """Fills the database from the GeoNames text dump file"""
        session = self.session()
        self.delete_existing_records()
        # Read data into tables
        start = dt.datetime.now()
        with open(fp, "r", encoding="utf-8-sig", newline="") as f:
            rows = csv.reader(skip_hashed(f), **self.csv_kwargs)
            # Get keys if not set manually
            if self.keys is None:
                keys = next(rows)
            else:
                keys = [k for k in self.keys if k != "continent_code"]
            # Import data
            features = []
            for i, row in enumerate(rows):
                if i and not i % 100000:
                    logger.debug("{:,} records processed".format(i))
                rowdict = {k: v if v else None for k, v in zip(keys, row)}
                if rowdict["fcl"] != "A":
                    continue
                rowdict = self.mapper(rowdict)
                # The GeoNames dump doesn't provide an easy way to get the short
                # country name, so pull that from elsewhere
                rowdict = self.assign_short_country_name(rowdict)
                # Extract names from the original rowdict
                names = self.get_names(self.finalize_names(rowdict))
                # Add features
                cols = self.names.__table__.columns
                feature = {k: v for k, v in rowdict.items() if k in cols}
                for st_name in set(self.std_names(names)):
                    alt_feature = feature.copy()
                    alt_feature["st_name"] = st_name
                    features.append(alt_feature)
                if len(features) >= 10000:
                    td = dt.datetime.now() - start
                    mask = "{:,} admins processed (t={}s)"
                    logger.debug(mask.format(len(features), td))
                    session.bulk_insert_mappings(self.names, features)
                    session.commit()
                    features = []
                    start = dt.datetime.now()
                    # break
            # Add remaining features
            logger.debug("{:,} records processed".format(i))
            session.bulk_insert_mappings(self.names, features)
            session.commit()
            session.close()
        self.remove_unwanted_names()
        self.index_names()
        return self

    def delete_existing_records(self):
        session = self.session()
        session.query(self.names).delete(synchronize_session=False)
        session.commit()

    def index_names(self, create=True, drop=True):
        """Builds or rebuilds indexes"""
        if create and not drop:
            drop = True
        for index in [
            Index(
                "idx_admin_divs",
                self.names.country_code,
                self.names.admin_code_1,
                self.names.admin_code_2,
            ),
            Index("idx_names", self.names.st_name),
            Index(
                "idx_thesaurus",
                AdminThesaurus.mapping,
                AdminThesaurus.country,
                AdminThesaurus.state_province,
                AdminThesaurus.county,
            ),
        ]:
            if drop:
                try:
                    index.drop(bind=self.base.metadata.bind)
                    logger.debug("Dropped index '%s'" % index.name)
                except OperationalError as e:
                    pass
            if create:
                try:
                    index.create(bind=self.base.metadata.bind)
                    logger.debug("Created index '%s'" % index.name)
                except OperationalError:
                    logger.debug("Failed to create index '%s'" % index.name)

    def _query(self, names, kind, is_name=True, **admin):
        fcodes = {
            "country": ["PCL", "PCLD", "PCLF", "PCLH", "PCLI", "PCLIX", "PCLS", "TERR"],
            "state_province": ["ADM1"],
            "county": ["ADM2"],
        }
        names = as_list(names)
        st_names = self.std_names(names)
        code_fld = getattr(self.names, self.kinds[kind])
        fltr = [self.names.fcode.in_(fcodes[kind])]
        # FIXME: The following two statements would ideally be combined with OR, but
        # I can't get an index for that combination to work. Until I work that out,
        # splitting the queries is faster.
        if is_name:
            fltr.append(self.names.st_name.in_(st_names))
        else:
            fltr.append(code_fld.in_(names))
        limit = len(names)
        for name, code in self.kinds.items():
            field = getattr(self.names, code)
            try:
                vals = as_list(admin[code])
            except KeyError:
                pass  # fltr.append(field == None)
            else:
                fltr.append(field.in_(vals))
                limit *= len(vals)
        session = self.session()
        result = (
            session.query(self.names.name, self.names.st_name, code_fld)
            .distinct()
            .filter(*fltr)
            .limit(limit)
            .all()
        )
        session.close()
        if is_name and not result:
            return self._query(names, kind, is_name=False, **admin)
        return result
