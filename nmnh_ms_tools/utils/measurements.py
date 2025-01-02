"""Parses measurements, including ranges"""

import re
from functools import cached_property

from .classes import custom_copy, custom_eq, del_immutable, mutable, set_immutable


UNITS = {
    "fath": "fathoms",
    "fathom": "fathoms",
    '"': "inches",
    "in": "inches",
    "inch": "inches",
    "inche": "inches",
    "'": "feet",
    "ft": "feet",
    "feet": "feet",
    "foot": "feet",
    "lb": "pounds",
    "pound": "pounds",
    "mi": "miles",
    "mile": "miles",
    "yd": "yards",
    "yard": "yards",
}

SHORT_UNITS = {
    "fathoms": "fath",
    "inches": "in",
    "feet": "ft",
    "miles": "mi",
    "pounds": "lb",
    "yards": "yd",
}

for prefix in ["milli", "centi", "", "kilo"]:
    for unit in ["gram", "liter", "meter"]:
        preferred = prefix + unit + "s"
        short = (prefix[0] if prefix else "") + unit[0]
        UNITS[prefix + unit] = preferred
        UNITS[prefix + unit.replace("er", "re")] = preferred
        UNITS[short] = preferred
        SHORT_UNITS[preferred] = short


class Measurement:

    def __init__(self, val=None, unit="", conj=" to "):

        self.verbatim = val
        self.conj = conj
        self.from_val = ""
        self.from_mod = ""
        self.to_val = ""
        self.to_mod = ""
        self.unit = ""
        self.short_unit = ""

        if val:
            with mutable(self):
                try:
                    self._parse(val, unit)
                except KeyError:
                    raise ValueError(f"Could not parse measurement: {self.verbatim}")

                # Add the unit to the verbatim string if no unit is present in val
                if unit and not re.match(r"[a-z]\.?$", str(self.verbatim), flags=re.I):
                    self.verbatim = f"{self.verbatim} {unit}".strip()

    def __setattr__(self, attr, val):
        set_immutable(self, attr, val)

    def __delattr__(self, attr):
        del_immutable(self, attr)

    def __int__(self):
        if self.from_val != self.to_val:
            raise ValueError(f"Cannot convert range to int: {self}")
        return int(self.from_val)

    def __float__(self):
        if self.from_val != self.to_val:
            raise ValueError(f"Cannot convert range to float: {self}")
        return float(self.from_val)

    def __str__(self):
        vals = [f"{self.from_mod}{self.from_val}"]
        if self.from_val != self.to_val:
            vals.append(f"{self.to_mod}{self.to_val}")
        return f"{self.conj.join(vals)} {self.short_unit}".strip()

    def __eq__(self, other):
        return custom_eq(self, other)

    def __repr__(self):
        return (
            "Measurement("
            f"from_val: {repr(self.from_val)}, "
            f"from_mod: {repr(self.from_mod)}, "
            f"to_val: {repr(self.to_val)}, "
            f"to_mod: {repr(self.to_mod)}, "
            f"unit: {repr(self.unit)}, "
            f"short_unit: {repr(self.short_unit)}, "
            f"verbatim: {repr(self.verbatim)}"
            ")"
        )

    def __format__(self, fmt):
        from_val = format(float(self.from_val.replace(",", "")), fmt)
        to_val = format(float(self.to_val.replace(",", "")), fmt)
        vals = [f"{self.from_mod}{from_val}"]
        if from_val != to_val:
            vals.append(f"{self.to_mod}{to_val}")
        return f"{self.conj.join(vals)} {self.short_unit}".strip()

    @cached_property
    def text(self):
        """Returns string representation of measurement

        Included for compatibility with namedtuple version of Measurement
        """
        return str(self)

    @cached_property
    def numeric(self):
        """Returns a non-range measurement as an int or float"""
        if self.from_val != self.to_val:
            raise ValueError(f"Cannot convert range to numeric: {self}")
        val = re.sub(r"\.0+$", "", self.from_val)
        return float(val) if "." in val else int(val)

    @cached_property
    def value(self):
        """Returns the value of the measurement"""
        return self.conj.join(list({self.from_val: None, self.to_val: None}))

    @cached_property
    def mean(self):
        """Returns the mean of the measurment"""
        if self.from_val == self.to_val:
            return self.from_val
        return (float(self.from_val) + float(self.to_val)) / 2

    def copy(self):
        return custom_copy(self)

    def is_metric(self):
        """Checks if unit is metric"""
        return re.match("^[kcmμn]?[mg]$", self.short_unit)

    def _parse(self, val, unit):
        if isinstance(val, Measurement):
            self.verbatim = val.verbatim
            self.conj = val.conj
            self.from_val = val.from_val
            self.from_mod = val.from_mod
            self.to_val = val.to_val
            self.to_mod = val.to_mod
            self.unit = val.unit
            self.short_unit = val.short_unit
            return

        if not isinstance(val, str):
            val = str(val)

        vals = []
        units = []

        negative = val.startswith("-")
        val = val.lstrip("-")
        val = re.sub(r"~ +", "~", val)
        val = re.sub(r"(^|[^\d])\.(\d)", r"\g<1>0.\g<2>", val)

        # Remove range delimiters
        pattern = r"(\b\s*-+\s*\b|\b\s*to\s*\b|\b\s*through\s*\b|\b\s*thru\s*\b)"
        val = re.sub(pattern, " ", val, flags=re.I)

        for part in re.split(r"([<>~]?(?:\d{1,2}(?:,\d{3})+|\d+)(?:\.\d+)?)", val):
            part = part.strip(". ")
            if part:
                if part[-1].isalpha() or part[-1] in ("'\""):
                    units.append(UNITS[part.lower().rstrip("s")])
                else:
                    vals.append(part)

        # Extract modifiers
        from_mod = vals[0][0] if vals[0][0] in "<>~" else ""
        to_mod = vals[-1][0] if vals[-1][0] in "<>~" else ""

        # Ensure that full unit is used
        try:
            unit = UNITS[unit.rstrip(".")]
        except KeyError:
            if unit and unit not in SHORT_UNITS:
                raise ValueError(f"Invalid unit: {repr(unit)}")
        if unit and units and unit not in units:
            raise ValueError(f"Inconsistent units: {repr(vals)}, ({repr({unit})})")

        if len(set(units)) == 1:
            unit = units[0]

        try:
            from_val, to_val = vals
        except ValueError:
            if len(vals) != 1:
                raise ValueError(f"Could not parse measurement: {self.verbatim}")
            from_val = to_val = vals[0]

        if negative:
            from_val = f"-{from_val}"
            to_val = f"-{to_val}"

        self.from_val = from_val.lstrip("<>~")
        self.from_mod = from_mod
        self.to_val = to_val.lstrip("<>~")
        self.to_mod = to_mod
        self.unit = unit
        self.short_unit = SHORT_UNITS.get(unit, unit)

        return self

    def convert_to(self, unit):
        """Converts the measurement to another unit"""

        from_val = float(self.from_val) if "." in self.from_val else int(self.from_val)
        to_val = float(self.to_val) if "." in self.to_val else int(self.to_val)

        short_unit = self.__class__(f"1 {unit}").short_unit

        # Convert to the base metric unit (m, g, etc.)
        conv_to_metric = {
            "dist": {
                "km": 1000,
                "cm": 100,
                "m": 1,
                "mm": 0.001,
                "ft": 0.3048,
                "mi": 1609.344,
                "yd": 0.9144,
            },
            "mass": {
                "kg": 1000,
                "g": 1,
                "mg": 0.001,
            },
        }
        for key, vals in conv_to_metric.items():
            try:
                vals[self.short_unit]
                conv_to_metric = vals
                break
            except KeyError:
                pass

        scalar = conv_to_metric[self.short_unit]
        if scalar == 1:
            return self.copy()

        from_metric = from_val * scalar
        to_metric = to_val * scalar

        # Convert to the specified unit
        try:
            scalar = 1 / conv_to_metric[short_unit]
        except KeyError:
            raise ValueError(f"Invalid unit for type {repr(key)}: {unit}")
        from_val = str(from_metric * scalar)
        to_val = str(to_metric * scalar)

        val = "-".join([from_val, to_val]) if from_val != to_val else from_val
        val = re.sub(r"\.0+", "", val)
        meas = parse_measurement(val, unit, conj=self.conj)

        # Retain the original verbatim string
        with mutable(meas):
            meas.verbatim = self.verbatim
        return meas


def parse_measurement(val, unit="", conj=" to "):
    """Parses a string measurement

    Args:
        val (str): a measurement or range
        unit (str): the expected unit. If unit information can be gleaned from
            val, the unit will be discarded.

    Returns:
        tuple as (from_value, to_value, unit, text, verbatim)
    """
    return Measurement(val, unit, conj)


def parse_measurements(val_from, val_to=None, unit="", conj=" to "):
    """Parses measurements with distinct from and to values

    Args:
        val_from (str): measurement from
        val_to (str): measurement to
        unit (str): the expected unit. If unit information can be gleaned from
            the values, the unit will be discarded.

    Returns:
        tuple as (from_value, to_value, unit, text, verbatim)
    """
    verbatim_from = val_from
    verbatim_to = val_to
    val_from = parse_measurement(val_from, unit=unit)
    if val_to:
        val_to = parse_measurement(val_to, unit=unit)
        if val_to != val_from:
            # Check if one or both values are ranges
            if val_from.from_val != val_from.to_val or val_to.from_val != val_to.to_val:
                raise ValueError(
                    f"Inconsistent measurements: {repr(val_from.verbatim)}, {repr(val_to.verbatim)}"
                )

            # Check units
            if len({m.unit for m in (val_from, val_to) if m.unit}) > 1:
                raise ValueError(
                    f"Inconsistent units: {repr(val_from.verbatim)}, {repr(val_to.verbatim)}"
                )

            return parse_measurement(
                f"{verbatim_from} to {verbatim_to}", unit=unit, conj=conj
            )
    return val_from
