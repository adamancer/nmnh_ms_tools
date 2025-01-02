"""Defines the PrefixedNum class to parse simple prefixed numbers"""

import re
from functools import total_ordering

from .classes import custom_copy, custom_eq, del_immutable, mutable, set_immutable
from .strings import as_str


@total_ordering
class PrefixedNum:
    """Parses and supports simple arithmetic for prefixed numbers

    Parameters
    ----------
    val : str
        an identifier as a string

    Attributes
    ----------
    prefix : str
        an alphabetic prefix
    number : int
        a numeric identifier
    """

    def __init__(self, val=None):
        val = as_str(val)
        if re.search(r"^([A-z]+[- ]?)?\d+$", val):
            match = re.search(r"^[A-z]+[- ]?", val)
            self.prefix = match.group().rstrip("- ") if match else ""
            self.number = int(re.search(r"\d+$", val).group())
        elif val:
            raise ValueError(f"Invalid prefixed number: {val}")
        else:
            self.prefix = None
            self.number = None

    def __bool__(self):
        return bool(self.number)

    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return f"{self.prefix}{self.number}"

    def __repr__(self):
        return f"PrefixedNum(prefix={repr(self.prefix)}, number={self.number})"

    def __add__(self, other):
        """Adds value to number"""
        return self.__class__(f"{self.prefix}{self.number + other}")

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        """Substracts value from number"""
        return self.__class__(f"{self.prefix}{self.number - other}")

    def __isub__(self, other):
        return self - other

    def __eq__(self, other):
        return self.prefix == other.prefix and self.number == other.number

    def __lt__(self, other):
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        if self.prefix == other.prefix:
            return self.number < other.number
        return self.prefix < other.prefix

    def __setattr__(self, attr, val):
        set_immutable(self, attr, val)

    def __delattr__(self, attr):
        del_immutable(self, attr)

    def copy(self):
        """Creates a copy of the object"""
        return custom_copy(self)
