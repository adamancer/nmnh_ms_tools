"""Extracts features from strings"""
import logging

logger = logging.getLogger(__name__)

import re

from ....utils import as_list, repr_class, str_class


class Parser:
    kind = None
    attributes = ["kind", "verbatim", "unconsumed", "feature"]
    feature_parser = None
    cache = {}

    def __init__(self, val=None, **kwargs):
        self.verbatim = None  # original text passed to the parser
        self.unconsumed = None  # fragment remaining after parsing
        self.feature = None  # parsed feature name
        self._hints = {}
        if val is not None:
            self.parse(val, **kwargs)

    def __str__(self):
        return self.name()

    def __repr__(self):
        return repr_class(self)

    def __eq__(self, other):
        try:
            for attr in self.attributes:
                if getattr(self, attr) != getattr(other, attr):
                    return False
            else:
                return True
        except AttributeError:
            return False

    def __iter__(self):
        """Returns the list of parsed features from a single parse

        Uses nested lists because some parsers return groups of options.
        """
        return iter([[self]])

    def variants(self):
        """Returns a list of possible interpretations for a given string"""
        return [str(self)]

    def parse(self, text):
        """Parses a locality string to extract usable geographic information"""
        return NotImplementedError

    def name(self):
        """Returns a string describing the parsed locality"""
        return NotImplementedError

    def names(self):
        """Returns the list of parsed names"""
        try:
            nested_features = self.features
        except AttributeError:
            nested_features = [[self.feature]]

        names = []
        for features in nested_features:
            for feat in as_list(features):
                if isinstance(feat, Parser):
                    names.extend(feat.names())
                else:
                    names.append(feat)

        return [n for n in names if n]

    def reset(self):
        """Resets all attributes to defaults"""
        for attr in self.attributes:
            if callable(getattr(self, attr)):
                raise ValueError("Cannot delete a method: {}".format(attr))
            setattr(self, attr, None)

    def expand(self, site, interpreted=None):
        """Expands generic features based on info in site"""
        if interpreted is None:
            interpreted = {}
        if self.feature is None:
            return self
        match = re.search(r"{([a-z\_]+)}", self.feature)
        if match is None:
            return self
        """
        # Match feature to adjacent phrase
        rel = {k: v for k, v in site.to_dict().items() if self.verbatim in v}
        for field, vals in rel.items():
            vals = as_list(vals)
            try:
                feature = self.feature_parser(vals[0])
                expanded = self.feature.format(**{key: feature})
                mask = 'Expanded {} to "{}"'
                logger.debug(mask.format(self.feature, expanded))
                self.feature = expanded
                return self
            except:
                pass
        rel = {k: v for k, v in site.to_dict().items() if self.verbatim in v}
        """
        # Match feature to specific field
        attrs = ["municipality", "island", "county", "state_province", "country"]
        key = match.group(1)
        if key != "feature":
            attrs = [key]
        for attr in attrs:
            vals = as_list(interpreted.get(attr, []))
            try:
                vals.extend(as_list(getattr(site, attr)))
            except AttributeError:
                pass
            if len(set(vals)) == 1:
                feature = self.feature_parser(vals[0])
                expanded = self.feature.format(**{key: feature})
                mask = 'Expanded {} to "{}"'
                logger.debug(mask.format(self.feature, expanded))
                self.feature = expanded
                return self
        # Warn user if not possible to expand the term
        raise ValueError("Could not expand {}".format(self.feature))
        # self.feature = self.feature.replace('{', '').replace('}', '')
        # return self
