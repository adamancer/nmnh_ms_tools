"""Defines class to capture manually georeferenced terms"""

from .core import MatchPipe, MatchResult


class MatchManual(MatchPipe):
    """Capture manually matched features"""

    def __init__(self):
        super().__init__()

    def process(self, site=None, **kwargs):
        """Processes all fields in the current site"""
        if site is not None:
            self.site = site
        results = []
        for (field, val), site in self.site.interpreted.items():
            self.add_filter(site)
            results.append(
                MatchResult(
                    sites=[site],
                    field=field,
                    terms_checked={val},
                    terms_matched={val},
                )
            )
        return results
