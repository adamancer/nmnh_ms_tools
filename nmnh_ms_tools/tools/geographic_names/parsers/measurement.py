"""Finds numbers and ranges with units"""
import re

from .core import Parser




class MeasurementParser(Parser):
    """Parses simple measurements"""
    kind = 'measurement'
    attributes = [
        'kind',
        'verbatim',
        'feature',
        'features'
    ]

    def __init__(self, *args, **kwargs):
        super(MeasurementParser, self).__init__(*args, **kwargs)
        self.specific = False


    def parse(self, val):
        """Parses a measurement with its unit"""
        self.verbatim = val.strip()
        if is_range(val):
            self.feature = val
            return self
        raise ValueError('Could not parse "{}"'.format(val))


    def name(self):
        """Returns a string describing the parsed locality"""
        return self.verbatim




def is_range(val):
    """Tests if value is a simple number or range"""
    pattern = (r'^(elev(\.|ation)? )?'
               r'\d+(\.\d+)?( ?(-|to|thro?ug?h?) ?\d+(\.\d+)?)? ?'
               r'[a-z]{2,3}\.?( (deep|depth|elev(\.|ation)|high))?$')
    return re.match(pattern, val, flags=re.I)
