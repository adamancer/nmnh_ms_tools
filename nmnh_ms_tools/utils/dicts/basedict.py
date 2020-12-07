from ..lists import iterable




class BaseDict(dict):
    """Routes dict operations through class-specific item methods"""

    def __init__(self, *args, **kwargs):
        if not hasattr(self, '_coerce_dicts_to'):
            self._coerce_dicts_to = None
        self.update(*args, **kwargs)


    def __setitem__(self, key, val):
        """Coereces dictionaries when key is set"""
        super(BaseDict, self).__setitem__(key, self._coerce_dicts(val))


    def update(self, *args, **kwargs):
        """Explicitly routes update through class.__setitem__"""
        for key, val in dict(*args, **kwargs).items():
            self[key] = val


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
