"""Defines helper functions for working with lists"""

from collections import Counter
from collections.abc import Iterable, KeysView, ValuesView

import pandas as pd
import six


def as_list(val, delims="|;"):
    """Returns a value as a list"""
    if isinstance(val, (bool, float, int, pd.DataFrame, pd.Series)):
        return [val]
    if not val:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        if delims:
            for delim in delims:
                vals = [s.strip() for s in val.split(delim)]
                if len(vals) > 1:
                    return vals
        return [val]
    if isinstance(val, (set, tuple, KeysView, ValuesView)):
        return list(val)
    # Fall back to a single-item list
    return [val]


def as_set(val, delims="|;"):
    """Returns a value as a set"""
    return val if isinstance(val, set) else set(as_list(val, delims))


def as_tuple(val, delims="|;"):
    return tuple(as_list(val, delims=delims))


def dedupe(lst: list, lower: bool = True) -> list:
    """Dedupes a list while maintaining order and case

    Parameters
    ----------
    lst : list
        list of values to dedupe
    lower : bool, default=True
        whether to convert strings to lowercase when deduping

    Returns
    -------
    list
        Deduplicated copy of the original list
    """
    prep = lambda v: v.casefold() if lower and isinstance(v, str) else v
    try:
        dct = {}
        for val in lst:
            dct.setdefault(prep(val), val)
        return list(dct.values())
    except TypeError:
        # Fallback for non-hashable list items
        lst_ = [prep(v) for v in lst]
        return [val for i, val in enumerate(lst) if prep(val) not in lst_[:i]]


def oxford_comma(lst, lowercase=False, delim=", ", conj="and"):
    """Formats list as comma-delimited string

    Args:
        lst (list): list of strings
        lowercase (bool): if true, convert the first letter in each value
            in the list to lowercase

    Returns:
        Comma-delimited string
    """
    lst = [s.strip() for s in lst if s.strip()]
    if lowercase:
        lst = [s[0].upper() + s[1:] for s in lst]
    if len(lst) <= 1:
        return "".join(lst)
    if len(lst) == 2:
        return (" " + conj.strip() + " " if conj else delim).join(lst)
    last = lst.pop()
    return delim.join(lst) + delim + conj + " " + last


def most_common(lst):
    """Finds the most common element in a list

    From https://stackoverflow.com/a/20872750
    """
    data = Counter(lst)
    return max(lst, key=data.get)


def iterable(val):
    return isinstance(val, Iterable) and not isinstance(val, six.string_types)
