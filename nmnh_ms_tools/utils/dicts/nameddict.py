"""Defines a namedtuple-style dict"""
from .attrdict import AttrDict


class NamedDict:
    """Defines a namedtuple-style dict"""

    def __init__(self, name, keys):
        assert all([isinstance(k, str) for k in keys])
        self._name = name
        self._keys = keys

    def __call__(self, *args):
        vals = list(args)
        if len(vals) == 1 and isinstance(vals[0], dict):
            assert set(vals[0].keys()) == set(self._keys)
            vals = vals[0]
        else:
            vals = list(zip(self._keys, vals))
        dct = AttrDict(vals)
        dct._name = self._name
        dct._keys = self._keys
        return dct


def nameddict(name, keys):
    """Creates a namedtuple-style NamedDict factory"""
    return NamedDict(name, keys)
