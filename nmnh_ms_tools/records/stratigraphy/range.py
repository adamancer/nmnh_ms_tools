from ..core import Record




class StratRange(Record):

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = []
        # Explicitly define defaults for all reported attributes
        self.units = []
        # Initialize instance
        super(StratRange, self).__init__(*args, **kwargs)


    @property
    def min_ma(self):
        return self.units[0].min_ma


    @property
    def max_ma(self):
        return self.units[-1].max_ma


    def parse(self, data):
        """Extracts bounding units from a list"""
        # Sort units from oldest to youngest
        units = sorted(data, key=lambda u: -u.max_ma)

        # Find most specific units
        for rank in units[0].ranks[::-1]:
            most_specific = [u for u in units if getattr(u, rank)]
            if most_specific:
                break

        # Test that all units are consistent with most specific units
        for unit in units:
            for attr in unit.ranks:
                val = getattr(unit, attr)
                if val and val not in [getattr(u, attr) for u in most_specific]:
                    raise ValueError(f'Units cannot be resolved: {units}')

        # Return the units bounding the range
        self.units = [most_specific[0], most_specific[-1]]


    def to_dwc(self):
        units = self.units[:]
        dwc = units[0].to_dwc('earliest')
        dwc.update(units[1].to_dwc('latest'))
        return dwc
