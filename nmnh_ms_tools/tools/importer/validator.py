"""Defines tools to validate EMu XML files"""

import csv
import os
import re
import warnings
import yaml
from pathlib import Path
from typing import Any

from xmu import (
    EMuDate,
    EMuFloat,
    EMuLatitude,
    EMuLongitude,
    EMuReader,
    EMuRecord,
    EMuSchema,
    is_ref,
)

from ...bots import Bot
from ...config import CONFIG
from ...records import CatNum, Reference, Site, get_tree, is_antarctic
from ...utils import get_windows_path


class Validator:
    """Validates data in an EMu XML file

    The file structure of the validation directory is as follows:
    - vocabs
        - module1
            - EmuField1.txt
            - EmuField2.txt
    - validate_fields.yml
    - validate_grids.yml
    - validate_hierarchies.yml
    - validate_related.yml

    Text files in the vocabs directory are organized by module. Files are named after
    an EMu field and contain lists of valid terms for that field, one per line.

    validate_fields.yml is used to validate the data in each field. Values may
    be regular expressions, lists of values, or keywords. Keywords include EMu data
    types (including Date, Float, Integer, Latitude, and Longitude) and keywords
    for common or complex validations (including DOI, FileExists, MeteoriteName,
    URLExists, YesNo, and YesNoUnknown).

    module1:
        EmuField1: [a-z]+
        EmuField2: Date

    validate_grids.yml is used to validate whether required grid fields are present.
    Each entry consists of a key and the list of all fields in the grid. Each grid
    should be listed only once.

    module1:
        EmuField1_tab:
        - EmuField1_tab
        - EmuField2_tab

    validate_hierarchies.yml is used to validate whether required hierarchies are fully
    populated. Each key consists of a list of parent fields that should be present if
    that key is populated.

    module1:
        EmuChild1_tab:
        - EmuParent1_tab
        - EmuParent2_tab
        EmuParent1_tab:
        - EmuParent2_tab

    validate_related.yml is used to validate whether related fields have been
    entered consistently. For example, if a town or station number is provided,
    are the administrative divisions all the same?

    module1:
        EmuField1:
        - EmuRelated1
        - EmuRelated2

    Parameters
    ----------
    import_path : str | Path
        the path to the EMu XML file
    validation_dir : str | Path
        the path to the directory containing the validation files

    Attributes
    ----------
    import_path : str | Path
        the path to the EMu XML file
    validation_dir : str | Path
        the path to the directory containing the validation files
    results : dict
        records validation results for all fields
    invalid : dict
        records invalid data in the file
    invalid : dict
        records data with no validation in the file
    """

    def __init__(self, import_path: str | Path, validation_dir: str | Path = None):
        self.import_path = import_path
        self.results = {}
        self.invalid = {}
        self.unvalidated = {}

        if validation_dir is None:
            validation_dir = CONFIG["data"]["importer"]

        self._schema = EMuSchema()
        self._bot = Bot(num_retries=2)
        self._related = {}
        self._tree = get_tree()

        self._val_fields = None
        self._val_grids = None
        self._val_hierarchies = None
        self._val_related = None
        self._lookups = {}

        # Read validation files
        for key in ("fields", "grids", "hierarchies", "related"):
            fn = f"validate_{key}.yml"

            with open(os.path.join(validation_dir, fn), encoding="utf-8") as f:
                try:
                    vals = yaml.safe_load(f)
                except yaml.parser.ParserError as exc:
                    raise ValueError(f"Could not parse {fn}") from exc

            with open(os.path.join(validation_dir, fn), "w", encoding="utf-8") as f:
                yaml.dump(vals, f)

            setattr(self, f"_val_{key}", vals if vals else {})

        # Update field validation from common
        common = self._val_fields.pop("common", {})
        for _, vals in self._val_fields.items():
            for key, val in common.items():
                vals.setdefault(key, val)

        # Update field validation from vocab files
        for root, dirs, files in os.walk(os.path.join(validation_dir, "vocabs")):
            for fn in files:
                if fn.lower().endswith(".txt"):
                    module = os.path.basename(root)
                    field = os.path.splitext(fn)[0]
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        vals = [s.strip() for s in f if s.strip()]
                    self._lookups.setdefault(module, {})[field] = vals

    def validate(self, limit: int = None) -> Path:
        """Validates an EMu XML file

        Parameters
        ----------
        limit : int, optional
            the maximum number of records to validate

        Returns
        -------
        Path
            path to CSV file with all invalid or unvalidated data
        """
        self.results = {}
        self.unvalidated = {}
        self._related = {}

        self.reader = EMuReader(self.import_path)
        for i, rec in enumerate(self.reader):

            if limit and i >= limit:
                break

            # Format and remove empty keys from record
            rec = _prep_record(EMuRecord(rec, module=self.reader.module))

            try:
                self.id = rec["irn"]
            except KeyError:
                self.id = str(CatNum(rec))
            self._recurse(rec)

            # Validate administrative divisions
            if self.reader.module == "ecatalogue":
                evt = rec.get("BioEventSiteRef", {})
            elif self.reader.module == "ecollectionevents":
                evt = rec
            else:
                evt = None
            if evt:
                if isinstance(evt, int):
                    evt = {}
                else:
                    evt = {k: v for k, v in evt.items() if k.startswith("Loc")}
                site = Site(evt)
                if site.country:
                    try:
                        site.map_admin()
                    except (IndexError, ValueError):
                        msg = "Could not map admin names"
                        module = "ecollectionevents"
                        field = "LocCountry/LocProvinceStateTerritory/LocDistrictCountyShire"
                        obj = str([site.country, site.state_province, site.county])
                        self.invalid[(module, field, obj)] = "Invalid data"

            self.reader.report_progress()

        # Identify inconsistencies between records
        for (mod, key), vals in self._related.items():
            for val, related in vals.items():
                if len(related) > 1:
                    # Identify the offending values
                    diff = []
                    for vals in zip(*related):
                        if len(set(vals)) > 1:
                            diff.append(vals)
                    msg = f"Inconsistent data in related fields (diff={diff})"
                    self.invalid[(mod, key, val)] = msg

        report = []

        for module, field, obj in sorted(self.unvalidated):
            warnings.warn(f"No validation defined: {module}.{field}")
            report.append(["No validation defined", module, field, obj])

        for module, field, obj in sorted(self.invalid):
            msg = self.invalid[(module, field, obj)]
            if msg is None:
                msg = "Invalid data"
            warnings.warn(f"{msg}: {module}.{field} = {repr(obj)}")
            report.append([f"{msg}", module, field, obj])

        path = Path(self.import_path).parent / "validation.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Warning", "Module", "Field", "Value"])
            writer.writerows(report)

        return path

    def is_valid(self, obj: Any, module: str, field: str) -> bool:
        """Tests if object is valid for the given module and field

        Parameters
        ----------
        obj : Any
            data to validate
        module : str
            an EMu module
        field : str
            an EMu field

        Returns
        -------
        bool
            whether the data is valid
        """

        # Empty objects are valid
        if not obj or obj == "--":
            return True

        dtypes = {
            "Date": EMuDate,
            "Float": EMuFloat,
            "Integer": int,
            "Latitude": EMuLatitude,
            "Longitude": EMuLongitude,
        }

        try:
            validation = self._val_fields[module]["irn" if is_ref(field) else field]
        except KeyError:
            try:
                validation = self._lookups[module][field]
            except KeyError:
                validation = self._schema.get_field_info(module, field)["DataType"]
                if validation not in dtypes:
                    if obj:
                        self.unvalidated[(module, field, str(obj))] = 1
                    return True

        if validation is None:
            return True

        # If validation is a list, object is valid if it appears in the list
        if isinstance(validation, list):
            return obj in validation

        # If validation is a data type, object is valid if it is or can be
        # coerced to the associated class
        try:
            is_dtype = isinstance(obj, dtypes[validation])
            if not is_dtype:
                try:
                    dtypes[validation](obj)
                    is_dtype = True
                except ValueError:
                    raise
            return is_dtype
        except KeyError:
            pass

        # Custom validations
        if validation == "PathExists":
            try:
                # Convert Citrix paths to local for validation
                with open(get_windows_path(obj)):
                    return True
            except FileNotFoundError:
                return False

        if validation == "URLExists":
            try:
                return self._bot.head(obj).status_code == 200
            except:
                return False

        if validation == "YesNo":
            return obj in ["Yes", "No"]

        if validation == "YesNoUnknown":
            return obj in ["Yes", "No", "Unknown"]

        if validation == "MeteoriteName":
            return is_antarctic(obj) or obj in self._lookups.get(module, {}).get(
                "MetMeteoriteName", []
            )

        if validation == "DOI":
            try:
                return bool(Reference(obj))
            except ValueError:
                return False

        if validation == "Taxon":
            try:
                self._tree[obj]
                return True
            except KeyError:
                return False

        if isinstance(obj, str):
            return bool(re.match(validation.rstrip("$") + "$", obj))

        return False

    def _recurse(self, obj: Any, path: list = None) -> None:
        """Recursively validates the given object"""
        if path is None:
            path = []
        if isinstance(obj, dict):

            # Validate grids
            for key, vals in self._val_grids.get(obj.module, {}).items():
                for row in obj.grid(key).pad():
                    filled = {k for k, v in row.items() if v}
                    missing = filled and set(vals) - filled
                    if missing:
                        val = f"Missing {sorted(missing)} ({self.id})"
                        msg = "Missing required values from grid"
                        self.invalid[(obj.module, key, val)] = msg

            # Validate hierarchies
            filled = {k for k, v in obj.items() if v}
            for key, vals in self._val_hierarchies.get(obj.module, {}).items():
                missing = obj.get(key) and set(vals) - filled
                if missing:
                    val = f"Missing {sorted(missing)} ({self.id})"
                    msg = "Missing required values from hierarchy"
                    self.invalid[(obj.module, key, val)] = msg

            # Capture data used to check consistency between records
            for key, vals in self._val_related.get(obj.module, {}).items():
                # Handle grids
                try:
                    items = obj.grid(key)
                except KeyError:
                    items = [obj]
                for item in items:
                    val = item.get(key)
                    if val:
                        rel = tuple((str(item.get(f)) for f in vals))
                        try:
                            self._related.setdefault((obj.module, key), {}).setdefault(
                                val, {}
                            )[rel] = True
                        except TypeError:
                            print(val, rel)
                            raise

            for key, val in obj.items():
                path.append(key)
                self._recurse(val, path)
                path.pop()

        elif isinstance(obj, list):
            for val in obj:
                self._recurse(val, path)
        else:
            module, field = self._get_local_path(path)

            dct = self.results.setdefault(module, {}).setdefault(field, {})
            try:
                dct[str(obj)] += 1
            except KeyError:
                dct[str(obj)] = 1

            try:
                valid = self.is_valid(obj, module, field)
            except Exception:
                raise
                valid = False
            if not valid:
                self.invalid[(module, field, str(obj))] = None
            elif self._is_mangled_date(obj, module, field):
                self.invalid[(module, field, str(obj))] = "Mangled date"

    def _get_local_path(self, path: list) -> tuple[str]:
        """Gets the path within the parent module"""
        path = path[::]
        last = path.pop()
        while path:
            info = self.reader.schema.get_field_info(self.reader.module, tuple(path))
            try:
                return info["RefTable"], last
            except KeyError:
                path.pop()
        return self.reader.module, last

    def _is_mangled_date(self, obj: Any, field: str, module: str) -> bool:
        """Tests if an object is a date in an improper format"""

        try:
            validation = self._val_fields[module]["irn" if is_ref(field) else field]
            if validation == "Date":
                return False
        except KeyError:
            pass

        patterns = (
            r"\d{1,2}-[A-Z][a-z]{2}",  # 1-Jan
            r"\d{1,2}/\d{1,2}/\d{4}",  # 1/1/1970
            r"\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}",  # 1970-01-01 00:00:00
        )
        return isinstance(obj, str) and re.match("^(" + "|".join(patterns) + ")$", obj)


def _prep_record(obj: Any) -> Any:
    """Recuresively removes empty items from an object"""
    if isinstance(obj, dict):
        delete = []
        for key, val in obj.items():
            if not _prep_record(val):
                delete.append(key)
        for key in delete:
            del obj[key]
    elif isinstance(obj, list):
        if not any((_prep_record(o) for o in obj)):
            obj.clear()
    elif isinstance(obj, str):
        return obj.rstrip("?")
    return obj
