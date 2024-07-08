"""Defines class to parse stratigraphic unit names"""

from .core import Parser


class StratParser(Parser):
    """Parses stratigraphic unit names"""

    kind = "junction"
    attributes = ["kind", "verbatim", "feature", "features"]

    def parse(self, val):
        raise NotImplementedError

    def name(self):
        """Returns a string describing the parsed locality"""
        raise NotImplementedError
