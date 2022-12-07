"""Defines classes to build and index a hierarchy of geological taxa"""
import json
import logging
import pprint as pp
import os
import re
from collections.abc import MutableMapping, MutableSequence

import yaml
from unidecode import unidecode

from .taxalist import TaxaList
from .taxaparser import TaxaParser
from .taxon import Taxon
from ...config import CONFIG
from ...utils import slugify




logger = logging.getLogger(__name__)




class TaxaIndex(MutableMapping):
    """Defines basic structure for a taxonomic hierarchy"""

    def __init__(self, *args, **kwargs):
        self.obj = {}
        self.new = {}
        self.timestamp = None
        self.update(*args, **kwargs)


    def __getattr__(self, attr):
        return self[attr]


    def __getitem__(self, key):
        try:
            return self.obj[self.key(key)]
        except KeyError:
            return self.new[self.key(key)]


    def __setitem__(self, key, val):
        if isinstance(val, dict):
            val = Taxon(val)
        self.obj[self.key(key)] = val


    def __delitem__(self, key):
        del self.obj[self.key(key)]


    def __iter__(self):
        return iter(self.obj)


    def __len__(self):
        return len(self.obj)


    def __str__(self):
        return pp.pformat(self.obj)


    def __repr__(self):
        return repr(self.obj)


    def __contains__(self, key):
        try:
            self[key]
        except KeyError:
            return False
        return True


    def update(self, *args, **kwargs):
        """Explicitly routes update through class.__setitem__"""
        for key, val in dict(*args, **kwargs).items():
            self[key] = val


    def one(self, key):
        """Returns match on key if exactly one found"""
        try:
            matches = self[key]
        except KeyError:
            raise KeyError('No matches on "{}"'.format(self.key(key)))
        # Result is a taxon record
        if isinstance(matches, dict):
            return matches
        # Result is a list of matching records
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise KeyError('No matches on "{}"'.format(self.key(key)))
        raise KeyError('Multiple matches on "{}"'.format(self.key(key)))


    def from_json(self, fp, encoding="utf-8"):
        """Reads data from JSON file"""
        if self.timestamp is not None and os.path.getmtime(fp) < self.timestamp:
            raise IOError('Taxa index is older than EMu export')
        with open(fp, encoding=encoding) as f:
            self.update(json.load(f))


    def to_json(self, fp, encoding="utf-8"):
        """Writes data to JSON file"""

        class _Encoder(json.JSONEncoder):

            def default(self, obj):
                try:
                    return json.JSONEncoder.default(self, obj)
                except TypeError as exc:
                    for from_class, to_class in (
                        (MutableMapping, dict),
                        (MutableSequence, list),
                    ):
                        if isinstance(obj, from_class):
                            return to_class(obj)
                    raise

        try:
            os.makedirs(os.path.dirname(fp))
        except OSError:
            pass

        with open(fp, "w", encoding=encoding) as f:
            json.dump(self, f, cls=_Encoder)


    @staticmethod
    def key(key):
        return slugify(str(key)).replace('_', '') if key else ''




class TaxaTree(TaxaIndex):
    """Builds an indexed taxonmic hierarchy"""
    name_index = None
    stem_index = None


    def __init__(self, *args, **kwargs):
        self.disable_index = False
        super(TaxaTree, self).__init__(*args, **kwargs)
        self.indexers = {
            'name_index': NameIndex,
            'stem_index': StemIndex
        }


    def __contains__(self, key):
        try:
            self.find(key)
            return True
        except KeyError:
            return False


    def __getitem__(self, key):
        return self.find_one(key)


    def find(self, term, index='name_index'):
        """Finds all matches for a search term"""
        try:
            return [super().__getitem__(term)]
        except KeyError:
            return [self[irn] for irn in self.get_index(index)[term]]


    def find_one(self, term, index='name_index'):
        """Finds the best match on a search term"""
        matches = self.find(term, index)
        if len(matches) == 1:
            return matches[0]
        return TaxaList(matches).best_match(term)


    def place(self, name):
        """Places a name in the hierarchy, adding a new entry if needed"""
        assert name.strip()
        qualifier = 'uncertain' if name.endswith('?') else ''
        name = name.rstrip('?')
        try:
            taxon = self.find_one(name)
        except KeyError:
            parsed = self.parse(name)
            try:
                taxon = self.find_one(parsed.name)
            except KeyError:
                taxon = Taxon(name)
                taxon['irn'] = self.key(name)
                self.new[self.key(name)] = taxon
                # Add new taxon to index
                for index in self.indexers:
                    self.get_index(index).add_taxon(taxon)
            # Create a copy and add the parsed name
            taxon = Taxon({k: v for k, v in taxon.items()})
            taxon['parsed'] = parsed
        taxon['qualifier'] = qualifier
        return taxon


    def guess_parent(self, name):
        """Guesses the parent of the given name"""
        parsed = TaxaParser(name)
        matches = []
        for parent in parsed.parents():
            try:
                matches = self.get_index('stem_index')[parent]
            except KeyError:
                pass
            else:
                matches = [self[irn].preferred() for irn in matches]
                matches.sort(key=parsed.compare_to, reverse=True)
                break
        # Filter recursive matches (parent == child)
        if not (parsed.alteration or parsed.colors or parsed.textures):
            matches = [m for m in matches if m.sci_name != name]
        # Filter matches so only official names remain
        if len(matches) > 1:
            official = [m for m in matches if m.is_official()]
            if official:
                matches = official
        return matches[0] if matches else None


    def get_index(self, name):
        """Retrieves the index, creating it if needed"""
        if self.disable_index:
            return TaxaIndex()
        index = getattr(self, name)
        if index is None:
            setattr(self.__class__, name, self.indexers[name](self))
            index = getattr(self, name)
        return index


    def write_new(self, fp='import.xml'):
        """Writes an EMu import file containing any new taxa"""
        try:
            from minsci import xmu
        except ModuleNotFoundError:
            raise ModuleNotFoundError('write_new requires the minsci module')
        if self.new:
            taxa = [self.new[k] for k in sorted(self.new.keys())]
            xmu.write(fp, [t.to_emu() for t in taxa], 'etaxonomy')


    @staticmethod
    def most_specific_common_parent(taxa):
        """Groups a list of taxa as specifically as possible"""
        return TaxaList(taxa).most_specific_common_parent()


    @staticmethod
    def parse(name):
        """Parses a name"""
        return TaxaParser(name)


    def _assign_synonyms(self):
        """Attaches list of synonyms to each preferred taxon"""
        for taxon in self.values():
            if not taxon.is_preferred():
                try:
                    current = self[taxon.current.irn]
                except (AttributeError, KeyError):
                    # Records with unknown current name end up here
                    pass
                else:
                    current.setdefault('synonyms', TaxaList()).append({
                        'irn': taxon.irn,
                        'sci_name': taxon.sci_name
                    })


    def _assign_similar(self):
        """Attaches list of similar taxa to each preferred taxon"""
        similar = {}
        for taxon in self.values():
            if taxon.gen_name:
                similar.setdefault(tuple(taxon.gen_name), []).append({
                    'irn': taxon.irn,
                    'sci_name': taxon.sci_name
                })
        for taxa in similar.values():
            if len(taxa) > 1:
                for taxon in taxa:
                    matches = [t for t in taxa if t['irn'] != taxon['irn']]
                    taxon = self[taxon['irn']]
                    taxon.setdefault('similar', TaxaList()).extend(matches)


    def _assign_official(self):
        """Assigns the closest official taxon"""
        for taxon in self.values():
            if not taxon.is_official():
                parent = taxon
                i = 0
                while parent.parent:
                    try:
                        parent = self[parent.parent.irn]
                    except KeyError:
                        break
                    else:
                        if parent.is_official():
                            taxon['official'] = {
                                'irn': parent.irn,
                                'rank': parent.rank,
                                'sci_name': parent.sci_name
                            }
                            break
                    i += 1
                    if i > 100:
                        break


class NameIndex(TaxaIndex):
    """Constructs an index of taxon names"""
    path = CONFIG["data"]["name_index"]

    def __init__(self, tree):
        super(NameIndex, self).__init__()
        try:
            self.from_json(self.path)
        except (IOError, OSError):
            print('Building {} index...'.format(self.path.split('_')[0]))
            count = 0
            for obj in (tree.obj, tree.new):
                for taxon in obj.values():
                    self.add_taxon(taxon)
                    count += 1
                    if not count % 5000:
                        print('{:,} names processed'.format(count))
            print('{:,} names processed'.format(count))
            for key, taxa in self.items():
                self[key] = sorted(set(taxa))
            self.to_json(self.path)
            print('Done!')


    def add_taxon(self, taxon):
        """Adds an entry to the index"""
        self.setdefault(taxon.sci_name, []).append(taxon.irn)
        if taxon.sci_name != taxon.name:
            self.setdefault(taxon.name, []).append(taxon.irn)




class StemIndex(TaxaIndex):
    """Constructs an index of stemmed taxon names"""
    path = CONFIG["data"]["name_index"]

    def __init__(self, tree):
        super(StemIndex, self).__init__()
        try:
            self.from_json(self.path)
        except (IOError, OSError):
            print('Building {} index...'.format(self.path.split('_')[0]))
            count = 0
            for obj in (tree.obj, tree.new):
                for taxon in obj.values():
                    self.add_taxon(taxon)
                    count += 1
                    if not count % 5000:
                        print('{:,} names processed'.format(count))
            print('{:,} names processed'.format(count))
            for key, taxa in self.items():
                self[key] = sorted(set(taxa))
            self.to_json(self.path)
            print('Done!')


    def add_taxon(self, taxon):
        """Adds an entry to the index"""
        self.setdefault(taxon.parsed.indexed, []).append(taxon.irn)


    @staticmethod
    def key(val):
        return val
