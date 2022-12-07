"""Extracts features from strings"""
import logging

logger = logging.getLogger(__name__)

import pprint as pp
import re

from .core import Parser
from .feature import is_generic_feature


class SimpleParser(Parser):
    """Parses apparent features not matched by any of the other parsers"""

    kind = "simple"
    attributes = [
        "kind",
        "verbatim",
        "unconsumed",
        "feature",
    ]

    def __init__(self, *args, **kwargs):
        super(SimpleParser, self).__init__(*args, **kwargs)

    def name(self):
        """Returns a string describing the parsed locality"""
        return self.feature

    def parse(self, val, test_generic=True):
        """Parses a locality string to extract usable geographic information"""
        val = val.strip()
        # Exclude generic features
        if test_generic and is_generic_feature(val):
            raise ValueError("Could not parse: {}".format(val))
        # Exclude values with common delimiters
        if re.search(r"(,|;|:|(?!\b[A-Z])\.)", val):
            raise ValueError("Could not parse: {}".format(val))
        self.verbatim = val
        self.feature = val
        # Not possible to calculate these?
        self.domain = None
        self.feature_kind = None
        self.specific = None
        return self
