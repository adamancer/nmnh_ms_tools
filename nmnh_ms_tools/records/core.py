"""Defines a generic record type to handle various data"""

import csv
import hashlib
import logging
import json
import os
import re
import warnings

from ..config import DATA_DIR
from ..utils.standardizers import Standardizer
from ..utils import (
    LazyAttr,
    as_list,
    as_str,
    coerce,
    custom_copy,
    custom_eq,
    get_attrs,
    get_common_items,
    mutable,
    set_immutable,
    to_attribute,
    to_dwc_camel,
)


logger = logging.getLogger(__name__)


class Record:
    """Defines base methods for parsing and manipulating natural history data"""

    # Deferred class attributes are defined at the end of the file
    std = None

    # Normal class attributes
    terms = []

    def __init__(self, data=None, **kwargs):
        # Generate defaults and attributes
        attrs = [a for a in self.terms if a in dir(self)]
        self.defaults = {a: getattr(self, a) for a in attrs}
        self.attributes = attrs + self.properties
        self.valid_attrs = set(dir(self)) - set(self._class_attrs)
        # Set default values for this instance
        with mutable(self):
            self.reset()
        self.irn = None
        # Define attribution parameters
        self.attribute_to = None
        self.sources = []
        self.url_mask = None
        # Some subclasses use URL as a term
        try:
            self._url = None
        except AttributeError as exc:
            if "Cannot modify existing attribute" not in str(exc):
                raise
        # Define indexing and cache params
        self.from_cache = False
        self._indexed = None
        self._state = {}
        try:
            self._writable = ["from_cache"]
        except AttributeError as exc:
            if not "Cannot modify existing" in str(exc):
                raise

        if not data:
            data = kwargs
        with mutable(self):
            self.verbatim = data
            if data:
                # Parse data using parse method defined in the subclass
                if isinstance(data, self.__class__):
                    data = data.to_dict()
                self.parse(data)

    def __str__(self):
        rows = [("class", self.__class__.__name__)]
        for attr in self.attributes:
            val = getattr(self, attr)
            if val:
                if not isinstance(val, list):
                    val = [val]
                for val in val:
                    rows.append((attr, val))
                    attr = ""
        maxlen = max([len(row[0]) for row in rows])
        val = "\n".join([f"{a.ljust(maxlen)}: {v}" for a, v in rows])
        return "-" * 70 + "\n" + val

    def __repr__(self):
        attrs = [f"{a}={repr(getattr(self, a))}" for a in self.attributes]
        return f"{self.__class__.__name__}({", ".join(attrs)})"

    def __setattr__(self, attr, val):
        try:
            default = self.defaults[attr]
            val = coerce(val, default)
        except (AttributeError, KeyError):
            pass
        # Hardcode Record so that subclasses that also call set_immutable (for
        # example, to include a class-specific list of overwritable fields) do
        # not get stuck in a recursion.
        set_immutable(self, attr, val, cls=Record)

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
            self._indexed = "|".join(indexed)
        return self._indexed

    @property
    def cite_sources(self):
        """Returns a statement summarizing references used in this record"""
        if self.sources:
            sources = sorted(set(self.sources))
            return (
                f"Data from the following sources was used to generate"
                f" this record: {"; ".join(sources)}"
            )
        return ""

    @property
    def url(self):
        if self._url:
            return self._url
        if hasattr(self, "url_mask") and self.url_mask:
            return self.url_mask.format(**self.to_dict())

    @url.setter
    def url(self, url):
        self._url = url

    def copy(self, attrs=None):
        obj = custom_copy(self)
        if attrs:
            with mutable(obj):
                empty = self.__class__()
                for attr in get_attrs(self) - set(attrs):
                    setattr(obj, attr, getattr(empty, attr))
        return obj

    def parse(self, data):
        """Placeholder function for routing parsing from different sources"""
        raise NotImplementedError

    def coerce(self, other):
        if not isinstance(other, self.__class__):
            return self.__class__(other)
        return other

    def update(self, data, append_to=None, delim="; ", inplace=False):
        """Updates site with the given data"""
        if not isinstance(data, dict):
            data = data.to_dict()
        obj = self.copy()
        with mutable(obj):
            append_to = {} if append_to is None else set(append_to)
            for key, val in data.items():
                # Verify that key is valid
                if key.rstrip("+") not in obj.valid_attrs:
                    warnings.warn(f"Unrecognized key: {key}")
                if key in append_to or key.endswith("+"):
                    key = key.rstrip("+")
                    existing = getattr(obj, key) if hasattr(obj, key) else ""
                    if isinstance(existing, list):
                        val = existing + as_list(val)
                    elif isinstance(existing, str):
                        val = as_str(val, "; ")
                        val = (existing + delim + val).strip(delim)
                    else:
                        raise TypeError(
                            f"Invalid data type for append: {type(existing)}"
                        )
                setattr(obj, key.rstrip("+"), val)
        return obj

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

    def same_as(self, other, strict=True, ignore=None):
        """Tests if object is the same as another object"""
        if ignore is None:
            ignore = self._writable
        return custom_eq(self, other, ignore=ignore)

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
        pattern = rf"\b{self.std(keyword)}\b"
        return bool(re.search(pattern, self.indexed))

    def changed(self, name):
        """Tests if record has been modified"""
        jsonstr = json.dumps(self.to_dict(), sort_keys=True, cls=RecordEncoder).lower()
        md5 = hashlib.md5(jsonstr.encode("utf-8")).hexdigest()
        if md5 != self._state.get(name):
            self._state[name] = md5
            return True
        return False

    def to_dict(self, attributes=None, drop_empty=False):
        """Converts record to a dict"""
        if attributes is None:
            attributes = self.attributes
        dct = {a: getattr(self, a) for a in attributes}
        if drop_empty:
            dct = {k: v for k, v in dct.items() if v and str(v) != "nan"}
        return dct

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
            attributes.append("cite_sources")
        html = []
        for attr in attributes:
            val = getattr(self, attr)
            if val:
                if isinstance(val, list):
                    val = "; ".join(val)
                key = attr.title().replace("_", " ").replace("Id", "ID")
                html.append(f"<strong>{key}:</strong> {val}")
        return "<br />".join(html)

    def to_emu(self, use_irn=True, **kwargs):
        """Converts record to an EMu XML record"""
        if use_irn and self.irn:
            return {"irn": irn}
        rec = self._to_emu()
        rec.update(kwargs)
        return rec

    def _parse(self, rec):
        """Parses pre-formatted data into a record object"""
        for key, val in rec.items():
            if key not in self.attributes:
                raise KeyError(f"Illegal key: {key}")
            setattr(self, key, val)
        return self

    def _sortable(self):
        """Returns a sortable version of the object"""
        return str(self)

    def _to_emu(self):
        raise NotImplementedError


class Records(list):
    """List of records with special methods to test membership"""

    item_class = Record

    def __init__(self, *args):
        super().__init__()

        # Does not use the native list transformation because the
        # the Record class has an __iter__ method that will cause it
        # to be expanded.
        if args:
            if len(args) != 1:
                raise TypeError("Too many arguments")
            self.extend(as_list(args[0]))

        self.eq_func = "similar_to"

    def __contains__(self, val):
        val = self._coerce(val)
        if self.eq_func == "equals":
            return val in self

        # Test membership using a custom method
        for item in self:
            if getattr(val, self.eq_func)(item):
                return True

        return False

    def __getitem__(self, i):
        item = super().__getitem__(i)
        return self.__class__(item) if isinstance(item, list) else item

    def __setitem__(self, i, val):
        super().__setitem__(i, self._coerce(val))

    def append(self, val):
        super().append(self._coerce(val))

    def extend(self, vals):
        for val in vals:
            self.append(val)

    def insert(self, i, val):
        super().insert(i, self._coerce(val))

    def count(self, val):
        return super().count(self._coerce(val))

    def unique(self, sort_values=True):
        unique = [v for i, v in enumerate(self) if v not in self[:i]]
        if sort_values:
            unique.sort()
        return unique

    def _coerce(self, val):
        if isinstance(val, self.item_class):
            return val
        return self.item_class(val)


class RecordEncoder(json.JSONEncoder):
    """Encodes record classes"""

    def default(self, obj):
        try:
            return json.JSONEncoder.default(self, obj)
        except TypeError:
            try:
                return obj.to_json()
            except AttributeError:
                return str(obj)


def read_dwc_terms():
    """Reads ordered list of DwC terms based on file from TDWG"""
    fp = os.path.join(DATA_DIR, "dwc", "simple_dwc_vertical.csv")
    terms = []
    with open(fp, "r") as f:
        terms.extend(f.read().splitlines())
    return [to_attribute(t.strip("*")) for t in terms]


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
    with open(fp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, dialect="excel")
        writer.writerow([to_dwc_camel(k) for k in keys])
        for rec in records:
            writer.writerow(rec.to_csv(keys))


# Define deferred class attributes
LazyAttr(Record, "std", Standardizer)
