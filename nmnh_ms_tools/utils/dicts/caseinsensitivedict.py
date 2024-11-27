"""Defines dict where keys can be accessed as attributes"""

from .basedict import BaseDict


class CaseInsentiveDict(BaseDict):
    """Defines dict where keys can be accessed as attributes"""

    def format_key(self, key):
        return key.casefold()
