"""Identifies feature names modified by compass directions"""

import logging
import re

from .core import Parser
from .feature import FeatureParser, is_generic_feature, get_feature_pattern, OF_WORDS
from ....utils import (
    LazyAttr,
    LocStandardizer,
    compass_dir,
    dedupe,
    std_case,
    validate_direction,
    ucfirst,
)


logger = logging.getLogger(__name__)


TO_WORDS = ["approach", "approaches" "entrance", "entrances"]


class ModifiedParser(Parser):
    """Parses feature names modified by compass directions"""

    # Deferred class attributes are defined at the end of the file
    std = None

    # Normal class attributes
    kind = "modified"
    attributes = ["kind", "verbatim", "unconsumed", "feature", "modifier", "modified"]

    def __init__(self, *args, **kwargs):
        self.modifier = None  # directional modifier on feature name
        self.long = False  # verbatim uses full direction
        self.adj = False  # verbatum uses adjective form of direction
        self.delimited = False  # verbatim uses comma-delimited direction
        self.intrinsic = False  # direction appears to be part of feature name
        self.feature = None
        super().__init__(*args, **kwargs)

    @property
    def modified(self):
        return self.name()

    @property
    def modifier(self):
        return self._modifier

    @modifier.setter
    def modifier(self, mod):
        try:
            valid = {"center", "inner", "lower", "near", "outer", "upper", None}
            assert mod in valid or validate_direction(mod)
        except (AssertionError, ValueError):
            raise ValueError(f"Invalid modifier: {mod}")
        self._modifier = mod

    def name(self):
        """Returns a string describing the most likely locality"""
        if self.modifier is None:
            return self.feature
        mask = "{modifier} {feature}"
        if self.adj and self.intrinsic:
            mod = ucfirst(expand_direction(self.modifier, True))
        elif self.long and self.intrinsic:
            mod = ucfirst(expand_direction(self.modifier, False))
        else:
            mod = self.modifier
            if self.modifier in {"center", "near"}:
                mask = "{feature} ({modifier})"
        return mask.format(feature=self.feature, modifier=mod)

    def variants(self):
        """Gets variants on the underlying feature name"""
        if self.modifier is None:
            return [self.feature]
        variants = []
        if "{" not in self.feature:
            long_dir = expand_direction(self.modifier, False)  # North
            adj_dir = expand_direction(self.modifier, True)  # Northern
            # Order the modified names based on the form of the modifier in
            # the original string
            mods = ["", long_dir, adj_dir]
            if self.adj:
                mods = [adj_dir, long_dir, ""]
            elif self.long:
                mods = [long_dir, "", adj_dir]
            mods = [ucfirst(mod) for mod in dedupe(mods)]
            variants = [(f"{m} {self.feature}").strip() for m in mods]
        # Prioritize verbatim if it occurs in list, otherwise append it
        try:
            variants.insert(0, variants.pop(variants.index(self.verbatim)))
        except ValueError:
            # Include verbatim if it is a plausible feature name on its own
            if self.verbatim == self.verbatim.title():
                variants.append(self.verbatim)
        return variants

    def parse(self, val):
        """Extracts a modified feature name from a locality string"""
        val = val.strip()
        self.verbatim = val

        try:
            validate_direction(val)
            val += " Feature"
        except ValueError:
            pass

        # Try replacing hyphens with commas to catch cases where direction
        # is delimited by a hyphen (ex. "Maine - Northern")
        if not is_modified_feature(val, False) and val.count("-") == 1:
            val = re.sub(r"\s*-\s*", ", ", val)

        # Test if modified feature
        if not is_modified_feature(val, False):
            raise ValueError(
                f"Could not parse {repr(val.strip('"'))} (not a modified feature)"
            )

        # Interpret generic features as modifying terms elsewhere in record
        if is_generic_feature(val):
            val += " of Unspecified Feature"
            # Force long adjective form of the direction
            self.long = True
            self.adj = True
            self.intrinsic = True
        else:
            self.delimited = is_delimited(val)
            self.long = is_long(val)
            self.adj = is_adjective(val)
            self.intrinsic = is_intrinsic(val)

        self._parse(self.std.std_directions(val))
        return self

    def _parse(self, val):
        for func in (self._extract_direction, self._extract_vicinity):
            try:
                parsed = func(val)
                find = "Unspecified Feature"
                repl = "{feature}"
                parsed.feature = parsed.feature.replace(find, repl)
                return parsed
            except ValueError:
                pass
        raise ValueError(f"Modifier not found: {repr(val)}")

    def _extract_direction(self, val):
        """Extracts cardinal direction from string"""
        dir_string = self._extract_directional_string(val)
        if dir_string is not None:
            cdr = dir_string.lower().split(" ")[0]
            for repl in ["orth", "outh", "ast", "est", "ern", "most"]:
                cdr = cdr.replace(repl, "")
            self.modifier = "".join([c for c in cdr if c.isalpha()]).upper()
            self.feature = self._extract_feature(val, dir_string)
            return self
        raise ValueError(f"Direction not found: {repr(val)}")

    def _extract_directional_string(self, val):
        """Extracts a string containing a compass direction"""
        dirs = ["North", "South", "East", "West"]
        dirs = [f"{d[0]}({d[1:]})?" for d in dirs]
        dirs = f"({"|".join(dirs)})"
        p1 = r"\b{0}(-?{0}){{,2}}(ern(most)?)?".format(dirs)
        p2_1 = rf"( ({"|".join(OF_WORDS)})( of)?)"
        p2_2 = rf"( ({"|".join(OF_WORDS)})( to)?)"
        p2 = rf"({p2_1}|{p2_2})?\b"
        pattern = re.compile(p1 + p2, flags=re.I)
        try:
            return pattern.search(val).group()
        except AttributeError:
            raise ValueError(f"Direction not found: {val}")

    def _extract_vicinity(self, val):
        """Extracts vicinity info"""
        vicinity = self._extract_vicinity_string(val)
        pattern = r"\b(and|of)\b"
        modifier = re.sub(pattern, "", vicinity, flags=re.I).strip().lower()
        self.feature = self._extract_feature(val, vicinity)

        # Assign non-directional modifiers
        self.modifier = None
        if modifier in {"center", "central", "middle"}:
            self.modifier = "center"
        elif modifier in {"inner", "lower", "outer", "upper"}:
            self.modifier = modifier
        elif modifier in {"area", "near", "surroundings", "vicinity"}:
            self.modifier = "near"

        return self

    def _extract_vicinity_string(self, val):
        """Extracts a string containing vicinity info"""
        terms = r"(({0})( ({0}))*)".format("|".join(OF_WORDS))
        pattern = (
            r"(^{0}( of)?\b|\({0}\);" r"|\b(and )?(area|surroundings|vicinity))"
        ).format(terms)
        try:
            return re.search(pattern, val, flags=re.I).group()
        except AttributeError:
            raise ValueError(f"Vicinity not found: {repr(val)}")

    def _extract_feature(self, val, mod_string):
        """Extracts feature name from string"""

        # Split full value on the modify string. Toss the results if multiple
        # values found (i.e., if the mod string is in the middle of the word
        # instead of the end.
        pattern = rf"\b{mod_string}\b"
        vals = [s for s in re.split(pattern, val) if s.strip(",;() ")]
        if len(vals) > 1:
            raise ValueError("Modifier in middle of string")
        if not vals:
            raise ValueError("String is empty")

        # Get specificity info from feature
        feature = re.sub(r" +", " ", vals[0].strip(",;() "))
        parsed = FeatureParser(feature, allow_generic=True)
        self.domain = parsed.domain
        self.feature_kind = parsed.feature_kind
        self.specific = parsed.specific

        return parsed.feature if "{" in parsed.feature else feature


def is_modified_feature(val, test_intrinsic=True):
    """Tests if string appears to be a modified feature name"""
    # Is the directional information likely to be an intrinsic part of the
    # feature name (e.g., North Carolina)? This is a holdover from an
    # earlier implementation of the ModifiedParser where names like North
    # Carolina (where the modifier is actually a part of the name) were not
    # prioritized during the georeference. The test_intrinsic parameter
    # should probably always be False.
    if test_intrinsic and is_intrinsic(val):
        logger.debug(f"Intrinsic modifier: {repr(val.strip('"'))}")
        return False

    # Is the feature name ONLY directional terms (e.g., North West)?
    # NOTE: Hashed because these names are not captured by FeatureParser
    # pattern = r'^(north|south|east|west)([ -](north|south|east|west))*$'
    # if re.match(pattern, val, flags=re.I):
    #    logger.debug(f'All directions: {repr(val.strip('"'))}')
    #    return False

    # Does the feature name match the general format expected for a modified
    # feature name?
    if isinstance(val, list):
        val = "; ".join(val)
    val = val.strip(",;.:")
    patterns = get_modified_patterns(True, True)
    for pattern in patterns:
        if (
            re.search(pattern, val, flags=re.I)
            and max([len(s) for s in val.split(" ")]) > 2
        ):
            return True

    # logger.debug(f'No modifier: {repr(val.strip('"'))}')
    return False


def is_intrinsic(val):
    """Tests if direction string appears to be an intrinic part of a name"""
    dirs = ["North", "South", "East", "West"]
    dirs = [f"{d[0]}({d[1:]})?" for d in dirs]
    dirs = f"({"|".join(dirs)})"
    has_direction = re.search(rf"\b{dirs}\b", val, flags=re.I)
    if not has_direction:
        return False
    vicinity = rf"({"|".join(OF_WORDS)})"
    mask = r"(^[NESW]{{1,3}}|{0}{{1,2}}ern(most)?|\bof|\bfrom|, {0}{{1,3}}|\b{1})\b"
    return not re.search(mask.format(dirs, vicinity), val, flags=re.I)


def expand_direction(val, adj=False):
    """Expand shortened cardinal directions"""
    dirs = {
        "N": "north",
        "S": "south",
        "E": "east",
        "W": "west",
    }
    expanded = val
    for find, repl in dirs.items():
        expanded = expanded.replace(find, repl)
    if adj:
        pattern = r"\b((?:north|south|east|west){1,2})\b"
        expanded = re.sub(pattern, r"\1ern", expanded, flags=re.I)
    expanded = re.sub("center", "central", expanded, flags=re.I)
    return std_case(expanded, val) if not val.isupper() else expanded


def shorten_direction(val):
    return compass_dir(val.sub("ern", ""))


def is_adjective(val):
    """Tests if string contains the adjective form of a direction"""
    pattern = (
        rf"\b((north|south|east|west)ern(most)?|central)\b"
        rf"(?! ({" | ".join(OF_WORDS)})( of\b|$))"
    )
    has_adjective = bool(re.search(pattern, val, flags=re.I))
    return has_adjective


def is_long(val):
    """Tests if string contains the long form of a direction"""
    pattern = (
        rf"\b((north|south|east|west){{1,2}}(ern(most)?)?|central)\b"
        rf"(?! ({"|".join(OF_WORDS)})( of\b|$))"
    )
    has_long = bool(re.search(pattern, val, flags=re.I))
    return has_long


def is_delimited(val):
    """Tests if string contains a comma-delimited direction

    Example: "Atlantic Ocean, North"
    """
    pattern = r", (north|south|east|west)(ern(most)?)?$"
    return "," not in val or bool(re.search(pattern, val, flags=re.I))


def has_direction(val, direction):
    """Tests if string contains the given direction"""
    # NOTE: This is missing a closing word break
    return bool(re.search(rf"\b{expand_direction(direction)}", val, flags=re.I))


def get_modified_patterns(match_start=False, match_end=False, masks=None):
    """Constructs feature pattern to use for matching modified"""
    if masks is None:
        masks = [
            r"{dirs} {feature}",
            r"{dirs}{mod}? {feature}",
            r"{feature}, {dirs}{mod}?",
            r"{feature} \({dirs}{mod}?\)",
            r"{vicinity} {feature}",
            r"{feature} \({vicinity}\)",
            r"{feature} (and )?(area|surroundings|vicinity)",
        ]
    dirs = ["North", "South", "East", "West"]
    dirs = [f"{d[0]}(?:{d[1:]})?" for d in dirs]
    dirs = rf"(?:{"|".join(dirs)})"
    dirs = r"(?:{0}(?:[- \.]*{0})?(?:ern(?:most)?)?)".format(dirs)
    vicinity = rf"(?:{"|".join(OF_WORDS)})"
    parts = {
        "dirs": dirs,
        "feature": get_feature_pattern(),  # r'(\w+\.? ?){1,4}',
        "mod": rf" ?(?:(?:{"|".join(OF_WORDS)})(?: of)? ?)",
        "vicinity": vicinity,
    }
    patterns = [m.format(**parts) for m in masks]
    mask = r"{}{{}}{}".format(
        "^" if match_start else r"\b", "$" if match_start else r"\b"
    )
    return [mask.format(p) for p in patterns]


def get_any_feature_pattern():
    """Matches simple features or simple modified features"""
    return get_modified_patterns(masks=[r"((?:{dirs}{mod}? )?{feature})"])[0]


def abbreviate_direction(name):
    def abbreviate(match):
        short_dir = match.group().lower().replace("ern", "")
        for dirname in ["north", "south", "east", "west"]:
            short_dir = short_dir.replace(dirname, dirname[0].upper())
        return short_dir

    pattern = r"\b(north|south|east|west)+(ern)?\b"
    return re.sub(pattern, abbreviate, name, flags=re.I)


# Define deferred class attributes
LazyAttr(ModifiedParser, "std", LocStandardizer)
