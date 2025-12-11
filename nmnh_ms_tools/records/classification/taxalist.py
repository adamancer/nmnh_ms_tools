"""Defines methods for parsing and manipulating lists of rock/mineral names"""

import re
from collections.abc import MutableSequence


class TaxaList(MutableSequence):
    """Parses and manipulate lists of rock and mineral names"""

    itemclass = dict

    def __init__(self, *args, **kwargs):
        self.obj = [self.itemclass(taxon) for taxon in list(*args, **kwargs)]

    def __getitem__(self, i):
        return self.obj[i]

    def __setitem__(self, i, val):
        self.obj[i] = self.itemclass(val)

    def __delitem__(self, i):
        del self.obj[i]

    def __len__(self):
        return len(self.obj)

    def __contains__(self, val):
        return val in self.irns() or val in self.sci_names() or val in list(self)

    def __str__(self):
        return str(self.sci_names())

    def __repr__(self):
        return repr(self.obj)

    def copy(self):
        """Returns a copy of the list"""
        return self.__class__(self[:])

    def wrap(self):
        """Wraps list items in itemclass"""
        self.obj = [self.itemclass(taxon) for taxon in self.obj]
        return self

    def insert(self, i, val):
        """Converts value to itemclass and inserts at index"""
        self.obj.insert(i, self.itemclass(val))

    def irns(self):
        """Returns list of irns corresponding to the taxa in the list"""
        return [t.irn for t in self.obj]

    def names(self):
        """Returns list of names corresponding to the taxa in the list"""
        return [t.name for t in self.obj]

    def sci_names(self):
        """Returns list of full names corresponding to the taxa in the list"""
        return [t.sci_name for t in self.obj]

    def best_match(self, name=None, force_match=True):
        """Finds the best match for a given name in this list"""
        orig = self.obj[:]
        # Finds taxa with same scientific name
        matches = [t for t in self if t.same_as(name)]
        # Finds taxa with similar scientific name
        if not matches:
            matches = [t for t in self if t.similar_to(name)]
        # Finds taxa with same short name
        if not matches:
            matches = [t for t in self if t.key(name) == t.key(t.name)]
        # Limit to official taxa if more than one match found
        if len(matches) > 1:
            official = [t for t in matches if t.is_official()]
            if official:
                matches = official
        if matches:
            self.obj = matches
            unique = self.unique()
            # Limit to official taxa if more than one match found... again
            if len(unique) > 1:
                matches = [t for t in unique if t.is_official()]
                if matches:
                    unique = matches
            # Reset the obj attribute on the original object
            self.obj = orig
            # Finds exact matches to the original name
            if len(unique) == 1 or (force_match and unique):
                return unique[0]
            if force_match:
                return self[0]
        raise ValueError(f"{name}: {self.irns()}")

    def unique(self):
        """Remove duplicate taxa, including less specific names"""
        all_parents = [t.parents(True, True) for t in self]
        taxa = self.copy()
        for i, parents in enumerate(all_parents):
            parents = TaxaList(parents)
            specific = parents.pop()
            for parent in parents:
                if parent.name != specific.name:
                    while parent.name in taxa.names()[:i]:
                        j = taxa.names().index(parent.name)
                        taxa[j] = specific
        unique = [t for i, t in enumerate(taxa) if t not in taxa[:i]]
        return self.__class__(unique)

    def simplify(self):
        """Remove redundant taxa"""
        taxa = []
        for taxon in self.unique():
            if not re.search(rf"\b{str(taxon).lower()}\b", "-".join(taxa)):
                taxa.append(str(taxon).lower())
        return self.__class__(taxa)

    def most_specific_common_parent(self, name="specimens"):
        """Finds the most specific common parent"""
        parents = [t.parents(True, False) for t in self]
        i = 0
        while True:
            try:
                distinct = list({str(p[i]) for p in parents})
                if len(distinct) != 1:
                    return name
                name = distinct[0]
                i += 1
            except IndexError:
                # At least one list is empty
                return name
