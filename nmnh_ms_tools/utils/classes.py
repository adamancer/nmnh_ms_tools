"""Defines methods used across internal classes"""

import logging
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Callable
from typing import Any

import pandas as pd
from shapely.geometry.base import BaseGeometry

from .files import read_csv, read_json, read_tsv, read_yaml

logger = logging.getLogger(__name__)


class LazyAttr:
    """Lazily loads data upon first access to a class attribute

    Parameters
    ----------
    obj : Any
        the object
    attr : str
        the name of the attribute
    action : callable | path
        the function used to load data or a path that can be read using a standard
        method (currently CSV, TSV, or JSON)
    args, kwargs:
        arguments and keyword arguments to pass to func
    """

    def __init__(self, obj: Any, attr: str, action: Callable | Path, *args, **kwargs):
        self._lazyobj = obj
        self._lazyattr = attr
        self._lazyargs = args
        self._lazykwargs = kwargs
        self._lazycached = None

        # Infer function for simple file reads
        if not callable(action):
            try:
                path = Path(action)
                action = {
                    ".csv": read_csv,
                    ".json": read_json,
                    ".tsv": read_tsv,
                    ".yaml": read_yaml,
                    ".yml": read_yaml,
                }[path.suffix.lower()]
            except (IndexError, KeyError):
                raise ValueError("Could not infer function from arguments")
            else:
                # Update args to include path
                self._lazyargs = [path] + list(args)

        self._lazyfunc = action

        # Assign self to attribute. This is to avoid having to specify the attribute
        # both here and during assignment.
        try:
            val = getattr(self._lazyobj, self._lazyattr)
        except AttributeError:
            _lazyobj = str(self._lazyobj)[8:].rstrip("'> ")
            raise AttributeError(
                f"Tried to lazy load an attribute that was not defined: {_lazyobj}.{self._lazyattr}"
            )
        else:
            if val is not None:
                _lazyobj = str(self._lazyobj)[8:].rstrip("'> ")
                raise AttributeError(
                    f"Tried to lazy load an attribute that is already populated: {_lazyobj}.{self._lazyattr}"
                )
            setattr(self._lazyobj, self._lazyattr, self)

    def __call__(self, *args, **kwargs):
        return self.lazyload("__call__")(*args, **kwargs)

    def __getattr__(self, attr):
        return getattr(self.lazyload("__getattr__"), attr)

    def __setattr__(self, attr, val):
        if attr in {
            "_lazyobj",
            "_lazyattr",
            "_lazyfunc",
            "_lazyargs",
            "_lazykwargs",
            "_lazycached",
        }:
            super().__setattr__(attr, val)
        else:
            return setattr(self.lazyload("__setattr__"), attr, val)

    def __delattr__(self, attr):
        delattr(self.lazyload("__delattr__"), attr)

    def __getitem__(self, key):
        return self.lazyload("__getitem__")[key]

    def __setitem__(self, key, val):
        self.lazyload("__setitem__")[key] = val

    def __deltitem__(self, key):
        del self.lazyload("__delitem__")[key]

    def __contains__(self, val):
        return val in self.lazyload("__contains__")

    def __iter__(self):
        return iter(self.lazyload("__iter__"))

    def __bool__(self):
        return bool(self.lazyload("__bool__"))

    def __float__(self):
        return float(self.lazyload("__float__"))

    def __int__(self):
        return int(self.lazyload("__int__"))

    def __str__(self):
        return str(self.lazyload("__str__"))

    def __repr__(self):
        return repr(self.lazyload("__repr__"))

    def lazyload(self, src):
        """Lazy loads data using function and sets the associated attribute"""

        # HACK: Cache result of lazyload. Some ipython processes result in the
        # lazy-loaded attributes not being updated as expect. This caches
        # the result so that the action is only run once even when this happens.
        if self._lazycached is None:
            logger.debug(
                f"Setting {self._lazyobj.__name__}.{self._lazyattr} ="
                f" {self._lazyfunc.__name__}(args={self._lazyargs},"
                f" kwargs={self._lazykwargs}) (triggered from {src})"
            )
            self._lazycached = self._lazyfunc(*self._lazyargs, **self._lazykwargs)

        setattr(self._lazyobj, self._lazyattr, self._lazycached)
        return getattr(self._lazyobj, self._lazyattr)


def get_attrs(inst: Any) -> set:
    """Gets the list of instance attributes, excluding class attributes

    Parameters
    ----------
    inst : Any
        a Python object

    Returns
    -------
    set
        instance attributes
    """
    return set(dir(inst)) - set(dir(inst.__class__))


def str_class(inst: Any, attributes: list = None) -> str:
    """Provides a human-readable depiction of the class as a string

    Parameters
    ----------
    inst : Any
        a Python object
    attributes : list
        a list of attributes to include. Defaults to attributes attribute if None.

    Returns
    -------
    str
        depiction of instance
    """
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
    return "\n".join([f"{a.ljust(maxlen)}: {v}" for a, v in rows])


def repr_class(inst: Any, attributes: list[str] = None) -> str:
    """Provides a compact depiction of the class as a string

    Parameters
    ----------
    inst : Any
        a Python object
    attributes : list
        a list of attributes to include. Defaults to attributes attribute if None.

    Returns
    -------
    str
        compact depiction of instance
    """
    if attributes is None:
        attributes = inst.attributes
    attrs = [f"{a}={repr(getattr(inst, a))}" for a in attributes]
    return f"{inst.__class__.__name__}({", ".join(attrs)})"


def custom_copy(inst: Any) -> Any:
    """Convenience function to copy all attributes of a class

    It must be possible to create an empty class based on the instance for this to work.

    Parameters
    ----------
    inst : Any
        a Python object

    Returns
    -------
    object
        a copy of the original object
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


def custom_eq(inst: Any, other: Any, coerce: bool = False, ignore: list = None) -> bool:
    """Convenience function to compare instance to another object

    Parameters
    ----------
    inst : Any
        a Python object
    other : Any
        a Python object
    coerce : bool
        whether to try to coerce other if it is not the same type as inst
    ignore :

    Returns
    -------
    bool
        whether the objects are the same
    """
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
            try:
                if not inst_val.equals(other_val):
                    return False
            except Exception as exc:
                raise Exception("Could not compare {inst_val} and {other_val}") from exc
        elif inst_val != other_val:
            return False
    return True


def set_immutable(inst: Any, attr: str, val: Any, cls: type = None):
    """Convenience function to make a custom class immutable

    Note that any data type that can be modified in place (like list or dict) is
    not immutable.

    Parameters
    ----------
    inst : Any
        a Python object
    attr : str
        an attribute
    val :
        the value to which to set the attribute
    cls : class
        a Python class

    Returns
    -------
    None
    """
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
            raise AttributeError(
                f"Cannot modify immutable attribute {repr(attr)} on {inst.__class__.__name__} object"
            )


def del_immutable(inst: Any, attr: str, cls: type = None):
    """Raises an error when trying to delete an immutable attribute

    Parameters
    ----------
    inst : Any
        an object
    attr : str
        an attribute name
    cls : class
        a Python class

    Raises
    ------
    AttributeError
    """
    if cls is None:
        cls = inst.__class__
    if attr != "_mutable":
        raise AttributeError(
            f"Cannot delete immutable attribute {repr(attr)} from {inst.__class__.__name__} object"
        )
    super(cls, inst).__delattr__(attr)


@contextmanager
def mutable(inst):
    """Context manager allowing nominally immutable classes to be modified"""
    inst._mutable = True
    try:
        yield inst
    finally:
        del inst._mutable
