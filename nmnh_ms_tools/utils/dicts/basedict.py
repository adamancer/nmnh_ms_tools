from ..lists import iterable


class BaseDict(dict):
    """Routes dict operations through class-specific item methods"""

    def __init__(self, *args, **kwargs):
        # Some subclasses will not want to coerce child dictionaries
        if not hasattr(self, "_coerce_dicts_to"):
            self._coerce_dicts_to = None
        # Child classes can set keymap to None to disable key formatting
        if not hasattr(self, "keymap"):
            self.keymap = {}
        self._deferred = {}
        self.update(*args, **kwargs)

    def __str__(self):
        if self.keymap is not None:
            return str(dict(self.items()))
        return super().__str__()

    def __repr__(self):
        if self.keymap is not None:
            return repr(dict(self.items()))
        return super().__repr__()

    def __setstate__(self, state):
        self.keymap = state["keymap"]
        self._coerce_dicts_to = state["_coerce_dicts_to"]
        self.update(self._deferred)
        self._deferred.clear()

    def __getitem__(self, key):
        return super().__getitem__(self.format_key(key))

    def __setitem__(self, key, val):
        """Coerces dictionaries when key is set"""
        try:
            if self.keymap is not None:
                formatted = self.format_key(key)
                self.keymap.setdefault(formatted, key)
                key = formatted
            super().__setitem__(key, self._coerce_dicts(val))
        except AttributeError:
            # Defer set item when loading with pickle, which does not set the
            # required attributes until after this method is called
            try:
                self._deferred[key] = val
            except AttributeError:
                self._deferred = {key: val}

    def __delitem__(self, key):
        if self.keymap is not None:
            key = self.format_key(key)
            del self.keymap[key]
        super().__delitem__(key)

    def __iter__(self):
        if self.keymap is not None:
            return iter(self.keymap.values())
        return super().__iter__()

    def __contains__(self, key):
        return super().__contains__(self.format_key(key))

    def format_key(self, key):
        return key

    def setdefault(self, key, default=None):
        """Explicitly route setdefault through class.__setitem__"""
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return self[key]

    def get(self, key, default=None):
        """Explicitly route get through class.__getitem__"""
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, *args):
        if self.keymap is not None:
            key = self.format_key(args[0])
            del self.keymap[key]
        return super().pop(key, *args)

    def update(self, *args, **kwargs):
        """Explicitly routes update through class.__setitem__"""
        for key, val in dict(*args, **kwargs).items():
            self[key] = val

    def items(self):
        for key, val in super().items():
            yield (self.keymap[key] if self.keymap is not None else key), val

    def keys(self):
        if self.keymap is not None:
            return dict(self.items()).keys()
        return super().keys()

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
