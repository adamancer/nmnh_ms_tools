"""Defines methods used across internal classes"""

from contextlib import contextmanager

import pandas as pd
from shapely.geometry.base import BaseGeometry


def get_attrs(inst):
    return set(dir(inst)) - set(dir(inst.__class__))


def str_class(inst, attributes=None):
    """Convenience function to depict a class as a string"""
    if attributes is None:
        attributes = inst.attributes
    rows = [("class", inst.__class__.__name__)]
    for attr in attributes:
        val = getattr(inst, attr)
        if val or val == 0:
            if not isinstance(val, list):
                val = [val]
            for val in val:
                rows.append((attr, val))
                attr = ""
    maxlen = max([len(row[0]) for row in rows])
    return "\n".join(["{}: {}".format(a.ljust(maxlen), v) for a, v in rows])


def repr_class(inst, attributes=None):
    """Convenience function to represent major attributes of a class"""
    if attributes is None:
        attributes = inst.attributes
    attrs = ["{}={}".format(a, getattr(inst, a)) for a in attributes]
    return "{}({})".format(inst.__class__.__name__, ", ".join(attrs))


def custom_copy(inst):
    """Convenience function to copy all attributes of a class

    It must be possibly to create an empty class for this to work.
    """
    obj = inst.__class__()
    with mutable(obj):
        for attr in get_attrs(inst):
            val = getattr(inst, attr)
            if not callable(val):
                try:
                    val = val.copy()
                except AttributeError:
                    pass
                setattr(obj, attr, val)
    return obj


def custom_eq(inst, other, coerce=False, ignore=None):
    """Convenience function to compare instance to another object"""
    if not isinstance(other, inst.__class__):
        if coerce:
            try:
                other = inst.__class__(other)
            except ValueError:
                return False
        else:
            return False
    inst_attrs = get_attrs(inst)
    other_attrs = get_attrs(other)
    # Ignore specified attributes. This is primarily used to skip writable attributes
    # in otherwise immutable objects.
    if ignore:
        inst_attrs = [a for a in inst_attrs if a not in ignore]
        other_attrs = [a for a in other_attrs if a not in ignore]
    if inst_attrs != other_attrs:
        return False
    for attr in inst_attrs:
        inst_val = getattr(inst, attr)
        other_val = getattr(other, attr)
        if isinstance(inst_val, (BaseGeometry, pd.Series, pd.DataFrame)):
            if not inst_val.equals(other_val):
                return False
        elif inst_val != other_val:
            return False
    return True


def set_immutable(inst, attr, val, cls=None):
    if cls is None:
        cls = inst.__class__
    if (
        hasattr(inst, "_mutable")
        or hasattr(inst, "_writable")
        and attr in inst._writable
    ):
        super(cls, inst).__setattr__(attr, val)
    else:
        try:
            getattr(inst, attr)
        except AttributeError:
            super(cls, inst).__setattr__(attr, val)
        else:
            raise AttributeError(f"Cannot modify existing attribute: {repr(attr)}")


@contextmanager
def mutable(inst):
    inst._mutable = True
    try:
        yield inst
    finally:
        del inst._mutable
