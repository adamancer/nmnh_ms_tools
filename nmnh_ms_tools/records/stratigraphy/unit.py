"""Defines methods for parsing straigraphic units

FIXME: Handle ranges using "to"
FIXME: Handle uncertainty
"""
import re

from .helpers import (
    base_name,
    long_name,
    short_name,
    std_modifiers,
    CHRONOSTRAT_LEVELS,
    LITHOLOGIES,
    LITHOSTRAT_LEVELS,
    MODIFIERS
)
from ..core import Record
from ...bots.adamancer import AdamancerBot
from ...bots.macrostrat import MacrostratBot




class StratUnit(Record):
    chronobot = AdamancerBot()
    lithobot = MacrostratBot()


    def __init__(self, *args, hint=None, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = []
        # Explicitly define defaults for all reported attributes
        self.verbatim = ''
        self.unit = ''
        self.kind = ''
        self.level = ''
        self.lithology = ''
        self.modifier = ''
        # Define additional attributes required for parse
        self._hint = '[{}]'.format(hint.lower()) if hint else None
        # Initialize instance
        super(StratUnit, self).__init__(*args, **kwargs)


    def __str__(self):
        return self.long_name()


    def __bool__(self):
        return bool(self.unit or self.level or self.lithology)


    @property
    def name(self):
        return long_name(self.summarize())


    def parse(self, unit):
        """Parses data from various sources to populate class"""
        self.reset()
        self.verbatim = unit
        if unit in (None, '', 'Unknown'):
            return
        # Remove some less common abbreviations
        unit = unit.replace('Bd', 'Bed')
        unit = unit.replace('Grp', 'Gp')
        # Parse components of the unit name
        unit = std_modifiers(long_name(unit))
        self.modifier = self._parse_modifier(unit)
        self.level = self._parse_level(unit)
        self.lithology = self._parse_lithology(unit)
        self.unit = self._parse_name(unit)
        self.kind = self._parse_kind(unit)
        self.uncertain = self._parse_uncertainty(unit)
        # Apply hint if level could not be parsed
        if self._hint and not self.level:
            self.level = self._hint
        # Check if modified name is an official ICS unit (e.g., Early Jurrasic)
        self.check_name()


    def augment(self, **kwargs):
        """Searches for additional info about this unit"""
        if self.kind == 'lithostrat':
            return self.lithobot.get_units_by_name(self.unit.rstrip('?'))
        names = ['{} {}'.format(self.modifier, self.unit).strip(), self.unit]
        for name in names:
            name = name.rstrip('?')
            response =  self.chronobot.chronostrat(name, **kwargs)
            if response.get('success'):
                return response


    def long_name(self):
        """Returns the full name of the unit"""
        return long_name(self.summarize())


    def short_name(self):
        """Returns the abbreviated name of the unit"""
        return short_name(self.summarize())


    def same_as(self, other, strict=True):
        """Tests if unit is the same as another unit"""
        if not isinstance(other, self.__class__):
            return False
        return (self.unit == other.unit
                and self.level.strip('[]') == other.level.strip('[]')
                and self.lithology == other.lithology
                and self.modifier == other.modifier)


    def same_name_as(self, other):
        """Tests if two names are the same or very similar"""
        names = []
        for obj in (self, other):
            name = short_name(obj.unit)
            name = name.replace(' ', '')
            name = name.rstrip('s. ')
            names.append(name.lower())
        return names[0] == names[1]


    def similar_to(self, other):
        """Tests if units are similar"""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        same_as = self.same_as(other)
        same_name = self.same_name_as(other)
        same_level = self.level.strip('[]') == other.level.strip('[]')
        same_lith = (self.lithology == other.lithology
                     or bool(self.lithology) != bool(other.lithology))
        same_pos = self.modifier == other.modifier
        return same_as or (same_name and same_level and same_lith and same_pos)


    def _to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError('to_emu')


    def summarize(self):
        """Constructs a name from class attributes"""
        vals = self.to_dict()
        if vals['modifier'] and not (vals['unit'] or vals['lithology']):
            vals['unit'] = vals['modifier']
            vals['modifier'] = ''
        name = '{unit} {lithology} {level} ({modifier})'.format(**vals)
        return re.sub(r' +', ' ', name).replace('()', '').strip()


    def _parse_level(self, unit):
        """Parses level from unit name"""
        matches = []
        for val in LITHOSTRAT_LEVELS.values():
            match = re.search(r'\b{}\b'.format(val), unit, flags=re.I)
            if match:
                matches.append(match)
        if matches:
            matches.sort(key=lambda m: m.span()[0])
            return matches[-1].group(0).lower()
        return


    def _parse_lithology(self, unit):
        """Parses lithology type from unit name"""
        matches = []
        for val in LITHOLOGIES.values():
            match = re.search(r'\b{}\b'.format(val), unit, flags=re.I)
            if match:
                matches.append(match)
        if matches:
            matches.sort(key=lambda m: m.span()[0])
            return matches[-1].group(0).lower()
        return


    def _parse_modifier(self, unit):
        """Parses relative modifier (upper, lower, etc.) from unit name"""
        modifier = None
        # Define compound modifier
        mask = r'(?:{0})(?:(?: ?- ?| to | |/)(?:{0}))*'
        mods = mask.format('|'.join(MODIFIERS))
        # Leading modifiers (Early Jurassic
        pattern = r'^((?:{0}))(?: part of(?: the)?)?'.format(mods)
        result = re.search(pattern, unit, flags=re.I)
        if result is not None:
            modifier = result.group(1)
        # Parenthetical modifiers (Jurassic (Early))
        if not modifier:
            pattern = r'\(({})\)$'.format(mods)
            result = re.search(pattern, unit, flags=re.I)
            if result is not None:
                modifier = result.group(1)
        # Trailing modifiers (Jurassic, Early)
        if not modifier:
            pattern = r', ?({})$'.format(mods)
            result = re.search(pattern, unit, flags=re.I)
            if result is not None:
                modifier = result.group(1)
        return modifier


    def _parse_name(self, unit):
        """Parses base name from unit name"""
        if self.level:
            unit = re.sub(self.level, '', unit, flags=re.I)
        if self.lithology:
            unit = re.sub(self.lithology, '', unit, flags=re.I)
        # Try to strip the more complicated upper/lower stuff
        pattern = r'(\({0}\)|{0}( part of(the ?))?)'.format(self.modifier)
        unit = re.sub(pattern, '', unit, flags=re.I)
        return re.sub(r' +', ' ', unit).strip(', ')


    def _parse_kind(self, unit):
        """Determines whether unit is chrono- or lithostrat"""
        if self.level in LITHOSTRAT_LEVELS.values():
            return 'lithostrat'
        if self._hint is not None:
            hint = self._hint.strip('[]')
            if hint in LITHOSTRAT_LEVELS.values():
                return 'lithostrat'
            if hint in CHRONOSTRAT_LEVELS:
                return 'chronostrat'
        # Final try is to check names against known geologic ages
        if self.unit:
            response = self.chronobot.chronostrat(self.unit)
            if response.get('success'):
                return 'chronostrat'
        return


    def _parse_uncertainty(self, unit):
        """Looks for uncertainty modifiers in the unit name"""
        pattern = r'(\?$|prob(\.|ably)?)'
        if re.search(pattern, unit, flags=re.I):
            self.unit = re.sub(pattern, '', unit, flags=re.I)
            return True
        return False


    def check_name(self):
        """Checks if modified unit name is an official ICS unit"""
        if self.kind == 'chronostrat' and self.modifier:
            mods = re.split(r' ', self.modifier)
            mod_name = '{} {}'.format(mods[-1], self.unit)
            response = self.chronobot.chronostrat(mod_name)
            if response.get('success'):
                self.unit = mod_name
                mod = ''.join(self.modifier.rsplit(mods[-1], 1)).strip()
                self.modifier = mod


    def _sortable(self):
        """Returns a sortable version of the object"""
        return str(self)




def split_strat(val):
    """Splits string containing multiple units"""
    val = val.strip(' .')
    val = re.sub(' of ', ' of ', val.strip(' .'), flags=re.I)
    # Treat "of"-delimited lists as hierarchies
    try:
        child, parent = val.rsplit(' of ')
    except ValueError:
        pass
    else:
        return split_strat(child)
    # Standardize Lower/Early to make splitting easier
    val = std_modifiers(val)
    # Extract parentheticals
    parens = re.findall(r'(\(.*?\))', val)
    parens = [s for s in parens if s.lower().strip('()') not in MODIFIERS]
    for paren in parens:
        val = val.replace(paren, '')
    val = re.sub(r' +', ' ', val)
    parens = [s.strip('()') for s in parens]
    # Split ranges. Because hyphens can also be used as parent-child
    # delimiters, only two-unit ranges are currently parseable.
    vals = re.split(r'(?:[ -]to[ -]| ?- ?)', val, flags=re.I)
    if len(vals) != 2:
        # Select delimiters to use to split names
        delims = [';', '/', ',? and ', ',? & ', ',? or ', '-', '_', r'\+']
        pattern = r'(, ({0}))(/({0}))?'.format('|'.join(MODIFIERS))
        if not re.search(pattern, val, flags=re.I):
            delims.append(',')
        pattern = r'(?:{})'.format('|'.join(delims))
        vals = re.split(pattern, val, flags=re.I)
    return parens + [val.strip() for val in vals if val]


def parse_strat(val, hint=None):
    """Parses a string containing stratigraphic info"""
    # Convert names to units
    units = [StratUnit(val, hint=hint) for val in split_strat(val)]
    # Propagate properties of the last unit up the list if needed
    if units:
        last = units[-1]
        if last.kind and all([not u.kind for u in units[:-1]]):
            for unit in units[:-1]:
                unit.kind = last.kind
        if last.lithology and all([not u.lithology for u in units[:-1]]):
            for unit in units[:-1]:
                unit.lithology = last.lithology
        # Case: Early-Middle Jurassic
        if last.unit and all([not u.unit for u in units[:-1]]):
            for unit in units[:-1]:
                unit.unit = base_name(last.unit)
                unit.check_name()
    return units
