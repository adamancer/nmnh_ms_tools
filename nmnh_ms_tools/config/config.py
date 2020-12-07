"""Reads the global configuration file"""
import logging
import csv
import os
import shutil

import yaml

from ..utils import AttrDict, skip_hashed




logger = logging.getLogger(__name__)




FILE_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), '..', '_files')
)
CONFIG_DIR = os.path.join(FILE_DIR, 'config')
DATA_DIR = os.path.join(FILE_DIR, 'data')
TEST_DIR = os.path.join(FILE_DIR, 'tests')




class MinSciUtilsConfig:
    """Reads and interprets the module-wide config file"""

    def __init__(self):
        self.config = None
        self.codes = None    # maps feature codes to data about them
        self.classes = None  # maps feature classes to feature codes
        self.fields = None   # maps DwC-ish fields to feature codes
        self.load()


    def __getattr__(self, attr):
        try:
            return getattr(self.config, attr)
        except AttributeError:
            mask = "'{}' object has no attribute '{}'"
            raise AttributeError(mask.format(self.__class__.__name__, attr))


    def load(self):
        """Reads the configuration file"""
        fp = os.path.join(CONFIG_DIR, 'config.yml')
        with open(fp, 'r') as f:
            self.config = AttrDict(yaml.safe_load(f))
        # Update config if config file found in script directory
        try:
            self.update('config.yml')
        except FileNotFoundError:
            # Custom config file is not required
            pass
        except ValueError:
            logger.warning('config.yml not for MinSciUtilsConfig')
        # Read GeoNames feature definitions needed for georeferencing
        fp = os.path.join(DATA_DIR, 'geonames', 'geonames_feature_codes.csv')
        self.read_feature_definitions(fp)
        # Expand all paths
        for key, path in self.config['data'].items():
            if path.startswith('~'):
                path = os.path.join(os.path.expanduser('~'), path.lstrip('~/\\'))
            self.config['data'][key] = os.path.realpath(path)
        return self


    def copy_config(self, dst=''):
        """Copies config file to given directory"""
        shutil.copy2(os.path.join(__file__, '..', 'config.yml'), dst)


    def update(self, mixed):
        """Updates configuration from filepath or dict"""
        if isinstance(mixed, str):
            with open(mixed, 'r') as f:
                mixed = yaml.safe_load(f)
        # Is this data actually a config dict?
        if set(mixed.keys()) - set(self.config.keys()):
            raise ValueError('Data not for MinSciUtilsConfig')
        self._update(mixed)


    def read_feature_definitions(self, fp=None):
        """Reads GeoNames feature definitions from CSV"""
        if fp is None:
            fp = os.path.join(DATA_DIR, 'geonames', 'feature_codes.csv')
        codes = {}
        classes = {}
        with open(fp, 'r', encoding='utf-8-sig', newline='') as f:
            rows = csv.reader(skip_hashed(f), dialect='excel')
            keys = next(rows)
            for row in rows:
                if not any(row):
                    continue
                rowdict = dict(zip(keys, row))
                try:
                    rowdict['SizeIndex'] = int(float(rowdict['SizeIndex']))
                except ValueError:
                    pass
                code = rowdict['FeatureCode']
                codes[code] = rowdict
                classes.setdefault(rowdict['FeatureClass'], []).append(code)
        # Fix empty codes
        for code in ['n/a', '', None]:
            codes[code] = {'SizeIndex': 10}
        fields = {}
        for i, row in enumerate(self.routines.georeferencing.ordered_field_list):
            field_codes = []
            for code in row['codes']:
                try:
                    expanded = classes[code]
                except KeyError:
                    field_codes.append(code)
                else:
                    for keyword in ['CONT', 'OCN']:
                        try:
                            expanded.remove(keyword)
                        except ValueError:
                            pass
                    # Look for and save the list of undersea feature codes
                    if code == 'U':
                        fields['undersea'] = expanded
                    field_codes.extend(expanded)
            fields[row['field']] = field_codes
            # Expand field codes in config
            self.routines.georeferencing.ordered_field_list[i]['codes'] = field_codes
        self.codes = codes
        self.classes = classes
        self.fields = fields


    def min_size(self, mixed):
        """Returns the smallest radius for a set of feature codes"""
        return min(self.sizes(mixed))


    def max_size(self, mixed):
        """Returns the largest radius for a set of feature codes"""
        return max(self.sizes(mixed))


    def sizes(self, mixed):
        """Returns radii for a set of sites, sites, or feature codes"""
        if isinstance(mixed[0], (float, int)):
            return [s for s in mixed if s]
        if hasattr(mixed[0], 'record'):
            return [m.radius for m in mixed if m.radius]
        if hasattr(mixed[0], 'site_kind'):
            fcodes = [m.site_kind for m in mixed]
        elif isinstance(mixed, str):
            if len(mixed) == 1:
                # Mixed is a GeoNames feature class
                fcodes = self.classes[mixed]
            elif mixed.islower():
                # Mixed a DwC-ish field
                fcodes = self.fields[mixed]
            else:
                # Mixed is a single GeoNames feature code
                fcodes = [mixed]
        else:
            fcodes = mixed
        key = 'SizeIndex'
        return [self.codes[c][key] for c in fcodes if self.codes[c][key]]


    def filter_codes(self, fclass=None, min_size=0, max_size=10000):
        """Filters the available feature codes based on given criteria"""
        filtered = []
        for key, vals in self.codes.items():
            if (vals['SizeIndex']
                and vals.get('FeatureClass')
                and min_size <= vals['SizeIndex'] <= max_size
                and (fclass is None or vals['FeatureClass'] == fclass)):
                    filtered.append(key)
        return filtered


    def get_feature_codes(self, fclass):
        """Gets all feature codes belonging to the given feature class"""
        return sorted({c for c in self.classes[fclass] if c})


    def get_feature_classes(self, fcodes):
        """Gets all feature classes represented in a set of feature codes"""
        fclasses = [self.codes[c].get('FeatureClass') for c in fcodes]
        return sorted({c for c in fclasses if c})


    def get_feature_class(self, fcode):
        """Gets feature class for the given feature code"""
        try:
            return self.get_feature_classes([fcode])[0]
        except IndexError:
            raise KeyError('Unrecognized feature code: {}'.format(fcode))


    def get_feature_radius(self, fcode):
        """Gets feature class for the given feature code"""
        return self.sizes([fcode])[0]


    def _update(self, dct, keys=None):
        """Recursively updates the config dictionary"""
        if keys is None:
            keys = []
        for key, obj in dct.items():
            keys.append(key)
            if isinstance(obj, dict):
                self._update(obj, keys=keys)
            else:
                dct = self.config
                for key_ in keys[:-1]:
                    dct = dct[key_]
                dct[keys[-1]] = obj
            keys.pop()
        return dct




CONFIG = MinSciUtilsConfig()
