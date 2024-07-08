"""Defines class to parse offshore localities"""

import re

from .core import Parser
from .border import BorderParser
from .feature import FeatureParser, get_feature_string
from .junction import is_road
from .modified import ModifiedParser
from ....utils import oxford_comma


OFFSHORE = [
    r"approach(?:es)? to(?: the)?",
    r"entrance(?:s) (?:of|to)(?: the)?",
    r"off(?: of)?(?: the)?",
    r"offshore(?: of)?(?: the)?",
]


class OffshoreParser(Parser):
    """Parses offshore localities

    For example, "Off the coast of Maine." Because extending a polygon
    into the ocean is fairly complex, this parser only identifies a name
    as being a likely marine locality and returns the geometry of the
    reference feature. Extending the polygon is handled by evaluator.
    """

    kind = "offshore"
    attributes = ["kind", "verbatim", "feature"]

    def __init__(self, *args, **kwargs):
        super(OffshoreParser, self).__init__(*args, **kwargs)

    def parse(self, val):
        feature = get_offshore(val)
        if feature:
            self.verbatim = val
            self.feature = feature
            self.feature_kind = "offshore"
            self.specific = True
            return self
        raise ValueError('Could not parse "{}"'.format(val))

    def name(self):
        """Returns a string describing the parsed locality"""
        return "Off of {}".format(self.feature)


def get_offshore(val):
    """Matches offshore features"""
    pattern = r"^(?:{}) (.*)$".format("|".join(OFFSHORE))
    match = re.match(pattern, val, flags=re.I)
    if match is not None:
        feature = match.group(1)
        if not is_road(feature):
            for parser in (BorderParser, ModifiedParser, FeatureParser):
                try:
                    return get_feature_string(parser(feature))
                except ValueError:
                    pass
