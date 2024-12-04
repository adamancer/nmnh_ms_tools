"""Defines the basic pipe, include parsing of the original site"""

import logging
import re

from ..evaluators.results import MatchResult
from ....config import CONFIG
from ....records import Site
from ....tools.geographic_names.parsers import (
    FeatureParser,
    MultiFeatureParser,
)
from ....utils import LazyAttr, LocStandardizer, as_list, mutable


logger = logging.getLogger(__name__)


class MatchPipe:

    # Deferred class attributes are defined at the end of the file
    std = None

    # Normal class attributes
    parser = None
    hints = {}

    def __init__(self, site=None):
        # Site params
        self._site = None
        self.std_site = None
        self.results = []
        self.prepared = {}
        self.interpreted = {}
        self.filter = {}
        self.populated = {}
        self.matched = {}
        self.leftovers = {}
        # Field params
        self.field = None
        self.codes = None
        self.verbatim = None
        self.features = None
        # Do initial load if site given
        if site is not None:
            self.site = site

    @property
    def site(self):
        if self._site is None:
            self.site = Site({})
        return self._site

    @site.setter
    def site(self, site):
        if site != self._site:
            self.load(site)

    @property
    def verbatim(self):
        if self._verbatim and str(self).startswith('"'):
            return f'"{self._verbatim}"'
        return self._verbatim

    @verbatim.setter
    def verbatim(self, val):
        self._verbatim = val

    def reset(self):
        """Resets match parameters"""
        # Site params
        self._site = None
        self.std_site = None
        self.prepared = {}
        self.interpreted = {}
        self.filter = {}
        self.populated = {}
        self.matched = {}
        self.leftovers = {}
        # Field params
        self.field = None
        self.codes = None
        self.verbatim = None
        self.features = None

    def load(self, site):
        """Loads a new site"""
        self.reset()  # explicitly reset the object when new site is loaded
        if isinstance(site, MatchPipe):
            self.copy_from(site)
            return self
        # Construct a standardized version of the site to simplify comparisons
        self._site = site
        self.site.map_admin()
        self.std_site = self.site.copy()
        # NOTE: Copy should handle this
        # for attr in self.std_site.attributes:
        #    setattr(self.std_site, attr, self.std(getattr(self.std_site, attr)))
        # for attr in ["country_code", "admin_code_1", "admin_code_2"]:
        #    setattr(self.std_site, attr, self.std(getattr(self.std_site, attr)))
        return self

    def prepare(self, field):
        """Parses the current field"""
        self.field = field["field"]
        self.codes = field["codes"]
        self.verbatim = getattr(self.site, self.field.rstrip("0123456789"))
        self.features = self.prepared.get(self.field, [])
        if self.verbatim and not self.populated.get(self.field):
            # Note that data was found in the field
            self.populated[self.field] = self.codes
            for val in as_list(self.verbatim, delims="|;"):
                # Exclude values that have already been interpreted
                try:
                    self.site.interpreted[(self.field.rstrip("0123456789"), val)]
                    break
                except KeyError:
                    parsed, leftover = self.parse(val)
                    for group in parsed:
                        self.features.append(group)
                    if leftover:
                        self.leftovers.setdefault(self.field, []).append(leftover)
            else:
                self.prepared[self.field] = self.features[:]
        return self

    def prepare_all(self):
        """Parses all fields"""
        self.prepared = {}
        self.interpreted = {}
        self.populated = {}
        self.leftovers = {}
        for field in CONFIG["georeferencing"]["ordered_field_list"]:
            self.prepare(field)
        self.interpret()
        for field, features in self.prepared.items():
            expanded = []
            for feature in features:
                try:
                    expanded.append(feature.expand(self.site, self.interpreted))
                except ValueError:
                    # Add unexpanded feature if not enclosed in brackets
                    if not re.search(r"^\{.*\}$", str(feature)):
                        expanded.append(feature)
            self.prepared[field] = expanded
        logger.debug("Finished preparing site")
        return self

    def test(self, feature):
        """Tests if matcher can be used for the given locality string"""
        return True

    def georeference(self, *args, **kwargs):
        """Placeholder function for georeferencing a place name"""
        raise NotImplementedError

    def process_one(self, field, **kwargs):
        """Prepares, tests, and georeferences one field using the current pipe

        Returns:
            List of MatchResult objects
        """
        self.prepare(field)
        results = []
        for feature in self.features:
            sites = []
            terms_checked = [feature.verbatim]
            terms_matched = []
            if self.test(feature) and feature.variants():
                result = self.georeference(feature, **kwargs)
                if result:
                    sites = result.sites
                    if result.terms_checked:
                        terms_checked = result.terms_checked
                        # Terms matched may include terms outside of checked because
                        # of how the script handles subsections
                        terms_matched = [feature.verbatim]
                        for site in result.sites:
                            terms_matched.append(site.filter["name"])
                            for rel in site.related_sites:
                                terms_matched.append(rel.filter["name"])
                    else:
                        terms_matched = [feature.verbatim]
                    # Verify that the pipe provided properly formatted output
                    assert [isinstance(s, Site) for s in sites]
            fld_name = field["field"]
            result = MatchResult(sites, fld_name, terms_checked, terms_matched)
            results.append(result)
        return results

    def process(self, site=None, **kwargs):
        """Processes all fields in the current site"""
        if site is not None:
            self.site = site
        if not self.prepared:
            self.prepare_all()
        results = []
        for field in CONFIG["georeferencing"]["ordered_field_list"]:
            if field["field"].rstrip("0123456789") in self.populated:
                results.extend(self.process_one(field, **kwargs))
        if not self.populated:
            raise ValueError(f"No place names found in site: {repr(site)}")
        return results

    def extract(self, site=None):
        """Extracts a list of a features from a site"""
        if site is not None:
            self.site = site
        features = {}
        for field in CONFIG["georeferencing"]["ordered_field_list"]:
            field = field["field"]
            if not field.endswith(tuple("0123456789")):
                vals = getattr(site, field)
                if not isinstance(vals, list):
                    vals = [vals]
                for val in vals:
                    features.setdefault(field, []).extend(self.parse(val)[0])
        return features

    def match_site(self, feature, refsite, pipes=None, **kwargs):
        """Matches a feature using provided pipes"""
        if pipes is None:
            pipes = self.pipes
        base = pipes[0].load(refsite).prepare_all()
        for pipe in pipes:
            result = pipe.copy_from(base).georeference(feature, **kwargs)
            if result:
                return result.sites
        return []

    def get(self, feature, parser=None):
        """Returns a parsed feature, parsing a string if necessary"""
        if parser is None:
            parser = self.parser
        if not isinstance(feature, parser):
            try:
                parsed = self.parser(feature.verbatim)
            except AttributeError:
                parsed = self.parser(feature)
            parsed.expand(self.site, self.interpreted)
            return parsed
        return feature

    def parse(self, val):
        """Parses verbatim locality into features"""
        return self.site.parse_locality(val)

    def build_site(self, name, attributes=None, **kwargs):
        """Constructs a site summarizing a georeference"""
        if attributes is not None:
            attributes = ["country", "state_province", "county"]
        site = self.site.copy(attributes)
        with mutable(site):
            site.site_names = [name]
            for attr, val in kwargs.items():
                setattr(site, attr, val)
        # The pipe used to match features for directions, etc. does not
        # include the field attribute, so add that here
        site.filter["name"] = site.locality
        site.field = self.field
        return site

    def find(self, val, attributes=None):
        """Finds all fields containing a given value"""
        found = {}
        for field in CONFIG["georeferencing"]["ordered_field_list"]:
            attr = field["field"].strip("0123456789")
            refval = getattr(self.site, attr)
            if val == refval:
                found[attr] = 1
            elif isinstance(refval, list) and val in refval:
                found[attr] = 1
        return found

    def interpret(self):
        """Interprets parsed features in context of the original site"""
        interpreted = {}
        for vals in self.prepared.values():
            for feature in vals:
                features = []
                if isinstance(feature, MultiFeatureParser):
                    for features in feature.features:
                        for feature in features:
                            key = feature.feature_kind
                            name = feature.feature
                            interpreted.setdefault(key, []).append(name)
                elif isinstance(feature, FeatureParser):
                    key = feature.feature_kind
                    name = feature.feature
                    interpreted.setdefault(key, []).append(name)
        interpreted = {k: sorted(set(v)) for k, v in interpreted.items()}
        self.interpreted = interpreted
        return self

    def add_filter(self, site=None):
        """Generates a filter noting what fields were used in the match

        The filter is also used during annotation to generate site names.
        """
        if site is None:
            site = self.site
        site.filter = {"name": site.name}
        for attr, code in (
            ("county", "admin_code_2"),
            ("state_province", "admin_code_1"),
            ("country", "country_code"),
        ):
            if getattr(site, attr) or getattr(site, code):
                site.filter[code] = 1

    def copy_from(self, pipe):
        """Copies attributes from another pipe"""
        for attr in (
            "_site",
            "std_site",
            "prepared",
            "interpreted",
            "populated",
            "leftovers",
        ):
            setattr(self, attr, getattr(pipe, attr))
        return self


class Georeference:
    def __init__(self, sites, terms_checked=None):
        self.sites = sites
        self.terms_checked = terms_checked if terms_checked else []

    def __bool__(self):
        return bool(self.sites)


# Define deferred class attributes
LazyAttr(MatchPipe, "std", LocStandardizer, allow_numbers=True)
