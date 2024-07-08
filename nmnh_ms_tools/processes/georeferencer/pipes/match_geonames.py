"""Defines class to match feature names to GeoNames records"""

import logging
import json
import re

from .core import MatchPipe, Georeference
from ....bots.geonames import GeoNamesBot, FEATURE_TO_CODES
from ....config import CONFIG, GEOCONFIG
from ....databases.geonames import GeoNamesFeatures
from ....databases.geohelper import get_preferred
from ....records import Site
from ....tools.geographic_names.caches import RecordCache
from ....tools.geographic_names.parsers.modified import has_direction
from ....utils import as_list


logger = logging.getLogger(__name__)


CODES_TO_FEATURE = {"-".join(sorted(set(v))): k for k, v in FEATURE_TO_CODES.items()}


class MatchGeoNames(MatchPipe):
    """Matches feature names to GeoNames records"""

    bot = GeoNamesBot()
    cache = {}
    use_cache = False

    def __init__(
        self,
        *args,
        username=None,
        use_local=None,
        include_feature_classes=False,
        **kwargs,
    ):
        super(MatchGeoNames, self).__init__(*args, **kwargs)
        if username is not None:
            MatchGeoNames.bot.username = username
        self.fields = GEOCONFIG.fields
        self.local = None
        self._use_local = None
        if use_local is None:
            use_local = CONFIG["bots"]["geonames_use_local"]
        self.use_local = use_local if use_local is not None else use_local
        self.include_feature_classes = include_feature_classes
        self.hint = self.field  # use to force a particular std function
        self.rows = []

    @property
    def use_local(self):
        return self._use_local

    @use_local.setter
    def use_local(self, val):
        assert isinstance(val, bool), "use_local must be bool"
        self._use_local = val
        if val:
            self.local = GeoNamesFeatures()
        else:
            self.local = None

    def test(self, feature):
        """Tests if matcher can be used on the given locality string"""
        parsers = {"modified", "multifeature", "feature", "simple"}
        return feature and feature.kind in parsers

    def georeference(self, feature, codes=None, size="normal"):
        """Georeferences one or more features using GeoNames

        The nested georeference functions are an attempt to account for
        ambiguous feature names (names containing "and", names with
        directional terms that may or may not be intrinsic to the feature,
        etc.) Each group is a list, and the script checks each name in
        the list. If any name hits, the function returns the list of
        matching sites.
        """
        if self.field and codes is None:
            codes = GEOCONFIG.fields[self.field]
        sites = []
        names_matched = []
        groups = self.group(feature)
        for group in groups:
            for grp in group:
                names, direction = grp
                for name in names:
                    feat = name, direction
                    result = self._georeference(feat, codes, size)
                    if result:
                        sites.extend(result)

                # Assign field to each result in sites
                if sites:
                    names_matched.extend(names)
                    for site in sites:
                        site.field = self.field
                        for rel in site.related_sites:
                            rel.field = self.field

                # The geoereference method can return sites that fail to
                # match the admin divs of the original site, but that's not
                # ideal, so keep looking if no good matches found. The
                # less-good matches are kept to pass to evaluator if needed.
                good = [s for s in sites if -1 not in s.filter.values()]
                if good:
                    return Georeference(good, names)

        return Georeference(sites, names_matched) if sites else None

    def _georeference(self, feature, codes=None, size="normal"):
        """Georeferences variants of a feature name using GeoNames"""
        name, direction = feature
        variants = self.std.variants(name)
        # Do not do variant matching on admin fields
        if self.field is not None and self.field.startswith(
            ("country", "state_province", "county")
        ):
            variants = {"standard": variants["standard"]}
        # Towns can look like anything, so include them for generic fields
        municipalities = []
        if codes is None or len(codes) > 20:
            municipalities = FEATURE_TO_CODES["municipality"]
        sites = []
        for kind, st_name in variants.items():
            # Only check names that differ from the standard
            if kind == "standard" or st_name != variants["standard"]:
                alt_codes = FEATURE_TO_CODES.get(kind, codes)
                if kind == "standard":
                    alt_codes = alt_codes[:] + municipalities

                matches = self._georeference_actual(
                    name, st_name, alt_codes, size, std_func=self.std.features.get(kind)
                )
                sites.extend(matches)
        sites = list({s.location_id: s for s in sites}.values())
        return self.subsection(sites, direction, feature)

    def _georeference_actual(
        self,
        name,
        st_name=None,
        codes=None,
        size="normal",
        std_func=None,
        use_cache=None,
    ):
        """Georeferences a single name using GeoNames"""
        if use_cache is None:
            use_cache = self.use_cache

        preferred = self.get_preferred(name)
        if preferred:
            return [preferred]
        sizes = {
            "small": 0,  # never exclude admin info
            "normal": 0,  # include all admin info
            "large": 50,  # exclude state from search
            "very large": 100,  # exclude country from search
        }
        assert size in sizes
        if st_name is None:
            st_name = std_func(name) if std_func is not None else self.std(name)
        if codes is None:
            codes = self.get_codes(name)
        # Filter query on high-level political geography
        if self.site.is_marine() or size == "very large":
            kwargs = {}
        elif self.site.country_code and size != "very large":
            kwargs = {"country": self.site.country_code}
            if (
                self.field != "country"
                and len(self.site.admin_code_1) == 1
                and size in {"small", "normal"}
            ):
                kwargs["adminCode1"] = self.site.admin_code_1[0]
        elif self.site.continent_code:
            kwargs = {"continentCode": self.site.continent_code}
        else:
            kwargs = {}
        # Add feature classes to query based on codes if that option is set
        if self.include_feature_classes:
            kwargs["featureClass"] = GEOCONFIG.get_feature_classes(codes)
        # Check cache to see if this query has been processed before
        min_size = sizes[size]
        key = self.key(name, codes, min_size, **kwargs)
        if use_cache:
            try:
                cached = []
                for site in self.cache[key]:
                    cloned = site.clone()
                    cloned.sources = site.sources
                    cached.append(cloned)
                logger.debug("Resolved from cache: {}".format(key))
                return cached
            except ValueError:
                logger.error("Could not restore cached records: {}".format(key))
            except KeyError:
                pass
        logger.debug(f"Searching for {key[:256]}...")
        # Create and filter a list of sites. If no records found, retry the
        # search with fewer constraints but require any remaining records to
        # be larger than a certain size.
        #
        # Note that this block had use_cache=False. Not sure if that was on
        # purpose or not.
        results = self.search_json(st_name, **kwargs)
        records = self.filter_records(results, name, codes, min_size, std_func=std_func)
        if not records and size not in {"small", "very large"}:
            logger.debug('Retrying search with min_size="very large"')
            records = self._georeference_actual(
                name, st_name, codes, "very large", use_cache=use_cache
            )
        # Log result
        if len(codes) > 20:
            codes = codes[:20] + ["..."]
        # mask = 'Search for {} (name={}, codes={}, kwargs={}) matched {} records: {}'
        # logger.debug(mask.format(st_name, name, codes, kwargs, len(records), gids))
        gids = [s.location_id for s in records]
        logger.debug("Search yielded {:,} records: {}".format(len(gids), gids))
        if use_cache:
            self.cache[key] = records
        return records

    def filter_records(self, records, name, codes=None, min_size=0, std_func=None):
        """Filters list of raw results, returning a list of matching sites"""
        if codes is None:
            codes = self.get_codes(name)
        if std_func is None:
            std_func = self.std
        st_name = std_func(name)
        filtered = []
        for i, site in enumerate(records):
            # Ignore records that do match the code set
            if not self.has_code(site, codes):
                continue
            # Record may be a dict or a site
            if isinstance(site, dict):
                site = self.build_site(site)
            # Ignore sites that don't match the feature name
            site.filter["name"] = name
            score = site.compare_names(name, std_func=std_func)
            # Compare all names to the original site
            if score < 0:
                score = site.compare_names(self.site, std_func=std_func)
            # Look for additional synonyms for first few names
            if score < 0 and i < 3:
                site.synonyms.extend(self.extend_synonyms(site))
                score = site.compare_names(name, std_func=std_func)
                if score < 0:
                    score = site.compare_names(self.site, std_func=std_func)
            if score < 0:
                names = sorted(set(site.site_names + site.synonyms))
                if len(names) > 10:
                    names = names[:9] + ["..."]
                mask = '{}: Name mismatch: "{}" not in {}'
                logging.debug(mask.format(site.location_id, name, names))
                continue
            # Filter sites from the wrong country or admin division
            try:
                site.map_admin()
            except ValueError:
                if (
                    site.country
                    and not site.country_code
                    or site.state_province
                    and not site.admin_code_1
                    or site.county
                    and not site.admin_code_2
                ):
                    raise
            # Construct filters for each site
            for attr in ["admin_code_2", "admin_code_1", "country_code"]:
                val = getattr(self.std_site, attr)  # already standardized
                site.compare_attr(val, self.std(getattr(site, attr)), attr)
            """
            attrs = ['admin_code_2', 'admin_code_1', 'country_code']
            if self.very_large_feature() or min_size == 100:
                attrs = []
            elif min_size == 50:
                attrs = ['country_code']
            for attr in attrs:
                val = getattr(self.std_site, attr)  # already standardized
                site.compare_attr(val, self.std(getattr(site, attr)), attr)
            if -1 in site.filter.values():
                mask = '{}: Admin mismatch: {}'
                logging.debug(mask.format(site.location_id, site.filter))
                continue
            """
            filtered.append(site)

        # Prefer countries or states if no country code given
        if not self.site.country_code or min_size >= 100:
            countries = [s for s in filtered if re.match(r"PCL", s.site_kind)]
            current_countries = [s for s in countries if s.site_kind != "PCLH"]
            if current_countries:
                return current_countries
            if countries:
                return countries
            states = [s for s in filtered if re.match(r"ADM1", s.site_kind)]
            if states:
                return states

        # Limit filtered to the highest quality match possible. Note that this
        # may miss nearby localities that fall into different jursidictions.
        if min_size < 100:
            ok_country = [s for s in filtered if s.filter["country_code"] != -1]
            ok_state = [s for s in ok_country if s.filter["admin_code_1"] != -1]
            ok_county = [s for s in ok_state if s.filter["admin_code_2"] != -1]
            for sites in [ok_county, ok_state, ok_country]:
                if sites:
                    filtered = sites
                    break

        # Fill in additional info from GeoNames if needed
        if self.use_cache:
            for site in filtered[:10]:
                if not site.country:
                    self.get_json(site.location_id)

        return filtered

    def key(self, name, codes, min_size, **kwargs):
        """Creates a key corresponding to a query"""
        key = [name]
        admin = {}
        for attr in ["country_code", "admin_code_1", "admin_code_2"]:
            admin[attr] = getattr(self.site, attr)
        key.append({k: v for k, v in admin.items() if v})
        key.append({k: v for k, v in kwargs.items() if v})
        key.append(codes)
        key.append(min_size)
        return json.dumps(key, sort_keys=True)

    def has_code(self, site, codes):
        """Tests if a site is of the proper kind"""
        # If no codes are passed, automatic match!
        if not codes:
            return True
        try:
            code = site.site_kind
        except AttributeError:
            code = site.get("fcode")
        return code in codes or (not code and len(codes) >= 100)

    def get_codes(self, name):
        codes = self.codes[:]
        # If only a general set of codes is given, check to see if the
        # same term appears more specifically elsewhere in the record
        if len(codes) > 100:
            alt_codes = []
            for field in self.find(name):
                if len(GEOCONFIG.fields[field]) < len(codes):
                    alt_codes.extend(GEOCONFIG.fields[field])
            if alt_codes:
                return alt_codes
        return codes

    def build_site(self, rec):
        """Builds a site from a record"""
        site = Site(rec)
        site.sources = [site.site_source]
        return site

    def subsection(self, sites, direction, feature=None):
        if direction:
            logger.debug(f"Subsectioning {len(sites)} features")
            name = "{1} {0}".format(*feature)
            return [s.subsection(direction, name) for s in sites]
        return sites

    def extend_synonyms(self, site):
        """Finds additional synonyms for a GeoNames record"""
        if self.use_local:
            return []
        resp = self.get_json(site.location_id)
        if resp:
            alt_names = [r.get("name") for r in resp.get("alternateNames", [])]
            for i, name in enumerate(alt_names):
                if name.startswith("http") and "wikipedia" in name:
                    alt_names[i] = name.split("/")[-1].replace("_", " ")
            return sorted({n for n in alt_names if n})
        return []

    def group(self, feature):
        """Groups names to pass to georeference"""
        is_parser = not isinstance(feature, str)
        # Group related names
        if is_parser:
            names = []
            subsections = []
            for f in feature:
                try:
                    names.append([f.variants() for f in f][0])
                except IndexError:
                    raise IndexError("No variants: {}".format(feature))
                try:
                    subsections.append(f[0].modifier)
                except (AttributeError, IndexError):
                    subsections.append(None)
        else:
            names = [feature]
            subsections = [None]
        features = []
        for i, names in enumerate(names):
            # Ensure that each group of names is a list
            if not isinstance(names, list):
                names = [names]
            group = []
            for name in names:
                # Nullify subsection if equivalent direction found in name
                subsection = subsections[i]
                if subsection and has_direction(name, subsection):
                    subsection = None
                group.append((as_list(name), subsection))
            features.append(group)
        return features

    def very_large_feature(self):
        """Identifies large features that may cross political boundaries"""
        return self.field in {"ocean", "sea_gulf"}

    def get_preferred(self, name):
        """Builds site based on the preferred feature for a major locality"""
        result = get_preferred(
            name,
            country_code=self.site.country_code,
            admin_code_1=self.site.admin_code_1,
            admin_code_2=self.site.admin_code_2,
        )
        if result:
            try:
                site = self.build_site(self.get_json(result.geonames_id).json)
            except AttributeError:
                site = self.build_site(self.get_json(result.geonames_id))
            site.filter["name"] = name
            return site
        return None

    def get_json(self, geoname_id, **kwargs):
        """Retrieves the JSON record corresponding to the geoname_id"""
        if self.use_local:
            return self.local.get_json(geoname_id, **kwargs)
        return self.bot.get_json(geoname_id)

    def search_json(self, st_name, **kwargs):
        """Retrieves records mathing the given search parameters"""
        if self.use_local:
            return self.local.search_json(st_name, **kwargs)
        return self.bot.search_json(st_name, **kwargs).all()

    @staticmethod
    def enable_sqlite_cache(path=None):
        MatchGeoNames.cache = RecordCache(path)
        MatchGeoNames.use_cache = True


Site.pipe = MatchGeoNames()
