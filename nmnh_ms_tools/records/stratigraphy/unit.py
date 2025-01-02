"""Defines methods for parsing straigraphic units"""

import re
from typing import Any

from xmu import EMuRecord

from .utils import (
    extract_modifier,
    long_name,
    short_name,
    split_strat,
    CHRONOSTRAT_RANKS,
    LITHOLOGIES,
    LITHOSTRAT_RANKS,
)
from ..core import Record
from ...bots.adamancer import AdamancerBot
from ...bots.macrostrat import MacrostratBot
from ...utils import LazyAttr, as_str, mutable


class StratUnit(Record):
    """Parses data about a single stratigraphic unit

    Attributes
    ----------
    unit_name : str
        the proper name of the unit without rank, lithology, etc.
    kind : str
        the type of unit ('lithostrat' or 'chronostrat'). Not to be confused with rank.
    rank : str
        the stratigraphic rank. In addition to the official lithostrat and
        chronostrat ranks, may also be 'unit' to capture research-definied units.
    lithology : str
        the rock type of the unit
    modifier : str
        the location within the unit (upper, middle, lower, etc.)
    uncertain : bool
        whether the unit idenfiticaiton is uncertain
    """

    # Deferred class attributes are defined at the end of the file
    chronobot = None
    lithobot = None

    # Normal class attributes
    terms = ["kind", "rank", "lithology", "modifier", "unit_name"]

    def __init__(self, *args, hint=None, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ["uncertain"]
        # Explicitly define defaults for all reported attributes
        self.unit_name = ""
        self.kind = ""
        self.rank = ""
        self.lithology = ""
        self.modifier = ""
        self.uncertain = ""
        # Define additional attributes required for parse
        self._hint = f"[{hint.lower()}]" if hint else None
        # Initialize instance
        super().__init__(*args, **kwargs)

    def __str__(self):
        return self.name

    def __bool__(self):
        return bool(self.unit_name or self.rank or self.lithology)

    @property
    def name(self):
        """Returns the full name of the unit

        :getattr: return long name as str
        :type: str
        """
        return f"{long_name(self.summarize())}{"?" if self.uncertain else ""}"

    @property
    def short_name(self):
        """Returns the abbreviated name of the unit

        :getattr: return short name as str
        :type: str
        """
        return f"{short_name(self.summarize())}{"?" if self.uncertain else ""}"

    def parse(self, unit: str) -> None:
        """Parses data from various sources to populate class

        Parameters
        ----------
        unit : str
            the unit name

        Returns
        -------
        None
        """
        self.reset()
        self.verbatim = unit
        if not unit or unit == "Unknown":
            return
        # Standardize some less common abbreviations
        unit = unit.replace("Bd", "Bed")
        unit = unit.replace("Grp", "Gp")
        # Parse components of the unit name
        unit = long_name(unit)
        self.modifier = self._parse_modifier(unit)
        self.rank = self._parse_rank(unit)
        self.lithology = self._parse_lithology(unit)
        self.unit_name = self._parse_name(unit)
        self.kind = self._parse_kind()
        self.uncertain = self._parse_uncertainty(unit)
        # Apply hint if rank could not be parsed
        if self._hint and not self.rank:
            self.rank = self._hint.strip("[]")
        # Default to formation if lithology but not rank is provided
        if self.lithology and not self.rank:
            self.rank = "formation"
        # Check if modified name is an official ICS unit (e.g., Early Jurrasic)
        self.check_chronostrat_name()

    def augment(self, **kwargs):
        """Searches for additional info about this unit

        Parameters
        ----------
        kwargs :
            keyword arguments to pass to a request

        Returns
        -------
        requets.Response
            a bot-specific response
        """
        if self.kind == "lithostrat":
            return self.lithobot.get_units_by_name(self.unit_name.rstrip("?"))
        names = [(f"{self.modifier} {self.unit_name}").strip(), self.unit_name]
        for name in names:
            name = name.rstrip("?")
            response = self.chronobot.chronostrat(name, **kwargs)
            if response.get("success"):
                return response

    def same_as(self, other: Any, strict: bool = True) -> bool:
        """Tests if unit is the same as another unit

        Parameters
        ----------
        other : Any
            the other object to compare
        strict : bool
            whether to test for exact equality

        Returns
        -------
        bool
            whether the two objects are the same
        """
        if not isinstance(other, self.__class__):
            return False
        return (
            self.unit_name == other.unit_name
            and self.rank.strip("[]") == other.rank.strip("[]")
            and self.lithology == other.lithology
            and self.modifier == other.modifier
        )

    def same_name_as(self, other: str) -> bool:
        """Tests if two names are similar

        Parameters
        ----------
        other : Any
            the other name to compare

        Returns
        -------
        bool
            whether the two names are the same or very close
        """
        names = []
        for obj in (self, other):
            name = short_name(obj.unit_name)
            name = name.replace(" ", "")
            name = name.rstrip("s. ")
            names.append(name.lower())
        return names[0] == names[1]

    def similar_to(self, other):
        """Tests if units are similar

        Parameters
        ----------
        other : Any
            the other object to compare

        Returns
        -------
        bool
            whether the two units are the same or very close
        """
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

    def summarize(self) -> str:
        """Constructs the unit name from class attributes

        Returns
        -------
        str
            the unit name as a string
        """
        vals = self.to_dict()
        if vals["modifier"] and not (vals["unit_name"] or vals["lithology"]):
            vals["unit_name"] = vals["modifier"]
            vals["modifier"] = ""
        # Present short names as "Unit 1" instead of "1 Unit"
        if len(vals["unit_name"]) > 2:
            mask = "{unit_name} {rank} ({modifier})"
        else:
            mask = "{rank} {unit_name} ({modifier})"
        name = mask.format(**vals)
        return re.sub(r" +", " ", name).replace("()", "").strip()

    def check_chronostrat_name(self) -> None:
        """Checks if modified unit name is an official ICS unit

        Updates class attributes in place if modifier is be part of official name
        (like Early Jurassic).

        Returns
        -------
        None
        """
        if self.kind == "chronostrat" and self.modifier:
            mods = re.split(r" ", self.modifier)
            mod_name = f"{mods[-1]} {self.unit_name}"
            response = self.chronobot.chronostrat(mod_name)
            if response.get("success"):
                self.unit_name = mod_name
                mod = "".join(self.modifier.rsplit(mods[-1], 1)).strip()
                self.modifier = mod

    def _parse_rank(self, unit: str) -> str:
        """Parses rank from unit name"""
        matches = []
        for val in LITHOSTRAT_RANKS:
            match = re.search(rf"\b{val}\b", unit, flags=re.I)
            if match:
                matches.append(match)
        if matches:
            matches.sort(key=lambda m: m.span()[0])
            return matches[-1].group(0).lower()
        return ""

    def _parse_lithology(self, unit: str) -> str:
        """Parses lithology type from unit name"""
        matches = []
        for val in LITHOLOGIES.values():
            match = re.search(rf"\b{val}\b", unit, flags=re.I)
            if match:
                matches.append(match)
        if matches:
            matches.sort(key=lambda m: m.span()[0])
            return matches[-1].group(0).lower()
        return ""

    def _parse_modifier(self, unit: str) -> str:
        """Parses relative modifier (upper, lower, etc.) from unit name"""
        return extract_modifier(unit)[1]

    def _parse_name(self, unit: str) -> str:
        """Parses base name from unit name"""
        if self.rank:
            unit = re.sub(self.rank, "", unit, flags=re.I)
        if self.lithology:
            unit = re.sub(self.lithology, "", unit, flags=re.I)
        unit = extract_modifier(unit)[0]
        return re.sub(r" +", " ", unit).strip(", ")

    def _parse_kind(self) -> str:
        """Determines whether unit is chrono- or lithostrat"""
        if self.rank in LITHOSTRAT_RANKS or self.rank == "other":
            return "lithostrat"
        if self._hint is not None:
            hint = self._hint.strip("[]")
            if hint in LITHOSTRAT_RANKS:
                return "lithostrat"
            if hint in CHRONOSTRAT_RANKS:
                return "chronostrat"
        # Final try is to check names against known geologic ages
        if self.unit_name:
            response = self.chronobot.chronostrat(self.unit_name)
            if response.get("success"):
                return "chronostrat"
        return ""

    def _parse_uncertainty(self, unit) -> bool:
        """Looks for uncertainty modifiers in the unit name"""
        pattern = r"(\(?\?\)?$|prob(\.|ably)?)"
        if re.search(pattern, unit, flags=re.I):
            self.unit_name = re.sub(pattern, "", self.unit_name, flags=re.I).strip()
            return True
        return False

    def _sortable(self) -> str:
        """Returns a sortable version of the object"""
        return str(self)


class StratPackage(Record):
    """Parses data about a stratigraphic package

    Parameters
    ----------
    units : str | list[str] | StratUnit | list[StratUnit]
        the units in the package in a format understood by the class

    Properties
    ----------
    units : list[StratUnit]
        a list of stratigraphic units in the package
    kind : str
        the type of unit ('lithostrat' or 'chronostrat'). Not to be confused with rank.
    lithology : str
        the lithology of the most specific unit
    uncertain : bool
        whether the identificaiton of any unit is uncertain
    """

    # Deferred class attributes are defined at the end of the file
    chronobot = None
    lithobot = None

    # Normal class attributes
    terms = ["units"]

    def __init__(self, units):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ["units"]
        super().__init__(units)

    def __str__(self):
        return self.name()

    def name(self) -> str:
        """A concatenated list of the units in order of specificity"""
        return " > ".join([str(u) for u in self.units])

    @property
    def kind(self):
        kinds = {u.kind for u in self.units}
        if len(kinds) == 1:
            return self.units[0].kind
        raise ValueError(f"Inconsistent kind: {kinds}")

    @property
    def lithology(self):
        lithology = ""
        for unit in self.units:
            if unit.lithology:
                lithology = unit.lithology
        return lithology

    @property
    def uncertain(self):
        for unit in self.units:
            if unit.uncertain:
                return True
        return False

    def parse(self, data: str | list[str] | StratUnit | list[StratUnit]) -> None:
        """Parses a list of units from the provided data

        Parameters
        ----------
        data : str | list[str] | StratUnit | list[StratUnit]
            the units in the package

        Returns
        -------
        None
        """
        self.verbatim = data
        if isinstance(data, str):
            data = parse_strat_units(data)
        elif isinstance(data, StratUnit):
            data = [data]
        elif isinstance(data, list):
            data = [u if isinstance(u, StratUnit) else StratUnit(u) for u in data]
        else:
            raise ValueError(f"Could not parse units from {repr(data)}")
        self.units = data
        # Sort units
        order = {
            "supergroup": 0,
            "group": 1,
            "subroup": 2,
            "formation": 3,
            "member": 4,
            "bed": 5,
        }
        self.units.sort(key=lambda u: order.get(u.rank, 6))

    def to_emu(self) -> EMuRecord:
        """Returns the package in EMu XML format

        Returns
        -------
        EMuRecord
            the stratigraphic package

        Raises
        ------
        ValueError
            if the package cannot be converted to EMu XML
        """
        rec = {}
        if self.kind == "lithostrat":
            for unit in self.units:
                if unit.rank in LITHOSTRAT_RANKS[:4]:
                    name = unit.short_name.rstrip("?")
                    rec[f"AgeLithostrat{unit.rank.title()}"] = name
                elif unit.rank in LITHOSTRAT_RANKS[:6]:
                    rec.setdefault("AgeOtherTermsRank_tab", []).append(
                        unit.rank.title()
                    )
                    rec.setdefault("AgeOtherTermsValue_tab", []).append(unit.short_name)
                else:
                    rec.setdefault("AgeOtherTermsRank_tab", []).append("Other")
                    rec.setdefault("AgeOtherTermsValue_tab", []).append(unit.short_name)
            rec["AgeLithostratLithology"] = self.lithology.lower()
            rec["AgeLithostratUncertain"] = "Yes" if self.uncertain else "No"
            rec["AgeVerbatimStratigraphy"] = as_str(self.verbatim)
            return EMuRecord(rec, module="ecatalogue")
        raise ValueError(f"Cannot convert {repr(self.kind)} to EMu")


def parse_strat_units(val, hint=None):
    """Parses a string containing stratigraphic info into a list of units

    Parameters
    ----------
    val : str | StratUnit
        stratigraphic units
    hint : str, optional
        the kind of unit. Useful if it cannot be inferred from val.

    Returns
    -------
    list[StratUnit]
        list of parsed units
    """

    # Return StratUnit as is
    if isinstance(val, StratUnit):
        return [val]

    # Remove parentheticals around uncertainty
    if isinstance(val, str):
        val = val.replace("(?)", "?")

    # Convert names to units
    units = [StratUnit(val, hint=hint) for val in split_strat(val)]

    # Propagate properties of the last unit up the list if needed
    if units:
        last = units[-1]
        if last.kind and all([not u.kind for u in units[:-1]]):
            for unit in units[:-1]:
                with mutable(unit):
                    unit.kind = last.kind
        if last.lithology and all([not u.lithology for u in units[:-1]]):
            for unit in units[:-1]:
                with mutable(unit):
                    unit.lithology = last.lithology
        # Case: Early-Middle Jurassic
        if last.unit_name and all([not u.unit_name for u in units[:-1]]):
            for unit in units[:-1]:
                with mutable(unit):
                    unit.unit_name = extract_modifier(last.unit_name)[0]
                unit.check_chronostrat_name()
    return units


# Define deferred class attributes
LazyAttr(StratUnit, "chronobot", AdamancerBot)
LazyAttr(StratUnit, "lithobot", MacrostratBot)
LazyAttr(StratPackage, "chronobot", AdamancerBot)
LazyAttr(StratPackage, "lithobot", MacrostratBot)
