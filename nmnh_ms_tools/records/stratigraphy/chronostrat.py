"""Definds methods to work with chronostratigraphic names"""
import logging
import re

import numpy as np

from .helpers import CHRONOSTRAT_LEVELS
from .unit import StratUnit
from ..core import Record
from ...bots.adamancer import AdamancerBot
from ...utils.dicts import get_common_items



logger = logging.getLogger(__name__)




class ChronostratHierarchy(Record):
    """Defines methods for working with chronostratigraphic names"""
    bot = AdamancerBot()


    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.eonothem = ''
        self.erathem = ''
        self.system = ''
        self.series = ''
        self.stage = ''
        self.substage = ''
        self.interval = ''
        self.min_ma = np.nan
        self.max_ma = np.nan
        # Initialize instance
        super(ChronostratHierarchy, self).__init__(*args, **kwargs)
        # Define additional attributes
        self._geometry = None
        self.intervals = [getattr(self, k) for k in CHRONOSTRAT_LEVELS]


    def __str__(self):
        units = self.intervals
        if self.interval:
            units = [self.interval]
        return ' - '.join([str(u) if u else '' for u in units]).strip('- ')


    def __bool__(self):
        return any(self.intervals)


    @property
    def name(self):
        raise NotImplementedError('name')


    def parse(self, data):
        """Parses data from various sources to populate class"""
        if isinstance(data, (list, str)):
            self._parse_names(data)
        else:
            self._parse_dwc(data)


    def same_as(self, other, strict=True):
        """Tests if object is the same as another object"""
        for i, unit in enumerate(self.intervals):
            try:
                other_unit = other.intervals[i]
            except IndexError:
                return False
            if unit != other_unit:
                return False
        return True


    def similar_to(self, other):
        """Tests if object is similar to another object"""
        if not isinstance(other, self.__class__):
            try:
                other = self.__class__(other)
            except:
                logger.error('Undefined exception: ChronostratHierarchy.similar_to')
                return False
        for i, unit in enumerate(self.intervals):
            if unit != other.intervals[i]:
                return False
        return True


    def to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError('to_emu')


    def augment(self, **kwargs):
        """Searches Macrostrat for related units"""
        raise NotImplementedError('augment')


    def _parse_dwc(self, data):
        """Parses chronostratigraphic info from a Darwin Core record"""
        keys = [
            '{}EonOrLowestEonothem',
            '{}EraOrLowestErathem',
            '{}PeriodOrLowestSystem',
            '{}EpochOrLowestSeries',
            '{}AgeOrLowestStage'
        ]
        # Populated dicts for earliest and latest
        earliest = {}
        latest = {}
        for key in keys:
            attr = re.findall(r'[A-Z][a-z]+', key)[-1].lower()
            val = data.get(key.format('earliest'))
            if val:
                earliest[attr] = val
            val = data.get(key.format('latest'))
            if val:
                latest[attr] = val
        # Check if earliest and latest differ if both are populated
        if earliest and latest and earliest != latest:
            raise ValueError('Record contains a stratigraphic range')
        # Populate hierarchy from whichever keys are populated
        for attr, val in (earliest if earliest else latest).items():
            setattr(self, attr, StratUnit(val, hint=attr))


    def _parse_names(self, data):
        """Parses chronostratigraphic info from a name or list of names"""
        if not isinstance(data, list):
            data = [data]
        for name in data:
            response = self.bot.chronostrat(name)
            if response.get('success'):
                earliest = response['data']['earliest']
                latest = response['data'].get('latest', earliest)
                common = get_common_items(earliest, latest)
                for key, val in common.items():
                    if key in self.attributes:
                        setattr(self, key, val)
                self.max_ma = earliest['min_ma']
                self.min_ma = latest['max_ma']
                if common.get('source'):
                    self.sources.append(common.get('source'))
            break
