"""Defines methods for parsing straigraphic units

FIXME: Handle ranges using "to"
FIXME: Handle uncertainty
"""

import re

from .utils import (
    base_name,
    long_name,
    short_name,
    split_strat,
    std_modifiers,
    CHRONOSTRAT_RANKS,
    LITHOLOGIES,
    LITHOSTRAT_RANKS,
    MODIFIERS,
)
from ..core import Record
from ...bots.adamancer import AdamancerBot
from ...bots.macrostrat import MacrostratBot
from ...utils import LazyAttr


class StratUnit(Record):

    # Deferred class attributes are defined at the end of the file
    chronobot = None
    lithobot = None

    # Normal class attributes
    terms = ["kind", "rank", "lithology", "modifier", "unit"]

    def __init__(self, *args, hint=None, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = []
        # Explicitly define defaults for all reported attributes
        self.unit = ""
        self.kind = ""
        self.rank = ""
        self.lithology = ""
        self.modifier = ""
        # Define additional attributes required for parse
        self._hint = f"[{hint.lower()}]" if hint else None
        # Initialize instance
        super().__init__(*args, **kwargs)

    def __str__(self):
        return self.long_name()

    def __bool__(self):
        return bool(self.unit or self.rank or self.lithology)

    @property
    def name(self):
        return long_name(self.summarize())

    def parse(self, unit):
        """Parses data from various sources to populate class"""
        self.reset()
        self.verbatim = unit
        if not unit or unit == "Unknown":
            return
        # Remove some less common abbreviations
        unit = unit.replace("Bd", "Bed")
        unit = unit.replace("Grp", "Gp")
        # Parse components of the unit name
        unit = std_modifiers(long_name(unit))
        self.modifier = self._parse_modifier(unit)
        self.rank = self._parse_rank(unit)
        self.lithology = self._parse_lithology(unit)
        self.unit = self._parse_name(unit)
        self.kind = self._parse_kind(unit)
        self.uncertain = self._parse_uncertainty(unit)
        # Apply hint if rank could not be parsed
        if self._hint and not self.rank:
            self.rank = self._hint.strip("[]")
        # Check if modified name is an official ICS unit (e.g., Early Jurrasic)
        self.check_name()

    def augment(self, **kwargs):
        """Searches for additional info about this unit"""
        if self.kind == "lithostrat":
            return self.lithobot.get_units_by_name(self.unit.rstrip("?"))
        names = [(f"{self.modifier} {self.unit}").strip(), self.unit]
        for name in names:
            name = name.rstrip("?")
            response = self.chronobot.chronostrat(name, **kwargs)
            if response.get("success"):
                return response

    def long_name(self):
        """Returns the full name of the unit"""
        return long_name(self.summarize())

    def short_name(self):
        """Returns the abbreviated name of the unit"""
        return short_name(self.summarize())

    def same_as(self, other, strict=True):
        """Tests if unit is the same as another unit"""
        if not isinstance(other, self.__class__):
            return False
        return (
            self.unit == other.unit
            and self.rank.strip("[]") == other.rank.strip("[]")
            and self.lithology == other.lithology
            and self.modifier == other.modifier
        )

    def same_name_as(self, other):
        """Tests if two names are the same or very similar"""
        names = []
        for obj in (self, other):
            name = short_name(obj.unit)
            name = name.replace(" ", "")
            name = name.rstrip("s. ")
            names.append(name.lower())
        return names[0] == names[1]

    def similar_to(self, other):
        """Tests if units are similar"""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        same_as = self.same_as(other)
        same_name = self.same_name_as(other)
        same_rank = self.rank.strip("[]") == other.rank.strip("[]")
        same_lith = self.lithology == other.lithology or bool(self.lithology) != bool(
            other.lithology
        )
        same_pos = self.modifier == other.modifier
        return same_as or (same_name and same_rank and same_lith and same_pos)

    def _to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError("to_emu")

    def summarize(self):
        """Constructs a name from class attributes"""
        vals = self.to_dict()
        if vals["modifier"] and not (vals["unit"] or vals["lithology"]):
            vals["unit"] = vals["modifier"]
            vals["modifier"] = ""
        mask = "{unit} {lithology} ({modifier})"
        name = mask.format(**vals)
        return re.sub(r" +", " ", name).replace("()", "").strip()

    def _parse_rank(self, unit):
        """Parses rank from unit name"""
        matches = []
        for val in LITHOSTRAT_RANKS:
            match = re.search(rf"\b{val}\b", unit, flags=re.I)
            if match:
                matches.append(match)
        if matches:
            matches.sort(key=lambda m: m.span()[0])
            return matches[-1].group(0).lower()
        return

    def _parse_lithology(self, unit):
        """Parses lithology type from unit name"""
        matches = []
        for val in LITHOLOGIES.values():
            match = re.search(rf"\b{val}\b", unit, flags=re.I)
            if match:
                matches.append(match)
        if matches:
            matches.sort(key=lambda m: m.span()[0])
            return matches[-1].group(0).lower()
        return

    def _parse_modifier(self, unit):
        """Parses relative modifier (upper, lower, etc.) from unit name"""
        modifier = None
        # Define compound modifier
        mask = r"(?:{0})(?:(?: ?- ?| to | |/)(?:{0}))*"
        mods = mask.format("|".join(MODIFIERS))
        # Leading modifiers (Early Jurassic
        pattern = rf"^((?:{mods}))(?: part of(?: the)?)?"
        result = re.search(pattern, unit, flags=re.I)
        if result is not None:
            modifier = result.group(1)
        # Parenthetical modifiers (Jurassic (Early))
        if not modifier:
            pattern = rf"\(({mods})\)$"
            result = re.search(pattern, unit, flags=re.I)
            if result is not None:
                modifier = result.group(1)
        # Trailing modifiers (Jurassic, Early)
        if not modifier:
            pattern = rf", ?({mods})$"
            result = re.search(pattern, unit, flags=re.I)
            if result is not None:
                modifier = result.group(1)
        return modifier

    def _parse_name(self, unit):
        """Parses base name from unit name"""
        if self.rank:
            unit = re.sub(self.rank, "", unit, flags=re.I)
        if self.lithology:
            unit = re.sub(self.lithology, "", unit, flags=re.I)
        # Try to strip the more complicated upper/lower stuff
        pattern = r"(\({0}\)|{0}( part of(the ?))?)".format(self.modifier)
        unit = re.sub(pattern, "", unit, flags=re.I)
        return re.sub(r" +", " ", unit).strip(", ")

    def _parse_kind(self, unit):
        """Determines whether unit is chrono- or lithostrat"""
        if self.rank in LITHOSTRAT_RANKS:
            return "lithostrat"
        if self._hint is not None:
            hint = self._hint.strip("[]")
            if hint in LITHOSTRAT_RANKS:
                return "lithostrat"
            if hint in CHRONOSTRAT_RANKS:
                return "chronostrat"
        # Final try is to check names against known geologic ages
        if self.unit:
            response = self.chronobot.chronostrat(self.unit)
            if response.get("success"):
                return "chronostrat"
        return

    def _parse_uncertainty(self, unit):
        """Looks for uncertainty modifiers in the unit name"""
        pattern = r"(\?$|prob(\.|ably)?)"
        if re.search(pattern, unit, flags=re.I):
            self.unit = re.sub(pattern, "", unit, flags=re.I)
            return True
        return False

    def check_name(self):
        """Checks if modified unit name is an official ICS unit"""
        if self.kind == "chronostrat" and self.modifier:
            mods = re.split(r" ", self.modifier)
            mod_name = f"{mods[-1]} {self.unit}"
            response = self.chronobot.chronostrat(mod_name)
            if response.get("success"):
                self.unit = mod_name
                mod = "".join(self.modifier.rsplit(mods[-1], 1)).strip()
                self.modifier = mod

    def _sortable(self):
        """Returns a sortable version of the object"""
        return str(self)


def parse_strat_unit(val, hint=None):
    """Parses a string containing stratigraphic info into a list of units"""

    # Return StratUnit as is
    if isinstance(val, StratUnit):
        return [val]

    # Convert names to units
    units = [StratUnit(val, hint=hint) for val in split_strat(val)]

    # Propagate properties of the last unit up the list if needed
    if units:
        last = units[-1]
        if last.kind and all([not u.kind for u in units[:-1]]):
            for unit in units[:-1]:
                unit.kind = last.kind
        if last.lithology and all([not u.lithology for u in units[:-1]]):
            for unit in units[:-1]:
                unit.lithology = last.lithology
        # Case: Early-Middle Jurassic
        if last.unit and all([not u.unit for u in units[:-1]]):
            for unit in units[:-1]:
                unit.unit = base_name(last.unit)
                unit.check_name()
    return units


# Define deferred class attributes
LazyAttr(StratUnit, "chronobot", AdamancerBot)
LazyAttr(StratUnit, "lithobot", MacrostratBot)
