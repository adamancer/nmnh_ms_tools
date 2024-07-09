"""Defines dict where keys can be accessed as attributes"""

import pprint as pp

from .basedict import BaseDict


class AttrDict(BaseDict):
    """Defines dict where keys can be accessed as attributes"""

    def __init__(self, *args, **kwargs):
        # Map values to a tuple if given as [(k1, v1)...]
        self._name = self.__class__.__name__
        self._keys = None
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            self._keys = tuple([a[0] for a in args])
        self._coerce_dicts_to = self.__class__
        super().__init__(*args, **kwargs)

    def __str__(self):
        return "{}({})".format(self._name, pp.pformat(self))

    def __getitem__(self, key):
        self._check_key(key)
        if self._keys is not None and isinstance(key, int):
            key = self._keys[key]
        return super().__getitem__(key)

    def __setitem__(self, key, val):
        self._check_key(key)
        if self._keys is not None and isinstance(key, int):
            key = self._keys[key]
        if key.startswith("_"):
            raise KeyError("Keys cannot start with _")
        super().__setitem__(key, val)

    def __delitem__(self, key):
        self._check_key(key)
        if self._keys is not None and isinstance(key, int):
            key = self._keys[key]
        super().__delitem__(key)

    def __getattr__(self, attr):
        try:
            return super().__getitem__(attr)
        except KeyError:
            raise AttributeError("{} not found".format(attr))

    def __setattr__(self, attr, val):
        """Routes set attribute to set item"""
        if not attr.startswith("_"):
            self[attr] = val
        else:
            super().__setattr__(attr, val)

    def _check_key(self, i):
        if isinstance(i, int) and not self._keys:
            raise IndexError("Indexes not supported if created from dict")
