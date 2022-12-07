"""Identifies simple feature names mushed together in one string"""
import logging
import re

from .border import BorderParser
from .core import Parser
from .feature import FeatureParser, FEATURES, OF_WORDS, append_feature_type
from .junction import JunctionParser
from .modified import ModifiedParser, is_modified_feature
from .offshore import OffshoreParser
from .simple import SimpleParser
from ....utils import as_list, oxford_comma


logger = logging.getLogger(__name__)


class MultiFeatureParser(Parser):
    """Parses strings containing one or more features

    This class tries to handle strings containing multiple names pointing
    to the same feature. By contrast, FeatureParser handles simple and/or
    parsing where the conjoined names are expected to either (1) be a single
    feature (like "Turks and Caicos Islands") or (2) represent multiple
    distinct features.
    """

    kind = "multifeature"
    attributes = ["kind", "verbatim", "features"]

    def __init__(self, *args, **kwargs):
        self.features = []
        self.specific = False
        super(MultiFeatureParser, self).__init__(*args, **kwargs)

    def __iter__(self):
        return iter(self.features)  # list of lists

    def __len__(self):
        return len(self.features)

    def __getitem__(self, i):
        return self.features[i]

    def __setitem__(self, i, val):
        self.features[i] = val

    def __delitem__(self, i):
        del self.features[i]

    def append(self, val):
        """Adds a feature name to the internal list"""
        self.features.append(val)

    def extend(self, vals):
        """Extends the internal feature list with a list of feature names"""
        self.features.extend(vals)

    def unique_match(self):
        """Tests if multifeature matches a single feature"""
        return len(self) == 1 and len(self[0]) == 1

    @property
    def feature(self):
        if self.unique_match():
            return self[0][0].name()
        return self.name()

    @feature.setter
    def feature(self, val):
        if val is not None:
            raise AttributeError("Cannot set feature attribute")

    @property
    def feature_kind(self):
        if self.unique_match():
            return self[0][0].feature_kind
        return

    def name(self):
        for features in list(self)[::-1]:
            return oxford_comma([str(f).strip('"') for f in features])
        return self.verbatim

    def variants(self):
        if self.unique_match():
            return self[0][0].variants()
        return [[f.feature for f in features] for features in self.features]

    def parse(self, val, allow_generic=False):
        """Parses string that may contain more than one feature"""
        # Not intended for delimited strings
        if re.search(r"[:;,\|]", val) and not is_modified_feature(val, False):
            raise ValueError('Could not parse: "{}" (delimited)'.format(val))
        val = val.strip()
        self.verbatim = val
        try:
            self.features = [self.parse_features([val])]
        except ValueError:
            pass

        # split_conjunction splits on "of", which is a problem for modified
        # strings like "S half of Place Name". Exclude those features from
        # the multifeature check.
        if self.unique_match() and self.features[0][0].kind == "modified":
            return

        # Look for alternative interpretations of a place name. For example,
        # "Turks and Caicos Islands" could be interpreted as is or could
        # be interpreted (wrongly) as ["Turks Islands", "Caicos Islands"].
        for func in (
            self.split_parentheticals,
            self.split_features,
            self.split_conjunction,
        ):
            try:
                vals = func(val)
                if len(vals) > 1:
                    if isinstance(vals[0], list):
                        self.features.extend(vals)
                        for val in vals:
                            self.specific = any([f.specific for f in val])
                            if self.specific:
                                break
                    else:
                        self.features.append(vals)
                        self.specific = any([f.specific for f in vals])
                    break
            except ValueError:
                pass

        if not any(self.features):
            mask = 'Could not parse: "{}" (invalid multifeature)'
            raise ValueError(mask.format(val))

    def parse_features(self, vals):
        """Parses features from a list of names"""
        features = []
        for val in as_list(vals):
            if val:
                # Parser list is roughly anything that could be used as
                # a reference point for a direction
                for parser in (
                    OffshoreParser,
                    JunctionParser,
                    BorderParser,
                    ModifiedParser,
                    FeatureParser,
                ):
                    try:
                        features.append(parser(val))
                        break
                    except ValueError:
                        pass
                else:
                    # Parser can reject initials and still return a valid match
                    if not re.match(r"^[A-Z]([\. ]+[A-Z])*[\. ]*$", val):
                        # mask = 'Name discarded: "{}" from {} (initials)'
                        # logger.info(mask.format(val, self.verbatim))
                        mask = "Could not parse: {} (invalid feature)"
                        raise ValueError(mask.format(vals))
        if not features:
            mask = "Could not parse: {} (invalid features)"
            raise ValueError(mask.format(vals))
        if not self.specific:
            self.specific = any([f.specific for f in features])
        return features

    def split_features(self, val):
        """Splits multiple but not delimited feature names

        Example: "Plummers Island Plummer's Island"
        """
        words = re.split(r"\W+", val)
        counts = {}
        for word in words:
            try:
                counts[word.lower()] += 1
            except KeyError:
                counts[word.lower()] = 1
        kinds = set(counts) & FEATURES
        count = sum([counts[k] for k in kinds])
        names = []
        if 0.4 <= count / len(words) <= 0.6:
            pattern = r"\b({})\b".format("|".join(kinds))
            words = re.split(pattern, val, flags=re.I)
            name = []
            for word in words:
                if word:
                    name.append(word)
                    if word.lower() in FEATURES and len(name) > 1:
                        names.append("".join(name).strip())
                        name = []
            if name:
                names.append("".join(name).strip())
        return self.parse_features(names)

    def split_conjunction(self, val):
        """Splits feature name at a non-and conjunction"""

        # Disregard borders and junctions
        for parser in (BorderParser, JunctionParser):
            try:
                parser().parse(val)
            except ValueError:
                pass
            else:
                mask = 'Conjunction probably part of border/junction: "{}"'
                raise ValueError(mask.format(val))

        # If only one name found, try splitting on "of" instead of an
        # and-like delimiter. This is a rare case and only applies to
        # pairs of features delimited by "of" where each feature can
        # stand alone.
        names = re.split(r"\b(?:and|or|y|&|\+)\b", val, flags=re.I)
        if len(names) == 1:
            names = [s.strip() for s in re.split(r"\bof\b", val, flags=re.I)]
            if (
                len(names) != 2
                or not all(names)
                or " " not in names[-1]
                or names[0].lower().endswith(tuple(OF_WORDS))
            ):
                mask = '"of" probably part of name: "{}"'
                raise ValueError(mask.format(val))

        # Do not consider leading or trailing conjunctions
        names = [s.strip() for s in names]
        if not all(names):
            raise ValueError('Leading or trailing conjunction: "{}"'.format(val))

        return self.parse_features(append_feature_type(names))

    def split_parentheticals(self, val):
        """Splits feature name with parentheticals"""
        names = []
        parens = re.findall(r"(\(.*?\)|\[.*?\])", val, flags=re.I)
        if len(parens) == 1:
            before, after = [s.strip() for s in val.split(parens[0])]
            name = parens[0].strip("()[]= ")
            if before and after:
                mask = "{{}} {}".format(after)
                if "=" in parens[0]:
                    # Keep both names if explicitly synonymous
                    names = [mask.format(n) for n in (before, name)]
                else:
                    # Drop the parenthetical is not explicitly a synonym
                    names = [mask.format(before)]
            elif before:
                names = [before, name]

        # Parentheticals are understood as pairs of equivalent terms, so
        # return them as a list of lists, not as individual terms
        return [[f] for f in self.parse_features(names)]

    def expand(self, site, *args, **kwargs):
        """Expands generic features found in lists"""
        for feature in self.features:
            if isinstance(feature, list):
                for feature in feature:
                    feature.expand(site, *args, **kwargs)
            else:
                feature.expand(site, *args, **kwargs)
        return self
