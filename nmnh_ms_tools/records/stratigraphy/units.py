from .unit import StratUnit
from ..core import Record


class StratUnits(Record):

    def __init__(self, data, delim='-'):
        self.delim = delim
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ['name']
        # Explicitly define defaults for all reported attributes
        self.verbatim = ''
        self.units = []
        self.kind = ''
        # Initialize instance
        super(StratUnits, self).__init__(data)


    def __iter__(self):
        return iter(self.units)


    def parse(self, data):
        self.verbatim = data
        if not isinstance(data, list):
            data = [s.strip() for s in data.split(self.delim)]
        assert len(data) == 2
        self.units = [StratUnit(data[0]), StratUnit(data[1])]
