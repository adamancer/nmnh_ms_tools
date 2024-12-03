"""Defines dict where keys can be accessed as attributes"""

import pprint as pp

from .basedict import BaseDict


class StaticDict(BaseDict):
    """Defines dict where keys can be accessed as attributes"""

    def __init__(self, *args, **kwargs):
        # Map values to a tuple if given as [(k1, v1)...]
        self._name = self.__class__.__name__
        self._coerce_dicts_to = self.__class__
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f"{self._name}({pp.pformat(self)})"

    def __setitem__(self, key, val):
        try:
            self[key]
        except KeyError:
            super().__setitem__(key, val)
        else:
            raise KeyError(f"{repr(key)} already set")

    def __delitem__(self, key):
        raise KeyError(f"Cannot delete {repr(key)} from StaticDict")
