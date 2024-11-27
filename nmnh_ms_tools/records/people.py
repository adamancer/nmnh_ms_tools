"""Defines methods for parsing, comparing, and representing names"""

import csv
import unicodedata
from pathlib import Path

from collections import namedtuple

import regex as re

from .core import Record, Records
from ..config import DATA_DIR
from ..utils import LazyAttr, Standardizer, mutable, oxford_comma, same_to_length


SimpleName = namedtuple("SimpleName", ["last", "first", "middle"])

TITLES = {}
with open(
    Path(DATA_DIR) / "records" / "titles.csv", encoding="utf-8-sig", newline=""
) as f:
    for row in csv.DictReader(f, dialect="excel"):
        TITLES[row["abbreviation"]] = row["title"]
ALL_TITLES = sorted(list(TITLES) + list(TITLES.values()), key=len, reverse=True)
ALL_TITLES = [s.rstrip(".") for s in ALL_TITLES]
SURNAME_PREFIXES = sorted(
    ["da", "de", "de la", "den", "do", "du", "st", "van", "van der", "von"],
    key=len,
    reverse=True,
)
SUFFIXES = {
    "II": "the second",
    "III": "the third",
    "IV": "the fourth",
    "Jr": "junior",
}
ALL_SUFFIXES = sorted(list(SUFFIXES) + list(SUFFIXES.values()), key=len, reverse=True)
TITLE_PATTERN = "^(" + "|".join(ALL_TITLES) + r")\b"
SURNAME_PATTERN = r"\b((" + "|".join(list(SURNAME_PREFIXES)) + r") )?[-\p{L}]+$"
SUFFIX_PATTERN = r"\b(" + "|".join(ALL_SUFFIXES) + ")$"


class Person(Record):
    """Defines methods for parsing and manipulating names"""

    # Deferred class attributes are defined at the end of the file
    std = None

    # Normal class attributes
    terms = [
        "title",
        "first",
        "middle",
        "last",
        "suffix",
        "organization",
    ]
    irns = {}

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.title = ""
        self.first = ""
        self.middle = ""
        self.last = ""
        self.suffix = ""
        self.organization = ""
        # Initialize instance
        super().__init__(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.summarize()

    @property
    def first_initial(self):
        return self.first[0] if self.first else ""

    @property
    def middle_initial(self):
        return re.sub(" +", " ", " ".join(re.split(r"[. ]+", self.middle)).strip())

    def parse(self, data):
        """Parses data from various sources to populate class"""
        if isinstance(data, str):
            self._parse_name(data)
        elif "NamLast" in data:
            self._parse_emu(data)
        elif {"last", "organization"} & set(data):
            self._parse(data)
        else:
            raise ValueError(f"Could not parse {repr(data)}")

        self.suffix = self.suffix.rstrip(".")

    def same_as(self, other, strict=True):
        """Compares name to another name"""
        try:
            assert isinstance(other, self.__class__)
        except AssertionError:
            return False
        if self.organization and self.organization == other.organization:
            return True
        names = []
        for name in [self, other]:
            first = self.std_name(name.first)
            last = self.std_name(name.last)
            middle = self.std_name(name.middle)
            names.append(SimpleName(last, first, middle))
        name, other = names
        # Force strict match on short last names
        if strict or min([len(n[0]) for n in names]) <= 3:
            # If strict, C. Darwin != Charles Darwin
            same_last = name.last == other.last
            same_first = name.first == other.first
            same_middle = name.middle == other.middle
        else:
            # If not strict, C. R. Darwin == Charles Darwin and
            # Char. Darwin == Charles Darwin, but
            # Christopher Darwin != Charles Darwin
            same_last = name.last == other.last
            same_first = same_to_length(name.first, other.first)
            same_middle = same_to_length(name.middle, other.middle)
        return same_last and same_first and same_middle

    def reset(self):
        """Resets all attributes to defaults"""
        self.verbatim = None
        self.title = None
        self.first = None
        self.middle = None
        self.last = None
        self.suffix = None
        self.organization = None

    def summarize(
        self, mask="{title} {first} {middle} {last}, {suffix}", initials=False
    ):
        """Converts name to a string"""
        if self.organization:
            return self.organization
        title = self.title if self.title else ""
        first = self.first if self.first else ""
        middle = self.middle if self.middle else ""
        suffix = self.suffix if self.suffix else ""
        if len(first) == 1 or (initials and first):
            first = first[0] + "."
        if len(middle) == 1 or (initials and " " in middle):
            middles = [m + "." if len(m) == 1 else m for m in middle.split(" ")]
            middle = " ".join(middles)
        name = mask.format(
            title=title, first=first, middle=middle, last=self.last, suffix=suffix
        )
        name = re.sub(r" +", " ", name)
        name = re.sub(r"\.[^ ]", ". ", name)
        name = name.strip(" ,")
        return name

    def initials(self, delim=". "):
        """Returns initials"""
        initials = [s[0] for s in [self.first, self.middle, self.last] if s]
        return delim.join(initials)

    def std_name(self, name):
        """Standardizes name for comparisons"""
        try:
            return self.std.std(name)
        except ValueError:
            return name

    def _to_emu(self):
        """Formats record for EMu eparties module"""
        try:
            irn = self.__class__.irns[str(self)]
            if irn:
                return {"irn": int(irn)}
        except KeyError:
            self.__class__.irns[str(self)] = None

        if self.last:
            return {
                "NamPartyType": "Person",
                "NamTitle": self.title,
                "NamFirst": self.first,
                "NamMiddle": self.middle,
                "NamLast": self.last,
                "NamSuffix": self.suffix,
            }

        return {
            "NamPartyType": "Organization",
            "NamOrganisation": self.organization,
        }

    def _parse_emu(self, rec):
        """Parses an EMu eparties record"""
        if rec.get("NamLast"):
            self.title = rec.get("NamTitle")
            self.first = rec.get("NamFirst")
            self.middle = rec.get("NamMiddle")
            self.last = rec.get("NamLast")
            self.suffix = rec.get("NamSuffix")
        else:
            self.organization = rec.get("NamOrganisation")

    def _parse_name(self, name):
        """Parses a name using the nameparser module"""

        name = clean_name(name)

        # Check if name appears to be an organization
        org_words = {
            "bureau",
            "college",
            "council",
            "expedition",
            "institution",
            "museum",
            "scientific",
            "society",
            "university",
        }
        words = set(re.split(r"(\W+)", name.lower()))
        if words & org_words:
            self.organization = name
            return

        # Reorder names with a single comma
        name = " ".join(name.split(",", 1)[::-1])
        # Check for title
        match = re.search(TITLE_PATTERN, name, flags=re.I | re.U)
        if match:
            val = match.group()
            name = name[len(val) :].strip(". ")
            for item in TITLES.items():
                if {val.lower(), val.lower() + "."} & {s.lower() for s in item}:
                    self.title = item[0]
                    break
        # Check for compound titles
        match = re.search("and " + TITLE_PATTERN[1:], name, flags=re.I | re.U)
        if match:
            val = match.group()
            name = name[len(val) :].strip(". ")
            val = val[4:]
            for item in TITLES.items():
                if {val.lower(), val.lower() + "."} & {s.lower() for s in item}:
                    self.title += " and " + item[0]
                    break
        # Check for suffix
        match = re.search(SUFFIX_PATTERN, name, flags=re.I)
        if match:
            val = match.group()
            name = name[: -len(val)].strip(". ")
            for item in SUFFIXES.items():
                if val.lower() in [s.lower() for s in item]:
                    self.suffix = item[0]
                    break
        # Check for last name, including compounds last names
        match = re.search(SURNAME_PATTERN, name, flags=re.I)
        if match:
            self.last = match.group()
            name = name[: -len(self.last)].strip(". ")
        # Split into parts
        parts = [s for s in re.split(r"[^-\p{L}]+", name, flags=re.I) if s]
        # First name is first part
        if parts:
            self.first = parts.pop(0)
        # Split first name that is likely to be initials
        if (
            not name.isupper()
            and len(self.first) > 1
            and self.first.isupper()
            or name.isupper()
            and len(self.first) == 2
        ):
            parts = list(self.first[1:]) + parts
            self.first = self.first[0]
        self.middle = " ".join(parts)

        # A short name in all caps without a first name is interpreted as initials
        if not self.first and not self.middle and self.last.isupper():
            if len(self.last) == 2:
                self.first, self.last = list(self.last)
            elif len(self.last) == 3:
                self.first, self.middle, self.last = list(self.last)

        # Verify that the name isn't et al
        if self.first == "Et" and self.last == "Al":
            raise ValueError(f"Name contains et al: {self.verbatim}")

        # Verify that at least the last name has been set
        if not self.last:
            raise ValueError(f"Failed to parse name: {repr(self.verbatim)}")

        # Check for multiple names
        if (
            re.search(f"\band\b", self.first)
            or re.search(f"\band\b", self.middle)
            or re.search(f"\band\b", self.last)
        ):
            raise ValueError(f"String contains multiple names: {name}")

    def _sortable(self):
        """Returns a sortable version of the object"""
        parts = [self.last, self.first, self.middle]
        return "".join([p.replace(".", "").ljust(32) for p in parts])


class People(Records):
    item_class = Person

    def __init__(self, val=None):
        super().__init__(parse_names(val) if isinstance(val, str) else val)

    def __str__(self):
        return combine_names(self)


def parse_names(val: str | list, delims: str = "|;,") -> list[Person]:
    """Parses names in the given object

    Parameters
    ----------
        val : str or list
            a list of names or string to break into a list of names
        delims : str
            delimiters to try when breaking a string into a list of names

    Returns
    -------
    list[Person]
        list of Person objects
    """
    if not val:
        return []
    if not isinstance(val, list):
        # Remove "et al" for string, truncating the string where et al occurs.
        # Then do the same for numbers. Both actions are useful for trimming
        # garbage from names pulled from citation strings.
        if "et al" in val.lower():
            val = re.split(r"\bet al\b", val, flags=re.I)[0].rstrip("., ")
        val = re.split(r"\d", val, 1)[0].strip()
        val = clean_name(val)

        # Check if all values are delimited by and
        vals = re.split(" +and +", val)
        # No more than one comma per name
        if all((s.count(",") <= 1 for s in vals)):
            delim = " and "
        else:
            # Split the list of names on the matching delimiter
            for delim in delims:
                if delim in val:
                    vals = re.split(
                        f" *{re.escape(delim)} *", val.replace(" and ", delim)
                    )
                    # No more than one comma per name
                    if all((s.count(",") <= 1 for s in vals)):
                        break
            else:
                delim = None
                vals = [val]

        # Some publishers use commas to delimit both first name and individual names.
        # This block works around this by replacing every other comma with a pipe, but
        # will give a bad result for a list of last names.
        if delim == ",":
            val_ = re.sub("(.*?,.*?),", r"\1|", val.replace(" and ", ", "))
            if val_ != val:
                return parse_names(val_)

        # Catch bad title splits
        names = []
        for i, val in enumerate(vals):
            try:
                names.append(Person(val))
            except ValueError:
                if re.match(TITLE_PATTERN, val):
                    vals[i + 1] = f"{val} and {vals[i + 1]}"

        return names


def clean_name(name: str) -> str:
    """Standardizes name string to make it easier to parse

    Parameters
    ----------
    name : str
        the name to clean

    Returns
    -------
    str
        a nice clean name
    """
    # Normalize unicode
    name = unicodedata.normalize("NFC", name)
    # Remove multiple spaces
    name = re.sub(r"\s+", " ", name)
    # Remove all periods
    name = re.sub(r"\. *", " ", name).strip()
    # Replace ampersand with "and"
    name = re.sub(" *& *", " and ", name)
    # Remove oxford comma
    name = re.sub(", and ", " and ", name)
    # Remove commas before suffixes
    name = re.sub(", *(" + "|".join(ALL_SUFFIXES) + ")", r" \1", name, flags=re.I)
    return name


def combine_names(
    names: list[str] | list[Person],
    mask: str = "{first} {middle} {last}",
    initials: bool = True,
    max_names: int = 2,
    delim: str = "; ",
    conj: str = "and",
):
    """Combines a list of names into a string

    Parameters
    ----------
    names : list[str] | list[Person]
        list of names
    mask : str
        mask to use to format each name
    initials : bool
        whether to use initials
    max_names : int
        maximum number of names to list individually. If more names are present,
        the combined string will conclude with et al.
    delim : str
        the character used to delimit each name in the string
    conj : str
        the word or character used to delimit the final name in the string

    Returns
    -------
    str
        the list of names as a string
    """
    if not any(names):
        return ""
    if not isinstance(names[0], Person):
        names = parse_names(names)
    names = [name.summarize(mask=mask, initials=initials) for name in names]
    if len(names) > max_names:
        names = re.sub(
            r" +", " ", oxford_comma(names[:max_names], delim=delim, conj="")
        )
        return f"{names} et al."
    return re.sub(r" +", " ", oxford_comma(names, delim=delim, conj=conj))


def is_name(val):
    """Checks if text contains exactly one name"""
    try:
        Person(val)
        return True
    except ValueError:
        return False


# Define deferred class attributes
LazyAttr(Person, "std", Standardizer, minlen=1)
