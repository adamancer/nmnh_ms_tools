"""Defines functions to help using dicts"""
from ..lists import as_list, dedupe, iterable

from lxml import etree




def combine(*args):
    """Combines a list of dicts, retaining all unique values"""
    args = list(args)
    combined = {k: as_list(v) for k, v in args[0].items()}
    for other in args[1:]:
        for key, val in other.items():
            combined.setdefault(key, []).extend(as_list(val))
    return {k: dedupe(v) for k, v in combined.items()}


def get_all(dct, keys, required=True):
    """Returns list of values matching a set of keys"""
    if required:
        return [dct[k] for k in keys if dct[k]]
    return [dct[k] for k in keys if dct.get(k)]


def get_common_items(*args, keep_empty=False):
    """Returns dict with elements common to a list of dicts"""
    args = list(args)
    common = args[0]
    for other in args[1:]:
        for key, val in other.items():
            if key in common and common[key] != val:
                del common[key]
        for key in list(common):
            if key not in other:
                del common[key]
    if not keep_empty:
        common = {k: v for k, v in common.items() if v}
    return common


def get_first(dct, keys, required=True):
    """Returns first populated values matching an ordered list of keys"""
    for key in keys:
        try:
            val = dct[key]
            if val:
                return val
        except KeyError:
            pass
    if required:
        raise ValueError('No value found in any of {}'.format(keys))


def dictify(obj, cols=None, recurse=True):
    """Converts object with named attributes to a dict"""
    if isinstance(obj, dict):
        return obj
    test = obj[0] if (isinstance(obj, list) and obj) else obj
    if not (isinstance(test, tuple)
            or hasattr(test, '__table__')
            or hasattr(test, 'keys')):
                raise TypeError('Object cannot be converted to dict')
    if isinstance(obj, list):
        return [dictify(obj, cols=cols, recurse=recurse) for obj in obj]
    # Determine columns based on attributes
    if cols is None:
        try:
            # Complete SQLAlchemy objects carry a table attribute
            cols = [col.name for col in obj.__table__.columns]
        except AttributeError:
            # Partial SQLAlchemy objects have an attribute called keys
            try:
                cols = obj.keys()
            except AttributeError:
                # As a last resort, use list of non-callable public attributes
                cols = [c for c in dir(obj)
                        if not (c[0] == '_' or callable(getattr(obj, c)))]
    if not cols:
        raise TypeError('Object cannot be converted to dict')
    # Convert children to dictionaries as well
    if recurse:
        dct = {}
        for col in cols:
            try:
                dct[col] = dictify(getattr(obj, col), recurse=False)
            except TypeError:
                dct[col] = getattr(obj, col)
        return dct
    return {col: getattr(obj, col) for col in cols}


def prune(dct):
    """Recursively deletes empty keys from a dict"""
    keys = []
    for key, val in dct.items():
        if isinstance(val, dict):
            val = prune(val)
        if not val:
            keys.append(key)
    for key in keys:
        del dct[key]
    return dct


def recursive_cast(obj, clss):
    """Recursively converts children dicts to given class"""
    if isinstance(obj, dict):
        for key, val in obj.items():
            obj[key] = recursive_cast(val, clss)
        return clss(obj)
    elif iterable(obj):
        return obj.__class__([recursive_cast(val, clss) for val in obj])
    return obj
