"""Defines helper functions for working with strings"""

import functools
import re

import inflect
from unidecode import unidecode


def as_str(val, delim=" | "):
    """Returns a value as a string"""
    if isinstance(val, (bool, float, int)):
        return str(val)
    if not val:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        return delim.join([str(s) for s in val])
    return str(val)


def singular(val):
    """Converts string to singular

    Args:
        s (str): a string

    Returns:
        The singular form of the original string
    """
    inflected = inflect.engine().singular_noun(val)
    if inflected:
        return inflected
    return val


def plural(val):
    """Converts string to plural

    Args:
        s (str): a string

    Returns:
        The plural form of the original string
    """
    return inflect.engine().plural(singular(val))


def ucfirst(val, lower=False):
    """Capitalize first letter of string while leaving the rest alone

    Args:
        val (str): string to capitalize

    Returns:
        Capitalized string
    """
    if val == "":
        return val
    if lower:
        val = val.lower()
    chars = []
    for i, char in enumerate(val):
        if char.isalpha():
            return "".join(chars) + char.upper() + "".join(val[i + 1 :])
        if not char.isnumeric():
            chars.append(char)
        else:
            return val


def lcfirst(val):
    """Lowercase first letter of string while leaving the rest alone

    Args:
        val (str): string to capitalize

    Returns:
        Decapitalized string
    """
    if val.isupper():
        return val
    chars = []
    for i, char in enumerate(val):
        if char.isalpha():
            return "".join(chars) + char.lower() + "".join(val[i + 1 :])
        chars.append(char)
    return val


def capitalize(val):
    """Capitalizes a string, leaving all-caps strings alone"""
    if val.isupper():
        return val
    return val.capitalize()


def is_uncertain(val):
    """Checks if string indicates uncertainty"""
    return "?" in val


def add_article(val):
    """Prepend the appropriate indefinite article to a string

    Args:
        val (str): string to which to add a/an

    Returns:
        String with indefinite article prepended
    """
    if val == plural(val) or val.lower().startswith(("a ", "an ")):
        return val
    starts_with = re.compile(r"[aeiou]|[fhlmnrsx]{1,2}(\s|\d)", re.I)
    not_starts_with = re.compile(r"eu|i{1,3}[abcd]|iv[abcd]", re.I)
    if starts_with.match(val) and not not_starts_with.match(val):
        return f"an {val}"
    return f"a {val}"


def collapse_whitespace(val):
    return re.sub(r" +", " ", val).strip()


@functools.lru_cache()
def to_attribute(val):
    """Constructs a python attribute string from the given value"""
    val = unidecode(val)
    val = re.sub(r'["\']', "", val)
    val = re.sub(r"[^A-z\d]+", "_", val)
    val = re.sub(r"([A-Z])(?!(?:[A-Za-z_]|$))", r"_\1", val)
    val = re.sub(r"(?<![A-Z_])([A-Z])", r"_\1", val)
    val = re.sub(r"(?<![\d_])([\d])", r"_\1", val)
    val = re.sub(r"_+", "_", val)
    return val.lower().strip("_")


@functools.lru_cache()
def to_camel(val):
    """Constructs a camelCase string from the given value"""
    capped = "".join([ucfirst(w) for w in to_attribute(val).split("_")])
    return lcfirst(capped)


@functools.lru_cache()
def to_pascal(val):
    """Constructs a PascalCase string from the given value"""
    return ucfirst(to_camel(val))


def to_snake(val):
    """Constructs snake_case string from the given value"""
    return to_attribute(val)


@functools.lru_cache()
def to_dwc_camel(val):
    """Constructs a DwC case string from the given value"""
    return re.sub(r"Id$", "ID", to_camel(val))


@functools.lru_cache()
def to_slug(val, delim="-"):
    """Formats value for use as a dict key, url, or filename"""
    return to_attribute(val).replace("_", delim)


@functools.lru_cache()
def natsortable(val):
    return tuple(
        [int(p) if p.isnumeric() else p.lower() for p in re.split(r"(\d+)", val)]
    )


def to_pattern(val, mask=r"\b{}\b", subs=None, **kwargs):
    """Constructs a re pattern based on a string"""
    if subs is None:
        subs = {}
    val = re.escape(val).replace(r"\ ", " ").replace(r"\-", "-")
    for find, repl in subs.items():
        val = re.sub(find, repl, val)
    return re.compile(mask.format(val), **kwargs)


def same_to_length(*args, length=None, strict=False):
    """Tests if strings are the same to a minimum length"""
    assert len(args) > 1
    vals = [as_str(s).strip() for s in args]
    if length is None:
        length = min([len(s) for s in vals])
    vals = [s[:length] for s in vals]
    if not strict:
        vals = [s.lower() for s in vals]
    return len(set(vals)) == 1


def overlaps(val, other, min_length=3):
    """Tests whether two strings overlap"""
    for i in range(min_length, min([len(val), len(other)]) + 1):
        if val[-i:] == other[:i] or val[:i] == other[-i:]:
            return True
    return False


def std_case(val, std_to):
    """Standardizes casing of value to a reference string"""
    if std_to.isupper():
        return val.upper()
    if std_to.islower():
        return val.lower()
    while len(val) > len(std_to):
        std_to += std_to[-1]
    std = []
    for i, char in enumerate(std_to[: len(val)]):
        std.append(val[i].upper() if char.isupper() else val[i].lower())
    return "".join(std)


def to_digit(val, mask=r"\b({})\b"):
    """Converts string representations of numbers to digits"""
    nums = {mask.format(n): str(i) for i, n in enumerate(NUMS)}
    for pattern in sorted(nums, key=len, reverse=True):
        val = re.sub(pattern, nums[pattern], val, flags=re.I)
    return val


def truncate(val, length=32, suffix="..."):
    """Truncates a string to the given length"""
    if len(val) > length:
        return val[: length - len(suffix)] + suffix
    return val


def join_strings(*args: str, delim: str = None) -> str:
    """Joins strings using the specified delimiter

    Parameters
    ----------
    args : str
        strings to join
    delim : str, optional
        delim used to join strings. If omitted, the delimiter will be inferred by
        looking for common delimiters in each arg, falling back to a pipe if none
        found.

    Returns
    -------
    str
        strings joined by delimiter
    """
    if delim is None:
        for delim in "|;":
            for arg in args:
                if delim in arg:
                    break
        else:
            delim = "|"

    # Add spacing around delim
    delim = delim.strip() + " "
    if delim.starswith("|"):
        delim = " " + delim

    return delim.join([s.strip(delim) for s in args])


def seq_split(
    val: str,
    hard_delims: str = r"[;\|]",
    soft_delims: str = r"[,]",
    split_and: bool = True,
) -> list[str]:
    """Splits a string on hard, then soft delimiters if no hard delimiters found

    Parameters
    ----------
    hard_delims : str
        regex pattern with primary delimiters, like pipes, that are highly likely
        to be a delimiter
    soft_delims : str
        regex pattern with secondary delimiters, like commas, that may or may not
        be intended to delimit discrete items
    split_and : bool
        whether to split on "and"

    Returns
    -------
    list[str]
        parts of the original value
    """
    parts = re.split(hard_delims, val)
    if len(parts) == 1:
        parts = re.split(soft_delims, val)
    if split_and:
        parts_ = []
        for part in parts:
            parts_.extend(re.split(r"(?:^| +)(?:and|&) +", part.strip(), flags=re.I))
        return [s for s in parts_ if s]
    return parts


def _get_nums():
    """Gets of a list of numbers from 0-99"""
    nums = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    ]
    tens = [
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
    ]
    for ten in tens:
        nums.append(ten)
        for num in nums[1:10]:
            nums.append(f"{ten}-{num}")
    return nums


NUMS = _get_nums()
