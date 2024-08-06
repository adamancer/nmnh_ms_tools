import csv
import os
import re
import warnings
import yaml

from nmnh_ms_tools.records import CatNum, Reference, Site, get_tree
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


class Validator:
    def __init__(self, import_path):
        self.import_path = import_path
        self.schema = EMuSchema()
        self.results = {}
        self.invalid = {}
        self.unvalidated = {}
        self._related = {}
        self._tree = get_tree()

        validation_dir = os.path.expanduser(r"~\data\nmnh_ms_tools\importer")

        self.val_fields = None
        self.val_grids = None
        self.val_hierarchies = None
        self.val_related = None
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

            setattr(self, f"val_{key}", vals)

        # Update field validation from common
        common = self.val_fields.pop("common")
        for _, vals in self.val_fields.items():
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

        # Load grid-based validation
        with open(
            os.path.join(validation_dir, "validate_grids.yml"), encoding="utf-8"
        ) as f:
            self.val_grids = yaml.safe_load(f)

        with open(
            os.path.join(validation_dir, "validate_grids.yml"), "w", encoding="utf-8"
        ) as f:
            yaml.dump(self.val_grids, f)

    def validate(self, limit=None):
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
            self.recurse(rec)

            # Validate administrative divisions
            evt = rec.get("BioEventSiteRef", {})
            if isinstance(evt, int):
                evt = {}
            else:
                evt = {k: v for k, v in evt.items() if k != "irn"}
            site = Site(evt)
            if site.country:
                try:
                    site.map_admin()
                except (IndexError, ValueError):
                    msg = "Could not map admin names"
                    module = "ecollectionevents"
                    field = (
                        "LocCountry/LocProvinceStateTerritory/LocDistrictCountyShire"
                    )
                    obj = str([site.country, site.state_province, site.county])
                    self.invalid[(module, field, obj)] = "Invalid data"

            self.reader.report_progress()

        # Identify inconsistencies between records
        for (mod, key), vals in self._related.items():
            for val, related in vals.items():
                if len(related) > 1:
                    msg = f"Inconsistent data in related fields"
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

        with open("validation.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Warning", "Module", "Field", "Value"])
            writer.writerows(report)

    def recurse(self, obj, path=None):
        if path is None:
            path = []
        if isinstance(obj, dict):

            # Validate grids
            for key, vals in self.val_grids.get(obj.module, {}).items():
                for row in obj.grid(key).pad():
                    filled = {k for k, v in row.items() if v}
                    missing = filled and set(vals) - filled
                    if missing:
                        val = f"Missing {sorted(missing)} ({self.id})"
                        msg = "Missing required values from grid"
                        self.invalid[(obj.module, key, val)] = msg

            # Validate hierarchies
            filled = {k for k, v in obj.items() if v}
            for key, vals in self.val_hierarchies.get(obj.module, {}).items():
                missing = obj.get(key) and set(vals) - filled
                if missing:
                    val = f"Missing {sorted(missing)} ({self.id})"
                    msg = "Missing required values from hierarchy"
                    self.invalid[(obj.module, key, val)] = msg

            # Capture data used to check consistency between records
            for key, vals in self.val_related.get(obj.module, {}).items():
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
                self.recurse(val, path)
                path.pop()

        elif isinstance(obj, list):
            for val in obj:
                self.recurse(val, path)
        else:
            module, field = self.get_local_path(path)

            dct = self.results.setdefault(module, {}).setdefault(field, {})
            try:
                dct[str(obj)] += 1
            except KeyError:
                dct[str(obj)] = 1

            valid = self.is_valid(obj, module, field)
            if not valid:
                self.invalid[(module, field, str(obj))] = None
            elif self.is_mangled_date(obj, module, field):
                self.invalid[(module, field, str(obj))] = "Mangled date"

    def get_local_path(self, path):
        path = path[::]
        last = path.pop()
        while path:
            info = self.reader.schema.get_field_info(self.reader.module, tuple(path))
            try:
                return info["RefTable"], last
            except KeyError:
                path.pop()
        return self.reader.module, last

    def is_valid(self, obj, module, field):

        dtypes = {
            "Date": EMuDate,
            "Float": EMuFloat,
            "Integer": int,
            "Latitude": EMuLatitude,
            "Longitude": EMuLongitude,
        }

        try:
            validation = self.val_fields[module]["irn" if is_ref(field) else field]
        except KeyError:
            try:
                validation = self._lookups[module][field]
            except KeyError:
                validation = self.schema.get_field_info(module, field)["DataType"]
                if validation not in dtypes:
                    if obj:
                        self.unvalidated[(module, field, str(obj))] = 1
                    return True

        if validation is None:
            return True

        # Empty objects are treated as valid
        if not obj or obj == "--":
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
                    pass
            return is_dtype
        except KeyError:
            pass

        # Custom validations
        if validation == "PathExists":
            try:
                # Convert Citrix paths to local for validation
                open(obj.replace("\\\\Client\\C$", "C:", 1))
                return True
            except FileNotFoundError:
                return False

        if validation == "YesNo":
            return obj in ["Yes", "No"]

        if validation == "YesNoUnknown":
            return obj in ["Yes", "No", "Unknown"]

        if validation == "MeteoriteName":
            return obj in self._lookups[module]["MetMeteoriteName"] or re.match(
                r"[A-Z]{3}[A ]\d{5,6},\d+$", obj
            )

        if validation == "DOI":
            return bool(Reference(obj).title)

        if validation == "Taxon":
            try:
                self._tree[obj]
                return True
            except KeyError:
                return False

        if isinstance(obj, str):
            return bool(re.match(validation.rstrip("$") + "$", obj))

        return False

    def is_mangled_date(self, obj, field, module):

        try:
            validation = self.val_fields[module]["irn" if is_ref(field) else field]
            if validation == "date":
                return False
        except KeyError:
            pass

        patterns = (
            r"\d{1,2}-[A-Z][a-z]{2}",  # 1-Jan
            r"\d{1,2}/\d{1,2}/\d{4}",  # 1/1/1970
            r"\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}",  # 1970-01-01 00:00:00
        )
        return isinstance(obj, str) and re.match("^(" + "|".join(patterns) + ")$", obj)


def _prep_record(obj):
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
