"""Defines a class for systematically naming rocks and minerals"""

import os
import re

import yaml

from .taxalist import TaxaList
from .taxatree import TaxaTree
from ...config import CONFIG_DIR
from ...utils import LazyAttr, ucfirst


class TaxaNamer(TaxaTree):
    """Derives names for taxa based on position in a hierarchy"""

    # Deferred class attributes are defined at the end of the file
    capex = None
    config = None

    def capped(self, name=None, capitalize=True):
        """Capitalizes taxon name based on simple set of rules and exceptions"""
        if name is None:
            name = self.sci_name
        # Filter out codes
        if re.match(r"\d", name):
            return name
        name = name.lower()
        for word in self.capex:
            pattern = re.compile(r"\b{}\b".format(word), flags=re.I)
            matches = pattern.findall(name)
            if matches and word.isupper():
                name = pattern.sub(matches[0].upper(), name)
            else:
                name = pattern.sub(word, name)
        return ucfirst(name) if name and capitalize else name

    def join(self, names, maxtaxa=3, conj="and"):
        """Joins a list of taxa into a string, a la oxford_comma"""
        conj = " {} ".format(conj.strip())
        if maxtaxa is not None and len(names) > maxtaxa:
            names = names[:maxtaxa]
        if len(names) <= 2:
            return conj.join(names)
        if conj.strip() in ["with"]:
            first = names.pop(0)
            return "{} with {}".format(first, self.join(names, None, "and"))
        last = names.pop()
        return "{},{}{}".format(", ".join(names), conj, last)

    def name_item(self, taxa, setting=None, allow_varieties=False):
        """Generates name based using a list of taxa and an optional setting"""
        taxalist = TaxaList()
        for taxon in [t for t in taxa if t]:
            matches = self.place(taxon)  # place always returns one
            taxalist.append(TaxaList([matches]).best_match(taxon, True))
        taxalist = taxalist.unique()
        if setting:
            name = "{} {}".format(self.join(taxalist.names()[:2]), setting)
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


def _read_capitalization_rules():
    return [str(s) if isinstance(s, int) else s for s in TaxaNamer.config["capex"]]


# Define deferred class attributes
LazyAttr(TaxaNamer, "capex", _read_capitalization_rules)
LazyAttr(TaxaNamer, "config", os.path.join(CONFIG_DIR, "config_classification.yml"))
