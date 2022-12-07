"""Defines class to convert PLSS strings to geometries"""
from .core import MatchPipe, Georeference
from ..evaluators.results import MatchResult
from ....bots.plss import PLSSBot
from ....tools.geographic_names.parsers import PLSSParser


class MatchPLSS(MatchPipe):
    """Converts PLSS strings to geometries"""

    parser = PLSSParser
    bot = PLSSBot()

    def __init__(self):
        super(MatchPLSS, self).__init__()

    def test(self, feature):
        """Tests if matcher can be used on the given locality string"""
        return feature and feature.kind == "plss"

    def georeference(self, feature):
        """Uses BLM webservice to georeference a PLSS string"""
        parsed = self.get(feature)
        for state in self.site.admin_code_1:
            sites = self._georeference(parsed, state)
            if sites:
                return sites
        return

    def _georeference(self, parsed, state):
        """Uses BLM webservice to georeference a PLSS string"""
        if len(state) != 2 or not state.isupper():
            raise ValueError("State must be a two-letter abbreviation")
        boxes = self.bot.get_sections(state, parsed.twp, parsed.rng, parsed.sec)
        sites = []
        for box in boxes:
            related_sites = []
            # Quarter sections increase in specificity from right to left,
            # so reverse the order for calculating subsections
            qtrs = [None] + parsed.qtr[::-1]
            for i, div in enumerate(qtrs):
                divs = ""
                if div is not None:
                    box = box.subsection(div)
                    divs = " ".join(qtrs[1 : i + 1][::-1])
                name = " ".join([divs, parsed.sec, parsed.twp, parsed.rng])
                site = self.create_site(
                    '"{}"'.format(name.strip()),
                    site_kind="plss",
                    site_source=parsed.__class__.__name__,
                    geometry=box,
                    locality='"{}"'.format(name.strip()),
                    sources=["BLM GIS webservices"],
                )
                site.field = self.field
                # Update location ID with direction info
                if divs:
                    site.location_id = "{}_{}".format(site.location_id, divs)
                related_sites.append(site)
            site = related_sites.pop(-1)
            site.site_names[0] = str(parsed)
            site.related_sites = related_sites
            site.sources = ["BLM GIS webservices"]
            # Manually add the site filter
            for site_ in [site] + site.related_sites:
                site_.filter = {
                    "name": site_.locality,
                    "country_code": 1,
                    "admin_code_1": 1,
                    "admin_code_2": 1,
                }
            sites.append(site)
        return Georeference(sites)
