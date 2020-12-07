"""Defines dict where keys can be accessed as attributes"""
import pprint as pp

from .basedict import BaseDict




class StaticDict(BaseDict):
    """Defines dict where keys can be accessed as attributes"""

    def __init__(self, *args, **kwargs):
        # Map values to a tuple if given as [(k1, v1)...]
        self._name = self.__class__.__name__
        self._coerce_dicts_to = self.__class__
        super(StaticDict, self).__init__(*args, **kwargs)


    def __str__(self):
        return '{}({})'.format(self._name, pp.pformat(self))


    def __setitem__(self, key, val):
        try:
            self[key]
        except KeyError:
            super(StaticDict, self).__setitem__(key, val)
        else:
            raise KeyError('{} already set'.format(key))


    def __delitem__(self, key):
        raise KeyError('Cannot delete key from StaticDict')
