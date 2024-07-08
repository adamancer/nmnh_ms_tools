"""Defines class to parse simple feature names"""

import logging
import re

from titlecase import titlecase

from .core import Parser
from ....utils import plural, singular


logger = logging.getLogger(__name__)


LAND_FEATURES = {
    "atoll": True,
    "bar": True,
    "borough": True,
    "butte": True,
    "caldera": True,
    "camp": True,
    "canal": True,
    "cape": True,
    "city": True,
    "cliff": True,
    "county": True,
    "crater": True,
    "creek": True,
    "department": True,
    "district": True,
    "escarpment": True,
    "forest": True,
    "harbor": True,
    "hill": True,
    "island": True,
    "islands": False,
    "islet": True,
    "lake": True,
    "maar": True,
    "meadow": True,
    "mesa": True,
    "mine": True,
    "mount": True,
    "mountain": True,
    "mountains": True,
    "mouth": True,
    "municipality": True,
    "pass": True,
    "peninsula": True,
    "plateau": True,
    "province": True,
    "preserve": True,
    "point": True,
    "reserve": True,
    "ridge": True,
    "river": True,
    "rock": True,
    "spring": True,
    "state": True,
    "stream": True,
    "sub-province": True,
    "town": True,
    "tributary": True,
    "valley": True,
    "village": True,
    "volcano": True,
    "well": True,
}
MARINE_FEATURES = {
    "archipelago": False,
    "bay": True,
    "beach": True,
    "channel": True,
    "lagoon": True,
    "gulf": False,
    "ocean": False,
    "passage": True,
    "playa": True,
    "reef": True,
    "sea": False,
    "shore": True,
    "sound": True,
    "strait": False,
    "ocean": False,
}
OTHER_FEATURES = {
    "core": False,
    "bridge": True,
    "dredge": False,
    "map": True,
    "quad": True,
    "quadrangle": True,
    "road": True,
    "route": True,
    "station": True,
    "trail": True,
}
FEATURES = set(
    list(LAND_FEATURES) + list(MARINE_FEATURES) + list(OTHER_FEATURES) + ["feature"]
)
OF_WORDS = [
    "area",
    "bank",
    "base",
    "bottom",
    "center",
    "central",
    "channel",
    "coast",
    "corner",
    "crest",
    "edge",
    "end",
    "entrance",
    "escarpment",
    "exit",
    "face",
    "head",
    "inner",
    "inside",
    "junction",
    "lower",
    "middle",
    "near",
    #'off',
    #'offshore',
    "outer",
    "part",
    "pinnacle",
    "point",
    "portion",
    "quadrant",
    "ridge",
    "rim",
    "section",
    "side",
    "shore",
    "slope",
    "spur",
    "summit",
    "surroundings",
    "top",
    "tributary",
    "upper",
    "vicinity",
    "wall",
]


class FeatureParser(Parser):
    """Parses simple feature names"""

    kind = "feature"
    bad = [
        r"approach(es)?",
        r"entrances?",
        r"and",
        # r'along',
        r"at",
        r"by",
        r"in",
        r"from",
        r"of",
        r"or",
        r"the",
        r"to",
    ]

    def __init__(self, *args, **kwargs):
        self._variants = []
        super(FeatureParser, self).__init__(*args, **kwargs)

    def variants(self):
        """Returns a list of plausible variants on a feature name"""
        return self._variants

    def parse(self, val, allow_generic=False):
        """Parses string if it looks anything like a feature name"""
        punc = "|:;,.()[] "
        self.verbatim = val

        # Normalize capitalizations of conjunctions
        def repl(match):
            return match.group().lower()

        val = re.sub(r"\b(and|or|to)\b", repl, val, flags=re.I)

        # Do not parse names that contain punctuation
        for char in punc.strip():
            if char in val:
                mask = 'Could not parse "{}" (illegal characters)'
                raise ValueError(mask.format(val))

        # Look for generic features
        if allow_generic and val.lower() in FEATURES:
            self.feature = self.build_mask(val)
            self.domain = None
            self.feature_kind = None
            self.specific = False
            return self

        if is_generic_feature(val):
            mask = 'Could not parse "{}" (generic name)'
            raise ValueError(mask.format(val))

        if val.islower():
            mask = 'Could not parse "{}" (all lower)'
            raise ValueError(mask.format(val))

        if val.isnumeric():
            mask = 'Could not parse "{}" (numeric)'
            raise ValueError(mask.format(val))

        # Reject borders and junctions
        if val.lower().startswith(("border of", "junction of")):
            mask = 'Could not parse "{}" (border/junction)'
            raise ValueError(mask.format(val))

        # Reject features that start with certain adjectives or prepositions
        if val.startswith(("which", "with")):
            mask = 'Could not parse "{}" (bad first word)'
            raise ValueError(mask.format(val))

        # Ensure that phrases look feature-like
        pattern = get_feature_pattern(True, True)
        if not re.search(pattern, val):
            raise ValueError('Could not parse "{}" (invalid name)'.format(val))

        # Ensure that phrase does not start with of/de/etc.
        if re.search(r"^[a-z]{1,3}(?= [A-Z])", val):
            raise ValueError('Could not parse "{}" (invalid first)'.format(val))

        # Ensure that phrase does not end with of/de/etc.
        if re.search(r"\b[a-z]{1,3}$", val):
            raise ValueError('Could not parse "{}" (invalid last)'.format(val))

        # Verify numbers if present
        pattern = r"(No\.? |Num(ber|\.)? |# ?)[0-9]+$"
        if val and val[-1].isdigit() and not re.search(pattern, val):
            raise ValueError('Could not parse "{}" (invalid num)'.format(val))

        # Look for phrases that are unlikely to be specific feature names
        pattern = r"(^({0})( {0})?\b|\b({0})$)".format("|".join(self.bad))
        if re.search(pattern, val, flags=re.I):
            raise ValueError('Could not parse "{}" (unlikely name)'.format(val))

        # Exclude features that start/end with a preposition
        pattern = r"(^{0}\b|\b{0}$)".format(r"(a|aux?|d[aeo]s?|del|of)")
        if re.search(pattern, val, flags=re.I):
            raise ValueError('Could not parse "{}" (starts/ends with prep)'.format(val))

        # Assign attributes
        cleaned = self.clean(val)
        if not cleaned:
            raise ValueError('Could not parse "{}" (clean failed)'.format(val))
        self.feature = titlecase(cleaned)

        # Attempt to classify the feature
        self.domain, self.feature_kind, self.specific = self.classify()

        # Consider also multiple features within a single name. This function
        # originally only considered conjunctions like "and" that may appear
        # in a place name, but now looks at several common conjunctions as
        # well. This adds some uncomfortable overlap with functionality found
        # in the MultiFeatureParser.
        # pattern = r'\b(?:and|y|&|\+)\b'
        pattern = r"\b(?:and|or|to|y|&|\+)\b"
        variants = []
        names = [s.strip() for s in re.split(pattern, val, flags=re.I)]
        if len(names) > 1:
            for name in names:
                try:
                    self.__class__(name)
                    variants.append(name)
                except ValueError:
                    variants = []
                    break

        self._variants = [self.feature]
        if variants:
            self._variants.append(append_feature_type(variants))

        return self

    def classify(self):
        """Classifies feature based on feature name"""
        terms = {
            "land": LAND_FEATURES,
            "marine": MARINE_FEATURES,
            None: OTHER_FEATURES,
        }
        for key, terms in terms.items():
            try:
                kind = self._classify(terms)
                if kind:
                    return key, kind, terms[kind]
            except KeyError:
                pass
        # logger.debug('Could not classify {}'.format(self.feature))
        return None, None, None

    def clean(self, val):
        """Removes terms that don't significantly affect meaning"""
        val = re.sub(r"^the ", "", val, flags=re.I)
        val = re.sub(r"\bit'?s\b", "", val, flags=re.I)  # forbid val = its
        return val

    def name(self):
        """Returns a string describing the most likely locality"""
        return self.feature

    def build_mask(self, val):
        """Builds a formatting mask with the name of the most likely field"""
        features = {
            "city": "municipality",
            "islands": "island_group",
            "province": "state_province",
            "state": "state_province",
            "town": "municipality",
            "village": "municipality",
        }
        val = val.lower()
        return "{" + features.get(val, val) + "}"

    def _classify(self, terms):
        """Classifies a feature based on a list of terms"""
        piped = "|".join([f + "(?:es|s)?" for f in terms])
        # If the parsed feature exactly matches one of the terms, raise error
        pattern = r"^({})$".format(piped)
        if re.search(pattern, self.feature, flags=re.I):
            mask = "Could not parse: {} (generic feature)"
            raise ValueError(mask.format(self.feature))
        # Check if feature is of the class defined by the keywords
        pattern = r"\b({})$".format(piped)
        match = re.search(pattern, self.feature, flags=re.I)
        if not match:
            pattern = r"^({})\b".format(piped)
            match = re.search(pattern, self.feature, flags=re.I)
        if match is not None:
            key = match.group().lower()
            while key not in terms:
                key = key[:-1]
                if not key:
                    mask = "Could not parse: {} (invalid feature)"
                    raise ValueError(mask.format(match.group().lower()))
            return key


def is_generic_feature(val):
    """Tests if feature name appears to be generic (e.g., East Coast)"""
    dirs = ["North", "South", "East", "West"]
    dirs = ["{}({})?".format(d[0], d[1:]) for d in dirs]
    dirs = "({})".format("|".join(dirs))
    features = r"({})".format("|".join(OF_WORDS))
    pattern = r"^({0}({0}){{0,2}}(ern)? )?{1}$".format(dirs, features)
    return bool(re.match(pattern, val, flags=re.I))


def get_feature_pattern(match_start=False, match_end=False):
    """Constructs feature pattern to use for regex match"""
    p0 = r"(?:U[\. ]*[KS][\. ]*(?:[A-Z]\.? )*|[Tt]he )"
    p1 = (
        r"(?:[MS]t\.? )?(O\'|Ma?c)?[A-Z][a-z\-]+(?:\'s|\.)?"
        r"(?:[ \-](O\'|Ma?c)?[A-Z][a-z\-]{1,}(?:\'s)?){1,4}"
    )
    # p2 = r'(?:[A-z][-a-z]+ (?:d[eo](?: la)?|el|of)(?: [A-Z][-a-z]+){1,3})'
    p2 = r"(?:[A-z][-a-z]+(?: (?:[A-Z][-a-z]+|a|aux?|d[aeo]s?|d?el|l[aeo]|l[aeo]s|of(?: the)?)){1,5})"
    p3 = r"[A-z][-a-z]{2,}"  # Maine
    p4 = r"(?:# ?)?[0-9]+"  # Test Well No. 1
    feature = r"(?:{})?(?:{}|{}|{})(?: {})?".format(p0, p1, p2, p3, p4)
    pattern = r"^" if match_start else r""
    # Match features jointed by "and" and equivalents
    pattern += r"(?:{0}(?: (?:[Aa]nd|&|[Yy]) {0})?)".format(feature)
    if match_end:
        pattern += "$"
    return pattern


def append_feature_type(features):
    """Appends feature type across a list"""
    if isinstance(features, str):
        features = re.split(r"\b(?:and|or|y|&|\+)\b", features, flags=re.I)
    if len(features) == 1:
        return features

    features = [s.strip() for s in features]
    singular_type = singular(features[-1].split(" ")[-1]).lower()
    if singular_type in FEATURES:

        # Does any feature but the last end with a recognized feature type?
        feat_types = tuple(list(FEATURES) + [plural(f) for f in FEATURES])
        for feature in features[:-1]:
            feature = feature.lower()
            if feature not in feat_types and feature.endswith(feat_types):
                return features

        # Append the feature from the last feature to all values in the list
        plural_type = plural(singular_type)
        for i, feature in enumerate(features):
            if feature.lower().endswith(plural_type):
                features[i] = features[i].rsplit(" ", 1)[0]
            if not feature.lower().endswith(singular_type):
                features[i] = (features[i] + " " + singular_type).title()

    return features


def get_feature_string(parsed):
    """Gets the verbatim or parsed feature depending on parser"""
    feature = str(parsed).lower()
    if "{" in feature or feature.startswith(("border of", "junction of")):
        return str(parsed).strip('"')
    return strip_of_modifiers(parsed.verbatim)


def strip_of_modifiers(feature):
    """Strips generic terms (like 'coast of') from feature name"""
    pattern = r"^({}) of\b".format("|".join(OF_WORDS))
    return re.sub(pattern, "", feature, flags=re.I).strip()


# Add FeatureParser to the main parser class to allow feature name expansions
Parser.feature_parser = FeatureParser
