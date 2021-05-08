"""Defines tools to parse and display NMNH catalog numbers"""
import functools
import logging
import pprint as pp
import re

from .core import Record, Records
from ..tools.specimen_numbers.parser import Parser, SpecNum
from ..utils import PrefixedNum, to_attribute




logger = logging.getLogger(__name__)




DEFAULT_PARSER = Parser(from_ocr=False)




class CatNum(Record):
    """Defines methods for parsing and manipulating NMNH catalog numbers"""
    terms = [
        'code',
        'prefix',
        'number',
        'suffix',
        'delim'
    ]
    parser = DEFAULT_PARSER

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ['coll_id']
        # Explicitly define defaults for all reported attributes
        self.code = ''
        self.prefix = ''
        self.number = ''
        self.suffix = ''
        self.delim = '-'
        # Define private variables
        self._department = ''
        self._division = ''
        self._collections = []
        self._primary = []
        self._is_antarctic = False
        self._masks = {
            'default': '{code} {prefix}{number}{delim}{suffix}',
            'antarctic': '{prefix}{number}{delim}{suffix}',
            'include_code': '{code} {prefix}{number}{delim}{suffix}',
            'exclude_code': '{prefix}{number}{delim}{suffix}',
            'include_div': '{code} {prefix}{number}{delim}{suffix} ({coll_id})'
        }
        self.mask = 'default'
        # Parse numbers
        if args:
            super(CatNum, self).__init__(args[0])
        else:
            super(CatNum, self).__init__(kwargs)
        # Enforce formatting for some attributes
        if self.code:
            self.code = self.code.upper()
        if self.prefix:
            self.prefix = self.prefix.upper()
        if self.suffix:
            self.suffix = self.suffix.strip(self.delim + ' ')
            if len(self.suffix) == 1 and self.suffix.isupper():
                self.delim = ''


    def __str__(self):
        return self.summarize()


    def __bool__(self):
        return bool(self.number)


    @property
    def name(self):
        return self.summarize()


    @property
    def department(self):
        """Returns the name of the collecting department"""
        return self._department


    @department.setter
    def department(self, department):
        if department:
            departments = {
                'Anthropology',
                'Botany',
                'Entomology',
                'Invertebrate Zoology',
                'Mineral Sciences',
                'Paleobiology',
                'Vertebrate Zoology: Birds',
                'Vertebrate Zoology: Fishes',
                'Vertebrate Zoology: Amphibians & Reptiles',
                'Vertebrate Zoology: Mammals'
            }
            assert department in departments
        self._department = department


    @property
    def division(self):
        """Returns the name of the collecting division"""
        try:
            div = self._division
            return (div if ':' in self._division else div[:3]).upper()
        except (AttributeError, TypeError):
            return None


    @division.setter
    def division(self, division):
        self._division = division
        self._guess_department()
        self._guess_code()


    @property
    def coll_id(self):
        """Determines the collection identifier

        Collection identifiers are based on detailed specimen info, including
        collection names and primary classifications. They are primarily used
        to distinguish samples in the Petrology Reference Standards collection
        when sharing data based on the full catalog record.
        """
        name = 'Smithsonian Microbeam'
        if [c for c in self._collections if c.startswith(name)]:
            return 'SMS'

        # Petrology has an unfortunate habit of assigning children the same
        # catalog number as their parents. This shows up especially in the
        # Reference Standards Collection, where you additionally run into
        # multiple children with the same catalog number (for example, the
        # OPX and CPX fractions from a sample may be assigned the same
        # number). These need to be sorted out manually.
        name = 'Reference Standards'
        if [c for c in self._collections if c.startswith(name)]:
            ambiguous = {
                '116610-5',
                '116610-15',
                '116610-16',
                '116610-18',
                '116610-21',
                '117213-5'
            }
            catnum = '{}-{}'.format(self.number, self.suffix)
            if catnum in ambiguous:
                if self._primary == 'Clinopyroxene':
                    return 'REF:CPX'
                if self._primary == 'Orthopyroxene':
                    return 'REF:OPX'
                if self._primary:
                    mask = 'Could not map {} (primary={})'
                    raise ValueError(mask.format(catnum, self._primary))
            return 'REF'

        return self.division


    @coll_id.setter
    def coll_id(self, val):
        if val and not self.division:
            self.division = val
        elif val and val != self.division:
            raise ValueError("Can't set division from coll_id")


    @property
    def mask(self):
        """Returns the mask used to format the catalog number"""
        return self._mask


    @mask.setter
    def mask(self, mask):
        try:
            self._mask = self._masks[mask]
        except KeyError:
            if '{' not in mask:
                raise
            self._mask = mask


    @property
    def prefixed_num(self):
        if self.number:
            return PrefixedNum('{}{}'.format(self.prefix, self.number))
        raise ValueError('Could not create prefixed_num (number empty)')



    def parse(self, data):
        """Parses catalog numbers contained in verbatim"""
        self.reset()
        if data and isinstance(data, str):
            # Some departments use trailing apostrophes to
            # differentiate between suffixes (A, A', A'', etc.) Trailing
            # apostrophes are a problem in OCR and haven't been/won't
            # be integrated into the parser, but are fine for more
            # reliable data, so handle them manaully here.
            trailing_primes = re.search(r"'+$", data)
            self._parse_string(data.rstrip("'"))
            if trailing_primes:
                self.suffix += trailing_primes.group()
        elif data and isinstance(data, self.__class__):
            self._parse_self(data)
        elif 'basisOfRecord' in data or 'basis_of_record' in data:
            self._parse_dwc(data)
        elif 'CatNumber' in data or 'MetMeteoriteName' in data:
            self._parse_emu(data)
        elif 'number' in data:
            self.code = data.pop('code', None)
            self.prefix = data.pop('prefix', None)
            self.number = data.pop('number', None)
            self.suffix = data.pop('suffix', None)
            self.delim = data.pop('delim', '-')
            self.department = data.pop('department', None)
            self.division = data.pop('division', None)
        elif isinstance(data, SpecNum):
            self._parse_spec_num(data)
        elif data:
            raise ValueError('Cannot parse: {}'.format(data))
        # Set code and delim for meteorites
        if self.is_antarctic():
            self.code = ''
            self.delim = ','
            self.mask = 'antarctic'


    def same_as(self, other, strict=True):
        """Tests if two catalog numbers are equivalent"""
        if not other:
            return False
        if not isinstance(other, self.__class__):
            other = self.__class__(other)

        # Compare museum codes (e.g., NMNH or USNM)
        same_code = self.code == other.code
        if not same_code and not strict:
            codes = sorted([self.code, other.code])
            same_code = (not all(codes) or codes == ['NMNH', 'USNM'])

        # Compare number
        same_number = int(self.number) == int(other.number)

        # Compare prefix. Published specimen numbers may include a
        # departmental code (ENT, PAL, etc.) which in the non-strict check
        # are checked using the department attribute.
        same_prefix = self.prefix == other.prefix
        if not same_prefix and self.department and not strict:
            same_prefix = self.prefix.upper() == self.department[:3].upper()

        # Compare suffix. The non-strict check will allow matches if
        # only one suffix is populated and the other is either 00 or a letter.
        # Both variants are common in the literature.
        same_suffix = self.suffix == other.suffix
        if not same_suffix and not strict:
            suffixes = (self.suffix, other.suffix)
            same_suffix = (any([s == '00' or s.isalpha() for s in suffixes])
                           and not(all(suffixes)))

        # Compare collection info
        same_dept = self.department == other.department
        if not same_dept and not strict:
            same_dept = not all([self.department, other.department])

        same_div = self.division == self.division
        if not same_div and not strict:
            same_div = not all([self.division, other.division])

        return (same_code
                and same_prefix
                and same_number
                and same_suffix
                and same_dept
                and same_div)


    def similar_to(self, other):
        """Tests if two catalog numbers are similar"""
        return self.same_as(other, strict=False)


    def key(self, attrs=None, length=16):
        """Converts object to a hashable key"""
        if attrs is None:
            attrs = ['coll_id', 'prefix', 'number', 'suffix']
        keyed = []
        for attr in attrs:
            val = getattr(self, attr).strip()
            if attr in ['number', 'suffix'] or re.match(r'^\d+$', val):
                keyed.append(val.zfill(length))
            else:
                keyed.append(val.ljust(length, '_'))
        key = '_'.join(keyed)
        return key


    def _to_emu(self):
        """Formats list for EMu"""
        if self.is_antarctic():
            return {'MetMeteoriteName': str(self)}
        return {
            'CatMuseumAcronym': self.code,
            'CatPrefix': self.prefix,
            'CatNumber': self.number,
            'CatSuffix': self.suffix,
            'CatDivision': self.division,
            }


    def to_filename(self, sortable=False, lower=False, **kwargs):
        """Converts the catalog number to a filename"""
        if sortable:
            if len(self.prefix) == 1:
                number = str(self.number).zfill(5)
            else:
                number = str(self.number).zfill(6)
            #suffix = self.suffix.zfill(4)
            catnum = self.summarize(number=number, **kwargs)
        else:
            catnum = self.summarize()
        catnum = catnum.replace(' ', '_')
        catnum = re.sub(r'-00$', '', catnum)
        return catnum.lower() if lower else catnum


    def summarize(self, mask=None, **kwargs):
        """Formats the catalog number as string"""
        if mask is None:
            mask = self.mask
        else:
            mask = self._masks.get(mask, mask)
        vals = self.to_dict()
        vals.update(kwargs)
        if self.is_antarctic():
            vals['prefix'] = vals['prefix'].ljust(4)
        elif len(vals['prefix']) > 1:
            vals['prefix'] += ' '
        val = mask.format(**vals) \
                  .replace(self.delim + ' ', ' ') \
                  .replace('()', '') \
                  .strip(' -,')
        return val


    def _parse_dwc(self, data):
        """Parses data from a Simple Darwin Core record"""
        data = {to_attribute(k): v for k, v in data.items()}
        self.verbatim = data['catalog_number']
        self._parse_string(self.verbatim)
        self.department = data.get('collection_code')


    def _parse_emu(self, data):
        """Parses data from the EMu ecatalogue module"""
        if is_antarctic(data.get('MetMeteoriteName', '')):
            self._is_antarctic = True
            self._parse_string(data.get('MetMeteoriteName'))
        else:
            self.code = data.get('CatMuseumAcronym')
            self.prefix = data.get('CatPrefix')
            self.number = data.get('CatNumber')
            self.suffix = data.get('CatSuffix')
            self.department = data.get('CatDepartment')
            self.division = data.get('CatDivision')
            self.delim = '-'
            # Get detailed specimen info from EMu data
            colls = data.get('CatCollectionName_tab', [])
            self._collections = [c['CatCollectionName'] for c in colls]
            try:
                self._primary = data['IdeTaxonRef_tab'][0]['ClaScientificName']
            except (KeyError, TypeError, IndexError):
                self._primary = data.get('MetMeteoriteType')


    def _parse_self(self, data):
        """Parses and copies data from another CatNum object"""
        attributes = list(set(self.attributes) - set(self.properties))
        attributes.extend([
            '_department',
            '_division',
            '_collections',
            '_primary',
            '_is_antarctic'
        ])
        for attr in attributes:
            setattr(self, attr, getattr(data, attr))


    def _parse_spec_num(self, data):
        """Parses SpecNum namedtuple returned by speciminer"""
        self.code = data.code
        self.prefix = data.prefix
        self.number = data.number
        self.suffix = data.suffix
        # Check for division code in suffix
        div = re.search(r' \([A-Z]{3}(:[A-Z]{3})?\)', self.suffix)
        if div is not None:
            self.division = div.group().strip('() ')
            self.suffix = self.suffix.rsplit('(', 1)[0].strip()


    def _parse_string(self, data):
        """Parses catalog number from string"""
        self.verbatim = data
        try:
            self._parse_spec_num(self.parser.parse_quick(data))
        except (AttributeError, ValueError):
            raise ValueError('Could not parse {}'.format(data))


    def is_antarctic(self):
        """Tests if catalog number looks like a NASA meteorite number"""
        return (self._is_antarctic
                or is_antarctic(str(self.verbatim))
                or 3 <= len(self.prefix) <= 4)


    def _guess_code(self):
        """Guesses the museum code for this catalog number"""
        if not self.code and self.division:
            self.code = 'USNM' if self.division == 'MET' else 'NMNH'


    def _guess_department(self):
        """Guesses the department for this catalog number"""
        if not self.department:
            if self.division in ['MET', 'MIN', 'PET']:
                self.department = 'Mineral Sciences'
            elif self.prefix == 'ENT':
                self.prefix = ''
                self.department = 'Entomology'
            elif self.prefix == 'PAL':
                self.prefix = ''
                self.department = 'Paleobiology'
        return self.department


    def _sortable(self):
        """Creates sortable version of the catalog number"""
        return self.key()




class CatNums(Records):
    """Parses and displays lists of catalog numbers"""
    item_class = CatNum

    def __init__(self, *args):
        super(CatNums, self).__init__()
        if len(args) == 1:
            if isinstance(args[0], (list, tuple)):
                catnums = args[0]
            else:
                raise ValueError("Could not coerce {}".format(args))
        elif len(args) > 1:
            catnums = args
        else:
            catnums = []
        self.extend([self._coerce(c) for c in catnums])


    def __str__(self):
        code = None
        vals = []
        for cluster in self.cluster():
            group = []
            for val in cluster:
                if val.code == code:
                    group.append(val.summarize('exclude_code'))
                else:
                    group.append(str(val))
                    code = val.code
            vals.append('-'.join(group))
        if len(vals) == 2:
            return ' and '.join(vals)
        if len(vals) > 1:
            vals[-1] = 'and ' + vals[-1]
        return ', '.join(vals)


    def __repr__(self):
        return pp.pformat([repr(c) for c in self])


    def for_filename(self, clustered=True, sortable=True,
                     lower=False, n_max=None):
        """Formats list for use as a filename"""
        if clustered:
            vals = ['-'.join([str(v) for v in c]) for c in self.cluster()]
        else:
            vals = [catnum.for_filename(sortable, lower) for catnum in vals]
        # Limit to the first n values
        if n_max and len(vals) > n_max:
            vals = vals[:n_max] + ['and others']
        filename = '_'.join(vals)
        if lower:
            filename = filename.lower()
        return filename.replace(' ', '_')


    def cluster(self):
        """Groups catalog numbers into continuous ranges"""
        catnums = self.unique()
        catnums.sort()

        codes = {}
        for catnum in catnums:
            codes.setdefault(catnum.code, CatNums()).append(catnum)

        clusters = []
        for code in sorted(codes):
            prefixes = {}
            for catnum in codes[code]:
                prefixes.setdefault(catnum.prefix, CatNums()).append(catnum)

            # Sort prefixed numbers to beginning of list
            keys = sorted(prefixes)
            if '' in keys:
                keys = [p for p in keys if p] + ['']

            for prefix in keys:
                cluster = []
                for catnum in prefixes[prefix]:
                    # Suffixes make this very complicated, so ignore for now
                    if catnum.suffix:
                        if cluster:
                            clusters.append([cluster[0], cluster[-1]])
                            cluster = []
                        clusters.append([catnum])
                    elif cluster and catnum.number - cluster[-1].number > 1:
                        clusters.append([cluster[0], cluster[-1]])
                        cluster = [catnum]
                    else:
                        cluster.append(catnum)
                if cluster:
                    clusters.append([cluster[0], cluster[-1]])
        return [c if c[0] != c[-1] else [c[0]] for c in clusters]


    def one(self):
        """Returns catalog number from lists containing only one"""
        if len(self) == 1:
            return self[0]
        raise IndexError('List does not have exactly one member')


    def _to_emu(self):
        """Formats list for EMu"""
        return [catnum.to_emu() for catnum in self]




def get_catnum(val, **kwargs):
    """Parses catalog numbers from a string, returning one if appropriate"""
    parsed = parse_catnums(val, **kwargs)
    if any(parsed) and len(parsed) == 1:
        return parsed[0]
    return parsed


def parse_catnums(val, parser=None):
    """Parses catalog numbers from a string"""
    if not val:
        return CatNums()
    if isinstance(val, dict):
        return CatNums([CatNum(val)])
    if parser is None:
        parser = DEFAULT_PARSER
    try:
        return CatNums([CatNum(parser.parse_quick(val))])
    except (AttributeError, TypeError):
        try:
            return CatNums([CatNum(c) for c in parser.parse(val)])
        except Exception as exc:
            logger.error('Undefined exception: parse_catnums', exc_info=exc)
            return CatNums()


@functools.lru_cache()
def is_antarctic(val):
    """Tests if catalog number is a NASA meteorite number"""
    return re.search(r'^[A-Z]{3}[A ]\d{5,6}(,\d+)?$', val) if val else False
