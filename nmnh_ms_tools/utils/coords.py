"""Defines methods to parse and validate coordinates

Decimal places:
+ 0: 111    km
+ 1:  11    km
+ 2:   1    km
+ 3:   0.1  km
+ 4:   0.01 km

"""

import logging
import re

from .classes import repr_class
from .geo import get_dist_km


logger = logging.getLogger(__name__)


DEG_DIST_KM = 110.567


class Coordinate:
    attributes = [
        "original",
        "verbatim",
        "hemisphere",
        "decimal",
        "dms",
        "degrees",
        "minutes",
        "seconds",
        "dec_places",
    ]

    def __init__(self, val, kind, validate=True):
        if not val and val != 0:
            raise ValueError(f"Invalid coordinate: {val}")
        if kind not in ["latitude", "longitude"]:
            raise ValueError("kind must be either latitude or longitude")
        if not isinstance(val, (float, int, str)):
            mask = "Coordinate must be float, int, or str ({} given)"
            raise TypeError(mask.format(type(val)))

        self.original = val
        self.kind = kind
        self.verbatim = self._format_verbatim()
        self.hemisphere = None

        # Components for decimal degrees
        self.decimal = None
        self.dec_places = None

        # Components for degrees-minutes-seconds
        self.dms = None
        self.degrees = None
        self.minutes = None
        self.seconds = None

        # Parse verbatim
        try:
            self.parse()
            self.validate()
        except ValueError:
            raise ValueError("Invalid {}: {}".format(kind, val))

    def __str__(self):
        if self.is_decimal():
            return self._format_decimal()
        return self.dms

    def __repr__(self):
        return repr_class(self)

    def __float__(self):
        return self.decimal

    def __format__(self, format_spec):
        try:
            return format(str(self), format_spec)
        except ValueError:
            return format(float(self), format_spec)

    def copy(self):
        return self.__class__(self.verbatim)

    def parse(self):
        """Parses verbatim coordinats into decimal degress and deg-min-sec"""
        self.dec_places = self._get_dec_places()
        self.hemisphere = self._get_hemisphere()
        if self.is_decimal():
            self.decimal = float(self.verbatim.strip("NnSsEeWw "))
            self.degrees, self.minutes, self.seconds = self._decimal_to_dms()
        else:
            self.degrees, self.minutes, self.seconds = self._parse_dms()
            # Estimate decimal places
            if float(self.seconds):
                self.dec_places = 3
            elif float(self.minutes):
                self.dec_places = 2
            else:
                self.dec_places = 0
            self.decimal = self._dms_to_decimal()
        self.dms = self._format_dms()
        return self

    def validate(self):
        """Validates coordinate"""
        if self.kind == "longitude":
            # Fix antimeridian-normalized longitudes
            if 180 < abs(self.decimal) <= 360:
                mod = -1 if self.decimal < 0 else 1
                self.degrees = str(mod * (abs(int(self.degrees)) - 360))
                self.decimal = mod * (abs(self.decimal) - 360)
            if abs(self.decimal) > 180:
                raise ValueError("Invalid longitude: {}".format(self.decimal))
        elif abs(self.decimal) > 90:
            raise ValueError("Invalid latitude: {}".format(self.decimal))

    def as_decimal(self):
        return self._format_decimal()

    def as_dms(self):
        return self._format_dms()

    def is_decimal(self):
        """Tests if a string represents a decimal degree"""
        return re.match(r"^-?\d{1,3}(\.\d+)?(?! ?[NnSsEeWw])$", self.verbatim)

    def is_dms(self):
        """Tests if a string represents degrees-minutes-seconds"""
        return not self.is_decimal()

    def estimate_uncertainty(self, rel_err=0.5, allow_zeroes=True):
        """Estimates uncertainty radius in km based on original value

        This method is based on distances at the equator, which will be a
        maximum for longitudes. The estiamte_uncertainty function, which
        looks at a latitude/longitude pair, will give a better sense of
        total uncertainty than this method.

        Arguments:
            rel_err (float): scales the uncertainty by the given amount.
              The default value of 0.5 produces an error radius of 0.5
              degrees for a coordinate reported to the degree; a value of
              1 for a degree would produce an error radius of 1 degree.
            allow_zeroes (bool): specifies whether to count zero as a valid
                degree/minute/second hen working with DMS coordinates

        Returns:
            Uncertainty radius as a float
        """
        base_dist_km = DEG_DIST_KM * rel_err
        if self.is_decimal():
            return base_dist_km / 10**self.dec_places
        if float(self.seconds) and (allow_zeroes or self.seconds):
            return base_dist_km / 3600
        if float(self.minutes) and (allow_zeroes or self.minutes):
            return base_dist_km / 60
        return base_dist_km

    def _parse_dms(self):
        """Parses DMS coordinates into a standard format"""
        coord = self.verbatim.strip("NnSsEeWw ").replace("--", "00").lstrip("-")
        coord = re.sub(r"(deg|min|sec)\. ?", r"\1 ", coord)  # deg.
        pattern = (
            r"^(?P<deg>\d{2,3})" r"(?P<min>\d{2}(\.\d+)?)" r"(?P<sec>\d{2}(\.\d+)?)?$"
        )
        match = re.match(pattern, coord)
        if match is not None:
            parts = [match.group("deg"), match.group("min"), match.group("sec")]
        else:
            parts = [p for p in re.split(r"[^0-9\.]+", coord) if p]
        while len(parts) < 3:
            parts.append("0")
        parts = [p if p else "0" for p in parts]
        # Convert decimals to minutes or seconds
        for i, part in enumerate(parts):
            if "." in part and i < 2:
                integer, fractional = part.split(".")
                parts[i] = integer
                if parts[i + 1] != "0":
                    mask = "Mixes deg-min-sec and decimals: {}"
                    raise ValueError(mask.format(self.verbatim))
                val = 60 * int(fractional) / 10 ** len(fractional)
                # Note the final value so high precision is OK
                val = self._strip_trailing_zeroes("{:.6f}".format(val))
                parts[i + 1] = val
        # Check if minutes or seconds equal 60, which is weirdly common and
        # is an import-breaking error in EMu
        for i in (2, 1):
            if parts[i] == "60":
                parts[i - 1] = str(int(parts[i - 1]) + 1)
                parts[i] = "0"
        return parts

    def _dms_to_decimal(self):
        """Converts degrees-minutes-seconds to decimal degrees"""
        dec = 0
        for i, part in enumerate([self.degrees, self.minutes, self.seconds]):
            dec += (float(part) if "." in part else int(part)) / 60**i
        if self.hemisphere in "SW" and dec > 0:
            dec *= -1
        return dec

    def _decimal_to_dms(self):
        """Converts decimal degrees to degrees-minutes-seconds"""
        degrees = abs(int(self.decimal))
        minutes = 60 * (abs(float(self.decimal)) % 1)
        seconds = 60 * (minutes % 1)
        # NOTE: Neither of these cases should be possible
        # if seconds >= 60:
        #    minutes += 1
        #    seconds -= 60
        # if minutes == 60:
        #    degrees += 1
        #    minutes = 0
        return [str(int(n)) for n in (degrees, minutes, seconds)]

    def _format_decimal(self):
        """Formats decimal as a string"""
        val = "{{:.{}f}}".format(self.dec_places).format(self.decimal)
        return val
        return self._strip_trailing_zeroes(val)

    def _format_dms(self):
        """Formats degrees-minutes-seconds as a string"""
        parts = []
        for part in [self.seconds, self.minutes, self.degrees]:
            if parts or float(part):
                parts.insert(0, str(part))
        return "{} {}".format(" ".join(parts), self.hemisphere)

    def _format_verbatim(self):
        """Coerces original value to a string"""
        verbatim = self.original
        if isinstance(verbatim, (float, int)):
            verbatim = self._strip_trailing_zeroes("{:.4f}".format(verbatim))
        return verbatim.strip()

    def _get_dec_places(self):
        """Calculates the number of decimal places based on a string"""
        if self.is_decimal():
            try:
                _, fractional = self.verbatim.strip("NnSsEeWw ").split(".")
            except ValueError:
                return 0
            else:
                return len(fractional)

    def _get_hemisphere(self):
        """Determines which hemisphere a coordinate falls into"""
        if self.verbatim.startswith("-"):
            return "S" if self.kind == "latitude" else "W"
        if self.verbatim.lower().endswith(("n", "e", "w", "s")):
            return self.verbatim[-1].upper()
        if self.verbatim.lower().startswith(("n", "e", "w", "s")):
            return self.verbatim[0].upper()
        # Assume positive if no other directional info given
        return "N" if self.kind == "latitude" else "E"

    @staticmethod
    def _strip_trailing_zeroes(val):
        """Strips trailing zeroes from a number string"""
        if "." in val:
            return val.rstrip("0").rstrip(".")
        return val


class Latitude(Coordinate):
    def __init__(self, val, **kwargs):
        super().__init__(val, "latitude", **kwargs)


class Longitude(Coordinate):
    def __init__(self, val, **kwargs):
        super().__init__(val, "longitude", **kwargs)


def parse_coordinate(coord, kind, delims="|;"):
    """Parses a single coordinate"""
    if not isinstance(coord, list):
        for delim in delims:
            try:
                if delim in coord:
                    coord = [s.strip() for s in coord.split(delim)]
                    break
            except TypeError:
                continue
        else:
            coord = [coord]
    return [Coordinate(c, kind) for c in coord]


def estimate_uncertainty(lat, lng, unit="m"):
    """Estimates uncertainty for a lat/long pair based on number of decimals"""

    if not isinstance(lat, Coordinate):
        lat = Latitude(lat)
    if not isinstance(lng, Coordinate):
        lng = Longitude(lng)

    # Get raw uncertainties for lat and long
    lat_unc = lat.estimate_uncertainty()
    lng_unc = lng.estimate_uncertainty()

    # Distance between circles of latitude is consistent (~111 km), but
    # distance between meridians of longitude varies by latitude. Use the
    # given latitude to adjust the longitude uncertainty.
    meridian_dist_km = get_dist_km(
        lat.decimal,
        lng.decimal,
        lat.decimal,
        lng.decimal + 1 if lng.decimal < 89 else lng.decimal - 1,
    )
    lng_unc *= meridian_dist_km / DEG_DIST_KM

    # Return the hypotenuse of the two uncertainties scaled to the given unit
    scalars = {"cm": 1000000, "m": 1000, "km": 1}
    try:
        return (lat_unc**2 + lng_unc**2) ** 0.5 * scalars[unit]
    except KeyError:
        raise KeyError(f"Invalid unit: {unit} (must be one of {list(scalars)}")


def round_to_uncertainty(lat, lng, dist_m=10):
    """Rounds coordinates to approximate the given uncertainty

    Parameters
    ----------
    lat : str or Latitude
        latitude
    lng : str or Longitude
        longitude
    dist_m : int
        uncertainty radius in meters

    Returns
    -------
    tuple of (Latitude, Longitude)
        tuple of rounded coordinates
    """

    if not isinstance(lat, Coordinate):
        lat = Latitude(lat)
    if not isinstance(lng, Coordinate):
        lng = Longitude(lng)

    dec_places = min([lat.dec_places, lng.dec_places])
    for dec in range(dec_places, -1, -1):
        lat.dec_places = dec
        lng.dec_places = dec
        unc_m = estimate_uncertainty(lat, lng)
        if dist_m / 5 < unc_m < dist_m * 5 or unc_m > dist_m:
            return lat, lng
