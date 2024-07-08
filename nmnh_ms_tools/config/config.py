"""Reads the global configuration file"""

import logging
import csv
import os
from collections.abc import MutableMapping
from pprint import pformat

import yaml

from ..utils import skip_hashed


logger = logging.getLogger(__name__)


FILE_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "_files"))
CONFIG_DIR = os.path.join(FILE_DIR, "config")
DATA_DIR = os.path.join(FILE_DIR, "data")
TEST_DIR = os.path.join(FILE_DIR, "tests")


class MinSciConfig(MutableMapping):
    """Reads and writes a configuration file

    Automatically loaded when EMuRecord is first accessed. The current configuration
    can be accessed using the config attribute on each of the EMu classes.

    Parameters
    ----------
    path : str
        path to the config file. If omitted, checks the current and home
        directories for the file.

    Attributes
    ----------
    path : str
        path to the config file
    title : str
        title to write at the top of the config file
    filename : str
        default filename for config file
    classes : list
        list of classes to add the config object to
    """

    def __init__(self, path=None):
        self.path = path
        self.title = "YAML configuration file for python nmnh_ms_tools package"
        self.filename = ".nmtrc"
        self.classes = []
        self._config = None

        # Options as key: (default, comment)
        self._options = {}

        self.load_rcfile()

        # Set config parameter on all classes
        for cl in self.classes:
            cl.config = self

    def __str__(self):
        return f"{self.__class__.__name__}({pformat(self._config)})"

    def __repr__(self):
        return repr(self._config)

    def __getitem__(self, key):
        return self._config[key]

    def __setitem__(self, key, val):
        self._config[key] = val

    def __delitem__(self, key):
        del self._config[key]

    def __len__(self):
        return len(self._config)

    def __iter__(self):
        return iter(self._config)

    def load_rcfile(self, path=None):
        """Loads a configuration file

        Parameters
        ----------
        path : str
            path to the rcfile. If not given, checks the current then home
            directory for the filename.

        Returns
        -------
        dict
            either a custom configuration loaded from a file or the
            default configuration defined in this function
        """

        if path is None:
            path = self.path

        # Check the current then home directories if path not given
        if path:
            paths = [path]
        else:
            paths = [os.path.join(CONFIG_DIR), os.path.expanduser("~"), "."]

        # Create a default configuration based on _options attribute
        self._config = {k: v[0] for k, v in self._options.items()}

        # Check each location for the rcfile
        for path in paths:

            # Use a default filename if none given
            if os.path.isdir(path):
                path = os.path.join(path, self.filename)

            try:
                with open(path, encoding="utf-8") as f:
                    self.update(yaml.safe_load(f))
                self.path = path
            except (FileNotFoundError, TypeError):
                pass

        return self._config

    def save_rcfile(self, path=None, overwrite=False):
        """Saves a configuration file

        Parameters
        ----------
        path : str
            path for the rcfile. If a directory, adds the filename.
            Defaults to the user's home directory.
        overwrite : bool
            whether to overwrite the file if it exists
        """

        # Default to user home directory
        if path is None:
            path = os.path.expanduser("~")

        # Use a default filename if none given
        if os.path.isdir(path):
            path = os.path.join(path, self.filename)

        # Check if a file already exists at the path
        try:
            with open(path, encoding="utf-8") as f:
                pass
            if overwrite:
                raise FileNotFoundError
            raise IOError(
                f"'{path}' already exists. Use overwrite=True to overwrite it."
            )
        except FileNotFoundError:
            pass

        # Write a commented YAML file. Comments aren't supported by pyyaml
        # and have to be hacked in.
        content = [f"# {self.title}"]
        for line in yaml.dump(self._config, sort_keys=False).splitlines():
            try:
                comment = self._options[line.split(":")[0]][1]
                wrapped = "\n".join([f"# {l}" for l in wrap(comment)])
                content.extend(["", wrapped, line])
            except KeyError:
                # Catches keys that are not top-level options
                content.append(line)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

    def update(self, obj, path=None):
        """Recusrively updates configuration from dict

        Parameters
        ----------
        obj : mixed
            configuration object. Usually a dict, although the function itself
            may pass a variety of object types.
        path : list
            path to the current item

        Returns
        -------
        None
        """
        if path is None:
            path = []

        if path:
            config = self._config
            for key in path[:-1]:
                try:
                    config = config[key]
                except KeyError:
                    config[key] = {}
                    config = config[key]

        if isinstance(obj, dict):
            for key, val in obj.items():
                path.append(key)
                self.update(val, path)
                path.pop()
        elif isinstance(obj, list):
            config[path[-1]] = []
            for i, val in enumerate(obj):
                config[path[-1]].append(type(val)())
                path.append(i)
                self.update(val, path)
                path.pop()
        else:
            if isinstance(obj, str) and obj.startswith("~"):
                obj = os.path.realpath(os.path.expanduser(obj))
            try:
                config[path[-1]] = obj
            except IndexError:
                config.append(obj)


class GeoConfig:
    """Configuration for geographic classes and functions"""

    def __init__(self, config):
        self.config = config
        self._codes = None  # maps feature codes to data about them
        self._classes = None  # maps feature classes to feature codes
        self._fields = None  # maps DwC-ish fields to feature codes

    @property
    def codes(self):
        if self._codes is None:
            self.read_feature_definitions()
        return self._codes

    @property
    def classes(self):
        if self._classes is None:
            self.read_feature_definitions()
        return self._classes

    @property
    def fields(self):
        if self._fields is None:
            self.read_feature_definitions()
        return self._fields

    def read_feature_definitions(self, fp=None):
        """Reads GeoNames feature definitions from CSV"""
        if fp is None:
            fp = os.path.join(DATA_DIR, "geonames", "geonames_feature_codes.csv")
        codes = {}
        classes = {}
        with open(fp, "r", encoding="utf-8-sig", newline="") as f:
            rows = csv.reader(skip_hashed(f), dialect="excel")
            keys = next(rows)
            for row in rows:
                if not any(row):
                    continue
                rowdict = dict(zip(keys, row))
                try:
                    rowdict["SizeIndex"] = int(float(rowdict["SizeIndex"]))
                except ValueError:
                    pass
                code = rowdict["FeatureCode"]
                codes[code] = rowdict
                classes.setdefault(rowdict["FeatureClass"], []).append(code)
        # Fix empty codes
        for code in ["n/a", "", None]:
            codes[code] = {"SizeIndex": 10}
        fields = {}
        for i, row in enumerate(self.config["georeferencing"]["ordered_field_list"]):
            field_codes = []
            for code in row["codes"]:
                try:
                    expanded = classes[code]
                except KeyError:
                    field_codes.append(code)
                else:
                    for keyword in ["CONT", "OCN"]:
                        try:
                            expanded.remove(keyword)
                        except ValueError:
                            pass
                    # Look for and save the list of undersea feature codes
                    if code == "U":
                        fields["undersea"] = expanded
                    field_codes.extend(expanded)
            fields[row["field"]] = field_codes
            # Expand field codes in config
            self.config["georeferencing"]["ordered_field_list"][i][
                "codes"
            ] = field_codes

        self._codes = codes
        self._classes = classes
        self._fields = fields

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
        if hasattr(mixed[0], "record"):
            return [m.radius for m in mixed if m.radius]
        if hasattr(mixed[0], "site_kind"):
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
        key = "SizeIndex"
        return [self.codes[c][key] for c in fcodes if self.codes[c][key]]

    def filter_codes(self, fclass=None, min_size=0, max_size=10000):
        """Filters the available feature codes based on given criteria"""
        filtered = []
        for key, vals in self.codes.items():
            if (
                vals["SizeIndex"]
                and vals.get("FeatureClass")
                and min_size <= vals["SizeIndex"] <= max_size
                and (fclass is None or vals["FeatureClass"] == fclass)
            ):
                filtered.append(key)
        return filtered

    def get_feature_codes(self, fclass):
        """Gets all feature codes belonging to the given feature class"""
        return sorted({c for c in self.classes[fclass] if c})

    def get_feature_classes(self, fcodes):
        """Gets all feature classes represented in a set of feature codes"""
        fclasses = [self.codes[c].get("FeatureClass") for c in fcodes]
        return sorted({c for c in fclasses if c})

    def get_feature_class(self, fcode):
        """Gets feature class for the given feature code"""
        try:
            return self.get_feature_classes([fcode])[0]
        except IndexError:
            raise KeyError("Unrecognized feature code: {}".format(fcode))

    def get_feature_radius(self, fcode):
        """Gets feature class for the given feature code"""
        return self.sizes([fcode])[0]


CONFIG = MinSciConfig()
GEOCONFIG = GeoConfig(CONFIG)
