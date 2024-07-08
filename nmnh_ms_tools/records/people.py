"""Defines methods for parsing, comparing, and representing names"""

import re

from collections import namedtuple
from nameparser import HumanName

from .core import Record, Records
from ..utils.standardizers import Standardizer
from ..utils.lists import oxford_comma
from ..utils.strings import lcfirst, same_to_length


SimpleName = namedtuple("SimpleName", ["last", "first", "middle"])
PREFIXES = sorted(
    ["da", "de", "de la", "den", "do", "du", "st", "van", "van der", "von"],
    key=len,
    reverse=True,
)
SUFFIXES = ["Jr", "Sr", "II", "III", "IV", "Esq"]


class Person(Record):
    """Defines methods for parsing and manipulating names"""

    terms = [
        "title",
        "first",
        "middle",
        "last",
        "suffix",
        "organization",
    ]
    std = Standardizer(minlen=1)
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
        super(Person, self).__init__(*args, **kwargs)

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
        self.reset()
        if isinstance(data, str):
            self._parse_name(data)
        elif "NamLast" in data:
            self._parse_emu(data)
        elif {"last", "organization"} & set(data):
            self._parse(data)
        else:
            raise ValueError("Could not parse {}".format(data))

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
        if len(middle) == 1 or (
            initials and middle and not (" " in middle or middle.count(".") > 1)
        ):
            middle = middle[0] + "."
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
        self.verbatim = rec
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

        self.verbatim = re.sub(r"\s+", " ", name)
        name = name.strip()

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

        # Check for multiple names
        if re.search(r" (and|&) ", name, flags=re.I):
            raise ValueError(f"String contains multiple names: {name}")

        # Check if name is just initials
        initials = "".join([c for c in name if c.isalpha()])
        if initials.isupper() and len(initials) == 3:
            self.first, self.middle, self.last = initials
            return
        if initials.isupper() and len(initials) == 2:
            self.first, self.last = initials
            return

        # If name matches pattern for a compound name (von Trapp), use
        # capitalization to decide whether the prefix should be interpreted
        # as a first name or part of a last name.
        pattern = r"^({}) [a-z]+$".format("|".join(PREFIXES))
        if re.search(pattern, name, flags=re.I):
            if name[0].isupper() and " " in name:
                self.first, self.last = name.rsplit(" ", 1)
            else:
                self.last = name
            return

        # Check for inverted name (Cee, A. B.)
        after_comma = name.rsplit(",", 1)[-1].strip(". ")
        if "," in name and not after_comma in SUFFIXES:
            parts = [s.strip() for s in name.rsplit(",", 1)[::-1]]
            parts[-1] = parts[-1].replace(" ", "_")
            name = " ".join(parts)

        # Link compound names (von Trapp) with underscores
        for prefix in PREFIXES:
            # Skip if prefix appears to be a first name
            if re.match(prefix + r"\b", name, flags=re.I) and name.count(" ") > 1:
                continue
            pattern = r"\b{} (?=[a-zA-Z]{{3,}})".format(prefix)
            repl = r"{}_".format(prefix.replace(" ", "_"))
            name = re.sub(pattern, repl, name, flags=re.I)

        # HumanName gets confused by initials without spacing, so
        # normalize names like AB Cee and A.B. Cee
        name = re.sub(r"\b([A-Z]\.)(?! )", r"\1 ", name)
        if not name.isupper():
            name = re.sub(r"^([A-Z])([A-Z])\b", r"\1. \2.", name)

        # HumanName will not accept certain words as first names (e.g., Bon,
        # Do), so force it to by salting the first word
        salt = "zzzzzzzz"
        name = name.replace(" ", salt + " ", 1) if " " in name else name + salt

        # Parse name using the HumanName class
        name = HumanName(name)
        for attr in self.attributes:
            if attr != "organization":
                setattr(self, attr, getattr(name, attr))

        # Remove salt
        self.title = self.title.replace(salt, "").strip()
        self.first = self.first.replace(salt, "").strip()
        self.middle = self.middle.replace(salt, "").strip()
        self.last = self.last.replace(salt, "").strip()

        # Fix misparsed suffix
        if not self.last:
            self.last = self.first
            self.first = self.suffix
            self.suffix = ""

        # Fix misparsed trailing suffix
        if self.middle.rstrip(".").endswith(tuple(SUFFIXES)):
            try:
                self.middle, self.suffix = self.middle.rsplit(" ", 1)
            except ValueError:
                self.suffix = self.middle

        # Fix titles that nameparser struggles with
        problem_words = ["Count", "Countess"]
        for word in sorted(problem_words, key=len)[::-1]:
            if self.verbatim.startswith(word):
                # unparsed = unparsed.split(word)[1].strip()
                self.title = word
                break

        # Fix mixed initial/full name in middle name by
        middle_names = self.middle.split(" ")
        if len(middle_names) > 1 and len(middle_names[0].rstrip(".")) == 1:
            while len(middle_names[-1].rstrip(".")) > 1:
                self.last = "{} {}".format(middle_names.pop(), self.last)
            self.middle = " ".join(middle_names)

        # Fix compound middle names
        if "_" in self.middle:
            self.middle = self.middle.replace("_", " ")
            self.middle = self.middle[0].lower() + self.middle[1:]

        # Fix compound last names
        if "_" in self.last:
            parts = self.last.split("_")
            if parts[-1].upper() in SUFFIXES:
                self.suffix = parts.pop(-1)
            self.last = " ".join(parts)

        # Fix capitalization in hyphenates
        for attr in ["first", "middle", "last"]:
            capped = getattr(self, attr).title()
            # Keep compound name prefixes lower case
            for prefix in PREFIXES:
                if capped.lower().startswith(prefix + " "):
                    capped = capped[: len(prefix)].lower() + capped[len(prefix) :]
                    break
            setattr(self, attr, "".join(capped))

        # Strip trailing periods
        self.first = self.first.rstrip(".")
        self.middle = self.middle.rstrip(".")
        if "." in self.middle:
            self.middle = self.middle.upper() + "."

        # Fix last name is suffix
        if self.last.rstrip(".") in SUFFIXES:
            self.suffix = self.last
            self.last = self.first
            self.first = ""

        # Verify that the name isn't et al
        if self.first == "Et" and self.last == "Al":
            raise ValueError("Name contains et al: {}".format(self.verbatim))

        # Verify that at least the last name has been set
        if not self.last or "_" in str(self):
            raise ValueError("Failed to parse name: {}".format(self.verbatim))

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


def parse_names(val, delims="&|;,"):
    """Parses names in the given object

    Parameters:
        val (mixed): a list of names or string to break into a list of names
        delims (str): list of delimiters to try when breaking a string into a list of
            names

    Returns:
        list of names
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
        # Normalize periods then split
        val = (
            val.replace(". ", ".")
            .replace(".", ". ")
            .replace(" and ", " & ")
            .strip(" ;,")
        )
        val = re.sub(r" and$", "", val)
        # Remove unicode spaces
        val = re.sub(r"\s+", " ", val)
        # Remove commas that precede suffixes
        pattern = r", ?({})".format("|".join(SUFFIXES))
        val = re.sub(pattern, r" \1", val, flags=re.I)

        # Try a simple split and parse
        pattern = "[" + re.escape(delims) + "]"
        return [Person(s) for s in [s.strip() for s in re.split(pattern, val)]]
        # Figure out the delimiter
        if is_name(val):
            names = [val]
        else:
            for delim in delims:
                if delim in val:
                    val = re.sub(delim + r" & ", delim, val)
                    names = [s.strip(" ,;") for s in val.split(delim)]
                    break
            else:
                # raise ValueError(f"Cannot identify delimiter: {val}")
                print(f"Cannot identify delimiter: {val}")
    else:
        names = val[:]

    # Convert each name to Person
    people = []
    for name in names:
        if name.strip() and name.strip(".") not in SUFFIXES:
            try:
                people.append(Person(name))
            except ValueError:
                pass

    # for name, person in zip(names, people):
    #    print(name, '=>', repr(person))

    return people


def combine_names(
    names,
    mask="{first} {middle} {last}",
    initials=True,
    max_names=2,
    delim="; ",
    conj="and",
):
    """Combines a list of names into a string"""
    if not any(names):
        return ""
    if not isinstance(names[0], Person):
        names = parse_names(names)
    names = [name.summarize(mask=mask, initials=initials) for name in names]
    if len(names) > max_names:
        names = re.sub(
            r" +", " ", oxford_comma(names[:max_names], delim=delim, conj="")
        )
        return "{} et al.".format(names)
    return re.sub(r" +", " ", oxford_comma(names, delim=delim, conj=conj))


def combine_authors(*args, **kwargs):
    """Combines list of authors into a string suitable for a reference"""
    kwargs.setdefault("mask", "{last}, {first} {middle}")
    kwargs.setdefault("initials", True)
    authors = combine_names(*args, **kwargs)
    return authors


def is_name(val):
    """Checks if text contains exactly one name"""
    try:
        Person(val)
        return True
    except ValueError:
        return False
