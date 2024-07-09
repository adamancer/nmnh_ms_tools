"""Defines class to parse borders between two named features"""

import re

from .core import Parser
from .feature import append_feature_type
from ....utils import oxford_comma


ADMINS = ["country", "county", "state"]
BORDERS = [
    "border",
    "boundary",
    "line",
]


class BorderParser(Parser):
    """Parses borders between two named localities"""

    kind = "border"
    attributes = ["kind", "verbatim", "feature", "features"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def parse(self, val):
        self.verbatim = val
        self.features = get_bordering(val)
        if self.features:
            self.feature = self.name()
            self.feature_kind = "border"
            self.specific = False
            return self
        raise ValueError('Could not parse "{}"'.format(val))

    def name(self):
        """Returns a string describing the parsed locality"""
        return "Border of {}".format(oxford_comma(self.features))


def get_feature_pattern():
    """Returns simplistic pattern to match feature"""
    return r"([A-Z][a-z\-]{2,}(?: ?[A-Z][a-z\-]{2,}){,2})"


def get_features_pattern():
    """Returns pattern to match feautres"""
    return r"{0}(?:(?: ?(-|/|and) ?){0})?".format(get_feature_pattern())


def is_border(val):
    """Tests if string appears to be a valid border description"""
    p1 = get_features_pattern()
    mask = r"(^border (of|between)|border$|({}) ({})$)"
    p2 = mask.format("|".join(ADMINS), "|".join(BORDERS))
    return bool(re.search(p1, val, flags=re.I) and re.search(p2, val, flags=re.I))


def get_bordering(val):
    """Returns bordering features"""
    if is_border(val):
        match = re.search(get_features_pattern(), val)
        # Forbid matches on terms from ADMINS or BORDERS
        last = None
        while match and match.group().lower() in (ADMINS + BORDERS):
            start = len(match.group()) + 1
            match = re.search(get_features_pattern(), val[start:])
            if match and last and match.group() == last.group():
                return
            last = match
        if match:
            border = match.group()
            # Include county in name if county line
            if re.search(r"county", val, flags=re.I) and not re.search(
                r"county", border, flags=re.I
            ):
                border += " County"
            # Pluralize county if needed
            if border.lower().count("county") == 1:
                border = re.sub(r"\bcounty\b", "Counties", border, flags=re.I)
            # Remove border, line, etc.
            admins = [a for a in ADMINS if a != "county"]
            mask = r"(({}) )?({})$"
            pattern = mask.format("|".join(admins), "|".join(BORDERS))
            border = re.sub(pattern, "", border, flags=re.I).strip()
            # Find and expand features
            features = re.findall(get_feature_pattern(), border)
            if len(features) == 1:
                features = features[0].split("-")
            if len(features) >= 2:
                features = append_feature_type(features)
                return features
