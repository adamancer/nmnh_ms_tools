"""Defines constants and utility functions used in the stratigraphy submodule"""

import re
from functools import cache

from titlecase import titlecase

from .range import StratRange
from ...utils import seq_split, std_case


AGE_RANKS = ["eon", "era", "period", "epoch", "age", "subage"]

CHRONOSTRAT_RANKS = ["eonothem", "erathem", "system", "series", "stage", "substage"]

LITHOSTRAT_RANKS = [
    "supergroup",
    "group",
    "subgroup",
    "formation",
    "member",
    "bed",
    # Informal ranks
    "layer",
    "series",
    "unit",
]

LITHOSTRAT_ABBRS = {
    "supgp": "supergroup",
    "gp": "group",
    "subgp": "subgroup",
    "fm": "formation",
    "mbr": "member",
    "bd": "bed",
}

# List of lithodeme rock types. Intrusion types are defined below so that they
# aren't absorbed into the lithology list.
LITHODEMES = [
    "gabbro",
    "granodiorite",
    "granite",
    "kimberlite",
    "syenite",
]

LITHOLOGIES = {
    "cgl": "conglomerate",
    "dol": "dolomite",
    "ls": "limestone",
    "sh": "shale",
    "sl": "slate",
    "ss": "sandstone",
    "volc": "volcanic",
}

for lithology in (
    [
        "anhydrite",
        "argillite",
        "basalt",
        "calcareous",
        "carbonate",
        "chalk",
        "clay",
        "claystone",
        "dolomite",
        "gneiss",
        "iron formation",
        "marl",
        "mudstone",
        "oolite",
        "quartzite",
        "sand",
        "siltstone",
    ]
    + LITHODEMES
    + list(LITHOLOGIES.values())
):
    LITHOLOGIES[lithology] = lithology

LITHODEMES += [
    "dike",
    "intrusion",
    "pluton",
    "sill",
]

MODIFIERS = {
    # Position modifiers
    "base": "base",
    "bottom": "base",
    "lowest": "lower",
    "lower": "lower",
    "low": "lower",
    "middle": "middle",
    "mid": "middle",
    "center": "middle",
    "upper": "upper",
    "high": "upper",
    "higher": "upper",
    "highest": "upper",
    "top": "top",
    # Postion most-modifiers
    "bottommost": "base",
    "lowermost": "lower",
    "uppermost": "upper",
    "topmost": "top",
    # Age modifiers
    "early": "early",
    "late": "late",
}
# Sort by longest to shortest key to facilitate search-and-replace below
MODIFIERS = dict(sorted(MODIFIERS.items(), key=lambda kv: -len(kv[0])))


def extract_modifier(name: str) -> tuple[str]:
    """Extracts a spatial or temporal modifier from a unit name

    Parameters
    ----------
    name : str
        a unit name

    Returns
    -------
    tuple[str]
        tuple with the unit name (without modifier) and the modifier
    """
    modpat = f"(?:(?:very) )?(?:{"|".join(MODIFIERS)})"
    modpat = f"({modpat}(?:(?:-+| to ){modpat})?)(?: (?:half|third|quarter|fifth))?"
    pattern = rf"\(?({modpat})( part)?( (?:in|of))?( the)?\)?"
    match = re.search(pattern, name, flags=re.I)
    if match:
        mod = re.sub(r"^very\b", "", match.group(1).lower())
        for find, repl in MODIFIERS.items():
            mod = re.sub(rf"\b{find}\b", repl, mod)
        return re.sub(pattern, "", name, flags=re.I).strip(", "), mod.strip()
    return name, ""


def split_strat(val: str) -> list[str]:
    """Splits given value into individual units

    Parameters
    ----------
    val : str
        a string including one or more stratigraphic units

    Returns
    -------
    list[str]
        list of individual units
    """

    # Standardize value to simplify splitting
    val = std_unit_name(val.strip(" ."))

    # Treat "of"-delimited lists as hierarchies
    ranks = [s.lower() for s in LITHOSTRAT_RANKS + list(LITHOSTRAT_ABBRS)]
    pattern = rf"\b((?:{"|".join(ranks)})(?: +of)(?: the )?)"
    parts = re.split(pattern, val, flags=re.I)
    clean = []
    for i, part in enumerate(parts):
        if re.search(pattern, part, flags=re.I):
            clean[i - 1] += f" {part.split(" ")[0]}"
        else:
            clean.append(part)
    if clean != parts:
        return clean

    # Split on delimiters, then rejoin any stray modifiers
    parts = seq_split(val, hard_delims=r"[;:>\|]")
    clean = []
    for i, part in enumerate(parts):
        val, mod = extract_modifier(part)
        if not val and mod:
            clean[i - 1] += f" ({mod})"
        else:
            clean.append(part)

    return clean


@cache
def std_unit_name(name: str, as_age: bool = False) -> str:
    """Standardizes geographic features and modifiers in a unit name

    Parameters
    ----------
    name : str
        the unit name

    Returns
    -------
    str
        unit name with abbreviated features expanded
    """
    if not name:
        return name

    # Standardize geogrpahic features
    words = {"cr": "creek", "mt": "mount", "mtn": "mountain"}
    for find, repl in words.items():
        pattern = rf"\b{find.capitalize()}(\.|\b)"
        name = re.sub(pattern, repl.capitalize(), name)

    # Standardize chrono and litho modifiers
    modifiers = {
        "early": "lower",
        "early/lower": "lower",
        "lower/early": "lower",
        "late": "upper",
        "late/upper": "upper",
        "upper/late": "upper",
        "mid": "middle",
    }
    if as_age:
        for key, val in modifiers.items():
            modifiers[key] = "early" if val == "lower" else "late"
    for key in sorted(modifiers, key=len, reverse=True):
        val = modifiers[key]
        match = re.search(rf"\b{key}\b", name, flags=re.I)
        if match is not None:
            repl = std_case(val, match.group(0))
            name = re.sub(rf"\b{key}\b", repl, name, flags=re.I)

    return name


@cache
def long_name(name: str) -> str:
    """Returns the long form of the unit name

    Parameters
    ----------
    name : str
        the unit name

    Returns
    -------
    str
        the full unit name
    """
    name = std_unit_name(name)
    for find, repl in LITHOSTRAT_ABBRS.items():
        pattern = rf"\b({find})(?=\b|\.)"
        name = re.sub(pattern, repl, name, flags=re.I)
    for find, repl in LITHOLOGIES.items():
        pattern = rf"\b({find})\b"
        name = re.sub(pattern, repl, name, flags=re.I)
    return titlecase(name)


@cache
def short_name(name: str) -> str:
    """Returns the short form of the unit name

    Abbreviates ranks and known lithologies.

    Parameters
    ----------
    name : str
        the unit name

    Returns
    -------
    str
        the short unit name
    """
    name = std_unit_name(name)
    for repl, find in LITHOSTRAT_ABBRS.items():
        name = re.sub(rf"\b({find})\b", repl, name, flags=re.I)
    for repl, find in LITHOLOGIES.items():
        name = re.sub(rf"\b({find})\b", repl, name, flags=re.I)
    # Fix combinations (e.g., Emily Iron Formation Member)
    pattern = r"({0}) ({0})".format("|".join(LITHOSTRAT_ABBRS.keys()))
    match = re.search(pattern, name)
    if match is not None:
        name = name.replace(match.group(1), LITHOSTRAT_ABBRS[match.group(1)])
    return titlecase(name).replace("MBR", "Mbr").replace("gp", "Gp")


def split_strat_dict(dct):
    """Splits a dict into units

    NOTE: Consider deprecating
    """
    units = None
    for key, vals in dct.items():
        if units is None:
            units = [{} for _ in vals]
        for val, unit in zip(vals, units):
            unit[key] = [val]
    return units


def parse_strat_package(val, class_):
    """Parses a stratigraphic package

    NOTE: Consider deprecating
    """

    strat = class_()
    parsed = strat.parse_to_dict(val)

    interpreted = []
    for rank in strat.ranks:
        for unit in parsed.get(rank, []):

            print(split_strat(unit.unit_name))
            names = [class_(u) for u in split_strat(unit.unit_name)]

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
