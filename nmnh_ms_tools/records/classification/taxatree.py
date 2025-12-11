"""Defines classes to build and index a hierarchy of geological taxa"""

import json
import logging
import pprint as pp
import os
import re
from collections.abc import MutableMapping, MutableSequence

from xmu import write_xml

from .taxalist import TaxaList
from .taxaparser import TaxaParser
from .taxon import Taxon
from ...config import CONFIG, CONFIG_DIR
from ...utils import LazyAttr, to_slug, ucfirst


logger = logging.getLogger(__name__)


class TaxaIndex(MutableMapping):
    """Defines basic structure for a taxonomic hierarchy"""

    def __init__(self, *args, **kwargs):
        self.obj = {}
        self.new = {}
        self.timestamp = None
        self.update(*args, **kwargs)

    def __getattr__(self, attr):
        return self[attr]

    def __getitem__(self, key):
        try:
            return self.obj[self.key(key)]
        except KeyError:
            return self.new[self.key(key)]

    def __setitem__(self, key, val):
        if isinstance(val, dict):
            val = Taxon(val)
        self.obj[self.key(key)] = val

    def __delitem__(self, key):
        del self.obj[self.key(key)]

    def __iter__(self):
        return iter(self.obj)

    def __len__(self):
        return len(self.obj)

    def __str__(self):
        return pp.pformat(self.obj)

    def __repr__(self):
        return repr(self.obj)

    def __contains__(self, key):
        try:
            self[key]
        except KeyError:
            return False
        return True

    def update(self, *args, **kwargs):
        """Explicitly routes update through class.__setitem__"""
        for key, val in dict(*args, **kwargs).items():
            self[key] = val

    def one(self, key):
        """Returns match on key if exactly one found"""
        try:
            matches = self[key]
        except KeyError:
            raise KeyError(f"No matches on {repr(self.key(key))}")
        # Result is a taxon record
        if isinstance(matches, dict):
            return matches
        # Result is a list of matching records
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise KeyError(f"No matches on {repr(self.key(key))}")
        raise KeyError(f"Multiple matches on {repr(self.key(key))}")

    def from_json(self, fp, encoding="utf-8"):
        """Reads data from JSON file"""
        if self.timestamp is not None and os.path.getmtime(fp) < self.timestamp:
            raise IOError("Taxa index is older than EMu export")
        with open(fp, encoding=encoding) as f:
            self.update(json.load(f))

    def to_json(self, fp, encoding="utf-8"):
        """Writes data to JSON file"""

        class _Encoder(json.JSONEncoder):
            def default(self, obj):
                try:
                    return json.JSONEncoder.default(self, obj)
                except TypeError as exc:
                    for from_class, to_class in (
                        (MutableMapping, dict),
                        (MutableSequence, list),
                    ):
                        if isinstance(obj, from_class):
                            return to_class(obj)
                    raise

        try:
            os.makedirs(os.path.dirname(fp))
        except OSError:
            pass

        with open(fp, "w", encoding=encoding) as f:
            json.dump(self, f, cls=_Encoder)

    @staticmethod
    def key(key):
        return to_slug(str(key)).replace("_", "") if key else ""


class TaxaTree(TaxaIndex):
    """Builds an indexed taxonmic hierarchy"""

    # Deferred class attributes are defined at the end of the file
    name_index = None
    stem_index = None
    capex = None
    config = None

    def __init__(self, *args, **kwargs):
        self.disable_index = False
        super().__init__(*args, **kwargs)
        self.indexers = {"name_index": NameIndex, "stem_index": StemIndex}

    def __contains__(self, key):
        try:
            self.find(key)
            return True
        except KeyError:
            return False

    def __getitem__(self, key):
        return self.find_one(key)

    def find(self, term, index="name_index"):
        """Finds all matches for a search term"""
        terms = [term]
        if isinstance(term, str) and term.count(",") == 1:
            terms.append(" ".join([s.strip() for s in term.split(",")][::-1]))
        for term in terms:
            try:
                return [super().__getitem__(term)]
            except KeyError:
                try:
                    return [self[irn] for irn in self.get_index(index)[term]]
                except KeyError:
                    pass
        raise KeyError(f"Term not found: '{terms[0]}'")

    def find_one(self, term, index="name_index"):
        """Finds the best match on a search term"""
        matches = self.find(term, index)
        if len(matches) == 1:
            return matches[0]
        return TaxaList(matches).best_match(term)

    def place(self, name):
        """Places a name in the hierarchy, adding a new entry if needed"""
        if not name.strip():
            raise ValueError(f"name is empty: {repr(name)}")
        qualifier = "uncertain" if name.endswith("?") else ""
        name = name.rstrip("?")
        try:
            taxon = self.find_one(name)
        except KeyError:
            parsed = self.parse(name)
            try:
                taxon = self.find_one(parsed.name)
            except KeyError:
                taxon = Taxon(name)
                taxon["irn"] = self.key(name)
                self.new[self.key(name)] = taxon
                # Add new taxon to index
                for index in self.indexers:
                    self.get_index(index).add_taxon(taxon)
            # Create a copy and add the parsed name
            taxon = Taxon({k: v for k, v in taxon.items()})
            taxon["parsed"] = parsed
        taxon["qualifier"] = qualifier
        return taxon

    def guess_parent(self, name):
        """Guesses the parent of the given name"""
        parsed = TaxaParser(name)
        matches = []
        for parent in parsed.parents():
            try:
                matches = self.get_index("stem_index")[parent]
            except KeyError:
                pass
            else:
                matches = [self[irn].preferred() for irn in matches]
                matches.sort(key=parsed.compare_to, reverse=True)
                break
        # Filter recursive matches (parent == child)
        if not (parsed.alteration or parsed.colors or parsed.textures):
            matches = [m for m in matches if m.sci_name != name]
        # Filter matches so only official names remain
        if len(matches) > 1:
            official = [m for m in matches if m.is_official()]
            if official:
                matches = official
        return matches[0] if matches else None

    def get_index(self, name):
        """Retrieves the index, creating it if needed"""
        if self.disable_index:
            return TaxaIndex()
        return getattr(self, name)

    def write_new(self, fp="import.xml"):
        """Writes an EMu import file containing any new taxa"""
        if self.new:
            taxa = [self.new[k] for k in sorted(self.new.identifiers())]
            write_xml([t.to_emu() for t in taxa], fp)

    def capped(self, name=None, capitalize=True):
        """Capitalizes taxon name based on simple set of rules and exceptions"""
        if name is None:
            name = self.sci_name
        # Filter out codes
        if re.match(r"\d", name):
            return name
        name = name.lower()
        for word in self.capex:
            pattern = re.compile(rf"\b{word}\b", flags=re.I)
            matches = pattern.findall(name)
            if matches and word.isupper():
                name = pattern.sub(matches[0].upper(), name)
            else:
                name = pattern.sub(word, name)
        return ucfirst(name) if name and capitalize else name

    def join(self, names, maxtaxa=3, conj="and"):
        """Joins a list of taxa into a string, a la oxford_comma"""
        conj = f" {conj.strip()} "
        if maxtaxa is not None and len(names) > maxtaxa:
            names = names[:maxtaxa]
        if len(names) <= 2:
            return conj.join(names)
        if conj.strip() in ["with"]:
            first = names.pop(0)
            return f"{first} with {self.join(names, None, "and")}"
        last = names.pop()
        return f"{", ".join(names)},{conj}{last}"

    def name_item(self, taxa, setting=None, allow_varieties=False):
        """Generates name based using a list of taxa and an optional setting"""
        taxalist = TaxaList()
        for taxon in taxa:
            if taxon:
                matches = self.place(str(taxon))  # place always returns one
                taxalist.append(TaxaList([matches]).best_match(taxon, True))
        taxalist = taxalist.simplify()
        if setting:
            name = f"{self.join(taxalist.names()[:2])} {setting}"
        elif len(taxa) == 1 or len(set(taxalist.names())) == 1:
            name = taxalist[0].name if allow_varieties else taxalist[0].sci_name
        elif len(taxa) == 2 and taxalist[0].is_mineral() and taxalist[1].is_rock():
            name = self.join(taxalist.names(), conj="from")
        else:
            name = self.join(taxalist.names(), conj="with")
        return self.capped(name, capitalize=True)

    def name_group(self, taxa, capitalize=False):
        """Generates a name describing a list of taxa"""
        name = self.join(TaxaList(taxa).names()).lower()
        return ucfirst(name) if capitalize else name

    @staticmethod
    def most_specific_common_parent(taxa):
        """Groups a list of taxa as specifically as possible"""
        return TaxaList(taxa).most_specific_common_parent()

    @staticmethod
    def parse(name):
        """Parses a name"""
        return TaxaParser(name)

    def _assign_synonyms(self):
        """Attaches list of synonyms to each preferred taxon"""
        for taxon in self.values():
            if not taxon.is_preferred():
                try:
                    current = self[taxon.current.irn]
                except (AttributeError, KeyError):
                    # Records with unknown current name end up here
                    pass
                else:
                    current.setdefault("synonyms", TaxaList()).append(
                        {"irn": taxon.irn, "sci_name": taxon.sci_name}
                    )

    def _assign_similar(self):
        """Attaches list of similar taxa to each preferred taxon"""
        similar = {}
        for taxon in self.values():
            if taxon.gen_name:
                similar.setdefault(tuple(taxon.gen_name), []).append(
                    {"irn": taxon.irn, "sci_name": taxon.sci_name}
                )
        for taxa in similar.values():
            if len(taxa) > 1:
                for taxon in taxa:
                    matches = [t for t in taxa if t["irn"] != taxon["irn"]]
                    taxon = self[taxon["irn"]]
                    taxon.setdefault("similar", TaxaList()).extend(matches)

    def _assign_official(self):
        """Assigns the closest official taxon"""
        for taxon in self.values():
            if not taxon.is_official():
                parent = taxon
                i = 0
                while parent.parent:
                    try:
                        parent = self[parent.parent.irn]
                    except KeyError:
                        break
                    else:
                        if parent.is_official():
                            taxon["official"] = {
                                "irn": parent.irn,
                                "rank": parent.rank,
                                "sci_name": parent.sci_name,
                            }
                            break
                    i += 1
                    if i > 100:
                        break


class NameIndex(TaxaIndex):
    """Constructs an index of taxon names"""

    path = CONFIG["data"].get("name_index", "name_index.json")
    tree = None

    def __init__(self, tree=None):
        super().__init__()
        try:
            self.from_json(self.path)
        except (IOError, OSError):
            if tree is None:
                tree = self.tree
            if tree:
                print(f"Building name index...")
                count = 0
                for obj in [tree.obj, tree.new]:
                    for taxon in obj.values():
                        self.add_taxon(taxon)
                        count += 1
                        if not count % 5000:
                            print(f"{count:,} names processed")
                print(f"{count:,} names processed")
                for key, taxa in self.items():
                    self[key] = sorted(set(taxa))
                self.to_json(self.path)
                print("Done!")

    def add_taxon(self, taxon):
        """Adds an entry to the index"""
        self.setdefault(taxon.sci_name, []).append(taxon.irn)
        if taxon.sci_name != taxon.name:
            self.setdefault(taxon.name, []).append(taxon.irn)


class StemIndex(TaxaIndex):
    """Constructs an index of stemmed taxon names"""

    path = CONFIG["data"].get("stem_index", "stem_index.json")
    tree = None

    def __init__(self, tree=None):
        super().__init__()
        try:
            self.from_json(self.path)
        except (IOError, OSError):
            if tree is None:
                tree = self.tree
            if tree:
                print(f"Building stem index...")
                count = 0
                for obj in [tree.obj, tree.new]:
                    for taxon in obj.values():
                        self.add_taxon(taxon)
                        count += 1
                        if not count % 5000:
                            print(f"{count:,} names processed")
                print(f"{count:,} names processed")
                for key, taxa in self.items():
                    self[key] = sorted(set(taxa))
                self.to_json(self.path)
                print("Done!")

    def add_taxon(self, taxon):
        """Adds an entry to the index"""
        self.setdefault(taxon.parsed.indexed, []).append(taxon.irn)

    @staticmethod
    def key(val):
        return val


def _read_capitalization_rules():
    return [str(s) if isinstance(s, int) else s for s in TaxaTree.config["capex"]]


# Define deferred class attributes
LazyAttr(NameIndex, "tree", lambda: Taxon.tree)
LazyAttr(StemIndex, "tree", lambda: Taxon.tree)
LazyAttr(TaxaTree, "name_index", NameIndex)
LazyAttr(TaxaTree, "stem_index", StemIndex)
LazyAttr(TaxaTree, "capex", _read_capitalization_rules)
LazyAttr(TaxaTree, "config", os.path.join(CONFIG_DIR, "config_classification.yml"))
