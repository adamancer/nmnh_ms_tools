from ..lists import iterable


class BaseDict(dict):
    """Routes dict operations through class-specific item methods"""

    def __init__(self, *args, **kwargs):
        if not hasattr(self, "_coerce_dicts_to"):
            self._coerce_dicts_to = None
        self.keymap = {}
        self.update(*args, **kwargs)

    def __getitem__(self, key):
        return super().__getitem__(self.format_key(key))

    def __setitem__(self, key, val):
        """Coerces dictionaries when key is set"""
        formatted = self.format_key(key)
        self.keymap.setdefault(formatted, key)
        super().__setitem__(formatted, self._coerce_dicts(val))

    def __delitem__(self, key):
        super().__delitem__(self.format_key(key))

    def get(self, key, default=None):
        """Explicitly route get through class.__getitem__"""
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *args):
        return super().pop(self.format_key(key), *args)

    def update(self, *args, **kwargs):
        """Explicitly routes update through class.__setitem__"""
        for key, val in dict(*args, **kwargs).items():
            self[key] = val

    def format_key(self, key):
        return key

    def to_dict(self):
        """Converts BaseDict to dict"""

        def _recurse(obj):
            if isinstance(obj, dict):
                dct = {}
                for key, val in obj.items():
                    dct[key] = _recurse(val)
                return dct
            elif isinstance(obj, list):
                lst = []
                for val in obj:
                    lst.append(_recurse(val))
                return lst
            return obj

        return _recurse(self)

    def _coerce_dicts(self, val):
        """Coerces dicts within value to specified class"""
        if self._coerce_dicts_to is None:
            return val
        # Coerce any iterable that is not already the proper class
        if iterable(val) and not isinstance(val, self._coerce_dicts_to):
            if isinstance(val, dict):
                return self._coerce_dicts_to(val)
            else:
                return val.__class__([self._coerce_dicts(v) for v in val])
        return val
