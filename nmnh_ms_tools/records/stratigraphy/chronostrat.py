"""Definds methods to work with chronostratigraphic names"""

import logging
import os
import re

import numpy as np

from .core import StratRecord
from .utils import CHRONOSTRAT_RANKS, parse_strat_package, split_strat, split_strat_dict
from .unit import StratUnit, parse_strat_units
from ...bots.adamancer import AdamancerBot
from ...config import DATA_DIR
from ...utils import LazyAttr, dedupe, to_attribute


logger = logging.getLogger(__name__)


class ChronoStrat(StratRecord):
    """Defines methods for storing a single chronostratigraphic unit"""

    # Deferred class attributes are defined at the end of the file
    bot = None
    keywords = None

    # Normal class attributes
    terms = [
        "eonothem",
        "erathem",
        "system",
        "series",
        "stage",
        "substage",
        "min_ma",
        "max_ma",
    ]
    ranks = CHRONOSTRAT_RANKS[:]

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ["min_ma", "max_ma"]

        # Explicitly define defaults for all reported attributes
        self.eonothem = StratUnit()
        self.erathem = StratUnit()
        self.system = StratUnit()
        self.series = StratUnit()
        self.stage = StratUnit()
        self.substage = StratUnit()
        self.interval = StratUnit()
        self._min_ma = np.nan
        self._max_ma = np.nan
        self.age_geom = None

        # Initialize instance
        super().__init__(*args, **kwargs)

        # Define additional attributes
        self.intervals = [getattr(self, k) for k in self.ranks]
        self._geometry = None

    def __bool__(self):
        return any(self.intervals)

    @property
    def name(self):
        vals = [getattr(self, a) for a in self.ranks]
        return ":".join(vals)

    def parse(self, data):
        """Parses data from various sources to populate class"""
        if data:
            for key, val in self.parse_to_dict(data).items():
                if isinstance(val, (list, tuple)):
                    if len(val) > 1:
                        raise TypeError("Attributes must be str or float")
                    val = val[0]
                setattr(self, key, val)
        return self

    def parse_to_dict(self, data):
        """Parses data from various sources to a dict

        The strat classes need to accommodate records that contain ranges,
        but are themselves only intended to hold distinct units. This method
        allows external functions to use the parsers without adding
        invalid data.
        """
        if isinstance(data, dict) and data.keys() & set(self.ranks):
            dct = data
        elif isinstance(data, (list, tuple)):
            dct = self._parse_names(data)
        elif isinstance(data, str):
            dct = self._parse_names(split_strat(data))
        elif isinstance(data, self.__class__):
            dct = data.to_dict()
        else:
            dct = self._parse_dwc(data)

        # Clean up orphaned modifiers using name from next highest rank
        for key in self.ranks:
            pass

        return dct

    def same_as(self, other, strict=True):
        """Tests if object is the same as another object"""
        for i, unit in enumerate(self.intervals):
            try:
                other_unit = other.intervals[i]
            except IndexError:
                return False
            if unit != other_unit:
                return False
        return True

    def similar_to(self, other):
        """Tests if object is similar to another object"""
        if not isinstance(other, self.__class__):
            try:
                other = self.__class__(other)
            except:
                logger.error("Undefined exception: ChronoStrat.similar_to")
                return False
        for i, unit in enumerate(self.intervals):
            if unit != other.intervals[i]:
                return False
        return True

    def _to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError("to_emu")

    def augment(self, **kwargs):
        """Searches Macrostrat for related units"""
        raise NotImplementedError("augment")

    def most_specific(self):
        """Finds the most specific rank and name"""
        for rank in self.ranks:
            name = getattr(self, rank)
            if name:
                return rank, name

    def to_dwc(self, kind="both"):
        """Exports records as DarwinCore"""
        kinds = {"both", "earliest", "latest"}
        if kind not in kinds:
            raise ValueError(f"kind must be one of {kinds} ('{kind}' given)")

        # DwC uses two sets of fields for chronostratigraphic ages: one for
        # earliest/lowest, one for latest/highest. Use the kind keywords to
        # determine which fields to populate.
        earliest = ("earliest", "Lowest")
        latest = ("latest", "Highest")
        if kind == "earliest":
            terms = [earliest]
        elif kind == "latest":
            terms = [latest]
        else:
            terms = [earliest, latest]

        keys = {
            "eonothem": "{}EonOr{}Eonothem",
            "erathem": "{}EraOr{}Erathem",
            "system": "{}PeriodOr{}System",
            "series": "{}EpochOr{}Series",
            "stage": "{}AgeOr{}Stage",
        }

        rec = {}
        for attr, field in keys.items():
            val = getattr(self, attr)
            if val:
                for group in terms:
                    rec[field.format(*group)] = str(val)
        return rec

    def _parse_dwc(self, data):
        """Parses chronostratigraphic info from a Darwin Core record"""
        masks = [
            "{}EonOr{}Eonothem",
            "{}EraOr{}Erathem",
            "{}PeriodOr{}System",
            "{}EpochOr{}Series",
            "{}AgeOr{}Stage",
        ]

        # Populated dicts for earliest and latest
        earliest = {}
        latest = {}
        for mask in masks:

            # Get the last word in the string
            attr = re.findall(r"[A-Z][a-z]+", mask)[-1].lower()

            # Look for data in lowest/earliest
            val = data.get(mask.format("earliest", "Lowest"))
            if val:
                earliest[attr] = val

            # Look for data in latest/highest
            val = data.get(mask.format("latest", "Highest"))
            if val:
                latest[attr] = val

        return self._combine_units(earliest, latest)

    def _parse_name(self, name):
        """Parses chronostratigraphic info from a name"""
        response = self.bot.chronostrat(name)
        if response.get("success"):
            earliest = response["data"]["earliest"]
            latest = response["data"].get("latest", {})
            return self._combine_units(earliest, latest)
        raise ValueError(f"Could not parse '{name}'")

    def _parse_names(self, names):
        """Parses chronostratigraphic info from a list of names"""
        parsed = []
        for name in names:
            parsed.append(self._parse_name(name))

        # Split units representing ranges
        units = []
        for unit in parsed:
            units.extend(split_strat_dict(unit))

        # Make sure values for each unit are strings
        units = [{k: v[0] for k, v in u.items()} for u in units]

        # Sort units from oldest to youngest
        units = sorted(units, key=lambda u: -u["max_ma"])

        # Find most specific units
        for rank in self.ranks[::-1]:
            most_specific = [u for u in units if u.get(rank)]
            if most_specific:
                break

        # Test that all units are consistent with most specific units
        for unit in units:
            for key in self.ranks:
                val = unit.get(key)
                if val and val not in [u.get(key) for u in most_specific]:
                    raise ValueError(f"Units cannot be resolved: {units}")

        return self._combine_units(most_specific[0], most_specific[-1])

    def _combine_units(self, *units):
        """Combines units into ranges

        Note that ranges will produce an error if you try to populate the
        class with these values.
        """

        combined = {}
        for unit in units:
            for key, val in unit.items():
                if val:
                    if key in self.ranks:
                        val = parse_strat_units(val, hint=key)
                        combined.setdefault(key, []).extend(val)
                    elif key in ("min_ma", "max_ma"):
                        combined.setdefault(key, []).append(val)

        if combined:
            combined = {k: dedupe(v) for k, v in combined.items()}
            # Test and standardize lengths by duplicating units where needed
            max_len = max([len(v) for v in combined.values()])
            if max_len > 2:
                raise ValueError("Record contains more than two units")
            for key, val in combined.items():
                if 0 < len(val) < max_len:
                    combined[key] = val * max_len

        return combined


def parse_chronostrat(val):
    return parse_strat_package(val, ChronoStrat)


def read_keywords(path):
    words = []
    with open(path, "r") as f:
        for line in f:
            words.append(to_attribute(line.rsplit(" ", 1)[0]))
    return set(words)


# Define deferred class attributes
LazyAttr(ChronoStrat, "bot", AdamancerBot)
LazyAttr(
    ChronoStrat,
    "keywords",
    read_keywords,
    os.path.join(DATA_DIR, "chronostrat", "chronostrat.txt"),
)
