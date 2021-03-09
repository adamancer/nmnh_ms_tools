"""Defines methods for parsing, comparing, and representing names"""
import re

from collections import namedtuple
from nameparser import HumanName

from .core import Record, Records
from ..utils.standardizers import Standardizer
from ..utils.lists import oxford_comma
from ..utils.strings import lcfirst, same_to_length




SimpleName = namedtuple('SimpleName', ['last', 'first', 'middle'])
PREFIXES = sorted([
    'da',
    'de',
    'de la',
    'den',
    'do',
    'du',
    'st',
    'van',
    'van der',
    'von'
], key=len, reverse=True)
SUFFIXES = ['Jr', 'Sr', 'II', 'III', 'IV', 'Esq']




class Person(Record):
    """Defines methods for parsing and manipulating names"""
    terms = [
        'title',
        'first',
        'middle',
        'last',
        'suffix'
    ]
    std = Standardizer(minlen=1)

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.title = ''
        self.first = ''
        self.middle = ''
        self.last = ''
        self.suffix = ''
        self.organization = ''
        # Initialize instance
        super(Person, self).__init__(*args, **kwargs)


    def __str__(self):
        return self.name


    @property
    def name(self):
        return self.summarize()


    @property
    def first_initial(self):
        return self.first[0] if self.first else ''


    def parse(self, data):
        """Parses data from various sources to populate class"""
        self.reset()
        if isinstance(data, str):
            self._parse_name(data)
        elif 'NamLast' in data:
            self._parse_emu(data)
        elif 'last' in data:
            self._parse(data)
        else:
            raise ValueError('Could not parse {}'.format(data))


    def same_as(self, other, strict=True):
        """Compares name to another name"""
        try:
            assert isinstance(other, self.__class__)
        except AssertionError:
            return False
        if self.organization and self.organization == other.organization:
            return True
        names = []
        for name in [self, other]:
            first = self.std_name(name.first)
            last = self.std_name(name.last)
            middle = self.std_name(name.middle)
            names.append(SimpleName(last, first, middle))
        name, other = names
        # Force strict match on short last names
        if strict or min([len(n[0]) for n in names]) <= 3:
            # If strict, C. Darwin != Charles Darwin
            same_last = name.last == other.last
            same_first = name.first == other.first
            same_middle = name.middle == other.middle
        else:
            # If not strict, C. R. Darwin == Charles Darwin and
            # Char. Darwin == Charles Darwin, but
            # Christopher Darwin != Charles Darwin
            same_last = name.last == other.last
            same_first = same_to_length(name.first, other.first)
            same_middle = same_to_length(name.middle, other.middle)
        return same_last and same_first and same_middle


    def reset(self):
        """Resets all attributes to defaults"""
        self.verbatim = None
        self.title = None
        self.first = None
        self.middle = None
        self.last = None
        self.suffix = None
        self.organization = None


    def summarize(self, mask='{title} {first} {middle} {last}, {suffix}',
                  initials=False):
        """Converts name to a string"""
        if self.organization:
            return self.organization
        title = self.title if self.title else ''
        first = self.first if self.first else ''
        middle = self.middle if self.middle else ''
        suffix = self.suffix if self.suffix else ''
        if len(first) == 1 or (initials and first):
            first = first[0] + '.'
        if (len(middle) == 1
            or (initials
                and middle
                and not (' ' in middle or middle.count('.') > 1))):
            middle = middle[0] + '.'
        name = mask.format(title=title,
                           first=first,
                           middle=middle,
                           last=self.last,
                           suffix=suffix)
        name = re.sub(r' +', ' ', name)
        name = re.sub(r'\.[^ ]', '. ', name)
        name = name.strip(' ,')
        return name


    def initials(self, delim='. '):
        """Returns initials"""
        initials = [s[0] for s in [self.first, self.middle, self.last] if s]
        return delim.join(initials)


    def std_name(self, name):
        """Standardizes name for comparisons"""
        try:
            return self.std.std(name)
        except ValueError:
            return name


    def _to_emu(self):
        """Formats record for EMu eparties module"""
        rec = {
            'NamPartyType': 'Person',
            'NamTitle': self.title,
            'NamFirst': self.first,
            'NamMiddle': self.middle,
            'NamLast': self.last,
            'NamSuffix': self.suffix
        }
        return rec


    def _parse_emu(self, rec):
        """Parses an EMu eparties record"""
        self.verbatim = rec
        if rec('NamOrganisation'):
            self.organization = rec('NamOrganisation')
        else:
            self.title = rec('NamTitle')
            self.first = rec('NamFirst')
            self.middle = rec('NamMiddle')
            self.last = rec('NamLast')
            self.suffix = rec('NamSuffix')


    def _parse_name(self, name):
        """Parses a name using the nameparser module"""
        self.verbatim = re.sub(r'\s+', ' ', name)
        name = name.strip()
        # Check if name appears to be an organization
        org_words = {
            'bureau',
            'college',
            'council',
            'institution',
            'museum',
            'society',
            'university'
        }
        words = set(re.split(r'(\W+)', name.lower()))
        if words & org_words:
            self.organization = name
            return
        # Check if name is just initials
        initials = ''.join([c for c in name if c.isalpha()])
        if initials.isupper() and len(initials) == 3:
            self.first, self.middle, self.last = initials
            return
        if initials.isupper() and len(initials) == 2:
            self.first, self.last = initials
            return
        # If name matches pattern for a compound name (von Trapp), use
        # capitalization to decide whether the prefix should be interpreted
        # as a first name or part of a last name.
        pattern = r'^({}) [a-z]+$'.format('|'.join(PREFIXES))
        if re.search(pattern, name, flags=re.I):
            if name[0].isupper():
                self.first, self.last = name.split(' ')
            else:
                self.last = name
            return
        # Link compound names (von Trapp) with underscores
        for prefix in PREFIXES:
            pattern = r"\b{} (?=[a-zA-Z]{{3,}})".format(prefix)
            repl =  r"{}_".format(prefix.replace(' ', '_'))
            name = re.sub(pattern, repl, name, flags=re.I)
        # Check for inverted name (Cee, A. B.)
        after_comma = name.rsplit(',', 1)[-1].strip('. ')
        if ',' in name and not after_comma in SUFFIXES:
            parts = [s.strip() for s in name.rsplit(',', 1)[::-1]]
            parts[-1] = parts[-1].replace(' ', '_')
            name = ' '.join(parts)
        # HumanName gets confused by initials without spacing, so
        # normalize names like AB Cee and A.B. Cee
        name = re.sub(r'\b([A-Z]\.)(?! )', r'\1 ', name)
        if not name.isupper():
            name = re.sub(r'^([A-Z])([A-Z])\b', r'\1. \2.', name)
        # HumanName will not accept certain words as first names (e.g., Bon,
        # Do), so force it to by appending some nonsense just before the
        # first space
        salt = 'zzzzzzzz'
        name = name.replace(' ', salt + ' ', 1) if ' ' in name else name + salt
        # Parse name using the HumanName class
        name = HumanName(name)
        for attr in self.attributes:
            setattr(self, attr, getattr(name, attr))
        # Remove salt
        self.first = self.first.replace(salt, '').strip()
        self.middle = self.middle.replace(salt, '').strip()
        self.last = self.last.replace(salt, '').strip()
        # Fix misparsed suffix
        if not self.last:
            self.last = self.first
            self.first = self.suffix
            self.suffix = ''
        # Fix misparsed trailing suffix
        if self.middle.rstrip('.').endswith(tuple(SUFFIXES)):
            try:
                self.middle, self.suffix = self.middle.rsplit(' ', 1)
            except ValueError:
                self.suffix = self.middle
        # Fix titles that nameparser struggles with
        problem_words = ['Count', 'Countess']
        for word in sorted(problem_words, key=len)[::-1]:
            if self.verbatim.startswith(word):
                #unparsed = unparsed.split(word)[1].strip()
                self.title = word
                break
        # Fix mixed initial/full name in middle name by
        middle_names = self.middle.split(' ')
        if len(middle_names) > 1 and len(middle_names[0].rstrip('.')) == 1:
            while len(middle_names[-1].rstrip('.')) > 1:
                self.last = '{} {}'.format(middle_names.pop(), self.last)
            self.middle = ' '.join(middle_names)
        # Fix compound last names
        if '_' in self.last:
            self.last = ' '.join(self.last.split('_'))
        # Fix capitalization in hyphenates
        for attr in ['first', 'middle', 'last']:
            capped = getattr(self, attr).title()
            # Keep compound name prefixes lower case
            for prefix in PREFIXES:
                if capped.lower().startswith(prefix + ' '):
                    capped = capped[:len(prefix)].lower() + capped[len(prefix):]
                    break
            setattr(self, attr, ''.join(capped))
        # Strip trailing periods
        self.first = self.first.rstrip('.')
        self.middle = self.middle.rstrip('.')
        if '.' in self.middle:
            self.middle = self.middle.upper() + '.'
        # Verify that the name isn't et al
        if self.first == "Et" and self.last == "Al":
            raise ValueError('Invalid name: {}'.format(self.verbatim))
        # Verify that ast least the last name has been set
        try:
            assert self.last
        except AssertionError:
            raise ValueError('Invalid name: {}'.format(self.verbatim))


    def _sortable(self):
        """Returns a sortable version of the object"""
        parts = [self.last, self.first, self.middle]
        return ''.join([p.replace('.', '').ljust(32) for p in parts])




class People(Records):
    item_class = Person

    def __init__(self, val=None):
        super().__init__(parse_names(val) if isinstance(val, str) else val)


    def __str__(self):
        return combine_names(self)




def parse_names(val):
    """Parses names from a string"""
    if not isinstance(val, list):
        # Remove "et al" for string, truncating the string where et al occurs.
        # Then do the same for numbers. Both actions are useful for trimming
        # garbage from names pulled from citation strings.
        if "et al" in val.lower():
            val = re.split(r"\bet al\b", val, flags=re.I)[0].rstrip('., ')
        val = re.split(r"\d", val, 1)[0].strip()
        # Normalize periods then split
        val = val.replace('. ', '.') \
                 .replace('.', '. ') \
                 .replace(' & ', ' and ') \
                 .strip(' ;,')
        # Remove unicode spaces
        val = re.sub(r'\s+', ' ', val)
        # Remove commas that precede suffixes
        pattern = r', ?({})'.format('|'.join(SUFFIXES))
        val = re.sub(pattern, r' \1', val, flags=re.I)
        # Split on common delimiters
        delims = r'(?:[,;]? and |&|\||;)'
        if not is_name(val) and not re.search(delims, val):
            delims = delims.rstrip(')') + r'|,)'
        names = [s.strip(' ,;') for s in re.split(delims, val, flags=re.I) if s]
    else:
        names = val[:]
    # Convert each name to Person
    people = []
    for name in names:
        if name.strip('.') not in SUFFIXES:
            try:
                people.append(Person(name))
            except ValueError:
                pass
    return people


def combine_names(names, mask='{first} {middle} {last}', initials=True,
                  max_names=2, delim='; ', conj='and'):
    """Combines a list of names into a string"""
    if not any(names):
        return ''
    if not isinstance(names[0], Person):
        names = parse_names(names)
    names = [name.summarize(mask=mask, initials=initials) for name in names]
    if len(names) > max_names:
        names = re.sub(r' +', ' ', oxford_comma(names[:max_names], delim=delim, conj=""))
        return '{} et al.'.format(names)
    return re.sub(r' +', ' ', oxford_comma(names, delim=delim, conj=conj))


def combine_authors(*args, **kwargs):
    """Combines list of authors into a string suitable for a reference"""
    kwargs.setdefault('mask', '{last}, {first} {middle}')
    kwargs.setdefault('initials', True)
    authors = combine_names(*args, **kwargs)
    return authors


def is_name(val):
    """Checks if text contains exactly one name"""
    pattern = r'(?:[,;]? and |&|;)'
    pattern = ';'
    if not re.search(pattern, val):
        # Check for last name first
        parts = [s.strip() for s in val.split(',')]
        pattern = r'^({}) [A-Z][a-zA-Z\-]+$'.format('|'.join(PREFIXES))
        if (len(parts) == 2
            and (' ' not in parts[0]
                 or ' ' not in parts[1]
                 or re.search(pattern, parts[0], flags=re.I))):
            return True
    return False
