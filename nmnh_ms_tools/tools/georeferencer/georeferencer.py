import csv
import datetime as dt
import hashlib
import json
import logging
import os
import pprint as pp
import re
import shutil
import sys
import warnings

import numpy as np

from .evaluators import MatchAnnotator
from .pipes import (
    MatchBetween,
    MatchBorder,
    MatchCustom,
    MatchDirection,
    MatchGeoNames,
    MatchOffshore,
    MatchPLSS,
)
from ...records import RecordEncoder, Site
from ...utils import (
    LazyAttr,
    as_list,
    clear_empty,
    configure_log,
    fast_hash,
    mutable,
    skip_hashed,
    to_attribute,
)


logger = logging.getLogger(__name__)


class Georeferencer:

    # Deferred class attributes are defined at the end of the file
    _site_attrs = None

    def __init__(
        self,
        records=None,
        pipes=None,
        tests=None,
        skip=0,
        limit=0,
        report=0,
        callback=None,
    ):
        self.readers = {
            ".csv": self.read_gbif,
            ".txt": self.read_gbif,
        }
        # Set pipes
        if pipes is None:
            pipes = [
                MatchPLSS(),
                MatchBetween(),
                MatchBorder(),
                MatchOffshore(),
                MatchDirection(),
                MatchCustom(),
                MatchGeoNames(),
            ]
        self.pipes = pipes
        # Set criteria for selecting records to georeference
        self._place_type = None
        self._coord_type = None
        self.place_type = "any"
        self.coord_type = "any"
        self.allow_sparse = False
        self.allow_invalid_coords = False
        self.require_coords = False
        self.include_failed = True
        self.raise_on_error = False
        self.eval_params = {}
        # Set read params
        self.id_key = r".*"
        self.skip = skip
        self.limit = limit
        self.report = report
        self.callback = callback
        # Initialize containers
        self.key = None
        try:
            with open("evaluated.json", encoding="utf-8") as f:
                self.evaluated = json.load(f)
        except:
            self.evaluated = {}
        self.results = []
        self.misses = {}
        self.admin_failed = {}
        # Initialize variables to track outcomes
        self._index = 0
        self._loc_id = None
        self._notified = False
        # Capture any tests
        self.tests = self.read_tests(tests)
        # Get records
        self.records = records

    def __iter__(self):
        if self.require_coords:
            return iter(self.evaluated.values())
        return iter(self.results)

    def __len__(self):
        if self.require_coords:
            return len(self.evaluated)
        return len(self.results)

    @property
    def coord_type(self):
        return self._coord_type

    @coord_type.setter
    def coord_type(self, val):
        allowed = ["any", "georeferenced", "measured"]
        if val in allowed:
            self._coord_type = val
        else:
            raise ValueError(f"coord_type must be one of {allowed} ({repr(val)} given)")

    @property
    def place_type(self):
        return self._place_type

    @place_type.setter
    def place_type(self, val):
        allowed = ["any", "marine", "terrestrial"]
        if val in allowed:
            self._place_type = val
        else:
            raise ValueError(f"place_type must be one of {allowed} ({repr(val)} given)")

    @property
    def records(self):
        return self._records

    @records.setter
    def records(self, records):
        if records is None:
            self.path = None
            self.slug = None
            self._records = []
        elif isinstance(records, str):
            self.path = records
            self.slug = to_attribute(os.path.basename(self.path))
            ext = os.path.splitext(records)[-1].lower()
            self._records = self.readers[ext]()
        else:
            self.path = None
            self.slug = "records"
            for _ in range(self.skip):
                next(records)
            self._records = records

    def georeference(self):
        """Georeferences a set of records"""
        logger.info(f"Limit is {self.limit}")
        if self.skip:
            logger.debug(f"Skipping first {self.skip:,} records...")
        for i, rec in enumerate(self.records):
            self._notified = False
            self._index = i
            self._loc_id = self.get_location_id(rec)

            if i and not i % 1000:
                print(f"{i:,} records processed")
                logger.debug(f"{i:,} records processed")

            if self.tests and self._loc_id not in self.tests:
                continue

            kill = False
            try:
                site = self.build_site(rec)
                self.georeference_one(site)
            except Exception as e:
                self.handle_exception(e, rec)
                site = pp.pformat(rec)
                kill = True
            finally:
                # Check if tests are exhausted
                if self.tests:
                    logger.debug(f"Index: {i + self.skip}")
                    logger.debug(site)
                    self.tests.remove(self._loc_id)
                    if not self.tests or kill:
                        return

            if not self._notified:
                raise RuntimeError("Notify did not run")

            if len(self) >= self.limit:
                break

    # @clock
    def georeference_one(self, site):
        """Georeference a single site"""
        self.key = self.keyer(site)
        try:
            result = self.evaluated[self.key].copy()
            result["location_id"] = site.location_id
            self.results.append(result)
            self.notify("Retrieved from cache")
            return result
        except KeyError:
            try:
                meets_criteria = self.meets_criteria(site, self.callback)
            except Exception as e:
                self.handle_exception(e, site)
                return
            # Only in-scope sites with coordinates can contribute to stats
            if meets_criteria or self.tests:
                if not meets_criteria:
                    logger.warning("Site does not meet criteria")
                return self._georeference_actual(site)

    def _georeference_actual(self, site):
        try:
            site.map_admin()
            site.map_marine_features()
            start_time = dt.datetime.now()
            evaluator = MatchAnnotator(site, self.pipes)
            for key, val in self.eval_params.items():
                if not hasattr(evaluator, key):
                    raise AttributeError(f"MatchEvaluator has no attribute {repr(key)}")
                setattr(evaluator, key, val)
            evaluator.encompass()
            # Test that result is valid
            str(evaluator.result)
            # Check for very long durations
            elapsed = (dt.datetime.now() - start_time).total_seconds()
            if elapsed > 30:
                logger.warning(f"{site.location_id}: Long duration (t={int(elapsed)}s)")
        except Exception as e:
            try:
                self.handle_exception(e, site, evaluator)
            except NameError:
                self.handle_exception(e, site)
            return
        try:
            dist_km = evaluator.centroid_dist_km(site, threshold_km=100)
            within_unc = dist_km <= evaluator.radius_km
        except ValueError:
            dist_km = None
            within_unc = None
        estimated = evaluator.estimate_minimum_uncertainty()
        within_est = evaluator.radius_km <= estimated
        # Save result as KML
        try:
            fn = f"{dist_km:.1f}km_{site.location_id}"
        except TypeError:
            fn = str(site.location_id)
        evaluator.kml(fn, refsite=site)

        result = dict(
            key=self.keyer(site),
            location_id=site.location_id,
            result="success",
            description=evaluator.describe(),
            geometry=evaluator.result.geometry.wkt,
            crs=str(evaluator.result.geometry.crs),
            radius_km=evaluator.radius_km,
            has_coords=bool(site.geometry),
            dist_km=dist_km,
            est_km=estimated,
            within_unc=within_unc,
            within_est=within_est,
            site=str(site),
        )
        self.evaluated[self.key] = result
        self.results.append(result)
        self.notify("Succeeded")
        return result

    def read_gbif(self, encoding="utf-8-sig"):
        """Reads Darwin Core CSV"""
        with open(self.path, encoding=encoding, newline="") as f:
            # GBIF files are comma-delimited utf-8 but homemade files may
            # use Excel dialect instead, so let the CSV module sort it out
            f = skip_hashed(f)
            dialect = csv.Sniffer().sniff(f.readline())
            f.seek(0)
            rows = csv.reader(skip_hashed(f), dialect=dialect)
            keys = [to_attribute(k) for k in next(rows)]
            for i, row in enumerate(rows):
                if i and self.report and not i % self.report:
                    logger.debug(f"{i:,} rows processed")
                if self.skip and i < self.skip:
                    continue
                if self.limit and len(self) >= self.limit:
                    logger.debug(f"Checked {i:,} total records")
                    break
                rowdict = dict(zip(keys, row))
                yield rowdict

    def read_tests(self, mixed):
        """Reads tests for the given filename from tests.csv"""
        if mixed:
            if isinstance(mixed, (list, tuple)):
                return mixed[:]
            tests = {}
            with open(mixed, "r", encoding="utf-8-sig", newline="") as f:
                f = skip_hashed(f)
                dialect = csv.Sniffer().sniff(f.readline())
                f.seek(0)
                rows = csv.reader(skip_hashed(f), dialect=dialect)
                keys = next(rows)
                for row in rows:
                    rowdict = dict(zip(keys, row))
                    if rowdict.get("runTest", "TRUE") == "TRUE":
                        tests.setdefault(rowdict.get("filename", ""), []).append(
                            rowdict[list(rowdict)[0]]
                        )
            # Limit to tests pertaining to the current file
            if tests:
                fn = os.path.basename(self.path)
                return test[fn] if any(list(tests)) else tests[""]
        # Remove the kml directory if no tests provided
        try:
            shutil.rmtree("kml")
        except OSError:
            pass
        return None

    def meets_criteria(self, site, callback=None):
        """Tests if record meets the minimum criteria"""
        if callback and not callback(site):
            # Log error in the callback function
            self.notify("Skipped (callback failed)")
            return False
        if self.require_coords and not site.geometry:
            self.notify("Skipped (no coordinates)")
            return False
        if self.coord_type == "measured" and site.geometry and site.is_georeferenced():
            self.notify("Skipped (coordinates georeferenced)")
            return False
        if (
            self.coord_type == "georeferenced"
            and site.geometry
            and not site.is_georeferenced()
        ):
            self.notify("Skipped (coordinates measured)")
            return False
        if self.place_type == "terrestrial" and site.is_marine():
            self.notify("Skipped (site is marine)")
            return False
        if self.place_type == "marine" and not site.is_marine():
            self.notify("Skipped (site is terrestrial)")
            return False
        if not self.allow_sparse and site.is_sparse():
            self.notify("Skipped (sparse site data)")
            return False
        if (
            not self.allow_invalid_coords
            and site.geometry
            and not site.has_valid_coordinates()
        ):
            self.notify("Skipped (invalid coordinates)")
            return False
        return True

    def map_admin(self, fp):
        """Maps admin divisions from a dict (much faster than site)"""
        keys = ("country", "state_province", "county")
        for rec in self.readers[os.path.splitext(fp)[-1].lower()]:
            country = clear_empty(rec[keys[0]])
            if country:
                args = [rec[k] for k in keys]
                if not Site.adm.get(*args):
                    raise ValueError(f"Could not map admin names: {json.dumps(args)}")

    def handle_exception(self, exc, site, evaluator=None):
        """Handles exceptions raised while georeferencing"""
        if not isinstance(site, Site):
            location_id = self.get_location_id(site)
            if not location_id:
                location_id = site.location_id
            if "resolves to empty mapping" in str(exc):
                warnings.warn(str(exc))
            else:
                self.notify(f"Failed to parse site: {exc}")
                logger.error(f"{location_id}: {exc}", exc_info=exc)
                if self.raise_on_error:
                    try:
                        raise exc
                    finally:
                        sys.exit()
            return

        desc = evaluator.describe() if evaluator else f"{exc.__class__.__name__}: {exc}"
        result = dict(
            key=self.keyer(site),
            location_id=site.location_id,
            result="failed",
            radius_km="",
            has_coords=bool(site.geometry),
            description=desc,
            site=str(site),
        )
        self.evaluated[self.key] = result
        if self.include_failed:
            self.results.append(result)
            if evaluator is not None:
                evaluator.kml(f"miss_{site.location_id}", refsite=site)
        self.notify(f"Failed: {exc}")
        # Count misses on admin names
        if "Could not map admin names:" in str(exc):
            names = [clear_empty(n) for n in json.loads(str(exc).split(": ", 1)[-1])]
            key = tuple([" | ".join(as_list(n)) for n in names])
            try:
                self.admin_failed[key] += 1
            except KeyError:
                self.admin_failed[key] = 1
            logger.warning(
                f"Georeference failed: {site.location_id} (failed to map admin={names})"
            )
        elif "Could not encompass sites" in str(
            exc
        ) or "Too many candidates to encompass" in str(exc):
            # Note failure but specifics not needed
            logger.warning(f"Georeference failed: {site.location_id} (no match)")
            pass
        else:
            # Unknown error, so include the traceback in the log
            logger.error(
                f"Georeference failed: {site.location_id} (error)", exc_info=exc
            )
            if self.raise_on_error:
                try:
                    raise exc
                finally:
                    sys.exit()

    def summarize(self, archive):
        """Summarizes performance for sites with known coordinates"""
        timestamp = archive.split("_", 1)[0]
        filename = archive.split("_", 1)[-1].rsplit("_", 1)[0]
        summary = dict(
            timestamp=timestamp,
            filename=filename,
            archive=archive,
            total=len(self),
            has_coords=0,
            found=0,
            within_unc=0,
            within_est=0,
            dist_km_median=0,
            radius_km_median=0,
            dist_km_mean=0,
            radius_km_mean=0,
            dist_km=[],
            radius_km=[],
        )
        for result in self.evaluated.values():
            if result["found"]:
                summary["found"] += 1
            if result["has_coords"]:
                summary["has_coords"] += 1
            try:
                summary["radius_km"].append(result["radius_km"])
                summary["dist_km"].append(result["dist_km"])
                if result["within_unc"]:
                    summary["within_unc"] += 1
                if result["within_est"]:
                    summary["within_est"] += 1
            except KeyError as e:
                pass
        for key in list(summary.keys()):
            vals = summary[key]
            if key in {"dist_km", "radius_km"}:
                vals = [n for n in vals if n is not None]
                summary[key + "_median"] = self._median(vals) if vals else ""
                summary[key + "_mean"] = self._mean(vals) if vals else ""
                del summary[key]
            elif key in {"within_unc", "within_est"}:
                count = summary["has_coords"]
                if count:
                    summary[key] = f"{100 * vals / count:.1f}%"
                else:
                    summary[key] = "-"
            elif key == "found":
                count = len(self.evaluated)
                summary[key] = f"{100 * vals / count:.1f}%"
        return summary

    def archive(self, path="archived", min_results=100):
        """Archives results"""
        try:
            os.makedirs(path)
        except OSError:
            pass
        for dirname in os.listdir(path):
            child = os.path.join(path, dirname)
            if os.path.isdir(child) and not os.listdir(child):
                shutil.rmtree(child)
        if len(self) >= min_results and self.tests is None:
            # Get job params
            timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
            archive = f"{timestamp}_{self.slug}_{len(self)}"
            try:
                os.makedirs(os.path.join(path, archive))
            except OSError:
                pass
            # Update master summary sheet
            summary = self.summarize(archive)
            fp = os.path.join(path, "summary.csv")
            while True:
                try:
                    with open(fp, "a", encoding="utf-8-sig", newline="") as f:
                        writer = csv.writer(f, dialect="excel")
                        if not f.tell():
                            writer.writerow(list(summary.keys()))
                        writer.writerow(list(summary.values()))
                    break
                except PermissionError:
                    input("Please close summary.csv and hit ENTER")
            # Summarize results of job
            fp = os.path.join(path, archive, "summary.csv")
            with open(fp, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, dialect="excel")
                # Get full set of keys
                for rec in self:
                    keys = list(rec.keys())
                    if len(keys) > 5:
                        break
                writer.writerow(keys)
                for rec in self:
                    writer.writerow([self._prep(rec.get(k, "")) for k in keys])
            # Copy KML and database files to archive directory
            shutil.move("kml", os.path.join(path, archive))
            shutil.move("job.sqlite", os.path.join(path, archive))
            # Copy clocked
            try:
                shutil.move("clocked.csv", os.path.join(path, archive))
            except FileNotFoundError:
                pass
            # Copy log
            root = logging.getLogger()
            for handler in root.handlers[:]:
                handler.close()
                root.removeHandler(handler)
            shutil.move("geo.log", os.path.join(path, archive))

    def get_location_id(self, rec, key=None):
        """Extracts location id from a record"""
        if key is None:
            key = self.id_key
        try:
            return rec[key]
        except KeyError:
            pass
        try:
            return re.search(key, str(rec)).group()
        except AttributeError:
            return hashlib.md5(json.dumps(rec).encode("utf-8")).hexdigest()

    def configure_log(self, level="WARNING", stream=True):
        """Set up log based on whether or not there are tests"""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            handler.close()
            root.removeHandler(handler)
        if level == "WARNING" and self.tests:
            configure_log("geo", level="DEBUG", stream=stream)
            root = logging.getLogger()
        else:
            configure_log("geo", level=level, stream=stream)

    def notify(self, outcome):
        succeeded = len([r for r in self.results if r["result"] == "success"])
        msg = (
            f"{self._loc_id}: {outcome}"
            f" ({succeeded:,}/{self._index + 1:,} succeeded)"
        )
        print(msg)
        logger.info(msg)
        self._notified = True

    def build_site(self, rowdict):
        from ...bots.geonames import GeoNamesBot

        rowdict["location_id"] = self._loc_id

        try:
            site = Site(rowdict)
        except KeyError:
            site = Site(
                {k: v for k, v in rowdict.items() if k in self._site_attrs and v}
            )

        # Remove sites from less specific fields
        sitedict = site.to_dict()
        geom = sitedict.pop("geometry", None)
        vals = []
        for key, vals_ in sitedict.items():
            if key != "locality":
                if isinstance(vals_, list):
                    vals.extend(vals_)
                else:
                    vals.append(vals_)
        vals = set(vals)

        loc = []
        for val in site.locality.split("|"):
            val = val.strip()
            if val not in vals:
                loc.append(val)
        with mutable(site):
            site.locality = " | ".join(loc)

        site.__class__.bot = GeoNamesBot()

        if geom:
            with mutable(site):
                site.site_names = ["Original Coordinates"]
                site.geometry = geom

        return site

    @staticmethod
    def keyer(site):
        site_dict = {k: v for k, v in site.to_dict(drop_empty=True).items() if v}
        del site_dict["location_id"]
        return fast_hash(
            json.dumps(site_dict, sort_keys=True, cls=RecordEncoder).lower()
        )

    @staticmethod
    def _prep(val):
        """Conditionally formats a string"""
        return f"{val:.1f}" if isinstance(val, float) else str(val)

    @staticmethod
    def _mean(vals):
        """Calculates the mean and standard deviation for a set of values"""
        return f"{np.mean(vals):.1f} ± {np.std(vals):.1f} km"

    @staticmethod
    def _median(vals):
        """Calculates the median and interquartile range for a set of values"""
        iqr = np.percentile(vals, 75) - np.percentile(vals, 25)
        return f"{np.median(vals):.1f} ± {iqr / 2:.1f} km"


# Define deferred class attributes
LazyAttr(Georeferencer, "_site_attrs", lambda: Site({}).attributes)
