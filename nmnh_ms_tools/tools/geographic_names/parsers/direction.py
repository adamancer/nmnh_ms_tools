"""Defines methods to parse directions and bearings"""

import logging
import math
import re
from fractions import Fraction

from titlecase import titlecase
from unidecode import unidecode

from .core import Parser
from .feature import get_feature_string
from .multifeature import MultiFeatureParser
from ....utils.standardizers import LocStandardizer
from ....utils import (
    as_numeric,
    lcfirst,
    num_dec_places,
    to_digit,
    validate_direction,
)


logger = logging.getLogger(__name__)


class DirectionParser(Parser):
    """Parses a simple direction into its component parts"""

    kind = "direction"
    attributes = [
        "kind",
        "verbatim",
        "unconsumed",
        "min_dist",
        "max_dist",
        "unit",
        "bearing",
        "feature",
    ]

    def __init__(self, *args, **kwargs):
        self._units = {
            r"f(?:oo|ee)?t\b": "ft",
            r"m(?:et[er]{2})?s?\b": "m",
            r"k(?:ilo)?m(?:et[er]{2})?s?\b": "km",
            r"mi(?:les?)?\b": "mi",
            r"y(?:ar)?ds?\b": "yd",
        }
        self._bearings = {
            r"n(?:orth)?\.?": "N",
            r"s(?:outh)?\.?": "S",
            r"e(?:ast)?\.?": "E",
            r"w(?:est)?\.?": "W",
        }
        self._to_km = {
            "ft": 0.0003048,
            "km": 1,
            "m": 0.001,
            "mi": 1.609344,
            "yd": 0.0009144,
        }
        # Values used for distance calculations if directions only
        # specify a bearing
        self.defaults = {"min_dist_km": 0, "max_dist_km": 16, "unit": "km"}
        self._min_dist = None
        self._max_dist = None
        self._unit = None
        self._bearing = None
        self._feature = None
        self.precision = None
        super(DirectionParser, self).__init__(*args, **kwargs)

    @property
    def min_dist(self):
        return self._format_distance(self._min_dist)

    @min_dist.setter
    def min_dist(self, min_dist):
        self._min_dist = min_dist

    @property
    def max_dist(self):
        return self._format_distance(self._max_dist)

    @max_dist.setter
    def max_dist(self, max_dist):
        self._max_dist = max_dist

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, unit):
        self._unit = self._format_unit(unit)

    @property
    def bearing(self):
        return self._bearing

    @bearing.setter
    def bearing(self, bearing):
        self._bearing = self._format_bearing(bearing)

    @property
    def feature(self):
        return self._feature

    @feature.setter
    def feature(self, feature):
        self._feature = self._format_feature(feature)

    @property
    def specific(self):
        dist_km = self.avg_dist_km()
        return bool(self._min_dist or self._max_dist) and dist_km <= 16

    def set_precision(self, dists):
        """Calculates precision for a distance based on MaNIS guidelines"""
        dists = sorted([d for d in dists if d], key=float)
        # Assume a 100% error if no distance given
        if not dists:
            return 1
        # Assume that ranges define their own precision
        if len(set(dists)) > 1:
            min_dist = as_numeric(dists[0])
            max_dist = as_numeric(dists[-1])
            dec_places = min([num_dec_places(d, 2) for d in dists])
            return round((max_dist - min_dist) / 2, dec_places)
        # Calculate uncertainties based on guidelines
        dist = max(dists)
        # Distance is decimal
        if "." in dist:
            dec = dist.split(".")[1]
            # Treat 0.0 same as 0.1
            if not dec.strip("0"):
                dec = 1
            prec = 1 / Fraction("0.{}".format(dec)).denominator
            return prec / as_numeric(dist)
        # Distance is fraction
        if "/" in dist:
            prec = 1 / Fraction(dist.split(" ")[-1]).denominator
            return prec / as_numeric(dist)
        # Distance is integer
        dist = int(float(dist))
        if not dist % 10:
            prec = 0.5 * 10 ** math.floor(math.log10(dist))
        else:
            # Default to a 10% uncertainty
            prec = math.ceil(0.1 * dist)
        # Convert to relative precision
        return prec / as_numeric(dist)

    def precision_km(self):
        """Converts relative precision to absolute distance in km"""
        unit = self.unit if self.unit else self.defaults["unit"]
        max_dist_km = max([d for d in self.dists_km() if d])
        return max_dist_km * self.precision

    def along_route(self):
        """Tests if direction is along a road, trail, or similar"""
        return re.search(r"\b(road|trail)\b", self.verbatim, flags=re.I)

    def name(self):
        """Returns a string describing the parsed locality"""
        if self.along_route():
            dist = self.max_dist
        else:
            dists = [d for d in [self._min_dist, self._max_dist] if d]
            dist = "-".join(sorted(set(dists)))
        feature = self._format_feature()
        if feature.startswith(("Border of", "Junction of")):
            feature = lcfirst(feature)
        if dist and self.unit and self.bearing and self.feature:
            return "{} {} {} of {}".format(dist, self.unit, self.bearing, feature)
        elif not self.unit and not dist and self.bearing and self.feature:
            return "{} of {}".format(self.bearing, feature)
        raise ValueError('Could not derive name: "{}"'.format(repr(self)))

    def parse(self, text):
        """Parses a simple direction string (e.g., 1 km N of Tacoma)"""

        if re.search(r"\bbetween\b", text, flags=re.I):
            raise ValueError('Could not parse "{}" (between)'.format(text))

        if re.search(r"\b(&|and) \d", text, flags=re.I):
            mask = 'Could not parse "{}" (composite direction)'
            raise ValueError(mask.format(text))

        self.verbatim = text.strip()
        text = self.verbatim
        # Convert distances to digits
        units = "|".join(self._units).replace("{", "{{").replace("}", "}}")
        mask = r"\b({{}})(?=[ -](?:{}))".format(units)
        text = to_digit(text, mask=mask)
        # Strip parentheses
        if re.match(r"^\(.*?\)$", text):
            text = text[1:-1]
        ascii_text = unidecode(text).lstrip(" ")
        mod1 = r"(?:[a-z\-\']+\.?(?: [a-z\-\']+)* )?"
        mod2 = (
            r"(?: or so| \(?(?:air(?:line)?|map|naut(?:ical)?|road|trail)"
            r"(?: distance)?\)?)?"
        )
        mod3 = (
            r"(?:due |\(?by [a-z\-\']+\)? |(?:up|down)stream from "
            r"|\((?:air(?:line)?|map|road|trail)(?: distance)?\) )?"
        )
        num = r"(\d+/\d+|\d*(?:\.\d+| \d/\d)?)"
        nums = r"{0}(?: ?(?:\-|or|to) ?{0})?".format(num)
        units = "|".join(list(self._units.keys()))
        dirs = "|".join(list(self._bearings.keys()))
        dirs = r"(?:{0}){{1,2}}(?: ?\d* ?(?:{0}))?".format(dirs)
        mask = r"{mod1}(?:{nums}{mod2} ?({units}) )?{mod3}({dirs})"
        bearing = mask.format(
            mod1=mod1, nums=nums, mod2=mod2, units=units, mod3=mod3, dirs=dirs
        )
        feature = r"([^,\(]+)"
        # feature = get_any_feature_pattern()
        # feature = r'((?:mt\.? )?[a-z \-\']+?)'
        # feature = r'(?:[a-z\-\']+\.?(?: [a-z\-\']+)*)'
        mod = r"(?: [a-z]+ (?:of|in))?"
        patterns = [
            r"{0} (?:de|of|from){2} {1}",  # 1 km N of Ellensburg
            r"{1} \({0}(?: (?:de|of|from){2})?\s*\)",  # Ellensburg(1 km N of)
            r"{1}, {0}(?: (?:de|of|from){2})?",  # Ellensburg, 1 km N of
            r"{0}{2} {1}",  # 1 km N Ellensburg
        ]
        mask = r"^(?:{})(?=(?:$|[,;\.\|]| \d| (?:N|S|E|W){{1,3}}\b))"
        pattern = mask.format("|".join(patterns).format(bearing, feature, mod))
        match = re.search(pattern, ascii_text, flags=re.I)
        # Try to extract a complete pattern from a string that contains
        # additional information
        # if match is None:
        #    mask = r'^(?:{})(?=(?:$|\.| \d| (?:N|S|E|W){{1,3}}\b))'
        #    pattern = mask.format('|'.join(patterns).format(bearing, feature))
        #    match = re.search(pattern, text, flags=re.I)
        if match is not None:
            self.matched = match.group(0).strip(". ")
            self.unconsumed = text[len(self.matched) :].strip(". ")
            if self.unconsumed:
                mask = 'Could not parse: "{}" (failed to parse full string)'
                raise ValueError(mask.format(self.verbatim))
            parts = []
            for i in range(1, 50):
                try:
                    parts.append(match.group(i))
                    # print('{}. {}'.format(i, parts[-1]))
                except IndexError:
                    break
            groups = [parts[i : i + 5] for i in range(0, 20, 5)]
            if any(groups[0]):
                self.min_dist = parts[0]
                self.max_dist = parts[1]
                self.unit = parts[2]
                self.bearing = parts[3]
                self.feature = parts[4]
            elif any(groups[1]):
                self.min_dist = parts[6]
                self.max_dist = parts[7]
                self.unit = parts[8]
                self.bearing = parts[9]
                self.feature = parts[5]
            elif any(groups[2]):
                self.min_dist = parts[11]
                self.max_dist = parts[12]
                self.unit = parts[13]
                self.bearing = parts[14]
                self.feature = parts[10]
                # For this pattern to hit, the verbatim string must include
                # at least the distance or a preposition after the comma
                pattern = r",.*?\b(de|of|from)\b"
                if not (self.min_dist or self.max_dist) and not re.search(
                    pattern, self.verbatim, flags=re.I
                ):
                    raise ValueError('Could not parse "{}"'.format(text))
            elif any(groups[3]):
                self.min_dist = parts[15]
                self.max_dist = parts[16]
                self.unit = parts[17]
                self.bearing = parts[18]
                self.feature = parts[19]
                # Distance required to prevent matching modified feature names
                if not self.min_dist:
                    raise ValueError('Could not parse "{}"'.format(text))
            else:
                raise ValueError('Could not parse "{}"'.format(text))
            # Test that feature name looks OK
            parsed = MultiFeatureParser(self.feature, allow_generic=True)
            self.feature = get_feature_string(parsed)
        else:
            raise ValueError('Could not parse "{}"'.format(text))
        # Distance required for verbatim strings ending in compass directions
        if re.search(r"\b[NEWS]{1,3}$", self.verbatim) and not self.min_dist:
            mask = 'Could not parse: "{}" (distance required)'
            raise ValueError(mask.format(self.verbatim))
        # Set max_dist to min_dist if not given
        if not self._max_dist:
            self.max_dist = self._min_dist
        # Interpret distances by road or trail as maxima
        if self.min_dist == self.max_dist and self.along_route():
            self.min_dist = str(as_numeric(self.max_dist) / 2)
        # Set precision
        self.precision = self.set_precision([self._min_dist, self._max_dist])
        # Verify that required attributes have been populated
        if bool(self.min_dist) == bool(self.unit) and self.bearing and self.feature:
            logger.debug('Parsed "{}"'.format(self.verbatim))
            return self
        mask = 'Could not parse: "{}" (missing required attributes)'
        raise ValueError(mask.format(self.verbatim))

    def dists(self):
        """Calculates min and max distances in original unit"""
        unit = self.unit if self.unit else self.defaults["unit"]
        min_dist = self.min_dist
        max_dist = self.max_dist
        if min_dist is None and max_dist is None:
            min_dist = self.defaults["min_dist_km"] / self._to_km[unit]
            max_dist = self.defaults["max_dist_km"] / self._to_km[unit]
        return [as_numeric(d) for d in [min_dist, max_dist] if d is not None]

    def avg_dist(self):
        """Calculates average distance in original unit"""
        dists = self.dists()
        return sum(dists) / len(dists)

    def dists_km(self):
        """Calculates min and max distances in km"""
        unit = self.unit if self.unit else self.defaults["unit"]
        return [d * self._to_km[unit] for d in self.dists()]

    def avg_dist_km(self):
        """Calculates average distance in km"""
        dists_km = self.dists_km()
        return sum(dists_km) / len(dists_km)

    def dist_km_with_precision(self):
        """Express distance as a distance and precision"""
        dists_km = self.dists_km()
        min_dist_km = min(dists_km)
        max_dist_km = max(dists_km)
        # Incorporate estimate of precision for simple distances
        if min_dist_km == max_dist_km:
            min_dist_km -= self.precision * max_dist_km
            max_dist_km += self.precision * max_dist_km
        # Distance is return as an average, precision is the value required to
        # cover the min to max values of the range
        dist_km = (min_dist_km + max_dist_km) / 2
        precision = (max_dist_km - dist_km) / dist_km
        return dist_km, precision

    def _format_distance(self, dist):
        """Formats distance to decimal for display"""
        if dist is not None:
            dec_places = num_dec_places(dist)
            dist = as_numeric(dist)
            if not dec_places:
                return "{:,}".format(int(dist))
            return "{{:.{}f}}".format(dec_places).format(dist)
        return

    def _format_unit(self, unit=None):
        """Formats unit for display"""
        if unit is None:
            try:
                unit = self.unit
            except AttributeError:
                unit = None
        if unit is not None:
            for pattern, preferred in self._units.items():
                if re.match(pattern, unit, flags=re.I):
                    return preferred
            raise KeyError("Unrecognized unit: {}".format(unit))

    def _format_bearing(self, bearing=None):
        """Formats bearing as N, NW, NNW for display"""
        if bearing is None:
            try:
                bearing = self.bearing
            except AttributeError:
                bearing = None
        if bearing is not None:
            for word in ["north", "south", "east", "west"]:
                bearing = bearing.lower().replace(word, word[0])
            bearing = re.sub(r"[^NSEW\d]", "", bearing.upper())
            try:
                self.validate_bearing(bearing)
            except ValueError:
                mask = "Could not parse: {} (invalid bearing)"
                raise ValueError(mask.format(self.verbatim))
            return bearing

    def _format_feature(self, feature=None):
        """Formats feature name for display"""
        if feature is None:
            try:
                feature = self.feature
            except AttributeError:
                feature = None
        if feature is not None:
            feature = LocStandardizer().sitify(str(feature))
            if feature.isupper():
                return titlecase(feature)
            return feature

    def validate_bearing(self, bearing=None):
        """Validates that bearing is valid"""
        if bearing is None:
            bearing = self.bearing
        if bearing:
            validate_direction(bearing)
