import logging
import re

from unidecode import unidecode

from ...utils import del_immutable, mutable, set_immutable

logger = logging.getLogger(__name__)


class SpecNum:

    def __init__(self, code, kind, prefix, number, suffix, delim=None):

        self.delim = None
        self.code = code if code else ""
        self.kind = kind if kind else ""
        self.prefix = prefix if prefix else ""
        self.number = str(number) if number else ""

        with mutable(self):
            # Call delim to finalize formatting of suffix
            if delim is None:
                delim = "-"
                if suffix and suffix[0] in "-,./ ":
                    delim = suffix[0]
                    suffix = suffix.lstrip("-,./ ")
                if (
                    suffix.isalpha()
                    and len(suffix) == 1
                    or re.match(r"[A-Za-z]-\d+", suffix)
                ):
                    delim = ""

            # Ensure that empty attributes are represented as empty strings
            self.suffix = suffix if suffix else ""
            self.delim = delim if delim and suffix else ""

        if not self.number:
            raise ValueError(f"Invalid number: {repr(self.number)}")

        # Look for catalog numbers that are too large
        if int(self) >= 1e7:
            raise ValueError(f"Invalid number: {repr(self.number)}")

    def __setattr__(self, attr, val):
        set_immutable(self, attr, val)

    def __delattr__(self, attr):
        del_immutable(self, attr)

    def __str__(self):
        return self._str()

    def __repr__(self):
        return (
            "SpecNum("
            f"code={repr(self.code)}, "
            f"kind={repr(self.kind)}, "
            f"prefix={repr(self.prefix)}, "
            f"number={repr(self.number)}, "
            f"delim={repr(self.delim)}, "
            f"suffix={repr(self.suffix)}"
            ")"
        )

    def __int__(self):
        return int(self.number)

    def __add__(self, val):
        return self.modcopy(number=int(self) + val)

    def __sub__(self, val):
        return self.modcopy(number=int(self) - val)

    def __eq__(self, other):
        return (
            self.code == other.code
            and self.kind == other.kind
            and int(self) == int(other)
            and self.suffix.lstrip("0") == other.suffix.lstrip("0")
        )

    def __lt__(self, other):
        try:
            return sortable_spec_num(self.key()) < sortable_spec_num(other.key())
        except AttributeError:
            raise TypeError(
                f"'<' not supported between instances of {repr(self)} and {repr(other)}"
            )

    @property
    def parent(self):
        return self.modcopy(suffix="", delim=None)

    def key(self, **kwargs):
        """Returns the specimen number standardized as text

        Returns
        -------
        str
            specimen number as a string suitable for comparisons

        """
        kwargs.setdefault("delim", "-")
        kwargs.setdefault("include_code", True)
        kwargs.setdefault("strip_leading_zeroes", True)
        kwargs.setdefault("drop_zero_suffixes", False)

        # Extract kwargs for the two functions called below
        str_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k in ("delim", "include_code", "strip_leading_zeroes")
        }
        std_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k in ("drop_zero_suffixes", "strip_leading_zeroes")
        }

        return std_spec_num(self._str(**str_kwargs), **std_kwargs)

    def copy(self):
        """Copies the current SpecNum object"""
        return self.modcopy()

    def modcopy(self, **kwargs):
        return self.__class__(
            code=kwargs.get("code", self.code),
            kind=kwargs.get("kind", self.kind),
            prefix=kwargs.get("prefix", self.prefix),
            number=kwargs.get("number", self.number),
            suffix=kwargs.get("suffix", self.suffix),
            delim=kwargs.get("delim", self.delim),
        )

    def is_similar_to(
        self,
        other,
        min_num=100,
        max_diff=500,
        match_empty_code=False,
        match_empty_prefix=False,
    ):
        """Tests if specimen number is similar to another specimen number

        Parameters
        ----------
        other : SpecNum or str
            another SpecNum or parseable string
        min_num : int
            the minimum catalog number value
        max_diff : int
            the maximum difference allowed between the two specimen numbers
        match_empty_code : bool
            if True, will match two otherwise similar numbers where one specifies
            a museum code and one does not
        match_empty_prefix : bool
            if True, will match two otherwise similar numbers where one specifies
            a prefix and one does not

        Returns
        -------
        bool
            return True if the two specimen numbers are similar
        """
        other = parse_spec_num(other)
        same_code = self.code == other.code
        same_prefix = self.prefix == other.prefix
        big_numbers = int(self) > min_num and int(other) > min_num
        small_diff = max_diff is None or abs(int(self) - int(other)) < max_diff
        no_suffix = not self.suffix and not other.suffix
        return (
            (same_code or match_empty_code)
            and (same_prefix or match_empty_prefix)
            and (big_numbers or small_diff)
            and small_diff
            and no_suffix
        )

    def is_range(self, other=None, max_diff=100, **kwargs):
        """Tests if specimen number is similar to another specimen number

        Parameters
        ----------
        other : SpecNum or str
            another SpecNum or parseable string
        max_diff : int
            the maximum difference allowed between the two specimen numbers
        kwargs :
            keyword arguments accepted by is_similar_to

        Returns
        -------
        bool
            returns True if supplied numbers can be interpreted as a range
        """

        if other is None:
            return len(self.as_range()) > 1

        kwargs["max_diff"] = max_diff
        kwargs.setdefault("match_empty_code", True)
        kwargs.setdefault("match_empty_prefix", True)
        other = parse_spec_num(other)
        result = (
            self.is_similar_to(other, **kwargs)
            and abs(int(other) - int(self)) <= max_diff
        )
        return result if result else is_range(self.suffix)

    def as_separate_numbers(self):
        """Expresses a number and suffix as separate specimen numbers

        Returns
        -------
        list of SpecNum
            list with the number and suffix attributes
        """
        try:
            suffix = parse_spec_num(self.suffix)
        except ValueError:
            pass
        else:
            return [self.modcopy(suffix=""), suffix]
        return [self]

    def as_range(self, max_diff=100):
        """Expresses a specimen number as a range

        Parameters
        ----------
        max_diff : int
            the maximum difference allowed between the two specimen numbers

        Returns
        -------
        list of SpecNum
            list of SpecNum when interpreted as a range. If not a range, the
            list will include a single value.
        """

        # When expanding a specimen number, assume that any suffix
        # that looks like a range is one
        try:
            suffixes = expand_range(self.suffix, max_diff=max_diff)
        except ValueError:
            pass
        else:
            spec_nums = []
            for suffix in suffixes:
                spec_nums.append(self.modcopy(suffix=suffix))
            logger.debug("Interpreted suffix as range of suffixes")
            return spec_nums

        try:
            spec_nums = [
                parse_spec_num(s) for s in expand_range(str(self), max_diff=max_diff)
            ]
        except ValueError:
            pass
        else:
            return spec_nums

        start = self.number
        end = start[: -len(self.suffix)] + self.suffix
        try:
            rng = expand_range(start, end, max_diff=max_diff)
        except ValueError:
            pass
        else:
            spec_nums = []
            for val in rng:
                spec_num = parse_spec_num(val)
                spec_nums.append(
                    spec_num.modcopy(
                        code=self.code,
                        kind=self.kind,
                        prefix=self.prefix,
                    )
                )
            return spec_nums

        return [self]

    def is_valid(self, min_num=1, max_num=9999999, max_suffix=10000, max_diff=100):
        """Tests if a specimen number is valid

        Parameters
        ----------
        min_num : int
            the minimum valid catalog number value
        max_num : int
            the maximum valid catalog number value
        max_suffix : int
            the maximum valid suffix. Disregarded for alpha or
            alphanumeric suffixes.

        Returns
        -------
        bool
            True if specimen number is valid. Note that numbers with
            ranged suffixes evaluate as True even when they might represent
            suffixes.
        """
        # Invalid is number is below stipulated value
        if int(self) < min_num or int(self) > max_num:
            return False

        # Invalid if suffix is likely to be a separate number
        spec_nums = self.as_separate_numbers()
        if len(spec_nums) == 2 and (
            is_range(*spec_nums) or int(spec_nums[1]) >= max_suffix
        ):
            return False

        # Invalid if suffix is likely to be a range
        if is_range(self.suffix, max_diff=max_diff):
            return False

        return True

    def _str(self, delim=None, include_code=True, strip_leading_zeroes=False):
        """Writes the specimen number as text"""
        delim_prefix = ""
        if len(self.prefix) > 1:
            delim_prefix = " "

        if delim is None:
            delim = self.delim

        mask = "{} {}{}{}{}{}{}"
        return (
            mask.format(
                self.code if include_code else "",
                self.kind + " " if self.kind else "",
                self.prefix,
                delim_prefix,
                self.number,
                delim,
                self.suffix.lstrip("0") if strip_leading_zeroes else self.suffix,
            )
            .rstrip(delim)
            .strip()
        )

    def _sortable(self):
        """Returns a sortable version of the specimen number"""
        vals = []
        for val in re.split(r"(\d+)", self.key()):
            if val.isnumeric():
                val = val.zfill()


def is_spec_num(val, min_num=1, max_num=9999999, max_suffix=10000):
    """Tests if value is a valid specimen number"""
    try:
        return parse_spec_num(val).is_valid(
            min_num=min_num, max_num=max_num, max_suffix=max_suffix
        )
    except ValueError:
        return False


def parse_spec_num(val, fallback=False):
    """Parses a single well-formed specimen number"""
    if isinstance(val, SpecNum):
        return val
    orig = val
    if not re.match(r"^[A-Z]{3,4}", val):
        val = f"ZZZZ {val}"
    mask = (
        r"^(?:(?P<code>AMNH|FMNH|MCZ|NMNH|USNM|YPM|ZZZZ) )?"
        r"(?:(?P<kind>(?:loc\.|locality|slide|type) no\.) )?"
        r"(?P<prefix>(?:[A-Z]{1,4}))?[- ]?"
        r"(?P<number>\d+)"
        r"(?P<suffix>(?:(?:[\-\.,/ ](?:[A-Z0-9]+)(?:[-\.][A-Z0-9]+)*)|[A-Z](-?\d)?)?"
        r"(?: \((?:[A-Z:]+)\))?)$"
    )
    match = re.search(mask, val, flags=re.I)
    if match is None:
        if fallback:
            return parse_spec_num_fallback(val)
        raise ValueError(f"Could not parse {repr(orig)} (fallback=False)")
    kwargs = match.groupdict()
    if kwargs["code"] == "ZZZZ":
        kwargs["code"] = ""
    return SpecNum(**kwargs)


def parse_spec_num_fallback(val):
    """Parses a specimen number using a simple regular expression"""
    orig = val
    if not re.match(r"^[A-Z]{3,4}", val):
        val = f"ZZZZ {val}"
    mask = (
        r"^(?:(?P<code>AMNH|FMNH|MCZ|NMNH|USNM|YPM|ZZZZ) )?"
        r"(?:(?P<kind>(?:loc\.|locality|slide|type) no\.) )?"
        r"(?P<prefix>(?:[A-Z]{1,4}))?[- ]?"
        r"(?P<number>\d+)"
    )
    match = re.match(mask, val)
    if match is None:
        raise ValueError(f"Could not parse {repr(orig)} (fallback=True)")
    kwargs = match.groupdict()
    if kwargs["code"] == "ZZZZ":
        kwargs["code"] = ""
    kwargs["suffix"] = val.replace(match.group(), "").strip()
    return SpecNum(**kwargs)


def std_spec_num(val, strip_leading_zeroes=True, drop_zero_suffixes=False):
    """Standardizes specimen number

    To standardize, the value is uppercased and split into alphanumeric
    chunks. Leading zeroes and zeroes between letters and numbers are
    removed, hyphens are inserted between distinct groups of numbers. If
    a run of numbers consists entirely of zeroes (for example, "000" or
    "A00"), a single zero is retained.

    Parameters
    ----------
    val : str
        a specimen number

    Returns
    -------
    str
        standardized text version of the specimen number
    """
    parts = re.split(r"[^A-Z0-9]+", unidecode(str(val)).upper())
    vals = []
    for part in parts:

        clean = part

        # Strip leading zeroes
        if strip_leading_zeroes:
            clean = clean.lstrip("0")

        # Retain a single zero if no other numbers in part
        if part and not clean:
            clean = "0"

        # Remove zeroes between letter and numbers
        if strip_leading_zeroes:
            clean = re.sub(r"([A-Z])0+([1-9])", r"\1\2", clean)

        # Reduce runs of zeroes between letters or a letter and
        # the end of the value to a single 0
        clean = re.sub(r"([A-Z])0+([A-Z]|$)", r"\1_\2", clean).replace("_", "0")

        # Add hyphens between numbers
        if clean and vals and clean[0].isnumeric() and vals[-1][-1].isnumeric():
            vals.append("-")

        if clean:
            vals.append(clean)

    if drop_zero_suffixes and vals[-1] == "0":
        vals = vals[:-1]

    return "".join(vals).strip("-")


def sortable_spec_num(val, length=16):
    """Returns a sortable version of the specimen number

    Parameters
    ----------
    val : str
        a specimen number
    length : int
        number of digits to zfill numbers to

    Returns
    -------
    str
        sortable version of the standardized specimen number
    """
    return re.sub(r"(\d+)", lambda m: m.group().zfill(length), std_spec_num(val))


def is_range(start, end=None, max_diff=100, **kwargs):
    """Tests if given value is a range"""
    if isinstance(start, SpecNum):
        start = str(start)
    if isinstance(end, SpecNum):
        end = str(end)
    if end is None:
        try:
            start, end = re.split(r" *-+ *", start)
        except ValueError:
            return False
    if start.isalpha() and end.isalpha():
        return len(start) == len(end) == 1 and end > start
    else:
        kwargs["max_diff"] = max_diff
        kwargs.setdefault("match_empty_code", True)
        kwargs.setdefault("match_empty_prefix", True)

        vals = (start, end)
        try:
            start = parse_spec_num(start)
        except ValueError:
            logger.debug(f"Could not parse first number in {vals}")
            return False

        try:
            end = parse_spec_num(end)
        except ValueError:
            logger.debug(f"Could not parse second number in {vals}")
            return False

        return (
            start.is_similar_to(end, **kwargs)
            and int(end) > int(start)
            and (max_diff is None or int(end) - int(start) <= max_diff)
        )


def expand_range(start, end=None, max_diff=100):
    """Expands numeric or alpha ranges"""
    args = (start, end)
    if end is None:
        start, end = re.split(r" *-+ *", start)
    if not is_range(start, end, max_diff=max_diff):
        raise ValueError(f"Not a range: start={start}, end={end}")

    is_alpha = False
    if start.isalpha():
        is_alpha = True
        is_lower = start.islower()
        letters = " ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        start = str(letters.index(start.upper()))
        end = str(letters.index(end.upper()))

    start = parse_spec_num(start)
    end = parse_spec_num(end)

    expanded = []
    for num in range(int(start.number), int(end.number) + 1):
        expanded.append(str(start.modcopy(number=num)))

    if is_alpha:
        expanded = [letters[int(i)] for i in expanded]
        if is_lower:
            expanded = [s.lower() for s in expanded]

    logger.debug(f"Expanded {repr(args)} to {repr(expanded)}")

    return expanded
