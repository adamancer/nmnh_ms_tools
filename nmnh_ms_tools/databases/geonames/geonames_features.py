"""Defines helper functions for the GeoNames SQLite table"""
import csv
import datetime as dt
import json
import logging
import os
import re

from requests.structures import CaseInsensitiveDict
from shapely import wkt
from sqlalchemy import case, func, or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import Index

from .database import (
    Base,
    Session,
    AllCountries,
    AlternateNames,
)
from ...config import DATA_DIR
from ...utils.standardizers import LocStandardizer
from ...utils import (
    as_list,
    as_str,
    dedupe,
    dictify,
    skip_hashed,
    std_names,
    to_attribute,
    to_camel,
)


logger = logging.getLogger(__name__)


class GeoNamesFeatures:
    """Fills and searches a SQLite db based on the GeoNames text dump file"""

    std = LocStandardizer()

    def __init__(self):
        self.features = AllCountries
        self.names = AlternateNames
        self.base = Base
        self.session = Session
        self.batch_size = 100000
        self.keys = [
            "geoname_id",
            "name",
            "ascii_name",
            "alternate_names",
            "lat",
            "lng",
            "fcl",
            "fcode",
            "continent_code",  # not part of the GeoNames dump
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
        # List of geonameid-st_name pairs that should be removed
        self.unwanted_names = {
            3358844: "atlantic-ocean",
            4597040: "carolina",
            5769223: "dakota",
        }

    def __getattr__(self, attr):
        if attr in [
            "continent_code_to_name",
            "continent_name_to_code",
            "country_code_to_name",
            "country_code_to_continent",
            "country_name_to_code",
        ]:
            self._load_continents()
            self._load_countries()
            return getattr(self, attr)
        mask = "'{}' object has no attribute '{}'"
        raise AttributeError(mask.format(self.__class__.__name__, attr))

    def mapper(self, rowdict, reverse=False):
        """Maps dictionary to GeoNames schema"""
        mapped = {}
        if reverse:
            mapped = {to_camel(k): v for k, v in rowdict.items()}
            synonyms = [s["name"] for s in mapped["alternateNames"]]
            mapped["alternateNames"] = as_str(synonyms)
        else:
            mapped = {to_attribute(k): v for k, v in rowdict.items()}
        return mapped

    def prep_id(self, key):
        """Prepares an identifier for a search against the database"""
        try:
            return int(key)
        except ValueError:
            return key

    def std_names(self, names, std_func=None):
        return std_names(names, std_func=std_func if std_func else self.std)

    def get_json(self, geoname_id):
        """Retrieves the feature matching a GeoName ID"""
        geoname_id = self.prep_id(geoname_id)
        session = self.session()
        row = (
            session.query(self.features)
            .filter_by(geoname_id=geoname_id)
            .limit(1)
            .first()
        )
        if not (row.bbox or row.country_name or row.ocean):
            try:
                row = self.fill_record(row, session=session)
            except NotImplementedError:
                # Subclasses should raise this error
                pass
        session.close()
        return to_geonames_api(row)

    def get_many(self, geoname_ids):
        """Retrieves features matchinng a list of GeoNames IDs"""
        geoname_ids = [self.prep_id(gid) for gid in geoname_ids]
        session = self.session()
        rows = (
            session.query(self.features)
            .filter(self.features.geoname_id.in_(geoname_ids))
            .limit(len(geoname_ids))
        )
        session.close()
        return to_geonames_api(rows)

    def search_json(self, st_name, limit=100, **kwargs):
        """Searches for a feature by name"""
        logger.debug(f"Searching for {st_name} ({kwargs})")
        session = self.session()
        # Map kwargs used by the GeoNames webservice to those needed here
        kwarg_map = {
            "adminCode1": "admin_code_1",
            "adminCode2": "admin_code_2",
            "continentCode": "continent_code",
            "country": "country_code",
            "featureClass": "fcl",
            "featureCode": "fcode",
        }
        # Define sort order
        whens = {k: i + 1 for i, k in enumerate("APHLTVSRU")}
        whens[None] = len(whens)
        sort_order = case(value=self.names.fcl, whens=whens)
        # Build search filter
        if not re.match(r"^[-a-z0-9]$", st_name):
            try:
                st_name = self.std(st_name)
            except ValueError:
                return []
        names = set([n for n in [st_name, st_name.replace("-", "")] if n])
        if not names:
            return []
        fltr = [self.names.st_name.in_(names)]
        for key, val in kwargs.items():
            if val:
                db_field = getattr(self.names, kwarg_map.get(key, key))
                if isinstance(val, (list, tuple)):
                    fltr.append(db_field.in_(val))
                else:
                    fltr.append(db_field == val)
        query = (
            session.query(self.features)
            .join(self.names)
            .filter(*fltr)
            .order_by(sort_order)
            .limit(limit)
        )
        # from ..helpers import time_query
        # time_query(query)
        results = list(query)
        # Extend result with a like query if too few results found
        if len(results) < limit and len(st_name) >= 3:
            fltr[0] = or_(
                self.names.st_name.like(st_name + "%"),
                self.names.st_name_rev.like(st_name[::-1] + "%"),
            )
            query = (
                session.query(self.features)
                .join(self.names)
                .filter(*fltr)
                .order_by(sort_order)
                .limit(limit - len(results))
            )
            # from ..helpers import time_query
            # time_query(query)
            results.extend(query)
        session.close()
        logger.debug(f"Search complete")
        return to_geonames_api(dedupe(results))

    def from_csv(self, fp, delete_existing=True):
        """Fills the database from the GeoNames text dump file"""
        session = self.session()
        if delete_existing:
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
            alt_names = []
            for i, row in enumerate(rows):
                rowdict = {k: v if v else None for k, v in zip(keys, row)}
                rowdict = self.mapper(rowdict)

                # Check for multiple names in main name field
                if self.delim in rowdict["name"]:
                    names = [s.strip() for s in rowdict["name"].split(self.delim)]
                    rowdict["name"] = names[0]
                    assert not rowdict.get("alternate_names")
                    rowdict["alternate_names"] = self.delim.join(names[1:])

                rowdict = self.assign_short_country_name(rowdict)
                rowdict = self.finalize_names(rowdict)

                # Add features
                cols = self.features.__table__.columns
                feature = {k: v for k, v in rowdict.items() if k in cols}
                try:
                    country_code = feature["country_code"]
                    continent_code = self.get_continent(country_code, False)
                    feature["continent_code"] = continent_code
                except (AttributeError, KeyError):
                    pass
                features.append(feature)

                alt_names.extend(self.map_alt_names(rowdict))
                if i and not i % 10000:
                    td = dt.datetime.now() - start
                    logger.debug("{:,} records processed (t={}s)".format(i, td))
                    session.bulk_insert_mappings(self.features, features)
                    session.bulk_insert_mappings(self.names, alt_names)
                    session.commit()
                    features = []
                    alt_names = []
                    start = dt.datetime.now()
                    # break
                elif i and not i % 5000:
                    logger.debug("{:,} records processed".format(i))

            # Add remaining features
            logger.debug("{:,} records processed".format(i))
            session.bulk_insert_mappings(self.features, features)
            session.bulk_insert_mappings(self.names, alt_names)
            session.commit()
            session.close()

        self.remove_unwanted_names()
        self.create_indexes()
        return self

    def delete_existing_records(self, source=None):
        """Deletes associated records in both tables"""
        session = self.session()
        if source is None:
            session.query(self.names).delete(synchronize_session=False)
            session.query(self.features).delete(synchronize_session=False)
        else:
            # If source is specified, delete only the rows matching that source
            query = session.query(self.features).filter_by(source=source)
            loc_ids = [r.geoname_id for r in query]
            if loc_ids:
                session.query(self.names).filter(
                    self.names.geoname_id.in_(loc_ids)
                ).delete(synchronize_session=False)
                session.query(self.features).filter_by(source=source).delete(
                    synchronize_session=False
                )
        session.commit()
        session.close()

    def update_alt_names(self, source=None):
        """Regenerates alternate names table"""
        session = self.session()
        # Deindex and clear existing data
        self.drop_indexes()
        if source:
            session.query(self.names).filter_by(source=source).delete()
        else:
            session.query(self.names).delete()
        session.commit()
        # Popuate names table
        alt_names = []
        query = (
            session.query(self.features)
            .order_by(self.features.geoname_id)
            .limit(self.batch_size)
        )
        total = 0
        offset = 0
        while query.first():
            logger.debug("New query: {:,}".format(offset))
            for row in query:
                alt_names.extend(self.map_alt_names(dictify(row)))
                if len(alt_names) >= 10000:
                    session.bulk_insert_mappings(self.names, alt_names)
                    session.commit()
                    total += len(alt_names)
                    logger.debug("Committed {:,} records".format(total))
                    alt_names = []
            offset += self.batch_size
            query = query.offset(offset)
        if alt_names:
            session.bulk_insert_mappings(self.names, alt_names)
            session.commit()
            total += len(alt_names)
            logger.debug("Committed {:,} records".format(len(alt_names)))
        session.close()
        self.create_indexes()

    def get_names(self, rec):
        names = rec.get("site_names", "").split("|")
        for key in ["ascii_name", "name", "toponym_name"]:
            try:
                names.extend(rec[key].split("|"))
            except (AttributeError, KeyError):
                pass
        names = [s.strip() for s in names]

        synonyms = []
        for key in ["alternate_names", "synonyms"]:
            if rec.get(key):
                synonyms.extend(as_list(rec[key], self.delim + "|;,"))

        return self.valid_names(set(names + synonyms))

    def finalize_names(self, rec):
        if re.search(r"\bADM\dH?\b", str(rec)):
            names = self.std_names(self.get_names(rec))
            try:
                variants = self.std_names(names, self.std.std_admin)
            except AttributeError:
                variants = []
            new = {n.title().replace("-", " ") for n in variants if n not in names}
            if new:
                # Update record to include new names
                for key in ["alternate_names", "synonyms"]:
                    try:
                        synonyms = as_list(rec[key], self.delim + "|;,")
                    except KeyError:
                        pass
                    else:
                        synonyms = sorted(set(synonyms + list(new)))
                        rec[key] = self.delim.join(synonyms)
        return rec

    def map_alt_names(self, rec):
        """Extracts alternate names from a GeoNames record"""
        cols = self.names.__table__.columns
        base = {k: v for k, v in rec.items() if k in cols}
        # Build a list of names from name and synonym fields
        names = self.get_names(rec)
        if not names:
            return []
        # Standardize names
        st_names = self.std_names(names)
        if not st_names:
            logger.debug('Could not standardize term: "{}"'.format(names[0]))
            return []
        # Create full records for valid names
        alt_names = []
        for st_name in set(st_names):
            if st_name and st_name.islower():
                alt_name = base.copy()
                alt_name["st_name"] = st_name
                alt_name["st_name_rev"] = "".join(st_name[::-1])
                alt_names.append(alt_name)
        return alt_names

    def remove_unwanted_names(self):
        """Removes synonyms that confuse matching

        Some names (either in GeoNames itself or after indexing) will drop the compass
        direction from a place name and include the directionless variant as a synonym.
        For example, the South (but not North) Atlantic Ocean includes Atlantic Ocean
        as a synonym. This can confuse attempts to match names. Complicating matters is
        the fact that sometimes these synonyms are legitimate. For example, North
        Macedonia was until recently known as Macedonia. Cleaning up the synonyms is
        therefore accomplised from a whitelist defined at the class level
        (self.unwanted_synonyms).
        """
        session = self.session()
        for geoname_id, st_name in self.unwanted_names.items():
            for row in session.query(self.features).filter(
                self.features.geoname_id == geoname_id
            ):
                synonyms = []
                for syn in as_list(row.alternate_names, self.delim + "|;,"):
                    if self.std(syn) != st_name:
                        synonyms.append(syn)
                synonyms = self.delim.join(synonyms)
                if synonyms != row.alternate_names:
                    mask = "Updated synonyms for geoname_id={}"
                    logger.debug(mask.format(row.geoname_id))
                    row.alternate_names = synonyms
            for row in session.query(self.names).filter(
                self.names.geoname_id == geoname_id, self.names.st_name == st_name
            ):
                mask = "Deleted geoname_id={} where st_name={}"
                logger.debug(mask.format(row.geoname_id, row.st_name))
                session.delete(row)
        session.commit()
        session.close()

    def remove_geoname_ids(self, geoname_ids):
        """Removes list of GeoNames features from the database"""
        session = self.session()
        session.query(self.features).filter(
            self.features.geoname_id.in_(geoname_ids)
        ).delete()
        session.query(self.names).filter(
            self.names.geoname_id.in_(geoname_ids)
        ).delete()
        session.commit()
        session.close()

    def index_names(self, create=True, drop=True):
        """Builds or rebuilds indexes on the self.names table"""
        if create and not drop:
            drop = True

        indexes = {
            "idx_alt_cont": ["continent_code", "country_code"],
        }

        primary = [
            self.names.fcl,
            self.names.fcode,
            self.names.continent_code,
            self.names.country_code,
            self.names.admin_code_1,
            self.names.admin_code_2,
        ]
        for index in [
            Index(
                "idx_alt_continents", self.names.continent_code, self.names.country_code
            ),
            Index("idx_alt_ids", self.names.geoname_id),
            Index("idx_alt_oceans", self.names.ocean),
            Index("idx_alt_primary", self.names.st_name, *primary),
            Index("idx_alt_primary2", self.names.st_name_rev, *primary),
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

    def create_indexes(self):
        """Helper method to create indexes on the names table"""
        return self.index_names(create=True, drop=True)

    def drop_indexes(self):
        """Helper method to drop indexes on the names table"""
        return self.index_names(create=False, drop=True)

    def fill_record(self, row, session):
        """Fills partial record using the GeoNames webservice"""
        # FIXME: Should be a top-level import
        from ...bots.geonames import GeoNamesBot

        geoname_id = self.prep_id(row.geoname_id)
        bot = GeoNamesBot()
        # Update political geography
        result = bot.get_json(geoname_id)
        update = {
            "geoname_id": geoname_id,
            "toponym_name": result.get("toponymName"),
            "continent_code": result.get("continentCode"),
            "country_name": result.get("countryName"),
            "admin_name_1": result.get("adminName1"),
            "admin_name_2": result.get("adminName2"),
        }
        try:
            update["bbox"] = json.dumps(result["bbox"])
        except KeyError:
            pass
        update = {k: (v if v else None) for k, v in update.items()}
        session.merge(self.features(**update))
        # Get sea/ocean name for undersea features
        if not row.ocean and result.get("fcl") == "U":
            session.flush()
            try:
                lat = float(result["lat"])
                lng = float(result["lng"])
                result = bot.ocean_json(lat, lng, dec_places=1, radius=10)
                ocean = result["ocean"]["name"]
                update = {"geoname_id": geoname_id, "ocean": ocean}
                session.merge(self.features(**update))
                session.query(self.names).filter(
                    self.names.geoname_id == geoname_id
                ).update({self.names.ocean: ocean}, synchronize_session=False)
            except KeyError:
                pass
        session.commit()
        return session.query(self.features).filter_by(geoname_id=geoname_id).first()

    def to_csv(self, fp, records=None, terms=None):
        """Exports records from a list or matching a term"""
        if records is None:
            records = []
        if terms is None:
            terms = []
        # Consolidate records given explicitly and via search
        results = {}
        for rec in self.get_many({t for t in terms if str(t).isnumeric()}):
            results[rec["geonameId"]] = rec
        for term in {t for t in terms if not str(t).isnumeric()}:
            for rec in self.search_json(term):
                results[rec["geonameId"]] = rec
        # Ensure that all records returned from search are complete
        try:
            results = {k: self.get_json(k) for k, v in results.items()}
        except TypeError:
            pass
        results.update({r["geonameId"]: r for r in records})
        keys = [to_camel(k) for k in self.keys] if self.keys else None
        with open(fp, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, dialect="excel")
            writer.writerow(["# Attribution goes here"])
            # Write keys if known, otherwise extract from results later
            if keys:
                writer.writerow(keys)
            for result in results.values():
                result = self.mapper(result, True)
                # Use keys from first result if not given explicitly
                if not keys:
                    keys = list(result.keys())
                    writer.writerow(keys)
                writer.writerow([result.get(k, "") for k in keys])

    @staticmethod
    def valid_names(names):
        """Limits list of names to valid names"""
        valid = []
        for name in names:
            if name and re.sub(r"[^A-z]", "", name) and not name.islower():
                valid.append(name)
        if not valid:
            return []
        # Limit to strings containing vowels if first valid value has any
        vowels = bool(re.search(r"[aeiou]", valid[0], flags=re.I))
        if vowels:
            valid = [n for n in valid if re.search(r"[aeiou]", n, flags=re.I)]
        return sorted(set([n for n in valid if n]))

    def get_continent_name(self, code):
        """Gets the continent name for the given continent code"""
        return self.continent_code_to_name[code]

    def get_continent_code(self, name):
        """Gets the continent code for the given continent name"""
        try:
            return self.continent_name_to_code[name]
        except KeyError:
            try:
                return self.continent_name_to_code[name.split("-")[0].strip()]
            except KeyError:
                logger.warning("Could not map continent: {}".format(name))
                return

    def get_country_name(self, code):
        """Gets the country name for the given country code"""
        return self.country_code_to_name[code]

    def assign_short_country_name(self, rec):
        """Gets the short country name from the GeoNames country list"""
        fcodes = ["PCL", "PCLD", "PCLF", "PCLH", "PCLI", "PCLIX", "PCLS", "TERR"]
        if rec.get("fcl") == "A" and str(rec.get("fcode")) in fcodes:
            try:
                name = self.get_country_name(rec["country_code"])
                if name != rec["name"] and (
                    name.lower() in rec["name"].lower()
                    or rec["fcode"][0].startswith("P")
                ):
                    rec["name"] = self.get_country_name(rec["country_code"])
            except (AttributeError, KeyError):
                logger.warning(
                    "Country code '{}' not found".format(rec["country_code"])
                )
        return rec

    def get_country_code(self, name):
        """Gets the country code for the given country name"""
        return self.country_name_to_code[name]

    def get_continent(self, country, return_continent_code=False):
        """Gets the continent name for the given country"""
        try:
            code = self.country_code_to_continent[self.get_country_code(country)]
        except KeyError:
            code = self.country_code_to_continent[country]
        return self.get_continent_name(code) if return_continent_code else code

    def _load_continents(self):
        """Loads continent lookups"""
        name_to_code = {
            "Africa": "AF",
            "Antarctica": "AN",
            "Asia": "AS",
            "Europe": "EU",
            "North America": "NA",
            "Oceania": "OC",
            "South America": "SA",
        }
        code_to_name = CaseInsensitiveDict({v: k for k, v in name_to_code.items()})
        # Map common synonyms
        name_to_code["Antarctic"] = "Antarctica"
        name_to_code["Australasia"] = "Oceania"
        name_to_code["Australia"] = "Oceania"
        name_to_code["Central America"] = "North America"
        name_to_code["North and Central America"] = "North America"
        name_to_code["Pacific Islands"] = "Oceania"
        name_to_code["West Indies"] = "North America"
        GeoNamesFeatures.continent_name_to_code = name_to_code
        GeoNamesFeatures.continent_code_to_name = code_to_name

    def _load_countries(self):
        """Loads country lookups from a GeoNames text file"""
        fp = os.path.join(DATA_DIR, "geonames", "geonames_countries.txt")
        code_to_name = {}
        code_to_cont = {}
        with open(fp, "r", encoding="utf-8", newline="") as f:
            for line in skip_hashed(f):
                row = line.split("\t")
                code_to_name[row[0]] = row[4]
                code_to_cont[row[0]] = row[8]
        # Map missing values that occur in the GeoNames database
        code_to_name["YU"] = "Yugoslavia"
        code_to_cont["YU"] = "Europe"
        name_to_code = {v.lower(): k for k, v in code_to_name.items()}
        GeoNamesFeatures.country_name_to_code = CaseInsensitiveDict(name_to_code)
        GeoNamesFeatures.country_code_to_name = CaseInsensitiveDict(code_to_name)
        GeoNamesFeatures.country_code_to_continent = CaseInsensitiveDict(code_to_cont)


def to_geonames_api(result):
    """Maps result to format used by the GeoNames API"""
    try:
        return [to_geonames_api(row) for row in result]

    except TypeError:

        # Mimic export format from GeoNames API
        cols = [str(c).split(".")[-1] for c in result.__table__.columns]
        rowdict = {to_camel(k): getattr(result, str(k)) for k in cols}
        try:
            alt_names = as_list(rowdict["alternateNames"], "|;,")
        except (AttributeError, KeyError):
            alt_names = []
        rowdict["alternateNames"] = [{"name": n.strip()} for n in alt_names]

        # Load bounding box or WKT from bbox key
        try:
            bbox = re.sub(r"'([A-z_]+)'(?=:)", r'"\1"', rowdict["bbox"])
            rowdict["bbox"] = json.loads(bbox)
        except TypeError:
            del rowdict["bbox"]
        except json.JSONDecodeError:
            # WKT strings may be hacked into the bbox field, so check for that
            try:
                wkt.loads(rowdict["bbox"])
            except ValueError:
                raise ValueError(rowdict)

        return rowdict
