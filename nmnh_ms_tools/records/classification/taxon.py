"""Defines class for parsing and manipualting rock and mineral names"""

import pprint as pp
import re
from itertools import zip_longest

from unidecode import unidecode

from .taxaparser import TaxaParser
from .taxalist import TaxaList
from ...utils import BaseDict, to_slug


class Taxon(BaseDict):
    """Defines methods for parsing and manipulating rock and mineral names"""

    # Populated by get_tree()
    tree = None

    def __init__(self, data):
        super().__init__()
        self._parsed = None
        self.errors = []
        try:
            self.verbatim = data.copy()
        except AttributeError:
            self.verbatim = data[:]
        if not data:
            pass
        elif isinstance(data, str):
            self._parse_name(data)
        elif "ClaScientificName" in data:
            try:
                self._parse_emu(data)
            except Exception as e:
                raise
        elif "sci_name" in data:
            self.update(data)
        else:
            raise ValueError("Could not parse " + repr(data))
        if self.errors:
            raise IOError(f"Input file contained the following errors: {self.errors}")

    def __getitem__(self, key):
        # Preferred is not stored if this taxon is the preferred name
        if key == "current" and self.is_preferred():
            return self.__class__({"irn": self.irn, "sci_name": self.sci_name})
        # Same with official
        # if key == 'official' and self.is_official():
        #    return self.__class__({
        #        'irn': self.irn,
        #        'sci_name': self.sci_name
        #    })
        if key == "gen_name":
            return sorted(set(self.parsed.keywords))
        # Convert to Taxon if dict
        val = super().__getitem__(key)
        if isinstance(val, dict) and not isinstance(val, self.__class__):
            self[key] = val
            val = self[key]
        return val

    def __setitem__(self, key, val):
        # Coerce dictionaries to Taxon
        if isinstance(val, dict):
            val = self.__class__(val)
        super().__setitem__(key, val)

    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            pass
        return super().__getattr__(attr)

    def __str__(self):
        try:
            return self.name
        except AttributeError:
            return self.sci_name

    def __repr__(self):
        return pp.pformat({k: v for k, v in self.items() if k != "parsed"})

    @property
    def parsed(self):
        if self.tree.disable_index:
            raise ValueError("Indexing has been disabled")
        if self._parsed is None:
            self._parsed = TaxaParser(self.sci_name)
        return self._parsed

    def get_index(self, name):
        """Retrieves the index, creating it if it does not exist"""
        return self.tree.get_index(name)

    def identifiers(self):
        """Returns the list of identifiers for this name"""
        ids = [self.name, self.sci_name] + [a["code"] for a in self.authorities]
        return sorted(set(ids))

    def same_as(self, other):
        """Tests if taxon is the same as another taxon"""
        names = [self.sci_name]
        try:
            others = [other.sci_name]
        except AttributeError:
            others = [other]

        for lst in (names, others):
            try:
                lst.append(_invert_delimited_name(lst[0]))
            except ValueError:
                pass

        return set({self.key(n) for n in names}) & set({self.key(n) for n in others})

    def similar_to(self, other):
        """Tests if taxon is similar to as another taxon"""
        try:
            return (
                self.same_as(other)
                or self.key(self.name) == self.key(other.name)
                or self.parsed.similar_to(other.parsed)
            )
        except AttributeError:
            return self.same_as(other) or self.key(self.name) == self.key(other)

    def facet(self, include_synonyms=True):
        """Facet a taxon for matching"""
        # Add common endings for groups, series, etc.
        variants = [
            self.get("name"),
            self.get("sci_name"),
            self.get("official"),
            self.get("preferred"),
        ]
        if include_synonyms:
            variants.extend(self.get("synonyms", []))
        variants = [s["sci_name"] if isinstance(s, dict) else s for s in variants]
        endings = (" series", " group", " (general term)")
        faceted = []
        for term in [s.lower() for s in variants if s]:
            term = term.lower()
            for ending in endings:
                if term.endswith(ending):
                    term = term[: -len(ending)].strip()
                    break
            for val in (term, unidecode(term)):
                faceted.append(val)
                faceted.extend([val + ending for ending in endings])
        return [sp for i, sp in enumerate(faceted) if not sp in faceted[:i]]

    def to_emu(self):
        """Converts taxon to EMu etaxonomy record"""
        if re.match(r"[0-9]+$", str(self.irn)):
            return {"irn": self.irn}
        return {
            "ClaScientificName": self.sci_name,
            "ClaOtherValue_tab": [self.name],
            "ClaOtherRank_tab": [self.rank],
            "RanParentRef": self.parent.to_emu(),
            "ClaCurrentlyAccepted": "Yes",
            "NotNotes": "Record generated by nmnh_ms_tools",
        }

    def _parse_emu(self, rec):
        """Parses an EMu record"""
        if (
            len(rec.get("ClaOtherValue_tab", [])) != 1
            or len(rec.get("ClaOtherRank_tab", [])) != 1
            or rec.get("ClaSpecies")
        ):
            raise ValueError(f"Data integrity error: {rec}")
        self["irn"] = int(rec["irn"])
        self["sci_name"] = rec["ClaScientificName"]
        self["rank"] = rec["ClaOtherRank_tab"][0]
        # Get the base name. For some records, this will be the same as the
        # scientific name.
        name = rec["ClaOtherValue_tab"][0]
        if name.count(",") == 1 and not name[0].isnumeric():
            name = " ".join([s.strip() for s in name.split(",")][::-1])
            if self.key(name) == self.key(self["sci_name"]):
                name = self["sci_name"]
        self["name"] = name
        # Set parent
        try:
            self["parent"] = {
                "irn": int(rec["RanParentRef.irn"]),
                "sci_name": rec["RanParentRef.ClaScientificName"],
            }
        except (KeyError, TypeError):
            self["parent"] = None
        # Set current
        self["_is_preferred"] = rec.get("ClaCurrentlyAccepted") == "Yes"
        if not self["_is_preferred"]:
            try:
                self["current"] = {
                    "irn": int(rec["ClaCurrentNameRef.irn"]),
                    "sci_name": rec["ClaCurrentNameRef.ClaScientificName"],
                }
            except KeyError:
                raise KeyError(f'Current taxon not defined: {rec["irn"]}')
        # Set official
        self["_is_official"] = (
            rec.get("TaxValidityStatus") == "Valid"
            and rec.get("ClaCurrentlyAccepted") == "Yes"
        )
        # Set authorities
        self["authorities"] = []
        for kind, val in zip_longest(
            rec.get("DesLabel0", []), rec.get("DesDescription0", [])
        ):
            self.authorities.append({"kind": kind, "val": val})
        # Set similar
        self["notes"] = rec.get("NotNotes", "")

    def _parse_name(self, name):
        """Parses a name"""
        try:
            self.update(self._find_one(name))
        except KeyError:
            # Set defaults for an unknown taxon
            self["_is_preferred"] = True
            self["_is_official"] = False
            self["authorities"] = []
            self._parsed = TaxaParser(name)
            name = self.tree.capped(self.parsed.name)
            self["name"] = name
            self["sci_name"] = name
            self["parent"] = self.tree.guess_parent(name)
            try:
                self["rank"] = self["parent"]["rank"]
            except TypeError:
                self["parent"] = self.__class__(
                    {"irn": "1014715", "sci_name": "Unknown"}
                )
                self["rank"] = "unknown"
            self["irn"] = None
            self["notes"] = ""

    def fix_current(self):
        """Fixes current taxon designation, which can break the other fixes"""
        try:
            self.preferred()
        except ValueError:
            if not self.is_preferred() and self.irn == self.current.irn:
                self["_is_preferred"] = True
                return {"irn": self.irn, "ClaCurrentlyAccepted": "Yes"}

    def fix(self):
        """Fixes integrity errors for this taxon"""
        rec = {}
        self.parents()
        parent = self.tree[self.parent.irn] if self.parent else None
        # Check for missing official taxon
        try:
            self.official()
        except ValueError:
            print(f"Warning: No official taxon for {self.name}")
            return {}
        # Check for infinite loops in preferred method
        try:
            preferred = self.preferred()
        except ValueError:
            if not self.is_preferred() and self.irn == self.current.irn:
                rec["ClaCurrentlyAccepted"] = "Yes"
                self["_is_preferred"] = True
            try:
                preferred = self.preferred()
            except ValueError:
                # Fall back to a lookup by irn
                preferred = self.tree[self.current.irn]
        # Map synonyms to fall under their preferred name in the hierarchy
        if (
            parent
            and not parent.name[0].isnumeric()
            and parent.rank != "synonym"
            and self != preferred
            and preferred.irn != parent.irn
        ):
            print(f"Species:   {self.name} (irn={self.irn})")
            print(f"Parent:    {parent.name} (irn={parent.irn})")
            print(f"Preferred: {preferred.name} (irn={preferred.irn})")
            print("---")
            rec["RanParentRef"] = preferred.irn
        # Set rank to synonym where appropriate
        if self != preferred and self.rank != "synonym":
            rec["ClaOtherRank_tab"] = ["synonym"]
        if rec:
            rec["irn"] = self.irn
        return rec

    def preferred(self):
        """Finds the preferred taxon for deprecated terms and other synonyms"""
        preferred = self
        i = 0
        while not preferred.is_preferred():
            preferred = self.tree[preferred.current.irn]
            i += 1
            if i > 100:
                raise ValueError(f"Infinite loop in preferred: {repr(self.name)}")
        return preferred

    def official(self):
        """Returns the most specific official taxon"""
        taxon = self.preferred()
        if not taxon.is_official():
            i = 0
            for parent in taxon.parents(include_self=True, full_records=True)[::-1]:
                if parent.is_official():
                    return parent
                i += 1
                if i > 100:
                    raise ValueError(f"Infinite loop in official: {repr(self.name)}")
        return taxon

    def parents(self, include_self=False, full_records=False):
        """Finds parents of this taxon to the top of the hierarchy"""
        parents = []
        taxon = self.preferred()
        i = 0
        while taxon.parent:
            taxon = self.tree[taxon.parent.irn].preferred()
            parents.insert(0, taxon)
            i += 1
            if i > 100:
                raise ValueError(f"Infinite loop in parents: {repr(self.name)}")
        if include_self:
            parents.append(Taxon({"irn": self.irn, "sci_name": self.sci_name}))
        if full_records:
            parents = [self.tree[p.irn] for p in parents if p.irn is not None]
        return TaxaList(parents)

    def codes(self, name=None):
        """Gets classification codes from authorities"""
        return [
            a["code"]
            for a in self.authorities
            if name is None or name.lower() in a["source"].lower()
        ]

    def autoname(self, ucfirst=True, use_preferred=True):
        """Generates the complete name of a taxon"""
        taxon = self.preferred() if use_preferred else self
        name = taxon.name
        # Filter out codes
        if re.match(r"\d", name):
            return name
        if taxon.rank == "variety":
            for parent in taxon.parents(full_records=True):
                if parent.rank == "mineral":
                    name = f"{parent.name} (var. {taxon.name})"
                    break
        if name.count(",") == 1 and not name[0].isnumeric():
            name = " ".join([s.strip() for s in name.split(",") if s][::-1])
        return self.tree.capped(name, ucfirst=ucfirst)

    def guess_parent(self):
        """Automatically places a taxon into the hierarchy"""
        return self.tree.guess_parent(self.preferred().sci_name)

    def classify(self, preferred=True):
        """Classifies a taxon as a rock, mineral, or meteorite"""
        taxon = self.preferred() if preferred else self
        parents = taxon.parents()
        if "Meteorites" in parents:
            return ["meteorite"]
        if "Minerals" in parents:
            return ["mineral"]
        if "Peridotite" in parents or "Pyroxenite" in parents:
            return ["rock", "igneous", "peridotite"]
        if "Pyroclastic-rock and pyroclastic-sediment" in parents:
            return ["rock", "igneous", "volcanic", "pyroclast"]
        if "Crystalline-igneous-rock" in parents and any(
            [str(p).startswith("Fine") for p in parents]
        ):
            return ["rock", "igneous", "volcanic", "lava"]
        if "Crystalline-igneous-rock" in parents and any(
            [str(p).startswith("Coarse") for p in parents]
        ):
            return ["rock", "igneous", "plutonic"]
        if "Igneous rock and igneous sediment" in parents:
            return ["rock", "igneous"]
        if "Metamorphic rocks and metasediments" in parents:
            return ["rock", "metamorphic"]
        if "Rock" in parents:
            return ["rock"]
        return ["other"]

    def is_meteorite(self, preferred=True):
        """Tests if taxon is a meteorite"""
        return "meteorite" in self.classify(preferred=preferred)

    def is_mineral(self, preferred=True):
        """Tests if taxon is a mineral"""
        return "mineral" in self.classify(preferred=preferred)

    def is_rock(self, preferred=True):
        """Tests if taxon is a rock"""
        return "rock" in self.classify(preferred=preferred)

    def is_igneous(self, preferred=True):
        """Tests if taxon is an igneous rock"""
        return "igneous" in self.classify(preferred=preferred)

    def is_metamorphic(self, preferred=True):
        """Tests if taxon is a metamorphic rock"""
        return "metamorphic" in self.classify(preferred=preferred)

    def is_sedimentary(self, preferred=True):
        """Tests if taxon is a sedimentary rock"""
        return "sedimentary" in self.classify(preferred=preferred)

    def is_peridotite(self, preferred=True):
        """Tests if taxon is a peridotite"""
        return "peridotite" in self.classify(preferred=preferred)

    def is_volcanic(self, preferred=True):
        """Tests if taxon is volcanic"""
        return "volcanic" in self.classify(preferred=preferred)

    def is_lava(self, preferred=True):
        """Tests if taxon is formed from lava"""
        return "lava" in self.classify(preferred=preferred)

    def is_pyroclast(self, preferred=True):
        """Tests if taxon is pyroclast"""
        return "pyroclast" in self.classify(preferred=preferred)

    def is_plutonic(self, preferred=True):
        """Tests if taxon is plutonic"""
        return "plutonic" in self.classify(preferred=preferred)

    def is_official(self):
        """Tests if taxon is an official name"""
        return self["_is_official"]

    def is_preferred(self):
        """Tests if taxon is a preferred name"""
        return self["_is_preferred"]

    @staticmethod
    def key(key):
        """Returns a standardized form of the name"""
        return to_slug(str(key)).replace("_", "") if key else ""

    def _find(self, val, index="name_index"):
        return self.tree.find(val, index)

    def _find_one(self, val, index="name_index"):
        return self.tree.find_one(val, index)


def _invert_delimited_name(name):
    if name.count(",") == 1:
        return " ".join([s.strip() for s in name.split(",")][::-1])
    raise ValueError(f"Could not invert name: {name}")


# Set itemclass attribute on TaxaList once Taxon exists
TaxaList.itemclass = Taxon
