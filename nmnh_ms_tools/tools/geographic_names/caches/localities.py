"""Defines class for caching parsed locality strings"""

import json

from ....databases.cache import CacheDict
from ....tools.geographic_names.parsers.between import BetweenParser
from ....tools.geographic_names.parsers.border import BorderParser
from ....tools.geographic_names.parsers.direction import DirectionParser
from ....tools.geographic_names.parsers.feature import FeatureParser
from ....tools.geographic_names.parsers.modified import ModifiedParser
from ....tools.geographic_names.parsers.multifeature import MultiFeatureParser
from ....tools.geographic_names.parsers.plss import PLSSParser
from ....tools.geographic_names.parsers.simple import SimpleParser


PARSERS = {
    "BetweenParser": BetweenParser,
    "BorderParser": BorderParser,
    "DirectionParser": DirectionParser,
    "FeatureParser": FeatureParser,
    "ModifiedParser": ModifiedParser,
    "MultiFeatureParser": MultiFeatureParser,
    "PLSSParser": PLSSParser,
    "SimpleParser": SimpleParser,
}


class LocalityCache(CacheDict):
    """Caches parses of locality strings"""

    def __init__(self, path=None):
        super().__init__()
        if path is not None:
            self.init_db(path)

    @staticmethod
    def writer(vals):
        """Stores features as verbatim plus parser and includes leftovers"""
        if not vals[0]:
            return None
        features, leftover = vals
        features = [(f.__class__.__name__, f.verbatim) for f in features]
        return json.dumps([features, leftover])

    @staticmethod
    def reader(row):
        """Reinflates verbatim values using the named parser"""
        if row.val is None:
            return [], row.key
        features, leftover = json.loads(row.val)
        return [PARSERS[parser](verb) for parser, verb in features], leftover
