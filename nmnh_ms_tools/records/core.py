"""Defines a generic record type to handle various data"""
import csv
import hashlib
import logging
import json
import os
import re

from ..config import CONFIG_DIR
from ..utils.standardizers import Standardizer
from ..utils import (
    as_list,
    as_str,
    coerce,
    get_common_items,
    to_attribute,
    to_dwc_camel
)




logger = logging.getLogger(__name__)




def read_dwc_terms():
    """Reads ordered list of DwC terms based on file from TDWG"""
    fp = os.path.join(CONFIG_DIR, 'simple_dwc_vertical.csv')
    terms = []
    with open(fp, 'r') as f:
        terms.extend(f.read().splitlines())
    return [to_attribute(t.strip('*')) for t in terms]


def write_csv(fp, records, keep_empty=False):
    """Write a list of records to CSV"""
    keys = records[0].attributes
    if not keep_empty:
        empty = keys[:]
        for rec in records:
            for key in empty[:]:
                if getattr(rec, key):
                    empty.remove(key)
        keys = [k for k in keys if k not in empty]
    with open(fp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, dialect='excel')
        writer.writerow([to_dwc_camel(k) for k in keys])
        for rec in records:
            writer.writerow(rec.to_csv(keys))




class Record:
    """Defines base methods for parsing and manipulating natural history data"""
    std = Standardizer()
    terms = read_dwc_terms()


    def __init__(self, data):
        # Generate defaults and attributes
        attrs = [a for a in self.terms if a in dir(self)]
        self.defaults = {a: getattr(self, a) for a in attrs}
        self.attributes = attrs + self.properties
        # Reset values for this instance
        self.reset()
        self.verbatim = data
        # Define attribution parameters
        self.attribute_to = None
        self.url_mask = None
        self.url = None
        # Define indexing params
        self._indexed = None
        self._state = {}
        # Parse data using parse method defined in the subclass
        if isinstance(data, self.__class__):
            data = data.to_dict()
        self.parse(data)
        self.sources = []


    def __str__(self):
        rows = [('class', self.__class__.__name__)]
        for attr in self.attributes:
            val = getattr(self, attr)
            if val:
                if not isinstance(val, list):
                    val = [val]
                for val in val:
                    rows.append((attr, val))
                    attr = ''
        maxlen = max([len(row[0]) for row in rows])
        val = '\n'.join(['{}: {}'.format(a.ljust(maxlen), v) for a, v in rows])
        return '-' * 70 + '\n' + val


    def __repr__(self):
        attrs = ['{}={}'.format(a, getattr(self, a)) for a in self.attributes]
        return '{}({})'.format(self.__class__.__name__, ', '.join(attrs))


    def __setattr__(self, attr, val):
        try:
            default = self.defaults[attr]
            val = coerce(val, default)
        except (AttributeError, KeyError):
            pass
        try:
            super(Record, self).__setattr__(attr, val)
        except AttributeError as e:
            raise AttributeError('{}: {} = {}'.format(e, attr, val))


    def __eq__(self, other):
        return self.same_as(other, strict=True)


    def __ne__(self, other):
        return not self.same_as(other, strict=True)


    def __gt__(self, other):
        return self._sortable() > other


    def __ge__(self, other):
        return self._sortable() >= other


    def __lt__(self, other):
        return self._sortable() < other


    def __le__(self, other):
        return self._sortable() <= other


    def __bool__(self):
        for attr in self.attributes:
            if getattr(self, attr):
                return True
        return False


    def __iter__(self):
        return iter(self.to_dict())


    @property
    def name(self):
        """Returns a name briefly describing the object"""
        raise NotImplementedError


    @property
    def properties(self):
        """Returns a list of properties"""
        try:
            return self._properties if self._properties else []
        except AttributeError:
            return []


    @property
    def indexed(self):
        """Serializes the record to a string to make it easier to search"""
        if self._indexed is None:
            indexed = []
            for vals in self.to_dict().values():
                for val in as_list(vals):
                    if val:
                        indexed.append(self.std(val))
            self._indexed = '|'.join(indexed)
        return self._indexed


    @property
    def cite_sources(self):
        """Returns a statement summarizing references used in this record"""
        if self.sources:
            sources = sorted(set(self.sources))
            return ('Data from the following sources was used to generate'
                    ' this record: {}').format('; '.join(sources))
        return ''


    @property
    def url(self):
        if self._url:
            return self._url
        if hasattr(self, 'url_mask') and self.url_mask:
            return self.url_mask.format(**self.to_dict())


    @url.setter
    def url(self, url):
        self._url = url


    def parse(self, data):
        """Placeholder function for routing parsing from different sources"""
        raise NotImplementedError


    def update(self, data, append_to=None, delim='; '):
        """Updates site with the given data"""
        if not isinstance(data, dict):
            data = data.to_dict()
        append_to = {} if append_to is None else set(append_to)
        for key, val in data.items():
            # Verify that key is valid
            if key.rstrip('+') not in self.attributes:
                raise KeyError('Illegal key: {}'.format(key))
            if key in append_to or key.endswith('+'):
                key = key.rstrip('+')
                existing = getattr(self, key) if hasattr(self, key) else ''
                if isinstance(existing, list):
                    val = existing + as_list(val)
                elif isinstance(existing, str):
                    val = as_str(val, '; ')
                    val = (existing + delim + val).strip(delim)
                else:
                    mask = 'Invalid data type for append: {}'
                    raise TypeError(mask.format(type(existing)))
            setattr(self, key.rstrip('+'), val)


    def combine(self, *others):
        """Returns common elements shared between list of records"""
        dcts = [self.to_dict()] + [o.to_dict() for o in others]
        return self.__class__(get_common_items(*dcts))


    def reset(self):
        """Resets all attributes to defaults"""
        for attr, default in self.defaults.items():
            if isinstance(default, (list, tuple)) and default:
                default = type(default)()
            setattr(self, attr, default)


    def same_as(self, other, strict=True):
        """Tests if object is the same as another object"""
        if not isinstance(other, self.__class__):
            return False
        for attr in self.attributes:
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True


    def similar_to(self, other):
        """Tests if object is similar to another object"""
        return self.same_as(other, strict=False)


    def same_attr(self, other, attr, strict=False):
        """Tests if two records have the same value for a given attribute"""
        if isinstance(attr, list):
            return all([self.same_attr(other, a, strict=strict) for a in attr])
        val = getattr(self, attr)
        other = getattr(other, attr)
        if strict:
            return val == other
        return val.lower() == other.lower() or bool(val) != bool(other)


    def summarize(self, mask=None, **kwargs):
        """Summarizes the content of a record"""
        if mask is None:
            return self.name
        return mask.format(**self.to_dict())


    def match(self, keyword):
        """Tests if keyword occurs in record"""
        pattern = r'\b{}\b'.format(self.std(keyword))
        return bool(re.search(pattern, self.indexed))


    def clone(self, attributes=None):
        """Clones the current record"""
        return self.__class__(self.to_dict(attributes=attributes))


    def changed(self, name):
        """Tests if record has been modified"""
        jsonstr = json.dumps(self.to_dict(), sort_keys=True).lower()
        md5 = hashlib.md5(jsonstr.encode('utf-8')).hexdigest()
        if md5 != self._state.get(name):
            self._state[name] = md5
            return True
        return False


    def to_dict(self, attributes=None):
        """Converts record to a dict"""
        if attributes is None:
            attributes = self.attributes
        return {a: getattr(self, a) for a in attributes}


    def to_csv(self, attributes=None):
        """Converts record to a CSV"""
        if attributes is None:
            attributes = self.attributes
        return [as_str(getattr(self, a)) for a in attributes]


    def to_html(self, attributes=None):
        """Converts record to an HTML table"""
        if attributes is None:
            attributes = self.attributes
        if self.sources:
            attributes.append('cite_sources')
        html = []
        for attr in attributes:
            val = getattr(self, attr)
            if val:
                if isinstance(val, list):
                    val = '; '.join(val)
                key = attr.title().replace('_', ' ').replace('Id', 'ID')
                html.append('<strong>{}:</strong> {}'.format(key, val))
        return '<br />'.join(html)


    def _parse(self, rec):
        """Parses pre-formatted data into a record object"""
        for key, val in rec.items():
            if key not in self.attributes:
                raise KeyError('Illegal key: {}'.format(key))
            setattr(self, key, val)
        return self


    def _sortable(self):
        """Returns a sortable version of the object"""
        return str(self)
