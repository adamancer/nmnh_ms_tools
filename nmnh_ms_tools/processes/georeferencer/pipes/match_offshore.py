"""Defines class to convert offshore strings to geometries"""

from .core import MatchPipe, Georeference
from .match_border import MatchBorder
from .match_custom import MatchCustom
from .match_geonames import MatchGeoNames
from ....tools.geographic_names.parsers import MultiFeatureParser, OffshoreParser


class MatchOffshore(MatchPipe):
    """Converts offshore strings to geometries"""

    parser = OffshoreParser

    def __init__(self, pipes=None):
        super(MatchOffshore, self).__init__()
        self.pipes = pipes if pipes else [MatchCustom(), MatchGeoNames()]

    def test(self, feature):
        """Tests if matcher is applicable to the given locality string"""
        if feature:
            is_offshore_1 = feature.kind == "offshore"
            is_offshore_2 = (
                feature.kind == "multifeature" and feature.feature_kind == "offshore"
            )
            return is_offshore_1 or is_offshore_2
        return False

    def georeference(self, feature):
        """Georeferences a direction string"""
        parsed = self.get(feature)
        name = parsed.feature
        if parsed.kind == "multifeature":
            name = parsed.features[0][0].feature
        sites = []
        # Match all options and let evaluator sort things out
        for refsite in self.georeference_feature(name):
            refsite.field = self.field
            site = self.create_site(
                str(parsed),
                location_id=refsite.location_id + "_OFF",
                site_kind="offshore",
                site_source=parsed.__class__.__name__,
                locality=str(parsed),
                geometry=refsite.geometry,
                related_sites=[refsite],
                filter=refsite.filter,
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
            refsite = self.site.clone(fields)
            matches = self.match_site(feature, refsite, pipes, **kwargs)
            if matches:
                return matches
        return []
