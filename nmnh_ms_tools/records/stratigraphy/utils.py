"""Defines constants and utility functions used in the stratigraphy submodule"""

import itertools
import re

from titlecase import titlecase

from .range import StratRange
from ...utils import as_list, std_case, to_attribute


CHRONOSTRAT_RANKS = ["eonothem", "erathem", "system", "series", "stage", "substage"]

LITHOSTRAT_RANKS = ["group", "formation", "member", "bed"]

LITHOSTRAT_ABBRS = {
    "gp": "group",
    "fm": "formation",
    "mbr": "member",
    #'bd': 'bed'
}

LITHOLOGIES = {
    "cgl": "conglomerate",
    "dol": "dolomite",
    "ls": "limestone",
    "sh": "shale",
    "sl": "slate",
    "ss": "sandstone",
    "volc": "volcanic",
}

for lithology in [
    "anhydrite",
    "basalt",
    "calcareous",
    "carbonate",
    "chalk",
    "clay",
    "claystone",
    "dolomite",
    "gneiss",
    "granite",
    "iron formation",
    "marl",
    "mudstone",
    "oolite",
    "sand",
    "siltstone",
]:
    LITHOLOGIES[lithology] = lithology


MODIFIERS = ["base", "lower", "middle", "mid", "upper", "top", "early", "late"]


def parse_strat_package(val, class_):

    strat = class_()
    parsed = strat.parse_to_dict(val)

    interpreted = []
    for rank in strat.ranks:
        for unit in parsed.get(rank, []):

            names = split_strat(unit.unit, class_)

            # Synonyms may resolve to a range of units that do not match
            # the rank being evaluated.
            units = []
            for name in names:
                unit = class_().parse_to_dict(name)
                for i in range(len(list(unit.values())[0])):
                    units.append(class_({k: v[i] for k, v in unit.items()}))

            # Verify that all units have overlapping ages
            if len(units) > 1:

                # Sort most specific unit to front of list
                units.sort(key=lambda u: u.max_ma - u.min_ma)

                # Test that all units overlap
                # FIXME: Large ranges may fail here
                for i, unit in enumerate(units[1:]):
                    last = units[i]
                    if unit.most_specific()[0] != last.most_specific()[
                        0
                    ] and unit.disjoint(last):
                        raise ValueError("Unit ages do not intersect")

            interpreted.extend(units)

    # Only keep the first and last units that match the lowest rank found
    interpreted.sort(key=lambda u: u.max_ma - u.min_ma)
    rank = units[0].most_specific()[0]
    interpreted = [u for u in interpreted if getattr(u, rank)]

    # Order units from youngest to oldest
    interpreted.sort(key=lambda u: u.min_ma)

    return StratRange(interpreted)


def split_strat(val, class_=None):
    """Splits given value into individual units"""
    val = val.strip(" .")
    val = re.sub(" of ", " of ", val.strip(" ."), flags=re.I)

    # Treat "of"-delimited lists as hierarchies
    try:
        child, parent = val.rsplit(" of ")
    except ValueError:
        pass
    else:
        return split_strat(child)

    # Standardize Lower/Early to simplify splitting
    val = std_modifiers(val)

    # Test if given string is valid for current class
    if class_ is not None and class_._keywords is None:
        class_().keywords
    if class_ is not None and to_attribute(val) in class_._keywords:
        return [val]

    # Extract parentheticals
    parens = re.findall(r"(\(.*?\))", val)
    parens = [s for s in parens if s.lower().strip("()") not in MODIFIERS]
    for paren in parens:
        val = val.replace(paren, "")
    val = re.sub(r" +", " ", val)
    parens = [s.strip("()") for s in parens]

    # Split ranges. Because hyphens can also be used as parent-child
    # delimiters, only two-unit ranges will be parsed correctly.
    vals = re.split(r"(?:[ -]+to[ -]+| *- *)", val, flags=re.I)
    if len(vals) == 2:
        # Each part of the range also needs to be checked
        units = []
        for val in vals:
            units.extend(split_strat(val))

    # If not a range, try to split using delimiters
    if len(vals) != 2:
        delims = [";", "/", ",? and ", ",? & ", ",? or ", "-", "_", ":", r"\+"]
        pattern = r"(, ({0}))(/({0}))?".format("|".join(MODIFIERS))
        if not re.search(pattern, val, flags=re.I):
            delims.append(",")
        pattern = r"(?:{})".format("|".join(delims))
        vals = re.split(pattern, val, flags=re.I)

    # If not delimited, try to split using keywords
    if len(vals) == 1 and class_ is not None:

        # Split value into all possible phrases while maintaining order
        phrase = as_list(vals[0])
        if len(phrase) != 1:
            phrases = [phrase]
        else:
            words = to_attribute(vals[0]).split("_")
            phrases = []
            for r in range(1, len(words) + 1):
                phrases.append(itertools.combinations(words, r))
            phrases = [["_".join(p) for p in p] for p in phrases]
            phrases.sort(key=len)

        # Validate each group against the keyword list. If all words  are found,
        # the names are considered valid, but if there are multiple words, they
        # need to be incorporated into the correct fields in the record.
        for group in phrases:
            if not set(group) - class_().keywords:
                return group
        else:
            raise ValueError(f"Unrecognized unit: {vals[0]}")

    vals = parens + [val.strip() for val in vals if val]

    # Assoicate orphaned modifiers (upper, lower, etc.) with previous unit
    for i, val in enumerate(vals[1:]):
        if val.lower() in MODIFIERS:
            vals[i + 1] = f"{val} {vals[i]}"

    return vals


def split_strat_dict(dct):
    """Splits a dict into units"""
    units = None
    for key, vals in dct.items():
        if units is None:
            units = [{} for _ in vals]
        for val, unit in zip(vals, units):
            unit[key] = [val]
    return units


def std(name):
    """Standardizes a stratigraphic name"""
    words = {"cr": "creek", "mt": "mount", "mtn": "mountain", "r": "river"}
    for find, repl in words.items():
        pattern = r"\b{}(\.|\b)".format(find.capitalize())
        name = re.sub(pattern, repl.capitalize(), name)
    return name


def long_name(name):
    """Returns the long form of the unit name"""
    name = std(name)
    for find, repl in LITHOSTRAT_ABBRS.items():
        pattern = r"\b({})(?=\b|\.)".format(find)
        name = re.sub(pattern, repl, name, flags=re.I)
    for find, repl in LITHOLOGIES.items():
        pattern = r"\b({})\b".format(find)
        name = re.sub(pattern, repl, name, flags=re.I)
    return titlecase(name)


def short_name(name):
    """Returns the short form of the unit name"""
    name = std(name)
    for repl, find in LITHOSTRAT_ABBRS.items():
        name = re.sub(r"\b({})\b".format(find), repl, name, flags=re.I)
    for repl, find in LITHOLOGIES.items():
        name = re.sub(r"\b({})\b".format(find), repl, name, flags=re.I)
    # Fix combinations (e.g., Emily Iron Formation Member)
    pattern = r"({0}) ({0})".format("|".join(LITHOSTRAT_ABBRS.keys()))
    match = re.search(pattern, name)
    if match is not None:
        name = name.replace(match.group(1), LITHOSTRAT_ABBRS[match.group(1)])
    return titlecase(name)


def std_modifiers(unit, use_age_modifiers=False):
    """Standardizes unit names to upper/lower instead of late/early"""
    if unit:
        modifiers = {
            "early": "lower",
            "early/lower": "lower",
            "lower/early": "lower",
            "late": "upper",
            "late/upper": "upper",
            "upper/late": "upper",
            "mid": "middle",
        }
        if use_age_modifiers:
            for key, val in modifiers.items():
                modifiers[key] = "early" if val == "lower" else "late"
        std = unit
        for key in sorted(modifiers, key=len, reverse=True):
            val = modifiers[key]
            pattern = r"\b{}\b".format(key)
            match = re.search(pattern, std, flags=re.I)
            if match is not None:
                repl = std_case(val, match.group(0))
                std = re.sub(pattern, repl, std, flags=re.I)
        return std
    return unit


def base_name(unit):
    """Returns the unmodified name from a stratigraphic unit"""
    pattern = r"\b({})\b".format("|".join(MODIFIERS))
    return re.sub(pattern, "", unit, flags=re.I).replace("()", "").strip(" -")
