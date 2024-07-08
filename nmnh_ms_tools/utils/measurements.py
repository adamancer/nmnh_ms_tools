import re


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

    def __init__(self, val, unit="", conj=" to "):
        self.verbatim = val
        self.conj = conj

        self.from_val = ""
        self.from_mod = ""
        self.to_val = ""
        self.to_mod = ""
        self.unit = ""
        self.short_unit = ""

        try:
            self._parse(val, unit, conj)
        except (KeyError, ValueError):
            raise ValueError(f"Could not parse measurement: {self.verbatim}")

    def __str__(self):
        vals = [f"{self.from_mod}{self.from_val}"]
        if self.from_val != self.to_val:
            vals.append(f"{self.to_mod}{self.to_val}")
        return f"{self.conj.join(vals)} {self.short_unit}".strip()

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

    @property
    def text(self):
        """Returns string representation of measurement

        Included for compatibility with namedtuple version of Measurement
        """
        return str(self)

    def _parse(self, val, unit, conj):
        if isinstance(val, Measurement):
            return val

        vals = []
        units = []

        verbatim = val

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

        if len(set(units)) == 1:
            unit = units[0] if units else ""

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
        self.short_unit = SHORT_UNITS.get(unit, "")

        return self

        vals = [from_val]
        if from_val != to_val:
            vals.append(to_val)
        text = f"{conj.join(vals)} {SHORT_UNITS.get(unit, '')}".strip()
        return Measurement(
            from_val, to_val, unit, SHORT_UNITS.get(unit, ""), text, verbatim
        )


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
    val_from = parse_measurement(val_from, unit=unit)
    if val_to:
        val_to = parse_measurement(val_to, unit=unit)
        if val_to != val_from:
            # Check if one or both values are ranges
            if val_from.from_val != val_from.to_val or val_to.from_val != val_to.to_val:
                raise ValueError(
                    f"Inconsistent measurements: {val_from.verbatim}, {val_to.verbatim}"
                )

            # Check units
            units = [m.unit for m in (val_from, val_to) if m.unit]
            if len({m.unit for m in (val_from, val_to) if m.unit}) > 1:
                raise ValueError(
                    f"Inconsistent units: {val_from.verbatim}, {val_to.verbatim}"
                )

            return parse_measurement(
                f"{val_from.verbatim} to {val_to.verbatim}", unit=unit, conj=conj
            )
    return val_from
