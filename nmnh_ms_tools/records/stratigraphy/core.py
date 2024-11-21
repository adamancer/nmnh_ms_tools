import numpy as np
from shapely.geometry import LineString, Point

from ..core import Record
from ...utils import mutable


class StratRecord(Record):
    def __init__(self, *args, **kwargs):
        with mutable(self):
            # Set lists of original class attributes and reported properties
            self._class_attrs = set(dir(self))
            self._properties = ["min_ma", "max_ma"]

            # Explicitly define defaults for all reported attributes
            self._min_ma = np.nan
            self._max_ma = np.nan
            self.age_geom = None

        # Initialize instance
        super().__init__(*args, **kwargs)

    @property
    def min_ma(self):
        return self._min_ma

    @min_ma.setter
    def min_ma(self, val):
        self._min_ma = val
        self._set_age_geom()

    @property
    def max_ma(self):
        return self._max_ma

    @max_ma.setter
    def max_ma(self, val):
        self._max_ma = val
        self._set_age_geom()

    def almost_equals(self, other, decimal=1):
        return self._shapely_op(other, "almost_equals", decimal=decimal)

    def contains(self, other):
        return self._shapely_op(other, "contains")

    def crosses(self, other):
        return self._shapely_op(other, "crosses")

    def disjoint(self, other):
        return self._shapely_op(other, "disjoint")

    def equals(self, other):
        return self._shapely_op(other, "equals")

    def intersection(self, other):
        return self._shapely_op(other, "intersection")

    def intersects(self, other):
        return self._shapely_op(other, "intersects")

    def overlaps(self, other):
        return self._shapely_op(other, "overlaps")

    def touches(self, other):
        return self._shapely_op(other, "touches")

    def within(self, other):
        return self._shapely_op(other, "within")

    def _shapely_op(self, other, op, *args, **kwargs):
        other = self.attune(other)
        return getattr(self.age_geom, op)(other.age_geom, *args, **kwargs)

    def pct_overlap(self, other, sort=True):
        """Calculates percent of shorter range encompassed by longer range"""
        ages = [self, self.attune(other)]
        if sort:
            ages.sort(key=lambda a: a.max_ma - a.min_ma)
        if ages[0].intersects(ages[1]):
            xtn = ages[0].intersection(ages[1])
            return xtn.length / ages[0].age_geom.length
        return 0

    def _set_age_geom(self):
        pts = [(n, 0) for n in (self.min_ma, self.max_ma) if not np.isnan(n)]
        if len(pts) == 1:
            self.age_geom = Point(pts)
        elif len(pts) == 2:
            self.age_geom = LineString(pts)
        else:
            self.age_geom = None
