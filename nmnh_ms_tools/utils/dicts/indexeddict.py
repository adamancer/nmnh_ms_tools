"""Defines dict where keys can be accessed as attributes"""

from collections import namedtuple

from .basedict import BaseDict


Index = namedtuple("Index", ["index"])


class Index:

    def __init__(self, val, length=3):
        self.index = str(val)[:length].zfill(length)

    def __hash__(self):
        return hash(self.index)

    def __str__(self):
        return str(self.index)

    def __repr__(self):
        return repr(self.index)

    def __len__(self):
        return len(self.index)

    def __eq__(self, other):
        return self.index == other or self.index == other.index


class IndexedDict(BaseDict):
    """Defines dict where values are under a three-character index"""

    def __init__(self, *args, **kwargs):
        self.keymap = None
        self.length = 3
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        if isinstance(key, Index):
            return super().__getitem__(key)
        return super().__getitem__(Index(key, self.length))[key]

    def __setitem__(self, key, val):
        if isinstance(key, Index):
            super().__setitem__(key, val)
        else:
            super().setdefault(Index(key, self.length), {})[key] = val

    def __delitem__(self, key):
        if isinstance(key, Index):
            super().__delitem__(key)
        else:
            idx = Index(key, self.length)
            del super().__getitem__(idx)[key]
            if not super().__getitem__(idx):
                super().__delitem__(idx)

    def update(self, *args, **kwargs):
        """Checks if dict is indexed then updates"""
        indexed = True
        for key, val in dict(*args, **kwargs).items():
            if len(key) != self.length or not isinstance(val, dict):
                indexed = False
                break
        for key, val in dict(*args, **kwargs).items():
            if indexed:
                # Manually index the key so that setitem knows how to map it
                super().__setitem__(Index(key, self.length), val)
            else:
                self[key] = val
