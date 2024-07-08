"""Defines class to convert between strings to geometries"""

import itertools

from .core import MatchPipe, Georeference
from .match_custom import MatchCustom
from .match_geonames import MatchGeoNames
from ..evaluators import MatchEvaluator
from ....tools.geographic_names.parsers import BetweenParser, MultiFeatureParser
from ....tools.geographic_operations.geometry import GeoMetry


class MatchBetween(MatchPipe):
    """Converts parsed between strings to geometries"""

    parser = BetweenParser

    def __init__(self, pipes=None):
        super(MatchBetween, self).__init__()
        self.pipes = pipes if pipes else [MatchCustom(), MatchGeoNames()]

    def test(self, feature):
        """Tests if matcher is applicable to the given locality string"""
        return feature and feature.kind == "between"

    def georeference(self, feature):
        """Georeferences a between string"""
        parsed = self.get(feature)
        # Locate the parsed features name using GeoNames
        refsites = []
        for feature in parsed.features:
            refsites_ = self.georeference_feature(feature)
            # Pass field attribute to refsite
            for refsite in refsites_:
                refsite.field = self.field
            if refsites_:
                refsites.append(refsites_)
        # FIXME: Handle combinations of more than two features. Existing
        #        code can theoretically handle those but is incredibly slow.
        sites = []
        if len(refsites) == len(parsed.features) == 2:
            for refsites in itertools.product(*refsites):
                refsites = list(refsites)
                location_id = "_".join([s.location_id for s in refsites])
                evaluator = MatchEvaluator(self.site, None)
                encircled = evaluator.encompass_sites(refsites)
                # Decrease radius by 50% because we know we're between the sites
                radius_km = encircled.radius_km
                if not parsed.inclusive:
                    radius_km /= 2
                # Get list of sources
                sources = []
                for refsite in refsites:
                    sources.extend(refsite.sources)
                sources = sorted(set(sources))
                # Create site summarizing the match
                geom = GeoMetry(encircled, radius_km=radius_km)
                site = self.create_site(
                    str(parsed),
                    location_id=location_id + "_BETWEEN",
                    site_kind="between",
                    site_source=parsed.__class__.__name__,
                    locality=str(parsed),
                    geometry=geom,
                    related_sites=refsites,
                    sources=sources,
                )
                sites.append(site)

        # Prefer sites compare similar features
        same_class = []
        same_code = []
        for site in sites:
            if len({s.site_kind for s in site.related_sites}) == 1:
                same_code.append(site)
            elif len({s.site_class for s in site.related_sites}) == 1:
                same_class.append(site)
        if same_code:
            sites = same_code
        elif same_class:
            sites = same_class

        return Georeference(sites)

    def georeference_feature(self, feature):
        """Georeferences a named feature using GeoNames"""
        if isinstance(feature, str):
            feature = MultiFeatureParser(feature)
        kwargs = {"codes": [], "size": "small"}
        fields = ["country", "state_province", "county"]
        for i in range(len(fields)):
            if i:
                fields.pop()
            refsite = self.site.clone(fields)
            matches = self.match_site(feature, refsite, self.pipes, **kwargs)
            if matches:
                return matches
        return []
