"""Standardizes strings for comparison"""

import csv
import os
import re
from collections import OrderedDict

from .standardizer import Standardizer
from ..files import skip_hashed


class LocStandardizer(Standardizer):
    def __init__(self, *args, **kwargs):
        replace_words = read_abbreviations()
        stopwords = {
            "a",
            "au",
            "aux",
            "da",
            "de",
            "del",
            "des",
            "di",
            "do",
            "dos",
            "du",
            "el",
            "historical",
            "la",
            "le",
            "of",
            "the",
            "un",
            "una",
            "une",
        }
        move_to_beginning = {"bay", "cape", "gulf", "lake", "mount"}
        # Set default kwargs
        kwargs.setdefault("minlen", 1)
        kwargs.setdefault("replace_words", replace_words)
        kwargs.setdefault("stopwords", stopwords)
        kwargs.setdefault("move_to_beginning", move_to_beginning)
        kwargs.setdefault("strip_parentheticals", True)
        super().__init__(*args, **kwargs)
        # Create lookup for feature-specific standardization functions
        self.features = {
            "admin": self.std_admin,
            "bay": self.std_bay,
            "crater": self.std_crater,
            "harbor": self.std_harbor,
            "lake": self.std_lake,
            "island": self.std_island,
            #'island_group': self.std_island,
            "mine": self.std_mine,
            "mining_district": self.std_mining_district,
            "mountain": self.std_mountain,
            "municipality": self.std_municipality,
            "river": self.std_river,
        }

    def _std(self, val, *args, **kwargs):
        if isinstance(val, (list, tuple)):
            return [self.std(s, *args, **kwargs) for s in val]
        if not isinstance(val, str):
            return val
        val = self.std_directions(val)
        val = self.std_companies(val)
        val = self.denumber(val)
        return super()._std(val, *args, **kwargs)

    def sitify(self, val, patterns=None):
        """Converts a description approximating a site to that site's name"""
        if patterns is None:
            patterns = [
                r"\bnear( the)?\b",
                r"\barea$",
                r"^center of\b",
                r"^just [nsew] of\b",
                r"^middle of\b",
                r"^summit of\b",
                r"\bsummit$",
            ]
        for pattern in patterns:
            val = re.sub(pattern, "", val, flags=re.I).strip()
        return val

    def std_directions(self, val, lower=False):
        """Standardizes cardinal directions to drop periods and spaces"""
        return std_directions(val, lower=lower)

    def debreviate(self, val):
        """Expands common abbreviations"""
        val = re.sub(r"(?<=\b)is?\.?$", "island", val)
        val = re.sub(r"^mt\.?(?=\b)", "mount", val)
        val = re.sub(r"(?<=\b)mt\.?$", "mountain", val)
        val = re.sub(r"(?<=\b)r\.?r\.?$", "railroad", val)
        val = re.sub(r"(?<=\b)r\.?$", "river", val)
        val = re.sub(r"(?<=\b)st\.?$", "saint", val)
        return val

    def denumber(self, val):
        """Removes variants of 'number' if followed by numbers"""
        pattern = r"(#|\bn(o|um(ber)?)s?(\. *| *|\b))(?= *\d)"
        return re.sub(pattern, "", val, flags=re.I)

    def std_companies(self, val):
        """Standardizes words associated with corporations"""
        val = re.sub(r"\bincorporated\b", "inc", val, flags=re.I)
        val = re.sub(r"\blimited liability company\b", "llc", val, flags=re.I)
        val = re.sub(r"\blimited\b", "ltd", val, flags=re.I)
        val = re.sub(r"\bco(mpany|rp(oration)?)\b", "co", val, flags=re.I)
        return val

    def std_admin(self, val):
        """Standardizes an admin division aggressively"""
        terms = [
            "autonomous region",
            "borough",
            "county",
            "comisaria",
            "department",
            "district",
            "division",
            "federal",
            "municipality",
            "oblast",
            "palata",
            "parish",
            "prefecture",
            "province",
            "region",
            "republic",
            "township",
            "subdistrict",
            "zone",
            # Spanish
            "barrio",
            "departmento",
            "distrito",
            "estado",
            "hacienda",
            "municipio",
            "provincia",
            # Abbreviations
            "bor",
            "co",
            "com",
            "dep",
            "depart",
            "dept",
            "depto",
            "df",
            "dist",
            "distr",
            "div",
            "dpto",
            "dto",
            "dtto",
            "edo",
            "fed",
            "gob",
            "govt",
            "pr",
            "pref",
            "prov",
            "reg",
            "rep",
            "subdist",
            "terr",
            "territ",
            "twp",
        ]
        return self._std_feature(val, terms)

    def std_bay(self, val):
        """Standardizes an island name aggressively"""
        terms = [
            "baai",
            "bay",
            "sound",
            "tangung",
            # Abbreviations
            "sd",
            "tg",
        ]
        return self._std_feature(val, terms)

    def std_crater(self, val):
        """Standardizes a crater name aggressively"""
        terms = ["impact crater", "crater", "impact structure", "structure"]
        return self._std_feature(val, terms)

    def std_harbor(self, val):
        """Standardizes a harbor name aggressively"""
        terms = [
            "harbor",
            "harbour",
            # Abbreviations
            "hbr",
        ]
        return self._std_feature(val, terms)

    def std_island(self, val):
        """Aggressively standardizes an island name"""
        terms = [
            "atoll",
            "dao",
            "ile",
            "ilet",
            "isla",
            "island",
            "isle",
            "islet",
            "guyot",
            "ko",
            "pulau",
            "seamount",
            "tao",
            # Abbreviations
            "i",
            "id",
            "is",
            "isl",
            "isld",
        ]
        terms.extend(
            [
                "archipel",
                "archipelago",
                "atolls",
                "iles",
                "islands",
                "group",
                # Abbreviations
                "ids",
                "isls",
                "islds",
            ]
        )
        return self._std_feature(val, terms)

    # def std_island_group(self, val):
    #    """Aggressively standardizes an island group name"""
    #    terms = [
    #        'archipel',
    #        'archipelago',
    #        'atolls',
    #        'iles',
    #        'islands',
    #        'group',
    #    ]
    #    return self._std_feature(val, terms)

    def std_lake(self, val):
        """Aggressively standardizes a lake name"""
        terms = [
            "golu",
            "lac",
            "lake",
            "ozero",
        ]
        return self._std_feature(val, terms)

    def std_mine(self, val):
        """Aggressively standardizes a mine name"""
        terms = [
            "adit",
            "claim",
            "deposit",
            "mina",
            "mine",
            "occurrence",
            "pit",
            "property",
            "prospect",
            "prospecto",
            "quarry",
            "shaft",
            "tailings",
        ]
        terms.extend([t + "s" for t in terms])
        return self._std_feature(val, terms)

    def std_mining_district(self, val):
        """Aggressively standardizes the name of a mining district"""
        terms = ["area", "district", "group", "mining"]
        terms.extend([t + "s" for t in terms])
        return self._std_feature(val, terms)

    def std_mountain(self, val):
        """Aggressively standardizes a mountain name"""
        terms = [
            "mont",
            "monte",
            "mount",
            "mountain",
            "peak",
            # Abbreviations
            "mt",
            "mtn",
            "pk",
        ]
        return self._std_feature(val, terms)

    def std_municipality(self, val):
        """Aggressively standardizes a municipality name"""
        terms = [
            "barrio",
            "city",
            "ciudad",
            "hacienda",
            "municipality",
            "municipio",
            "town",
            "township",
            "village",
            # Abbreviations
            "bo",
            "cd",
            "hda",
            "mun",
            "twp",
        ]
        return self._std_feature(val, terms)

    def std_river(self, val):
        """Aggressively standardizes a river name"""
        terms = [
            "dry fork",
            "creek",
            "little",
            "mouth",
            "river",
            "stream",
            # Abbreviations
            "ck",
            "cr",
            "mo",
            "r",
            "riv",
        ]
        return self._std_feature(val, terms)

    def std_feature(self, val, hint=None):
        """Standardizes a feature name based on the type of feature"""
        if hint == "island_group":
            hint = "island"
        return self.guess_std_function(val, hint=hint)(val)

    def _std_feature(self, val, terms):
        if not isinstance(terms, list):
            terms = [terms]
        key = hash(str(terms))
        try:
            return self.hints[key][str(val)]
        except KeyError:
            try:
                st_val = self(self.remove(self(val), terms))
            except ValueError:
                st_val = self(val)
            self.hints.setdefault(key, {})[str(val)] = st_val
            return st_val

    def guess_std_function(self, val, hint=None):
        """Guesses the type of feature based on keywords"""
        try:
            return self.features[hint]
        except KeyError:
            val = self(val)
            options = []
            for kind, func in self.features.items():
                if func(val) != val and func not in options:
                    options.append(func)
            if len(options) == 1:
                return options[0]
        raise ValueError(f"Could not guess feature type for {repr(val)}")

    def validate(self, val):
        """Tests if result is valid"""
        return val.strip() and not re.match(r"^\d+$", val)

    def variants(self, name):
        """Calculates possible variants of a name"""
        st_name = self.std(name)
        variants = OrderedDict()
        variants["standard"] = st_name
        if not st_name:
            return {}
        expanded = self.debreviate(self.std(name, post=[]))
        if expanded != st_name:
            variants["expanded"] = expanded
            st_name = expanded
        # Check for field-specific variants
        for key in [
            "admin",
            "bay",
            "crater",
            "harbor",
            "island",
            #'island_group',
            "lake",
            "mountain",
            "municipality",
            "river",
        ]:
            spec_name = getattr(self, f"std_{key}")(st_name)
            if spec_name != st_name:
                variants[key] = spec_name
        return variants


def std_directions(val, lower=False):
    """Standardizes cardinal directions within a longer string"""
    orig = val

    # Standardize N. to N
    def callback_n(m):
        return m.group(1).upper() + " "

    # val = re.sub(r'\b([NSEW])\. ?', callback_n, val, flags=re.I)
    val = re.sub(r"\b([A-Z])\.", callback_n, val, flags=re.I)
    val = re.sub(r" +", " ", val)

    # Standardize N.N.E. or similar to NNE
    def callback_nne(m):
        return (m.group(1) + m.group(2) + m.group(3)).upper()

    pattern = r"\b([NEWS])[ -]*([NS])[ -]*([EW])\b"
    val = re.sub(pattern, callback_nne, val, flags=re.I)

    # Standardize N.E. or similar to NE
    def callback_ne(m):
        return (m.group(1) + m.group(2)).upper()

    val = re.sub(r"\b([NS])[ -]*([EW])\b", callback_ne, val, flags=re.I)

    # Standardize patterns similar to N.45E., etc.
    def callback_n45e(m):
        return (m.group(1) + m.group(2) + m.group(3)).upper().rstrip(".")

    pattern = r"(\b[NS])[ -]*(\d+(?:\.\d+)?)°?[ -]*([EW]\b.)"
    val = re.sub(pattern, callback_n45e, val, flags=re.I)

    return val.lower() if lower else val


def compass_dir(val):
    """Abbreviates a compass direction or bearing"""
    orig = val
    val = std_directions(val)
    # Replace full names with abbreviations
    for cdir in ("north", "south", "east", "west"):
        val = re.sub(cdir, cdir[0], val, flags=re.I)

    # Clean up spaces and punctuation
    val = val.upper().replace(" ", "").replace("-", "")
    val = re.sub(r"(\d)(?:°|deg\.?|degrees?)", r"\1", val, flags=re.I)

    # Verify that the direction is valid
    if not re.match(r"([NSEW]{1,3}|[NS]\d+(\.\d+)?[EW])$", val):
        raise ValueError(f"Invalid compass direction: {repr(orig)}")

    return val


def read_abbreviations(fp=None):
    """Reads common place name abbreviations from a file"""
    from ...config import DATA_DIR

    if fp is None:
        fp = os.path.join(DATA_DIR, "geonames", "place_name_abbreviations.csv")
    abbr = {}
    with open(fp, "r", encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(skip_hashed(f), dialect="excel")
        keys = next(rows)
        for row in rows:
            rowdict = dict(zip(keys, row))
            if rowdict["full_word"]:
                if rowdict["expand_when"] == "always":
                    abbr[rowdict["word"]] = rowdict["full_word"]
                    abbr[rowdict["word"] + "."] = rowdict["full_word"]
                elif rowdict["expand_when"] == "has period":
                    abbr[rowdict["word"] + "."] = rowdict["full_word"]
    return abbr
