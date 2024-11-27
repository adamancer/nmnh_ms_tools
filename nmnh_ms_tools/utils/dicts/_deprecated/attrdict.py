"""Defines dict where keys can be accessed as attributes"""

from .basedict import BaseDict
from ...utils import LazyAttr, get_attrs


class AttrDict(BaseDict):
    """Defines dict where keys can be accessed as attributes"""

    # Deferred class attributes are defined at the end of the file
    _reserved = {"keymap", "_coerce_dicts_to"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(
                f"{repr(self.__class__.__name__)} has no attribute {repr(attr)}"
            )

    def __setattr__(self, attr, val):
        if attr in dir(self.__class__):
            if attr.startswith("_"):
                raise AttributeErrr
        if attr in self._reserved or attr in dir(self):
            super().__setattr__(attr, val)
        self[attr] = val

    def __delattr__(self, attr):
        if attr in self._reserved:
            super().__delattr__(attr)
        del self[attr]
