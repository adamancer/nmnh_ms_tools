"""Defines class to convert border strings to geometries"""

import itertools

from .core import MatchPipe, Georeference
from .match_custom import MatchCustom
from .match_geonames import MatchGeoNames
from ....tools.geographic_names.parsers import BorderParser, MultiFeatureParser


class MatchBorder(MatchPipe):
    """Converts parsed border strings to geometries"""

    parser = BorderParser

    def __init__(self, pipes=None):
        super(MatchBorder, self).__init__()
        self.pipes = pipes if pipes else [MatchCustom(), MatchGeoNames()]

    def test(self, feature):
        """Tests if matcher is applicable to the given locality string"""
        if feature:
            is_border_1 = feature.kind == "border"
            is_border_2 = (
                feature.kind == "multifeature" and feature.feature_kind == "border"
            )
            return is_border_1 or is_border_2
        return False

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
                # Calculate overlap of slightly enlarged polygons
                geoms = [s.geometry for s in refsites]
                if geoms[0].disjoint(geoms[1]):
                    geoms = [s.resize(1.05) for s in refsites]
                    if geoms[0].disjoint(geoms[1]):
                        continue
                location_id = "_".join([s.location_id for s in refsites])
                geom = geoms[0].intersection(geoms[1])
                # Get list of sources
                sources = []
                for refsite in refsites:
                    sources.extend(refsite.sources)
                sources = sorted(set(sources))
                # Create site summarizing the match
                site = self.create_site(
                    str(parsed),
                    location_id=location_id + "_BORDER",
                    site_kind="border",
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
        # Unlike most features that we'd like to match on, borders can be very
        # large, so allow the georeference to fall back to large features.
        kwargs = {"codes": [], "size": "normal"}
        fields = ["country", "state_province", "county"]
        for i in range(len(fields)):
            if i:
                fields.pop()
            refsite = self.site.clone(fields)
            matches = self.match_site(feature, refsite, self.pipes, **kwargs)
            if matches:
                return matches
        return []
