"""Defines class to parse localities falling between two named features"""

import logging
import re

from .core import Parser
from .feature import FeatureParser, append_feature_type
from ....utils import oxford_comma


logger = logging.getLogger(__name__)


class BetweenParser(Parser):
    """Parses localities between two named localities"""

    kind = "between"
    attributes = ["kind", "verbatim", "unconsumed", "features", "inclusive"]
    quote = True

    def __init__(self, *args, **kwargs):
        self.features = None
        self.inclusive = False
        self.specific = None
        super().__init__(*args, **kwargs)

    @property
    def feature(self):
        return oxford_comma(self.features)

    @feature.setter
    def feature(self, features):
        self.features = features

    def name(self):
        """Returns a string describing the parsed locality"""
        if self.features and not self.inclusive:
            return f"Between {self.feature}"
        elif self.features:
            return self.feature
        return ""

    def parse(self, text):
        """Parses a locality string to extract usable geographic information"""
        self.verbatim = text
        # Extract between string and test feature names
        delim = r"(?:between|from)(?: the )?"
        if not re.search(delim, text, flags=re.I):
            self.inclusive = True
            raise ValueError(f"Could not parse {repr(text)}")
        else:
            pre, text = re.split(delim, text, 1, flags=re.I)
            # Check pre for common delimiters
            if re.search(r"[,;:]", pre):
                raise ValueError(
                    f"Could not parse: {repr(pre + delim + text)} (too complex)"
                )
        between = text.rstrip("() ")
        delim = r"(?:\band\b|\bor\b|\bto\b|&|\+|,|;)(?: the )?"
        features = re.split(delim, between, flags=re.I)
        features = [s.strip() for s in features if s.strip()]
        if len(features) < 2:
            raise ValueError(f"Could not parse {repr(text)}")
        # Test feature names using FeatureParser
        for feature in features:
            try:
                FeatureParser(feature)
            except ValueError:
                raise ValueError(f"Could not parse {repr(text)}")
        self.features = append_feature_type(features)
        self.specific = True
        return self
