"""Definds methods to work with lithostratigraphic names"""

import numpy as np

from .utils import LITHOSTRAT_ABBRS, LITHOSTRAT_RANKS
from .unit import StratUnit, parse_strat_unit
from ..core import Record
from ...bots.macrostrat import MacrostratBot
from ...tools.geographic_operations.geometry import GeoMetry
from ...utils import LazyAttr


class LithoStrat(Record):
    """Defines methods for working with lithostratigraphic names"""

    # Deferred class attributes are defined at the end of the file
    bot = None

    # Normal class attributes
    terms = [
        "unit_id",
        "macrostrat_id",
        "group",
        "formation",
        "member",
        "min_ma",
        "max_ma",
        "current_latitude",
        "current_longitude",
    ]

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.unit_id = ""
        self.macrostrat_id = ""
        self.group = StratUnit()
        self.formation = StratUnit()
        self.member = StratUnit()
        self.min_ma = np.nan
        self.max_ma = np.nan
        self.current_latitude = np.nan
        self.current_longitude = np.nan
        # Initialize instance
        super().__init__(*args, **kwargs)
        # Define additional attributes
        self._geometry = None

    def __str__(self):
        units = [self.group, self.formation, self.member]
        return " - ".join([str(u[0]) if u else "" for u in units]).strip("- ")

    def __bool__(self):
        return bool(self.group or self.formation or self.member)

    @property
    def name(self):
        raise NotImplementedError("name")

    @property
    def geometry(self):
        """Returns a GeoMetry object for this unit, populating it if needed"""
        if self._geometry is None and self.current_latitude and self.current_longitude:
            self._geometry = GeoMetry((self.current_latitude, self.current_longitude))
        return self._geometry

    def parse(self, data):
        """Parses data from various sources to populate class"""
        if "strat_name_id" in data:
            self._parse_macrostrat(data)
        elif "min_ma" in data:
            self._parse_self(data)
        else:
            self._parse_dwc(data)
        # Clean up empty stratigraphic units
        for attr in ["group", "formation", "member"]:
            setattr(self, attr, [u for u in getattr(self, attr) if u])

    def same_as(self, other, strict=True):
        """Tests if object is the same as another object"""
        try:
            assert type(self) == type(other)
            assert self.group == other.group
            assert self.formation == other.formation
            assert self.member == other.member
            return True
        except AssertionError:
            return False

    def similar_to(self, other):
        """Tests if object is similar to another object"""
        for attr in ["group", "formation", "member"]:
            stop = False
            units = getattr(self, attr)
            if units:
                for unit in units:
                    for other_unit in getattr(other, attr):
                        if unit.similar_to(other_unit):
                            stop = True
                            break
                    if stop:
                        break
                else:
                    return False
        return True

    def _to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError("to_emu")

    def augment(self):
        """Searches Macrostrat for related units"""
        matches = []
        keys = ["member", "formation", "group"]
        for key in keys:
            units = getattr(self, key)
            if units:
                for unit in units:
                    results = unit.augment()
                    for rec in results:
                        strat = self.__class__(rec)
                        if self.similar_to(strat):
                            matches.append(strat)
                # Only want the most specific rank, so break on populated
                break
        if matches:
            # Limit matches to those no more specific than this
            subset = matches[:]
            for key in keys[: keys.index(key)]:
                subset = [m for m in subset if not getattr(m, key)]
            # If all matches have the same strat_name_id, combine them
            if len({m.macrostrat_id for m in subset}) == 1:
                primary = subset[0].combine(*subset[1:])
                # Incorporate data from children of the primary unit
                children = matches[0].combine(*matches[1:])
                primary.current_latitude.extend(children.current_latitude)
                primary.current_longitude.extend(children.current_longitude)
                if primary.min_ma > children.min_ma:
                    primary.min_ma = children.min_ma
                if primary.max_ma < children.max_ma:
                    primary.max_ma = children.max_ma
                # Update sources based on complete list of units checked
                for macrostrat_id in sorted({m.macrostrat_id for m in matches}):
                    primary.sources.append(
                        f"https://macrostrat.org/api/units?strat_name_id={macrostrat_id}"
                    )
                return primary
        return

    def combine(self, *others):
        """Combines ages from multiple packages with this one"""
        combined = {}
        for obj in [self] + list(others):
            for attr in self.attributes:
                val = getattr(obj, attr)
                if isinstance(val, list):
                    combined.setdefault(attr, []).extend(val)
                else:
                    combined.setdefault(attr, []).append(val)
        # Reduce lists where possible
        for key in ["group", "formation", "member"]:
            vals = combined[key]
            combined[key] = [v for i, v in enumerate(vals) if v not in vals[:i]]
        for key in ["macrostrat_id"]:
            combined[key] = combined[key][0]
        # Get extremes of top and bottom ages
        combined["min_ma"] = min(combined["min_ma"])
        combined["max_ma"] = max(combined["max_ma"])
        return self.__class__(combined)

    def _parse_dwc(self, data):
        for key in LITHOSTRAT_RANKS:
            setattr(self, key, [StratUnit(data.get(key, ""), hint=key)])

    def _parse_macrostrat(self, data):
        self.macrostrat_id = data["strat_name_id"]
        self.unit_id = data["unit_id"]
        for key in ["Gp", "Fm", "Mbr"]:
            kind = LITHOSTRAT_ABBRS[key.lower()].lower()
            units = parse_strat_unit(data[key], hint=kind)
            setattr(self, kind, units)
        # Update stratigraphic hierarchy with unit
        # Get additional info about age and locality
        self.min_ma = float(data["t_age"])
        self.max_ma = float(data["b_age"])
        self.current_latitude = float(data["clat"])
        self.current_longitude = float(data["clng"])

    @staticmethod
    def _simplify_macrostrat(data, keys=None):
        if keys is None:
            keys = [
                "Gp",
                "Fm",
                "Mbr",
                "unit_name",
                "strat_name_long",
                "unit_id",
                "section_id",
                "strat_name_id",
            ]
        return {k: data[k] for k in keys}

    def _parse_self(self, data):
        for key, val in data.items():
            setattr(self, key, val)


def parse_lithostrat(val):
    return val


# Define deferred class attributes
LazyAttr(LithoStrat, "bot", MacrostratBot)
