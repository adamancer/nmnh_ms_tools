"""Defines dict where keys can be accessed as attributes"""
import pprint as pp

from .basedict import BaseDict




class IndexedDict(BaseDict):
    """Defines dict where values are under a three-character index"""

    def __init__(self, *args, **kwargs):
        self.length = 3
        super().__init__(*args, **kwargs)


    def __getitem__(self, key):
        return super().__getitem__(self._key(key))[key]


    def __setitem__(self, key, val):
        idx = self._key(key)
        if (key == idx
            and isinstance(val, dict)
            and self._key(list(val.keys())[0]) == idx):
                super().__setitem__(key, val)
        else:
            super().setdefault(idx, {})[key] = val


    def __delitem__(self, key):
        idx = self._key(key)
        del super().__getitem__(idx)[key]
        if not super().__getitem__(idx):
            super().__delitem__(idx)


    def _key(self, val):
        return str(val)[:self.length].zfill(self.length)


    def update(self, *args, **kwargs):
        """Checks if dict is indexed then updates"""
        indexed = True
        for key, val in dict(*args, **kwargs).items():
            if len(key) != self.length or not isinstance(val, dict):
                indexed = False
                break
        for key, val in dict(*args, **kwargs).items():
            if indexed:
                super().__setitem__(key, val)
            else:
                self[key] = val
