"""Defines class to convert direction strings to geometries"""

from .core import MatchPipe, Georeference
from .match_border import MatchBorder
from .match_custom import MatchCustom
from .match_geonames import MatchGeoNames
from ....tools.geographic_names.parsers import DirectionParser, MultiFeatureParser


class MatchDirection(MatchPipe):
    """Converts direction strings to geometries"""

    parser = DirectionParser

    def __init__(self, pipes=None):
        super().__init__()
        self.pipes = pipes if pipes else [MatchCustom(), MatchGeoNames()]

    def test(self, feature):
        """Tests if matcher is applicable to the given locality string"""
        return feature and feature.kind == "direction"

    def georeference(self, feature):
        """Georeferences a direction string"""
        parsed = self.get(feature)
        sites = []
        # Match all options and let evaluator sort things out
        for refsite in self.georeference_feature(parsed.feature):
            refsite.field = self.field
            dist, precision = parsed.dist_km_with_precision()
            # DirectionParser assigns unknown distances a precision of 1,
            # but this does not carry over for large, well-constrained
            # features like countries.
            if not parsed.min_dist and not parsed.max_dist:
                dist = None
            kwargs = {"rel_err_distance": precision}
            geom = refsite.smart_translate(parsed.bearing, dist, **kwargs)
            site = self.build_site(
                str(parsed),
                location_id=refsite.location_id + "_DIR",
                site_kind="direction",
                site_source=parsed.__class__.__name__,
                locality=str(parsed),
                geometry=geom,
                related_sites=[refsite],
                filter=refsite.filter.copy(),
                sources=refsite.sources,
            )
            sites.append(site)
        return Georeference(sites)

    def georeference_feature(self, feature):
        """Georeferences a named feature using GeoNames"""
        if isinstance(feature, str):
            try:
                feature = MultiFeatureParser(feature)
            except ValueError:
                # FIXME: Junctions fail here
                return []
        # FIXME: Implement georeferencing for junctions
        if str(feature).lower().startswith(("junction of", "off of")):
            return []
        if str(feature).lower().startswith("border of"):
            pipes = [MatchBorder(self.pipes)]
            kwargs = {}
        else:
            pipes = self.pipes
            kwargs = {"codes": [], "size": "small"}
        fields = ["country", "state_province", "county"]
        for i in range(len(fields)):
            if i:
                fields.pop()
            refsite = self.site.copy(fields[:])
            matches = self.match_site(feature, refsite, pipes, **kwargs)
            if matches:
                # Exclude rivers from directions if other locations found
                nonstreams = [s for s in matches if not s.site_kind.startswith("STM")]
                return nonstreams if nonstreams else matches
        return []
