import logging
import os
import re
import yaml

from ...config import CONFIG_DIR

logger = logging.getLogger(__name__)
logger.debug("Loading utils.py")

with open(os.path.join(CONFIG_DIR, "config_specimen_numbers.yml"), "r") as f:
    _REGEX = yaml.safe_load(f)
    _CATNUM_REGEX = _REGEX["catnum"].format(**_REGEX)

GEOSCIENCE_KEYWORDS = [
    "fossils?",
    "pala?eo(biolog|botan|ntolog).*?",
    # Deprecated major chronostrat terms
    "Carboniferous",
    "Tertiary",
    # ICS and land mammal chronostrat terms
    "Aalenian",
    "Aeronian",
    "Agenian",
    "Albian",
    "Anisian",
    "Aptian",
    "Aquilian",
    "Aquitanian",
    "Arikareean",
    "Arshantan",
    "Artinskian",
    "Arvernian",
    "Asselian",
    "Astaracian",
    "Bajocian",
    "Barremian",
    "Barstovian",
    "Bartonian",
    "Bashkirian",
    "Bathonian",
    "Berriasian",
    "Blancan",
    "Bridgerian",
    "Bumbanian",
    "Burdigalian",
    "Calabrian",
    "Callovian",
    "Cambrian",
    "Campanian",
    "Capitanian",
    "Carnian",
    "Casamayoran",
    "Cenomanian",
    "Cenozoic",
    "Cernaysian",
    "Chadronian",
    "Changhsingian",
    "Chapadmalalan",
    "Chasicoan",
    "Chattian",
    "Cisuralian",
    "Clarendonian",
    "Clarkforkian",
    "Colhuehuapian",
    "Colloncuran",
    "Coniacian",
    "Cretaceous",
    "Danian",
    "Dapingian",
    "Darriwilian",
    "Deseadan",
    "Devonian",
    "Divisaderan",
    "Drumian",
    "Duchesnean",
    "Eifelian",
    "Emsian",
    "Ensenadan",
    "Eocene",
    "Ergilian",
    "Famennian",
    "Floian",
    "Fortunian",
    "Frasnian",
    "Friasian",
    "Furongian",
    "Gashatan",
    "Geiseltalian",
    "Gelasian",
    "Geringian",
    "Givetian",
    "Gorstian",
    "Grauvian",
    "Greenlandian",
    "Guadalupian",
    "Guzhangian",
    "Gzhelian",
    "Hadean",
    "Harrisonean",
    "Hauterivian",
    "Headonian",
    "Hemingfordian",
    "Hemphillian",
    "Hettangian",
    "Hirnantian",
    "Holocene",
    "Homerian",
    "Houldjinian",
    "Hsandagolian",
    "Huayquerian",
    "Induan",
    "Irdinmanhan",
    "Irvingtonian",
    "Itaboraian",
    "Jiangshanian",
    "Judithian",
    "Jurassic",
    "Kasimovian",
    "Katian",
    "Kekeamuan",
    "Kimmeridgian",
    "Kungurian",
    "Ladinian",
    "Lancian",
    "Langhian",
    "Laventan",
    "Llandovery",
    "Lochkovian",
    "Lopingian",
    "Ludfordian",
    "Ludlow",
    "Lujanian",
    "Lutetian",
    "Maastrichtian",
    "Mayoan",
    "Meghalayan",
    "Mesozoic",
    "Messinian",
    "Miaolingian",
    "Miocene",
    "Mississippian",
    "Monroecreekian",
    "Montehermosan",
    "Moscovian",
    "Mustersan",
    "Neogene",
    "Neustrian",
    "Norian",
    "Northgrippian",
    "Olenekian",
    "Oligocene",
    "Ordovician",
    "Orellan",
    "Orleanian",
    "Oxfordian",
    "Paibian",
    "Paleocene",
    "Paleogene",
    "Paleozoic",
    "Peligran",
    "Pennsylvanian",
    "Permian",
    "Phanerozoic",
    "Piacenzian",
    "Pleistocene",
    "Pliensbachian",
    "Pliocene",
    "Pragian",
    "Priabonian",
    "Puercan",
    "Quaternary",
    "Rancholabrean",
    "Rhaetian",
    "Rhuddanian",
    "Riochican",
    "Roadian",
    "Robiacian",
    "Rupelian",
    "Ruscinian",
    "Saintaugustinean",
    "Sakmarian",
    "Sandbian",
    "Santacrucian",
    "Santarosean",
    "Santonian",
    "Selandian",
    "Series 2",
    "Serpukhovian",
    "Serravallian",
    "Sharamurunian",
    "Sheinwoodian",
    "Silurian",
    "Sinemurian",
    "Suevian",
    "Tabenbulakian",
    "Telychian",
    "Terreneuvian",
    "Thanetian",
    "Tiffanian",
    "Tinguirirican",
    "Tithonian",
    "Tiupampan",
    "Toarcian",
    "Torrejonian",
    "Tortonian",
    "Tournaisian",
    "Tremadocian",
    "Triassic",
    "Turolian",
    "Turonian",
    "Uintan",
    "Ulangochuian",
    "Uquian",
    "Valanginian",
    "Vallesian",
    "Villafranchian",
    "Visean",
    "Wasatchian",
    "Wenlock",
    "Whitneyan",
    "Wordian",
    "Wuchiapingian",
    "Wuliuan",
    "Ypresian",
    "Zanclean",
]


class SpecNum:

    def __init__(self, code, kind, prefix, number, suffix):

        self.code = code if code else ""
        self.kind = kind if kind else ""
        self.prefix = prefix if prefix else ""
        self.number = int(number if number else "")
        self.suffix = suffix if suffix else ""

        if not self.number:
            raise ValueError(f"Invalid number: {repr(self.number)}")

        self.delim = "-"
        if (
            self.suffix.isalpha()
            and len(self.suffix) == 1
            or re.match(r"[A-Za-z]-\d+", self.suffix)
        ):
            self.delim = ""
        elif self.suffix and self.suffix[0] in "-,./ ":
            self.delim = self.suffix[0]
            self.suffix = self.suffix.lstrip("-,./ ")

        # Look for catalog numbers that are too large
        if self.number >= 1e7:
            raise ValueError(f"Invalid number: {repr(self.number)}")

        # Look for suffixes that are probably ranges
        if re.match(r"(\d+[A-z]?\-\d+[A-z]?|[A-z]\-[A-z])", self.suffix):
            raise ValueError(f"Invalid suffix: {repr(self.suffix)}")

        # Look for suffixes that are probably separate numbers
        if self.suffix:
            try:
                suffix_num = parse_spec_num(self.suffix)
            except ValueError:
                pass
            else:
                if not suffix_num.prefix and suffix_num.number >= 1000:
                    raise ValueError(
                        f"Suffix could be a catalog number: {repr(self.suffix)}"
                    )

    def __str__(self):
        delim_prefix = ""
        if len(self.prefix) > 1:
            delim_prefix = " "

        return (
            "{} {}{}{}{}{}{}".format(
                self.code,
                self.kind + " " if self.kind else "",
                self.prefix,
                delim_prefix,
                self.number,
                self.delim,
                self.suffix,
            )
            .rstrip(self.delim)
            .strip()
        )

    def __repr__(self):
        return (
            "SpecNum("
            f"code={repr(self.code)},"
            f"kind={repr(self.kind)}, "
            f"prefix={repr(self.prefix)}, "
            f"number={repr(self.number)}, "
            f"suffix={repr(self.suffix)}"
            ")"
        )

    def __lt__(self, other):
        try:
            return self._sortable() < other._sortable()
        except AttributeError:
            raise TypeError(
                f"'<' not supported between instances of {repr(self)} and {repr(other)}"
            )

    def copy(self):
        val = self.__class__(
            code=self.code,
            kind=self.kind,
            prefix=self.prefix,
            number=self.number,
            suffix=self.suffix,
        )
        val.delim = self.delim
        return val

    def is_similar_to(
        self,
        other,
        min_num=100,
        max_diff=500,
        match_empty_code=False,
        match_empty_prefix=False,
    ):
        """Tests if specimen number is similar to another specimen number"""
        other = parse_spec_num(other)
        same_code = self.code == other.code
        same_prefix = self.prefix == other.prefix
        big_numbers = self.number > min_num and other.number > min_num
        small_diff = abs(self.number - other.number) < max_diff
        no_suffix = not self.suffix and not other.suffix
        return (
            (same_code or match_empty_code)
            and (same_prefix or match_empty_prefix)
            and (big_numbers or small_diff)
            and small_diff
            and no_suffix
        )

    def is_range(self, other, max_diff=100, **kwargs):
        kwargs["max_diff"] = max_diff
        kwargs.setdefault("match_empty_code", True)
        kwargs.setdefault("match_empty_prefix", True)
        other = parse_spec_num(other)
        return (
            self.is_similar_to(other, **kwargs)
            and other.number - self.number <= max_diff
        )

    def _sortable(self):
        return (
            self.code.zfill(23),
            self.kind.zfill(32),
            self.prefix.zfill(32),
            str(self.number).zfill(32),
            self.suffix.zfill(32),
        )


def is_geoscience(text):
    """Tests if a string contains any geoscience keywords"""
    pattern = r"\b({})\b".format("|".join(GEOSCIENCE_KEYWORDS))
    return bool(re.search(pattern, text, flags=re.I))


def is_spec_num(val, min_num=0):
    """Tests if value is a valid specimen number"""
    try:
        return parse_spec_num(val).number > min_num
    except ValueError:
        return False


def are_spec_nums(vals, min_num=0):
    try:
        return vals and all((is_spec_num(s, min_num=min_num) for s in vals))
    except ValueError:
        return False


def is_range(n1, n2, max_diff=100, **kwargs):
    kwargs["max_diff"] = max_diff
    kwargs.setdefault("match_empty_code", True)
    kwargs.setdefault("match_empty_prefix", True)
    n1 = parse_spec_num(n1)
    n2 = parse_spec_num(n2)
    return (
        n1.is_similar_to(n2, **kwargs)
        and n2.number > n1.number
        and n2.number - n1.number <= max_diff
    )


def parse_spec_num(val):
    """Parses a single well-formed specimen number"""
    if isinstance(val, SpecNum):
        return val
    orig = val
    if not re.match(r"^[A-Z]{3,4}", val):
        val = f"ZZZZ {val}"
    mask = (
        r"^(?:(?P<code>AMNH|FMNH|MCZ|NMNH|USNM|YPM|ZZZZ) )?"
        r"(?:(?P<kind>(?:loc\.|locality|slide|type) no\.) )?"
        r"(?P<prefix>(?:[A-Z]{1,4}))? ?"
        r"(?P<number>\d+)"
        r"(?P<suffix>(?:(?:[\-\.,/ ](?:[A-Z0-9]+)(?:[-\.][A-Z0-9]+)*)|[A-Z](-?\d)?)?"
        r"(?: \((?:[A-Z:]+)\))?)$"
    )
    match = re.search(mask, val, flags=re.I)
    if match is None:
        raise ValueError(f"Could not parse {repr(orig)}")
    kwargs = match.groupdict()
    if kwargs["code"] == "ZZZZ":
        kwargs["code"] = ""
    spec_num = SpecNum(**kwargs)
    return spec_num


def combine_vals(vals, min_num=1000, from_ocr=False):

    if is_spec_num(" ".join(vals), min_num=min_num):
        return vals

    orig = vals[:]

    # Fill out shorthand numbers (like 123456 57 58)
    for i, val in enumerate(vals):
        last = vals[i - 1]
        if i and val.isnumeric() and len(val) < len(last):
            full = last[: -len(val)] + val
            if parse_spec_num(last).is_similar_to(full):
                vals[i] = full

    if are_spec_nums(vals):
        return vals

    # Fix erroneous spaces introduced by OCR (like 211 106)
    if from_ocr:
        nums = []
        vals = []
        for val in orig:
            if val.isnumeric():
                if nums:
                    num = "".join(nums) + val
                    if is_spec_num(num, min_num=min_num):
                        nums.append(val)
                    else:
                        vals.append("".join(nums))
                        nums = [val]
                else:
                    nums = [val]
            elif re.match(r"[A-Z]?\d+(?!\.)", val):
                if nums:
                    vals.append("".join(nums))
                nums = [val]
            elif val:
                if nums:
                    vals.append("".join(nums))
                vals.append(val)
                nums = []
        if nums:
            vals.append("".join(nums))
        return vals

    return orig
