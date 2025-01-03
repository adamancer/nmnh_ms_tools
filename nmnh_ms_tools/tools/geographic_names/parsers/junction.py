"""Defines class to parse roads and junctions"""

import re

from .core import Parser
from ....utils import RE, oxford_comma


ROAD_TYPES = {
    "ave": "avenue",
    "blvd": "boulevard",
    "dr": "drive",
    "hwy": "highway",
    "rd": "road",
    "rt": "route",
    "st": "street",
    "tr": "trail",
    "way": "way",
}
ROADS = list(ROAD_TYPES.keys()) + list(ROAD_TYPES.values())


class JunctionParser(Parser):
    """Parses roads and junctions"""

    kind = "junction"
    attributes = ["kind", "verbatim", "feature", "features"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def parse(self, val):
        """Parses roads and junctions"""
        self.verbatim = val.strip()
        self.features = get_junction(val)
        if not self.features:
            road = get_road(val)
            if road:
                self.features = [road]
        if self.features:
            self.feature = self.name()
            self.feature_kind = "road"
            self.specific = True
            return self
        raise ValueError(f"Could not parse {repr(val)}")

    def name(self):
        """Returns a string describing the parsed locality"""
        name = []
        if len(self.features) > 1:
            return f"Junction of {oxford_comma(self.features)}"
        elif len(self.features) == 1:
            return self.features[0]
        raise ValueError(f"Could not derive name: {repr(self)}")


def get_road_pattern():
    """Returns simplistic pattern to match a road name"""
    return r"({feature}|{highway})"


def get_roads_pattern():
    """Returns pattern to match"""
    return r"{0} (?:and|with|&) {0}".format(get_road_pattern())


def is_road(val):
    """Tests if string appears to be a valid road name"""
    val = val.strip()
    if re.search(r"\bat\b", val, flags=re.I):
        return False
    is_highway = RE.search(r"\b{highway}\b", val)
    is_feature = RE.search(r"\b{feature}\b", val)
    is_street = RE.search(rf"\b({"|".join(ROADS)})\b", val, flags=re.I)
    return is_highway or (is_feature and is_street and val.lower() not in ROADS)


def get_road(val):
    """Matches descriptions on a road"""
    pattern = rf"^(?:(?:along|off|on|side of) )?{get_road_pattern()}$"
    match = RE.search(pattern, val)
    if match is not None and is_road(match.group(1)):
        return match.group(1)


def get_junction(val):
    """Matches road intersections"""
    match = RE.search(
        rf"\b(?:intersection|jct|junction) (?:(?:between|of|with) )?{get_roads_pattern()}\b",
        val,
        flags=re.I,
    )
    if match is not None:
        roads = [match.group(1), match.group(2)]
        if all([is_road(r) for r in roads]):
            return roads
    # Junctions referencing features defined elsewhere
    pattern = (
        rf"\b(?:beyond|it\'?s|past) (?:intersection|jct|junction)"
        rf" (?:between|of|with) ({get_road_pattern()})\b"
    )
    match = RE.search(pattern, val, flags=re.I)
    if match is not None and is_road(match.group(1)):
        return ["{road}", match.group(1)]
