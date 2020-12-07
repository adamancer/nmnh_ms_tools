"""Defines helper functions for working with lists"""
import six
from collections import Counter
from collections.abc import Iterable




def as_list(val, delims='|;'):
    """Returns a value as a list"""
    if isinstance(val, (bool, float, int)):
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
    if isinstance(val, (set, tuple)):
        return list(val)
    raise TypeError('Cannot coerce {} to list'.format(type(val)))


def as_set(val, delims='|;'):
    """Returns a value as a set"""
    return val if isinstance(val, set) else set(as_list(val, delims))


def dedupe(lst, lower=True):
    """Dedupes a list while maintaining order and case

    Args:
        list (list): a list of strings

    Returns:
        Deduplicated copy of the original list
    """
    prep = lambda v: v.lower() if lower and isinstance(v, str) else v
    lst_ = [prep(v) for v in lst]
    return [val for i, val in enumerate(lst) if not prep(val) in lst_[:i]]



def oxford_comma(lst, lowercase=False, delim=', ', conj='and'):
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
        return ''.join(lst)
    if len(lst) == 2:
        return ' {} '.format(conj).join(lst)
    last = lst.pop()
    return delim.join(lst) + delim + conj + ' ' + last


def most_common(lst):
    """Finds the most common element in a list

    From https://stackoverflow.com/a/20872750
    """
    data = Counter(lst)
    return max(lst, key=data.get)


def iterable(val):
    return isinstance(val, Iterable) and not isinstance(val, six.string_types)
