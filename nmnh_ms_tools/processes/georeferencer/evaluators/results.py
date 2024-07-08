"""Defines class for summarizing result of a match operation"""

import logging


logger = logging.getLogger(__name__)


class MatchResult:
    """Summarizes the results of a matching operation"""

    def __init__(self, sites, field, terms_checked, terms_matched, related_sites=None):
        self.sites = sites if isinstance(sites, list) else [sites]
        self.field = field if field else "locality"
        self.terms_checked = set(terms_checked)
        self.terms_matched = set(terms_matched)
        self.related_sites = related_sites

    def __repr__(self):
        attributes = ["sites", "field", "terms_checked", "terms_matched"]
        attrs = ["{}={}".format(a, getattr(self, a)) for a in attributes]
        return "{}({})".format(self.__class__.__name__, ", ".join(attrs))

    def __iter__(self):
        return iter(self.sites)

    def __len__(self):
        return len(self.sites) if self else 0

    def __bool__(self):
        return bool(self.sites)
