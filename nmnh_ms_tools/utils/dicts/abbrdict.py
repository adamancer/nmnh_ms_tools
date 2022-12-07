"""Defines dict where key lookups check for possible abbreviations"""
from unidecode import unidecode

from .basedict import BaseDict


class AbbrDict(BaseDict):
    """Defines dict where values"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Compile a list of the abbreviations in the dict
        abbreviations = {}
        for abbrs in self.values():
            for abbr, langs in abbrs:
                abbreviations.setdefault(abbr, []).extend(langs)
        self._abbreviations = {k: list(set(v)) for k, v in abbreviations.items()}

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            pass

        orig = key

        # Search for stem- variants
        key += "-"
        while key.rstrip("-"):
            try:
                return super().__getitem__(key)
            except KeyError:
                key = f"{key.rstrip('-')[:-1]}-"

        raise KeyError(f"'{orig}' not found")

    def is_abbreviation(self, val):
        if isinstance(val, (list, tuple)):
            for val in val:
                if not self.is_abbreviation(val):
                    return False
            return True
        return unidecode(val.lower()) in self._abbreviations
