from ..lists import iterable


class BaseDict(dict):
    """Routes dict operations through class-specific item methods"""

    def __init__(self, *args, **kwargs):
        # Some subclasses will not want to coerce child dictionaries
        if not hasattr(self, "_coerce_dicts_to"):
            self._coerce_dicts_to = None
        self._keymap = {}
        self.update(*args, **kwargs)

    def __setstate__(self, state):
        self._keymap = state["_keymap"]
        self._coerce_dicts_to = state["_coerce_dicts_to"]
        self.update(self._deferred)
        del self._deferred

    def __getitem__(self, key):
        return super().__getitem__(self.format_key(key))

    def __setitem__(self, key, val):
        """Coerces dictionaries when key is set"""
        try:
            formatted = self.format_key(key)
            self._keymap.setdefault(formatted, key)
            super().__setitem__(formatted, self._coerce_dicts(val))
        except AttributeError:
            # Defer set item when loading with pickle, which does not set the
            # required attributes until after this method is called
            try:
                self._deferred[key] = val
            except AttributeError:
                self._deferred = {key: val}

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
