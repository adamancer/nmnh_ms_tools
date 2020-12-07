from .core import Parser

class UncertainParser(Parser):
    """Defines wrapper for uncertain strings"""

    def __init__(self, parsed):
        self.verbatim = parsed.verbatim + '?'
        self.kind = 'uncertain'
        self._parsed = parsed


    def __getattr__(self, attr):
        return getattr(self._parsed, attr)


    def __str__(self):
        return self.verbatim
