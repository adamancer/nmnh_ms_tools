"""Defines classes for creating an EMu import file from cataloging worksheet"""

import logging
import os
import re
import warnings
from copy import deepcopy
from functools import cached_property
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import numpy as np
import pandas as pd
import yaml
from xmu import (
    EMuRecord,
    EMuLatitude,
    EMuLongitude,
    is_tab,
    is_ref,
    write_import,
)
from Levenshtein import distance as levdist

from .actions import run_action, to_emu
from .attachments import Attachment, CollectionEvent, Location
from ...databases.gvp import GVPVolcanoes
from ...records import (
    CatNum,
    Person,
    Reference,
    Site,
    StratPackage,
    get_tree,
    parse_catnum,
    parse_names,
)
from ...tools.georeferencer import Georeferencer
from ...utils import (
    BaseDict,
    DateRange,
    LazyAttr,
    as_list,
    create_note,
    create_yaml_note,
    join_strings,
    parse_measurement,
    parse_measurements,
    to_attribute,
    ucfirst,
)

logger = logging.getLogger(__name__)


class Job(BaseDict):
    """Stores information about field mappings, etc. from import-specific job file"""

    def __init__(self, path="job.yml"):
        if path is None:
            super().__init__({})
        else:
            super().__init__(self.load(path))
        self.used = {}

        # Reset map property
        for field_info in self.get("fields", {}).values():
            for key, props in field_info.items():
                try:
                    props["map"] = {
                        k: v for k, v in props["map"].items() if v is not None
                    }
                except AttributeError:
                    props["map"] = {}
                except KeyError:
                    pass
                except TypeError:
                    raise TypeError(f"{key}: {props}")

    def __contains__(self, val):
        return str(val).casefold() in {f.casefold() for f in self.source_fields}

    @cached_property
    def source_fields(self):
        """List of fields in source

        :getattr: returns fields in source
        :type: list
        """
        return list(pd.read_excel(self["job"]["import_file"]).columns)

    def load(self, path: str | Path) -> None:
        """Loads the job file

        Parameters
        ----------
        path : str | Path
            path to job file

        Returns
        -------
        dict
            job file as dict
        """
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def save(self, path: str | Path = "job.yml") -> None:
        """Saves the job file to path

        Parameters
        ----------
        path : str | Path
            path to job file

        Returns
        -------
        None
        """
        with NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
            yaml.dump(
                self.to_dict(), tmp, sort_keys=False, indent=4, allow_unicode=True
            )
        Path(tmp.name).replace(path)

    def import_source_files(self, path: str | Path) -> None:
        """Write an EMu XML import for source files related to this import

        If an IRN is specified for the source file in the job configuration file,
        this function will be produce an update file instead.

        Parameters
        ----------
        path : str | Path
            path to which to write the import file

        Returns
        -------
        None
        """
        import_file = Path(self["job"]["import_file"]).resolve()

        supp = []
        for path_ in extract_csvs(import_file):
            path_ = Path(path_)
            supp.append(
                (
                    path_.resolve(),
                    "Alternative format",
                    "Individual sheet from the modified Excel workbook as CSV (Excel dialect, UTF-8-BOM)",
                )
            )

        orig_import_file = Path(self["job"]["orig_import_file"]).resolve()
        supp.append(
            (
                orig_import_file,
                "Original workbook",
                "Original workbook submitted by cataloger",
            )
        )

        for path_ in extract_csvs(orig_import_file):
            path_ = Path(path_)
            supp.append(
                (
                    path_.resolve(),
                    "Alternative format",
                    "Individual sheet from the original Excel workbook as CSV (Excel dialect, UTF-8-BOM)",
                )
            )

        try:
            cataloger = self["fields"]["cataloging"]["cataloged_by"]["kwargs"]["src"]
        except KeyError:
            cataloger = self["fields"]["cataloging"]["cataloged_by"]["default"]

        name = self["job"]["name"]
        rec = {
            "MulTitle": f"Batch import spreadsheet for the {name}",
            "MulCreator_tab": [cataloger],
            "MulDescription": (
                f"Excel workbook used to import the {name}. The workbook submitted by the cataloger was"
                f" edited by the data manager to improve the specificity, consistency, and accuracy"
                f" of the data prior to import into EMu."
            ),
            "Multimedia": import_file,
            "DetSource": "Mineral Sciences, NMNH",
            "DetCollectionName_tab": ["Documents and data (Mineral Sciences)"],
            "DetSIRightsStatement": "Usage conditions apply",
            "DetSIRestrictionUser_tab": ["Records not covered by this policy"],
            "DetRights": "Not for publication",
            "AdmPublishWebNoPassword": "No",
            "AdmPublishWebPassword": "No",
        }
        for path_, usage, notes in supp:
            rec.setdefault("Supplementary_tab", []).append(path_)
            rec.setdefault("SupUsage_nesttab", []).append([usage])
            rec.setdefault("SupNotes0", []).append(notes)

        # Change import to update if IRN is included in the job file
        try:
            irn = self["fields"]["cataloging"]["sheet"]["default"]
        except KeyError:
            pass
        else:
            if irn and irn.strip("0"):
                rec["irn"] = irn

        write_import([EMuRecord(rec, module="emultimedia")], path)

    def tailor(self, path: str | Path = "job.yml") -> None:
        """Tailors the job file by removing unneeded fields and mappings

        Parameters
        ----------
        path : str | Path
            path to job file

        Returns
        -------
        None

        Raises
        ------
        IOError
            if job file is updated
        """

        if not self["job"].get("tailored"):

            # Limit to fields used by the current import
            used = {}
            for group, fields in self["fields"].items():
                for field, props in fields.items():
                    if str(props) in self.used:
                        # Clear map attribute if exists
                        try:
                            props["map"]
                        except AttributeError:
                            props["map"] = {}
                        except KeyError:
                            pass
                        used.setdefault(group, {})[field] = props

            self["fields"] = used

            for key in ("ignore", "irns"):
                try:
                    del self[key]
                except KeyError:
                    pass

            self["job"]["tailored"] = True

            self.save(path)

            raise IOError("Updated job file! Please re-run the notebook.")

    def compare(
        self,
        orig_path: str = None,
        clean_path: str = None,
        ignore_case: bool = True,
        ignore_spaces: bool = True,
    ) -> pd.DataFrame:
        """Compares data from original and clean workbooks

        In addition to returning a dataframe including all detected changes, this
        function writes two files (changes.csv and changes_unique.csv) with the
        same info.

        Parameters
        ----------
        orig_path : str
            path to original file. If omitted, the path is pulled from the job file.
        clean_path : str
            path to cleaned file. If omitted, the path is pulled from the job file.
        ignore_case : bool, default=True
            whether to ignore case when comparing original and clean data
        ignore_spaces : bool, default=True
            whether to ignore spaces when comparing original and clean data

        Returns
        -------
        pd.DataFrame
            dataframe with changes to the original data
        """

        def _describe_move(val, other, other_row, direction):
            if val and not other and other_row.isin([val]).any():
                keys = []
                for key, val_ in other_row.items():
                    if val == val_:
                        keys.append(key)
                return f"Moved {direction} {keys[0]}"
            return ""

        if orig_path is None:
            orig_path = self["job"]["orig_import_file"]

        if clean_path is None:
            clean_path = self["job"]["import_file"]

        with open(orig_path, "rb") as f:
            orig_db = pd.read_excel(f, sheet_name=None)

        with open(clean_path, "rb") as f:
            clean_db = pd.read_excel(f, sheet_name=None)

        changes = []

        # Iterate instead of checking keys to account for name changes
        for i, sheet in enumerate(orig_db):

            # Load sheets
            orig_sheet = orig_db[sheet].replace([np.nan], [None])
            orig_sheet = orig_sheet.rename(
                columns={c: c.title() for c in orig_sheet.columns}
            )
            try:
                clean_sheet = clean_db[sheet]
            except KeyError:
                try:
                    clean_sheet = clean_db[list(clean_db)[i]]
                except IndexError:
                    changes.append(
                        {
                            "sheet": sheet,
                            "row": "",
                            "col": "",
                            "orig": "",
                            "clean": "Sheet missing",
                        }
                    )
                    continue

            clean_sheet = clean_sheet.replace([np.nan], [None])
            clean_sheet = clean_sheet.rename(
                columns={c: c.title() for c in clean_sheet.columns}
            )

            keys = list(orig_sheet.columns)
            keys.extend((c for c in clean_sheet.columns if c not in keys))

            # Compare cells
            for i, orig_row in orig_sheet.iterrows():
                try:
                    clean_row = clean_sheet.iloc[i]
                except IndexError:
                    changes.append(
                        {
                            "sheet": sheet,
                            "row": i,
                            "col": "",
                            "orig": "",
                            "clean": "Row missing",
                        }
                    )
                else:
                    for key in keys:
                        orig_val = orig_row.get(key)
                        clean_val = clean_row.get(key)

                        # Standardize empty values
                        if not orig_val:
                            orig_val = ""
                        if not clean_val:
                            clean_val = ""

                        orig_val = str(orig_val)
                        clean_val = str(clean_val)

                        orig_cmp = orig_val
                        clean_cmp = clean_val

                        if (
                            ignore_case
                            and isinstance(orig_cmp, str)
                            and isinstance(clean_cmp, str)
                        ):
                            orig_cmp = orig_cmp.lower()
                            clean_cmp = clean_cmp.lower()

                        if (
                            ignore_spaces
                            and isinstance(orig_cmp, str)
                            and isinstance(clean_cmp, str)
                        ):
                            orig_cmp = orig_cmp.replace(" ", "")
                            clean_cmp = clean_cmp.replace(" ", "")

                        if orig_cmp != clean_cmp and not (
                            pd.isna(orig_cmp) and pd.isna(clean_cmp)
                        ):

                            # Check for moves
                            move = _describe_move(orig_val, clean_val, clean_row, "to")
                            if not move:
                                move = _describe_move(
                                    clean_val, orig_val, orig_row, "from"
                                )

                            changes.append(
                                {
                                    "sheet": sheet,
                                    "row": i,
                                    "col": key,
                                    "orig": orig_val,
                                    "clean": clean_val,
                                    "lev_dist": levdist(str(orig_val), str(clean_val)),
                                    "note": move if move else "",
                                }
                            )

        if changes:
            return pd.DataFrame(changes)[
                ["sheet", "row", "col", "orig", "clean", "lev_dist", "note"]
            ]

    def _add_source(self, path: str, join_key: str) -> None:
        """Adds ancillary records to the ImportRecord"""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            with open(path, encoding="utf-8-sig", newline="") as f:
                df = pd.read_csv(f, dtype=str).fillna("")
        elif "xls" in ext:
            with open(path, "rb") as f:
                df = pd.read_excel(f, dtype=str).fillna("")
        else:
            raise OSError(f"Invalid file type: {path}")

        data = {}
        for _, row in df.iterrows():
            row = {k: v for k, v in row.to_dict().items() if v}
            key = self._keyer(row.get(join_key))
            if key:
                data.setdefault(key, []).append(row)

        cleaned = {}
        for key, vals in data.items():
            cleaned[key] = self._combine_dicts(*vals)

        if not cleaned:
            warnings.warn(f"No ancillary records loaded: {path}")

        self.__class__.ancillary.append(cleaned)


class Source(BaseDict):
    """Container for mapping data from source to EMu"""

    found = {}
    defaults = {}
    missing = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._popped = {}

    def pop(self, *args) -> None:
        """Pops a value from the dict

        Accepts same arguments as dict.pop()
        """
        if not args or len(args) > 2:
            raise ValueError(f"pop accepts 1-2 arguments (got {args})")

        key = args[0]

        # Literals can be explicitly represented as "literal(Value)"
        if key and isinstance(key, str):
            match = re.match(rf"literal\((.*)\)$", key)
            if match:
                return match.group(1)

        # Warn but return value if key has been popped from this record already
        try:
            val = self._popped[key]
        except KeyError:
            pass
        else:
            warnings.warn(
                f"{repr(key)} was already popped from source! Returning {repr(val)}"
            )
            return val

        # Check source data for key
        try:
            val = super().pop(key)
            if val == "--":
                val = ""
            self.__class__.found[key] = True
            self._popped[key] = val
            return val
        except KeyError:
            if len(args) > 1:
                self.__class__.defaults[key] = True
                return args[1]
            else:
                self.__class__.missing[key] = True
                raise KeyError(f"{repr(key)} not found in source ({self.to_dict()})")

    def format_key(self, key) -> str:
        """Formats key using casefold

        Parameters
        ----------
        key : str
            dictionary key

        Returns
        -------
        str
            casefolded key
        """
        return str(key).casefold()

    def to_dict(self) -> dict:
        """Non-recursively converts to dict using the original keys

        Returns
        -------
        dict
            contents of Source as a dict using the original keys
        """
        return dict(self.items())


class ImportRecord(EMuRecord):
    """Record with special methods to map data from source"""

    # Deferred class attributes are defined at the end of the file
    job = None
    geo = None
    gvp = None
    tree = None
    ancillary = None

    # Normal class attributes
    module_classes = {
        "ebibliography": Reference,
        "ecollectionevents": CollectionEvent,
        "elocations": Location,
        "eparties": Person,
    }
    records = {}
    fast = False
    test = False

    def __init__(self, *args, **kwargs):

        kwargs["dict_class"] = self.__class__

        super().__init__(*args, **kwargs)

        self.data = None
        self.combined = None
        self.defaults = {}
        self.dynamic_props = {}
        self.automap = True
        self._source = None

        self._catnum = None
        self._cataloger = None

        # Read mapped attachments
        for module, cl in self.module_classes.items():
            irns = self.job.get("irns", {}).get(module, {})
            if not cl.irns and irns and any(irns.values()):
                cl.irns = {k: v for k, v in irns.items() if v}

    @property
    def catnum(self):
        """Catalog number specified in source

        :getattr: returns the catalog number
        :type: CatNum
        """
        return self._catnum

    @property
    def cataloger(self):
        """Cataloger specified in source

        :getattr: returns the name of the cataloger
        :type: str
        """
        if not self._cataloger:
            self._cataloger = str(self["CatCatalogedBy"])
        return self._cataloger

    @property
    def cataloged_date(self):
        """Cataloged date

        :getattr: returns the cataloged date
        :type: EMuDate
        """
        return self["CatDateCataloged"]

    @property
    def source(self):
        """The source data being mapped to EMu

        :getattr: returns the unmapped source data
        :setattr: sets and maps the source data to EMu
        :type: Source
        """
        return self._source

    @source.setter
    def source(self, val):

        self.data = self._check_data(val)
        self._source = Source(deepcopy(self.data))

        if self.automap and any(self._source.values()):
            # Check for additional data
            join_key = self.job.get("job", {}).get("join_key")
            if join_key:
                key = self._keyer(self._source[join_key])
                anc = [s.get(key, {}) for s in self.ancillary]
                self._source = Source(self._combine_dicts(self._source, *anc))
                self.combined = self._source.to_dict()

            # Delete ignored keys
            for key in self.job.get("ignore", []):
                try:
                    del self._source[key.rstrip("*")]
                except KeyError as exc:
                    warnings.warn(str(exc))

            # Set defined values
            for field_info in self.job.get("fields", {}).values():
                for field, props in field_info.items():
                    try:
                        self._map_props(props, field=field)
                    except Exception as exc:
                        raise ValueError(
                            f"Could not map {props} (field={repr(field)})"
                        ) from exc

            # Create note for dynamic properties
            for dst, data in self.dynamic_props.items():
                if data:
                    try:
                        self.cataloged_date
                    except KeyError:
                        if not self.schema.validate_paths:
                            self["Dynamic Properties"] = yaml.dump(data)
                        else:
                            raise
                    else:
                        module = self.module
                        if dst:
                            field_info = self.schema.get_field_info(module, dst)
                            try:
                                module = field_info["RefTable"]
                            except KeyError:
                                pass

                        text = "Additional data from donor"
                        kwargs = {
                            "module": module,
                            "mod": "",
                            "date": self["CatDateCataloged"],
                            "kind": "Dynamic Properties",
                        }
                        rec = self.setdefault(dst, {}) if dst else self
                        for key, val in create_yaml_note(data, text, **kwargs).items():
                            rec.setdefault(key, []).extend(val)

            # Fill in continent
            try:
                evt = self["BioEventSiteRef"]
            except KeyError:
                pass
            else:
                # Fill in continent
                if evt.get("LocCountry") and not evt.get("LocContinent"):
                    site = Site({"country": evt["LocCountry"]})
                    site.map_admin()
                    evt["LocContinent"] = site.continent
                # Fill in collection event
                if not self.fast:
                    self["BioEventSiteRef"] = CollectionEvent(
                        self["BioEventSiteRef"]
                    ).to_emu()
                    CollectionEvent.irns = {}

        # Clear empty values from source
        for key in list(self._source):
            if not self._source[key]:
                del self._source[key]

    def to_emu_record(self) -> EMuRecord:
        """Converts the ImportRecord to an EMuRecord"""
        return EMuRecord({k: v for k, v in self.items()}, module=self.module)

    def pop(self, *args) -> None:
        """Pops a key from the source dict

        Keys are popped as they are mapped so that it is (fairly) clear which
        keys still need to be mapped. If a default value is provided, it will
        be returned only if it is not a field in source.

        Accepts the same arguments as dict.pop()
        """
        val = self._source.pop(*args)
        # Many functions defined here pass the same value to args[0] and args[1].
        # This allows the user to pass a default value if the appropriate data is
        # not included in the spreadsheet but sometimes results in the script
        # returning the column name (for example, if the key is missing from a
        # given record). Identify cases where args[1] is a column and return None
        # instead.
        if len(args) == 2 and val == args[0] == args[1] and val in self.job:
            return None
        return val

    def unmapped(self) -> list:
        """Returns a sorted list of unmapped keys from the source dict

        Returns
        -------
        list
            sorted list of unmapped keys from the source dict
        """
        return sorted({k for k, v in self.source.items() if v})

    def attach(self, src, dst) -> None:
        """Maps a string as an attachment

        Parameters
        ----------
        src : str
            key to read from the source dict
        dst : str
            key to set in the ImportRecord

        Returns
        -------
        None
        """
        module = self.schema.get_field_info(self.module, dst)["RefTable"]
        self[dst] = Attachment(
            self.pop(src, src), irns=self.job.get("irns", {}).get(module, {})
        ).to_emu()

    def map_age(
        self, src_earliest: str, time_unit: str, src_latest: str = None
    ) -> None:
        """Maps geologic age from source

        Parameters
        ----------
        src_earliest : str
            the value or key in source containing the value for the earliest
            geologic age or the geologic age range. If a range, the function
            will try to parse the earliest and latest values from the range
            and src_latest should not be provided.
        time_unit : str
            the geochronologic time unit, e.g., period, epoch, age, etc.
        src_latest : str, optional
            the value or key in source containing the value for the latest
            geologic age

        Returns
        -------
        None
        """

        src_earliest = self.pop(src_earliest, src_earliest)
        if src_latest:
            src_latest = self.pop(src_latest, src_latest)

        # Try to split src_earliest if src_latest empty
        if not src_latest:
            try:
                src_earliest, src_latest = re.split("-+", src_earliest)
            except ValueError:
                src_latest = src_earliest

        for key, val in {
            "Earliest": src_earliest,
            "Latest": src_latest,
        }.items():
            self[f"AgeGeologicAge{key}{time_unit.title()}"] = val.title()

    def map_associated_taxa(
        self,
        src,
        named_part="Associated",
        texture_structure=None,
        id_by=None,
        comments=None,
    ) -> None:
        """Maps data for associated taxa

        Determines named part for associated taxa, then passes args/kwargs to
        `ImportRecord.map_taxa()`.
        """
        named_part = self.pop(named_part, named_part)
        if not named_part.startswith("Associated"):
            named_part = f"Associated {named_part}"
        return self.map_taxa(src, named_part, texture_structure, id_by, comments)

    def map_catalog_number(
        self,
        code: str,
        number: str,
        prefix: str = "",
        suffix: str = "",
        delim: str = "-",
    ) -> None:
        """Parses and maps the catalog number from source

        Parameters
        ----------
        code : str
            the four-character museum code for the catalog number
        number : str
            the value or key in source containing the value for the catalog number.
            This can be either the numeric component of the catalog number but is
            more typically the full, unparsed catalog number.
        prefix : str, default = ""
            the value or key in source containing the value for the catalog number
            prefix
        suffix : str, default = ""
            the value or key in source containing the value for the catalog number
            suffix
        delim : str, default = "-"
            the value or key in source containing the value used to delimit the suffix

        Returns
        -------
        None

        Raises
        ------
        ValueError
            if the catalog number cannot be parsed or converted to EMu
        """
        code = self.pop(code, code)
        prefix = self.pop(prefix, prefix)
        number = self.pop(number)
        suffix = self.pop(suffix, suffix)
        verbatim = f"{code} {prefix}{number}{delim}{suffix}".rstrip(delim)

        self._catnum = CatNum(verbatim)
        self.records.setdefault(str(self._catnum), []).append(self)
        try:
            for key, val in self._catnum.to_emu().items():
                self.setdefault(key, val)
        except TypeError:
            raise ValueError(
                f"Could not coerce value to catalog number: {repr(verbatim)}"
            )

    def map_cataloger(self, src: str) -> None:
        """Maps the cataloger from source

        Parameters
        ----------
        src : str
            the value or key in source containing the value for the cataloger name

        Returns
        -------
        None
        """
        self._cataloger = Person(self.pop(src, src))
        self["CatCatalogedByRef"] = self._cataloger.to_emu()

    def map_contingent(self, src: str, dst: str, contingent: dict) -> None:
        """Maps data related to the primary fiel

        Parameters
        ----------
        src : str
            name of source column
        dst : str
            name of the EMu field to map to
        contingent : dict
            mapping of EMu fields to columns or fixed values that must be mapped
            if src is populated

        Returns
        -------
        None
        """
        vals = [s[0] for s in split(self.pop(src))]

        is_grid = is_tab(dst)
        if is_grid:
            i = len(self.get(dst, []))
            cols = self.grid(dst).group

        self._set_path(dst, vals)

        for key, val in contingent.items():

            # Align data to same row in grid
            if is_grid:
                if not key in cols:
                    raise ValueError(
                        f"Tabular fields must be in the same grid ({repr(key)} not in {cols})"
                    )
                self.setdefault(key, [])
                while len(self[key]) < i + len(vals):
                    self[key].append(None)
                for j, _ in enumerate(vals):
                    self[key][i + j] = val
            else:
                if is_tab(key):
                    raise ValueError(
                        "Contingent fields must be all atomic or all tabular"
                    )
                self._set_path(key, val)

    def map_coordinates(self, *args, **kwargs) -> None:
        """Maps coordinates from source

        See `ImportRecord.georeference()` for parameters.

        Raises
        ------
        KeyError
            if both latitude and longitude do not exist in source
        """
        args = [self.pop(a, a) for a in args]
        kwargs = {k: self.pop(v, v) for k, v in kwargs.items()}
        kwargs = {k: v if v else None for k, v in kwargs.items()}
        if (
            kwargs["lats"]
            and not kwargs["lats"].isalpha()
            and kwargs["lons"]
            and not kwargs["lons"].isalpha()
        ):
            return self.georeference(*args, **kwargs)
        raise KeyError("Coordinates not found in source")

    def map_dates(
        self,
        src_from: str,
        dst_from: str,
        src_to: str = None,
        dst_to: str = None,
        dst_verbatim: str = None,
    ) -> None:
        """Maps dates and date ranges from source

        Parameters
        ----------
        src_from : str
            the value or key containing the value for start date. Can be a single
            date or a date range. In the latter case, the function will attempt to
            split the range to determine the end date.
        dst_from : str
            key to set start date in ImportRecord
        src_to : str, optional
            the value or key containing the value for end date
        dst_to : str, optional
            the key to use for end date in ImportRecord
        dst_verbatim : str, optional
            the key to use for the verbatim date or date range in ImportRecord

        Returns
        -------
        None
        """
        date_from = self.pop(src_from)
        date_to = self.pop(src_to, date_from)
        try:
            dates = DateRange(date_from, date_to)
        except ValueError:
            raise ValueError(date_from)
        else:
            val_from = dates.from_val
            val_to = dates.to_val
            verbatim = dates.verbatim

            if val_from:

                try:
                    self._set_path(dst_from, val_from)
                except TypeError:
                    pass

                if dst_to:
                    try:
                        self._set_path(dst_to, val_to)
                    except TypeError:
                        pass

                if dst_verbatim:
                    try:
                        self._set_path(dst_verbatim, verbatim)
                    except TypeError:
                        pass

    def map_depths(
        self,
        src_from: str,
        unit: str = None,
        src_to: str = None,
        water_depth: bool = True,
        bottom_depth: bool = False,
    ) -> None:
        """Maps water depths from source

        Parameters
        ----------
        src_from : str
            the value or key in source containing the value for the starting depth
            or depth range. If a range, the function will attempt to parse the
            range and src_to should not be provided. May include unit.
        unit : str, optional
            the value or key in source containing the value for the unit. May be
            omitted if the depth is presented as a value with unit, e.g., 10 m.
        src_to : str, option
            the value or key in source containing the value for the end depth
        water_depth : bool, default=True
            whether the specified depth is in the water column and not all the way
            to the bottom. If True, the water depth fields in EMu will be populated.
        bottom_depth : bool, default=False
            whether the specified depth is to the bottom. If True, the bottom depth
            fields in EMu will be populated.

        Returns
        -------
        None
        """

        val_from = self.pop(src_from)
        val_to = self.pop(src_to, src_to)
        if val_from:

            meas = parse_measurements(val_from, val_to, unit=self.pop(unit, unit))

            # Convert measurements to a valid unit if necessary
            allowed_units = {"fathoms": "Fath", "feet": "Ft", "meters": "Met"}
            try:
                suffix = allowed_units[meas.unit]
            except KeyError:
                meas = meas.convert_to("meters" if meas.is_metric() else "feet")
                suffix = allowed_units[meas.unit]

            dst_to = []
            dst_from = []
            dst_verbatim = []

            if water_depth:
                dst_from.append(f"AquDepthFrom{suffix}")
                dst_to.append(f"AquDepthTo{suffix}")
                dst_verbatim.append(f"AquVerbatimDepth")

            if bottom_depth:
                dst_from.append(f"AquBottomDepthFrom{suffix}")
                dst_to.append(f"AquBottomDepthTo{suffix}")
                dst_verbatim.append(f"AquVerbatimBottomDepth")

            evt = self.setdefault("BioEventSiteRef", {})

            for key in dst_from:
                evt._set_path(key, meas.from_val)

            for key in dst_to:
                evt._set_path(key, meas.to_val)

            for key in dst_verbatim:
                verbatim = meas.text
                if re.search(r"[a-z]", meas.verbatim, flags=re.I):
                    verbatim = meas.verbatim
                evt._set_path(key, verbatim)

    def map_dynamic_properties(
        self,
        src: str,
        dst: str = "",
        key: str = None,
        mask: str = "{}",
        raise_on_error: bool = False,
    ) -> None:
        """Maps data with no obvious home to a YAML note

        You can pass a single field or a dict. Here is an example of what the latter
        case looks like in the job file:

        ```yaml
        other:
            dynamic_props:
                method: map_dynamic_properties
                kwargs:
                    src:
                        col name 1: YAML name 1
                        col name 2: YAML name 2
        ```

        Parameters
        ----------
        src : str | dict
            the key containing the property to map or a dict of key-value pairs to map
        dst : str, optional
            the key to use in the dynamic properties note for the given src. Omit
            if src is a dict.
        key : str, optional
            ????
        mask : str, optional
            mask used to format the value, for example, to assign units
        raise_on_error : bool
            whether to raise an error if src is not found

        Returns
        -------
        None

        Raises
        ------
        KeyError
            if raise_on_error is True and src not found in source

        """
        if isinstance(src, dict):
            for src, key in src.items():
                # Catch KeyError so iteration isn't disrupted by a bad field name
                try:
                    self.map_dynamic_properties(src, key=key, mask=mask)
                except KeyError:
                    if raise_on_error:
                        raise KeyError(f"Dynamic property {repr(src)} not found")
        else:
            data = self.dynamic_props.setdefault(dst, {})
            for src in as_list(src):
                val = self.pop(src)
                if val:
                    try:
                        dct = yaml.safe_load(val)
                    except:
                        dct = None
                    if isinstance(dct, dict):
                        data.update(dct)
                    else:
                        data[key if key else src] = mask.format(val)

    def map_elevations(self, src_from, unit=None, src_to=None) -> None:
        """Maps elevation from source

         Parameters
        ----------
        src_from : str
            the value or key in source containing the value for the starting elevation
            or elevation range. If a range, the function will attempt to parse the
            range and src_to should not be provided. May include unit.
        unit : str, optional
            the value or key in source containing the value for the unit. May be
            omitted if the deelevationpth is presented as a value with unit, e.g.,
            10 m.
        src_to : str, option
            the value or key in source containing the value for the end elevation

        Returns
        -------
        None
        """
        val_from = self.pop(src_from)
        val_to = self.pop(src_to, src_to)
        if val_from:

            meas = parse_measurements(val_from, val_to, unit=self.pop(unit, unit))

            # Convert measurements to a valid unit if necessary
            allowed_units = {"feet": "Ft", "meters": "Met"}
            try:
                suffix = allowed_units[meas.unit]
            except KeyError:
                meas = meas.convert_to("meters" if meas.is_metric() else "feet")
                suffix = allowed_units[meas.unit]

            evt = self.setdefault("BioEventSiteRef", {})
            evt._set_path(f"TerElevationFrom{suffix}", meas.from_val)
            evt._set_path(f"TerElevationTo{suffix}", meas.from_val)

            verbatim = meas.text
            if re.search(r"[a-z]", meas.verbatim, flags=re.I):
                verbatim = meas.verbatim
            evt._set_path("TerVerbatimElevation", verbatim)

    def map_measurements(
        self,
        src_from: str,
        kind: str,
        src_to: str = None,
        unit: str = None,
        by: str = None,
        date: str = None,
        remarks: str = None,
        current: str = "Yes",
    ) -> None:
        """Maps measurement from source

         Parameters
        ----------
        src_from : str
            the value or key in source containing the value for the measurement
            or range. If a range, the function will attempt to parse the range
            and src_to should not be provided. May include unit.
        kind : str
            the type of measurement, e.g., length, width, or weight
        unit : str, optional
            the value or key in source containing the value for the unit. May be
            omitted if the measurement is presented as a value with unit, e.g., 10 m.
        src_to : str, optional
            the value or key in source containing the value for the end value
        by : str, optional
            the value or key in source containing the value for the person who
            made the measurement
        date : str, optional
            the value or key in source containing the value for the date on which
            the measurement was made
        remarks : str, optional
            the value or key in source containing the value for remarks about the
            measurement
        current : str, default="Yes"
            the value or key in source containing the value for whether this
            measurement is current. Must be "Yes" or "No".

        Returns
        -------
        None
        """
        val_from = self.pop(src_from)
        val_to = self.pop(src_to, src_to)
        if val_from:

            unit = self.pop(unit, unit)
            by = self.pop(by, by)
            date = self.pop(date, date)
            current = self.pop(current, current)
            remarks = self.pop(remarks, remarks)

            if by:
                by = to_emu(by, "eparties")

            meas = parse_measurements(val_from, val_to, unit=unit)

            # Record ranges as separate entries in the measurement grid
            vals = [meas.from_val]
            if meas.to_val != meas.from_val:
                vals.append(meas.to_val)
            vals.sort(key=float)

            if len(vals) > 1:
                if remarks:
                    remarks += f" ({meas.text})"
                else:
                    remarks = meas.text

            for i, val in enumerate(vals):
                kind_ = f"{kind} ({"Max" if i else "Min"})" if len(vals) > 1 else kind
                self._set_path("MeaType_tab", kind_)
                self._set_path("MeaVerbatimValue_tab", val)
                self._set_path("MeaVerbatimUnit_tab", meas.unit)
                self._set_path("MeaByRef_tab", by)
                self._set_path("MeaDate0", date if date else self.cataloged_date)
                self._set_path("MeaRemarks_tab", remarks)
                self._set_path("MeaCurrent_tab", current)

    def map_notes(
        self,
        src: str,
        dst: str = None,
        date: str = None,
        kind: str = "Comments",
        by: str = None,
        publish: str = "No",
        delim: str = "|",
    ) -> None:
        """Maps note from source

         Parameters
        ----------
        src : str
            the value or key in source containing the value for the note
        dst : str, optional
            key to a reference field in the ImportRecord where the note will be
            created. Used to create a note in another module. If blank, the note
            will be added to the catalog record.
        date : str, optional
            the value or key in source containing the value for the date the note
            was created. If omitted, defaults to the catalog date.
        kind : str, default="Comments"
            the value or key in source containing the value for the kind of note
        by : str, optional
            the value or key in source containing the value for the author of the
            note. If omitted, defaults to the cataloger.
        publish : str, default="No"
            the value or key in source containing the value for whether to publish
            the note. Must be "Yes" or "No".
        delim : str, default= "|"
            the delimiter to split on if parameters are concatenated strings

        Returns
        -------
        None
        """
        text = self.pop(src)
        if text:
            module = self.module
            if dst:
                module = self.schema.get_field_info(module, dst)["RefTable"]

            text = [t[0] for t in split(text, delim=delim)]

            # Get related fields
            date = self.pop(date, date)
            if not date:
                date = self["CatDateCataloged"]

            by = self.pop(by, by)
            if not by:
                by = self.cataloger

            # Split related into lists
            date = split(date, delim=delim)
            by = split(by, delim=delim)
            kind = split(self.pop(kind, kind), delim=delim)
            publish = split(self.pop(publish, publish), delim=delim)

            # Remove the delimiter from the split values
            date = [d[0] for d in date]
            by = [b[0] for b in by]
            kind = [k[0] for k in kind]
            publish = [p[0] for p in publish]

            # Pad related to number of notes
            date = _pad(date, len(text))
            by = _pad(by, len(text))
            kind = _pad(kind, len(text))
            publish = _pad(publish, len(text))

            # Convert by to an attachment
            by = [as_list(to_emu(b, module="eparties")) for b in by]

            # Append notes
            for text, date, by, kind, publish in zip(text, date, by, kind, publish):
                kwargs = {
                    "module": module,
                    "mod": "",
                    "date": date,
                    "kind": kind,
                    "by": by,
                    "publish": publish,
                }
                rec = self.setdefault(dst, {}) if dst else self
                for key, val in create_note(ucfirst(text), **kwargs).items():
                    rec.setdefault(key, []).extend(val)

    def map_parties(self, src: str, dst: str, contingent: dict = None) -> None:
        """Maps parties from source

         Parameters
        ----------
        src : str
            the value or key in source containing the value for the names. If
            multiple names are given in a string, the function will attempt to
            parse them.
        dst : str
            the key to store the parties in ImportRecord
        contingent : dict
            contingent fields to populate, for example, if populating a grid
            that also includes a role columns

        Returns
        -------
        None
        """
        for val in parse_names(self.pop(src)):
            self._set_path(dst, [val.to_emu()])
            for key, val in (contingent if contingent else {}).items():
                self._set_path(key, val)

    def map_prep(
        self,
        src: str,
        prep: str = None,
        remarks: str = None,
        remarks_only: bool = False,
        infer_count: bool = False,
    ) -> None:
        """Maps a single prep from a column containing a count and/or remark

        Parameters
        ----------
        src : str
            the value or key in source containing the value for either the prep count
            or remarks about the prep. If the value is numeric, it is treated as a
            count. If not *and* remarks_only is True, it is treated as a remark.
        prep : str, optional
            the name of the preparation. If omitted, uses the src column name with
            any trailing s stripped.
        remarks : str, optional
            the value or key in source containing the value for remarks about the prep.
            If src also contains text, src and remarks will be combined.
        remarks_only : bool, default=False
            whether remarks should be published without a count
        infer_count : bool, default = False
            whether a count of 1 should be assigned where no count is provided

        Returns
        -------
        None
        """
        if prep is None:
            prep = src.rstrip("s").capitalize()
        remarks = self.pop(remarks, remarks)
        for key in as_list(src):
            try:
                vals = [s[0] for s in split(self.pop(key)) if s]
            except KeyError:
                pass
            else:
                for val in vals:
                    remarks_ = None

                    # Allow remark (count) as well
                    if "(" in val:
                        orig = val
                        try:
                            remarks_, val = [s.strip(" )") for s in val.split("(")]
                        except ValueError as exc:
                            if infer_count:
                                remarks_ = val
                                val = 1
                            else:
                                raise ValueError(f"Invalid prep: {repr(orig)}") from exc
                        if not val.isnumeric():
                            raise ValueError(f"Invalid prep: {repr(orig)}")
                        if remarks and remarks_:
                            remarks_ = f"{remarks_.rstrip('. ')}. {ucfirst(remarks).strip('. ')}."
                        elif remarks:
                            remarks_ = remarks

                    val = val.lstrip("0")
                    if val and not val.isnumeric():
                        if remarks:
                            remarks_ = (
                                f"{val.rstrip('. ')}. {ucfirst(remarks).strip('. ')}."
                            )
                        else:
                            remarks_ = val
                        val = None

                    if val or remarks_ and remarks_only:
                        self.setdefault("ZooPreparationCount_tab", []).append(val)
                        self.setdefault("ZooPreparation_tab", []).append(prep)
                        self.setdefault("ZooPreparationRemarks_tab", []).append(
                            remarks_
                        )
                return
        raise KeyError(f"'{src}' not found in source")

    def map_primary_taxa(
        self,
        src: str,
        named_part: str = "Primary",
        texture_structure: str = None,
        id_by: str = None,
        comments: str = None,
    ) -> None:
        """Maps data for the primary taxon

        Determines named part for primary taxa, then passes args/kwargs to
        `ImportRecord.map_taxa()`.

        Returns
        -------
        None
        """
        named_part = self.pop(named_part, named_part)
        if not named_part.startswith("Primary"):
            named_part = f"Primary {named_part}"
        return self.map_taxa(src, named_part, texture_structure, id_by, comments)

    def map_record_classification(self):
        """Maps record classification for Collection Event records

        Returns
        -------
        None
        """
        for key in (
            "AquVesselName",
            "ColCollectionMethod",
            "ColParticipantRef_tab",
            "ColVerbatimDate",
            "ExpExpeditionName",
        ):
            if self.get("BioEventSiteRef", {}).get(key):
                self["BioEventSiteRef"]["LocRecordClassification"] = "Collection Event"
                break
        else:
            self["BioEventSiteRef"]["LocRecordClassification"] = "Site"

    def map_related(self, src, relationship) -> None:
        """Maps a relationship to another object

        Parameters
        ----------
        src : str
            the value or key in source containing the value for an identifier for the
            related object
        relationship : str
            the relationship of the related object to this object. For example, if
            the related object is a subsample, the relationship might be "Child".

        Returns
        -------
        None
        """
        val = self.pop(src)
        if val:
            for val, _ in split(val):

                try:
                    val = parse_catnum(val)
                    if val.is_antarctic():
                        kind = "NASA meteorite number"
                        val = str(val)
                        ref = None
                    else:
                        if val.prefix and val.prefix not in {
                            "B",
                            "C",
                            "G",
                            "M",
                            "S",
                            "R",
                        }:
                            raise IndexError
                        if not val.code:
                            val.code = "NMNH"
                        kind = "NMNH catalog number"
                        ref = val.to_emu()
                except IndexError:
                    kind = "Collector's field number"
                    ref = None

                self.setdefault("RelNhURI_tab", []).append(str(val))
                self.setdefault("RelNhIDType_tab", []).append(kind)
                self.setdefault("RelObjectsRef_tab", []).append(ref)
                self.setdefault("RelRelationship_tab", []).append(relationship)
                self.setdefault("RelNhDate0", []).append(self.cataloged_date)
                self.setdefault("RelNhIdentifyByRef_tab", []).append(
                    self.cataloger.to_emu()
                )

    def map_site_number(
        self,
        site_num: str,
        source: str = None,
        name: str = None,
        rec_class: str = "Collection Event",
    ) -> None:
        """Maps a site/station number from the source

        Parameters
        ----------
        site_num : str
            the value or key in source containing the value for the site identifier
        source : str
            the database, system, or role of the person who assigned the site identifier
        name : str, optional
            the name of the site represented by the identifier
        rec_class : str, default="Collection Event"
            a high-level classification for a Collection Event record. Should be either
            Site (for a generic location record) or Event (for a specific collecting
            event).

        Returns
        -------
        None
        """
        evt = self.setdefault("BioEventSiteRef", {})
        evt["LocSiteStationNumber"] = self.pop(site_num, site_num)
        evt["LocSiteNumberSource"] = self.pop(source, source)
        evt["LocRecordClassification"] = self.pop(rec_class, rec_class)
        if name is not None:
            evt["LocSiteName_tab"] = [s[0] for s in split(self.pop(name, name))]

    def map_storage_location(
        self, building: str, room_pod: str, case_shelves: str, drawer_shelf: str
    ) -> None:
        """Maps storage location to permanent and current locations

        Parameters
        ----------
        building : str
           the value or key in source containing the value for the building
        room_pod : str
            the value or key in source containing the value for the room or pod
        case_shelves : str
            the value or key in source containing the value for the case or shelves
        drawer_shelf : str
            the value or key in source containing the value for the drawer or shelf

        Returns
        -------
        None
        """
        loc = {
            "LocLevel1": self.pop(building, building),
            "LocLevel2": self.pop(room_pod, room_pod),
            "LocLevel3": self.pop(case_shelves, case_shelves),
            "LocLevel4": self.pop(drawer_shelf, drawer_shelf),
        }

        # Use mineralogy format if room is E431
        if loc["LocLevel2"] == "E431":
            loc.update(
                {
                    "LocLevel2": "East Wing",
                    "LocLevel3": "Fourth Floor",
                    "LocLevel4": loc["LocLevel2"],
                    "LocLevel5": loc["LocLevel3"],
                    "LocLevel6": loc["LocLevel4"],
                }
            )

        # Normalize case in room/pod
        if re.match(r"^(E\d+|Pod \d+)$", loc["LocLevel2"], flags=re.I):
            loc["LocLevel2"] = loc["LocLevel2"].capitalize()

        # Zero-pad case and drawer numbers for MIN and PET
        if self.get("CatDivision") in ("Mineralogy", "Petrology & Volcanology"):

            if loc["LocLevel3"] and loc["LocLevel3"][0].isnumeric():
                loc["LocLevel3"] = _pad_numeric(loc["LocLevel3"], 3)

            if loc["LocLevel4"] and loc["LocLevel4"][0].isnumeric():
                loc["LocLevel4"] = _pad_numeric(loc["LocLevel4"], 2)

        loc = Location(loc).to_emu()

        self["LocPermanentLocationRef"] = loc
        self["LocLocationRef_tab"] = [loc]

    def map_strat(self, src: list[str], remarks: str = None) -> None:
        """Maps lithostrat package from a set of fields

        Parameters
        ----------
        src : list[str]
            list of fields containing stratigraphic data or default values
        remarks : str
            the value or key in source containing the value for remarks about
            stratigraphy

        Returns
        -------
        None
        """
        units = [self.pop(src, src) for src in src]
        units = [u for u in units if u]
        units = units[0] if len(units) == 1 else units
        remarks = self.pop(remarks)
        if units:
            for key, val in StratPackage(units, remarks=remarks).to_emu().items():
                self._set_path(key, val)

    def map_taxa(
        self,
        src,
        named_part="Associated",
        texture_structure=None,
        id_by=None,
        comments=None,
    ) -> None:
        """Maps taxa from source

        Parameters
        ----------
        src : str
            the value or key in source containing the value for the taxa
        named_part : str, default="Associated"
            the value or key in source containing the value for the named part.
            Usually either Primary or Associated or a variant thereof.
        texture_structure : str, optional
            the value or key in source containing the value for the texture/structure
        id_by : str, optional
            the value or key in source containing the value for the name of the
            person responsible for the identification
        comments : str, optional
             the value or key in source containing the value for comments about the
             identification

        Returns
        -------
        None
        """

        # Record whether arguments are fields or verbatim
        part_is_field = named_part in self._source
        texture_is_field = texture_structure in self._source
        id_is_field = id_by in self._source
        comment_is_field = comments in self._source

        # Split values
        for src in as_list(src):
            taxa = split(self.pop(src))
            if taxa:
                break
        parts = split(self.pop(named_part, named_part))
        textures = split(self.pop(texture_structure, texture_structure), "|")
        ids_by = split(self.pop(id_by, id_by))
        comments = split(self.pop(comments, comments))

        if taxa:

            # Remove the delimiter from the split values
            taxa = [t[0] for t in taxa]
            parts = [p[0] for p in parts]
            textures = [t[0] for t in textures]
            ids_by = [i[0] for i in ids_by]
            comments = [c[0] for c in comments]

            # Repeat value in associated fields if verbatim
            if not part_is_field and len(parts) == 1:
                if parts[0].startswith("Primary"):
                    parts += [parts[0].replace("Primary", "Associated")] * (
                        len(taxa) - 1
                    )
                else:
                    parts = parts * len(taxa)
            if not texture_is_field and len(textures) == 1:
                textures = textures * len(taxa)
            if not id_is_field and len(ids_by) == 1:
                ids_by = ids_by * len(taxa)
            if not comment_is_field and len(comments) == 1:
                comments = comments * len(taxa)

            parts += [None] * (len(taxa) - len(parts))
            textures += [None] * (len(taxa) - len(textures))
            ids_by += [None] * (len(taxa) - len(ids_by))
            comments += [None] * (len(taxa) - len(comments))

            # Move non-texture terms to comments

            for taxon, part, texture, id_by, comment in zip(
                taxa, parts, textures, ids_by, comments
            ):

                # Handle parentheticals
                if taxon.endswith(")"):
                    taxon, parens = [s.strip() for s in taxon.rstrip(")").split("(")]
                    textures = []
                    for paren, _ in split(parens):
                        if paren in {"TAS"} or paren.startswith("var."):
                            taxon = f"{taxon} ({paren})"
                        elif paren in {"host", "vein", "xenolith"}:
                            if not part in {"Primary", "Associated"}:
                                raise ValueError(
                                    f"Taxon includes part, but part was already"
                                    f" provided: {taxon}, part={part}"
                                )
                            part = f"{part} {paren.title()}"
                        else:
                            textures.append(paren)

                    # Textures can be specified as parentheticals in names or as a
                    # keyword passed to this function. Those sources are combined here.
                    if texture:
                        textures.append(texture)

                    if textures:
                        texture = "; ".join(sorted({t.lower() for t in textures}))

                # Move non-texture concepts into comments
                if texture:
                    texture, comment_ = _split_texture_comments(
                        re.split("; *", texture)
                    )
                    if comment_:
                        if not comment:
                            comment = comment_
                        else:
                            comment = join_strings(comment, comment_)

                taxon = self.tree.place(taxon).to_emu()
                if "irn" in taxon:
                    taxon = {"irn": taxon["irn"]}
                self.setdefault("IdeTaxonRef_tab", []).append(taxon)
                self.setdefault("IdeNamedPart_tab", []).append(part)
                self.setdefault("IdeTextureStructure_tab", []).append(texture)
                self.setdefault("IdeIdentifiedByRef_tab", []).append(
                    Person(id_by).to_emu() if id_by else None
                )
                self.setdefault("IdeComments_tab", []).append(comment)

    def map_volcano(self, src_name=None, src_num=None, src_feature=None) -> None:
        """Maps GVP volcano name and number from source

        Parameters
        ----------
        src_name : str, default=None
            the value or key in source containing the value for the volcano name
        src_num : str, default=None
            the value or key in source containing the value for the volcano number
        src_feature : str, default=None
            the value or key in source containing the value for the volcanic subfeature

        Returns
        -------
        None
        """
        missed = False

        # Use country to improve match quality
        evt = self.get("BioEventSiteRef", {})
        country = evt.get("LocCountry")
        if country:
            site = Site({"country": country})
            site.map_admin()
            country = site.country

        matches = []
        vals = []
        for src, kind in (
            (src_name, "volcano"),
            (src_num, "volcano"),
            (src_feature, "feature"),
        ):
            val = self.pop(src, None)
            vals.append(val)
            if val:
                try:
                    matches.append(self.gvp.find(val, kind, country))
                except ValueError:
                    missed = True

        if matches and not missed:
            # Make sure that all volcanoes are accounted for if features present
            df = pd.concat(matches)
            for vnum in df["site_num"].unique():
                matches.append(self.gvp.find(vnum))
            df = pd.concat(matches)

            # Check for unique names
            vnames = list(df[df["site_kind"] == "GVPVLC"]["site_names"].unique())
            vnums = list(df["site_num"].unique())
            fnames = list(df[df["site_kind"] == "GVPSUB"]["site_names"].unique())

            if len(set(vnames)) == 1 and len(set(vnums)) == 1 and len(set(fnames)) <= 1:
                evt["VolVolcanoName"] = vnames[0]
                evt["VolVolcanoNumber"] = vnums[0]
                if fnames:
                    evt["VolSubfeature"] = fnames[0]
                return

        # If not found, use verbatim values instead
        if vals:
            evt["VolVolcanoName"] = vals.pop(0)
        if vals:
            evt["VolVolcanoNumber"] = vals.pop(0)
        if vals:
            evt["VolSubfeature"] = vals.pop(0)

    def map_to_yaml(self, dst: str, **kwargs) -> None:
        """Maps a set of kwargs to YAML and assigns it to the given path

        Parameters
        ----------
        dst : str
            the key to store the resulting YAML in ImportRecord
        kwargs :
            key-value pairs to include in the YAML

        Returns
        -------
        None
        """
        kwargs = {k: self.pop(v) for k, v in kwargs.items()}
        kwargs = {k: v for k, v in kwargs.items() if v}
        if kwargs:
            self._set_path(dst, yaml.dump(kwargs))

    def add_receipt(self, data: dict = None, path: str = None) -> str:
        """Adds receipt to record

        Parameters
        ----------
        data : Source, optional
            the source data used to create the receipt. If omitted, the value
            in the data attribute will be used.
        path : str, optional
            path to receipt file. If omitted, the path is inferred from the catalog
            number.

        Returns
        -------
        str
            path to receipt file
        """

        data = data if data else self.data

        # Exclude ignored fields from receipt
        ignore = {s.lower() for s in self.job.get("ignore", [])}
        data = {k: v for k, v in data.items() if k.lower() not in ignore}

        # Map dict-like data as dicts
        for key, val in data.items():
            lines = val.splitlines()
            if len(lines) > 1:
                dct = {}
                for line in val.splitlines():
                    key_, val_ = line.split(":", 1)
                    dct[key_] = val_
                data[key] = dct

        # Test receipt even if not writing it
        if self.test:
            return generate_receipt(data, str(self.catnum))

        if path is None:
            path = str(
                Path(self.job["job"]["import_file"]).parent
                / "receipts"
                / f"{to_attribute(str(self.catnum)).replace("_", "-")}.txt"
            )

        # Add suffix to filename if path already exists. This allows duplicate
        # catalog numbers to each generate a unique receipt.
        orig = Path(path)
        for i in range(1, 1000):
            try:
                open(path)
            except FileNotFoundError:
                path = str(path)
                break
            else:
                path = orig.parent / f"{orig.stem}_{str(i).zfill(3)}{orig.suffix}"

        receipt = wrap_receipt(
            data,
            path,
            self.catnum,
            str(self.cataloger),
            overwrite=not self.test,  # always overwrite if not a test
        )
        self.setdefault("MulMultiMediaRef_tab", []).insert(0, receipt)
        return path

    def georeference(
        self,
        lats: str | list[str],
        lons: str | list[str],
        crs: str,
        source: str,
        method: str,
        det_by: str,
        det_date: str,
        radius: str,
        radius_unit: str,
        notes: str,
    ) -> None:
        """Updates record with a manual georeference

        Parameters
        ----------
        lats : str | list[str]
            latitude as string or list of strings
        lons : str | list[str]
            longitude as string or list of strings
        crs : str
            coordinate reference system
        source : list
            list of sources used to make the georeference
        method : str
            procedure used to make the georeference
        det_by : str
            name of the person who made the georeference
        det_date : str
            date on which the georeference as made as YYYY-MM-DD
        radius : mixed
            numeric radius
        radius_unit : str
            unit of radius (miles, kilometers, etc.)
        notes : str
            description of how georeference was made

        Returns
        -------
        None
        """

        lats = [EMuLatitude(c) for c in as_list(lats)]
        lons = [EMuLongitude(c) for c in as_list(lons)]

        if not lats or len(lats) != len(lons):
            raise ValueError(f"Coordinate mismatch: {lats}, {lons}")

        if lats[0].kind == "decimal":
            lat_key = "LatLatitudeDecimal_nesttab"
            lon_key = "LatLongitudeDecimal_nesttab"
        else:
            lat_key = "LatLatitude_nesttab"
            lon_key = "LatLongitude_nesttab"

        evt = self.setdefault("BioEventSiteRef", {})

        evt.setdefault(lat_key, []).append(lats)
        evt.setdefault(lon_key, []).append(lons)

        evt.setdefault("LatLatitudeVerbatim_nesttab", []).append(
            [c.verbatim for c in lats]
        )
        evt.setdefault("LatLongitudeVerbatim_nesttab", []).append(
            [c.verbatim for c in lons]
        )

        evt.setdefault("LatDatum_tab", []).append(crs)

        if isinstance(source, list):
            source = " | ".join(source)
        evt.setdefault("LatDetSource_tab", []).append(source)

        evt.setdefault("LatLatLongDetermination_tab", []).append(method)

        det_by = Person(det_by).to_emu() if det_by else None
        evt.setdefault("LatDeterminedByRef_tab", []).append(det_by)

        evt.setdefault("LatDetDate0", []).append(det_date)

        if radius:
            if radius_unit:
                radius = f"{radius} {radius_unit}"

            # Use Measurement to standardize to full unit
            parsed = parse_measurement(radius)
            radius = parsed.value
            radius_unit = parsed.unit

            evt.setdefault("LatRadiusNumeric_tab", []).append(radius)
            evt.setdefault("LatRadiusUnit_tab", []).append(radius_unit)
            if radius is not None:
                evt.setdefault("LatRadiusVerbatim_tab", []).append(
                    f"{radius} {radius_unit}"
                )

        if len(lats) == 1:
            geom = "Point"
        elif len(lats) == 2:
            geom = "LineString"
        else:
            geom = "Polygon"
        evt.setdefault("LatGeometry_tab", []).append(geom)

        evt.setdefault("LatGeoreferencingNotes0", []).append(notes)

    @staticmethod
    def csvs(src=None, **kwargs) -> list:
        """Converts workbook sheets to CSV

        Parameters
        ----------
        src : str, optional
            path to Excel workbook. If omitted, extract path from job file.
        kwargs :
            parameters to pass to `extract_csvs()`

        Returns
        -------
        list[str]
            list of paths to the CSVs created from the workbook sheets
        """
        if src is None:
            src = ImportRecord.job["job"]["import_file"]
        dst = os.path.join(os.path.dirname(src), "csvs")
        kwargs = ImportRecord.job["job"].get("open_kwargs", {}).copy()
        return extract_csvs(src, dst, **kwargs)

    @staticmethod
    def _check_data(data: dict) -> dict:
        """Checks for empty rows and other common errors in row data"""

        # Check for key format issues
        bad_keys = [k for k in data if re.search(r"( {2,}| +$)", k)]
        if bad_keys:
            raise RuntimeError(f"Bad keys: {bad_keys}")

        # Confirm that data contains data
        data = {k: format_val(v) for k, v in data.items()}
        if not any(data.values()):
            return {}

        return data

    @staticmethod
    def _keyer(val: Any) -> str:
        """Converts a value to a key

        TODO: Evaluate replacing with to_attribute
        """
        if pd.isna(val) or (not val and val not in (0, False)):
            return ""

        # Split into chunks of letters or numbers
        parts = [p for p in re.split(r"([A-Za-z]+|[0-9]+)", val) if p]

        # Capture trailing non-alphanumeric suffix
        prefix = parts.pop(0) if not parts[0].isalnum() else ""
        suffix = parts.pop(-1) if not parts[-1].isalnum() else ""

        # Strip leading zeroes from parts
        cleaned = []
        if prefix:
            cleaned.append(prefix)
        for part in parts:
            if part.isalnum():
                part = part.lstrip("0")
                cleaned.append(part)
        if suffix:
            cleaned.append(suffix)

        return "|".join(cleaned).casefold()

    @staticmethod
    def _combine_dicts(*dcts: list[dict]) -> dict:
        """Combines a list of dictionaries

        TODO: Evaluate replacing with the combine utility function
        """
        dcts = list(dcts)
        combined = dcts.pop(0)
        for dct in dcts:
            for key, val in dct.items():
                if val:
                    try:
                        existing = combined[key]
                        if existing and existing != val:
                            warnings.warn(
                                f"Value conflict: {key} ({repr(val)} != {repr(existing)})"
                            )
                            val = existing
                    except KeyError:
                        pass
                    finally:
                        combined[key] = val
        return combined

    def _map_props(self, props: dict, field: str = None, **kwargs) -> bool:
        """Maps field based on the given properties"""

        # Validate keys
        allowed = {
            "action",
            "default",
            "delim",
            "dst",
            "kwargs",
            "map",
            "method",
            "required",
            "src",
        }
        undefined = set(props) - allowed
        if undefined:
            raise ValueError(f"Invalid properties: {props} (undefined={undefined})")

        # Check for mapping function
        try:
            method = props["method"]
            args = props.get("args", [])
            kwargs = props.get("kwargs", {})
        except KeyError as exc:
            pass
        else:
            try:
                getattr(self, method)(*args, **kwargs)
                self.job.used[str(props)] = True
                return True
            except KeyError as exc:
                if "not found in source" not in str(exc) or props.get("required"):
                    raise
                return False

        # Check for simple mapping
        vals = []
        try:
            src = as_list(props["src"])
        except KeyError:
            pass
        else:
            for key in src:
                try:
                    val = self.pop(key)
                except KeyError:
                    pass
                else:
                    vals_ = split(val, delim=props.get("delim", "|;"))
                    # Use column names instead of values if specified
                    if props.get("use_cols"):
                        vals_ = [key for v in vals_ if v]
                    vals.extend(vals_)

        # Check for default
        if not vals:
            vals = as_list(props.get("default", []))
            if vals:
                self.defaults[props["dst"]] = vals

        # Map to EMu field
        if any(vals):

            # Remove delimiters and duplicates from the list of values
            if isinstance(vals[0], (list, tuple)):
                delim = [v[1] for v in vals][0]
                vals = list({v[0]: None for v in vals})
            else:
                delim = " | "

            # Map values if mapping provided
            try:
                vals = [
                    props["map"].setdefault(val, int(val) if _is_irn(val) else None)
                    for val in vals
                ]
            except KeyError:
                pass
            else:
                props["map"] = {k: props["map"][k] for k in sorted(props["map"])}
                if None in props["map"].values():
                    warnings.warn(f"Null values found in map for {field}")

            # Run formatting action
            try:
                vals = [run_action(v, props["action"]) for v in vals]
            except KeyError as exc:
                if str(exc) != "'action'":
                    raise

            # Set destination keys
            try:
                dsts = as_list(props["dst"])
            except KeyError:
                raise KeyError(f"No destination specified: {props}")
            for path in dsts:
                self._set_path(path, vals, delim=delim)

            self.job.used[str(props)] = True
            return True

        elif props.get("required"):
            warnings.warn(f"Required field empty: {field}")

        return False

    def _set_path(self, path: str, vals: Any, delim: str = None) -> None:
        """Sets path in EMu record to the given value"""
        if not isinstance(vals, list):
            vals = [vals]

        obj = self
        default = None
        segments = path.split(".")
        last = segments.pop()
        for seg in segments:
            if is_tab(seg):
                obj = obj.setdefault(seg, [])
                default = {} if is_ref(seg) else None
            elif seg.isnumeric():
                while len(obj) < (int(seg) + 1):
                    obj.append(default)
                obj = obj[seg]
            elif seg == "+":
                obj.append(default)
                obj = obj[-1]
            else:
                obj = obj.setdefault(seg, {} if is_ref(seg) else None)

        if is_tab(last):
            for val in vals:
                obj.setdefault(last, []).append(val)
        elif len(vals) == 1 and isinstance(vals[0], int):
            if isinstance(obj, dict):
                obj[last] = vals[0]
            else:
                obj.append({last: vals[0]})
        elif len(vals) == 1 or delim:
            try:
                existing = split(obj[last])
                # Defer to existing delimiter if present
                try:
                    delim_ = [v[1] for v in existing if v[1]][0]
                except IndexError:
                    delim_ = "; "
                existing = [v[0] for v in existing]
                obj[last] = (delim_ if delim_ else delim).join(existing + vals)
            except KeyError:
                obj[last] = (
                    vals[0] if len(vals) == 1 else delim.join([v for v in vals if v])
                )
            except TypeError:
                print(path, vals, delim, existing)
                raise

    def _suppressible(self, exc: Exception, key: str) -> bool:
        """Checks if an exception should be suppressed"""
        return str(exc).strip("'") in set([key] + self.job.source_fields)


def format_val(val: str) -> str:
    """Cleans up string by stripping whitespace and unnecessary punctuation

    Parameters
    ----------
    val : str
        string to format

    Returns
    -------
    str
        string with extra whitespace removed
    """
    val = val.strip()
    val = re.sub(" +", " ", val)

    # Look for likely sentence breaks
    candidates = [
        w.lower().rstrip(".")
        for w in re.findall(r"[a-z0-9]{2,}\.(?= )", val, flags=re.I)
        if w.rstrip(".")
    ]

    abbrs = [
        # Titles
        "dr",
        "mr",
        "mrs",
        "ms",
        "mx",
        # Units
        "ft",
        "mi",
        # Other
        "al",
        "approx",
        "no",
        "tel",
        "vs",
    ]

    if any((w for w in candidates if w not in abbrs)):
        val = val.rstrip(". ") + "."

    # Fix trailing double quote
    if val.endswith(('"."', '".')):
        val = val.rstrip('".') + '."'

    return val


def split(vals: str | list[str], delim: str = "|;", trim: bool = True) -> list[str]:
    """Splits a string into a list using common delimiters

    Parameters
    ----------
    vals : str | list[str]
        string to split or list of values to format
    delim : str, default="|;"
        delimiters to use to split a string in order of priority. Stops
        splitting at the first matching delimiter.
    trim : bool, default=True
        whether or not to trim values after splitting

    Returns
    -------
    list[str]
        list of values as (value, delimiter)
    """
    if not vals:
        return []

    if isinstance(vals, str):
        vals = [vals]
        for delim in delim:
            vals = vals[0].split(delim)
            if len(vals) > 1:
                break
        else:
            delim = ""
    else:
        vals = as_list(vals)
        delim = ""

    # Recombine parentheticals
    combined = [vals.pop(0)]
    for val in vals:
        if "(" in combined[-1] and ")" not in combined[-1]:
            combined[-1] += delim + val
        else:
            combined.append(val)
    vals = combined

    # Strip whitespace from values
    if trim:
        vals = [s.strip() if isinstance(s, str) else s for s in vals]

    # Standardize spacing on delimiter
    delim = {"|": " | ", ";": "; ", ",": ", ", "": ""}[delim]

    return [(s, delim if len(vals) > 1 else "") for s in vals]


def generate_receipt(data: dict, catnum: CatNum) -> str:
    """Generates a receipt for the given data

    Parameters
    ----------
    data : dict
        data for the receipt
    catnum : CatNum
        catalog number

    Returns
    -------
    str
        YAML-ish receipt
    """

    # Clear empty, non-zero keys
    data = {
        k: v.strip() if isinstance(v, str) else v
        for k, v in data.items()
        if (v or v == 0)
    }

    # Create YAML receipt
    receipt = f"# Verbatim data for {catnum} from cataloging spreadsheet\n"
    receipt += yaml.dump(data, sort_keys=False, allow_unicode=True, width=1e6)

    # Clean and remove quotes around values
    last = receipt
    while True:
        receipt = re.sub(
            r"(^|\n|\r)([A-z0-9' /\-\(\)]+: )'(.*)'($|\n|\r)", r"\1\2\3\4", receipt
        )
        if receipt == last:
            break
        last = receipt

    # Check for lines with no field name
    for line in receipt.splitlines()[1:]:
        if line.strip() and ":" not in line:
            raise ValueError(f"Receipt contains line with no key: {receipt} ({data})")

    # Check for additional quoted vales
    if ": '" in receipt:
        print(data)
        orig = yaml.dump(data, sort_keys=False, allow_unicode=True, width=1e6)
        warnings.warn(f"Quoted values in receipt: {receipt} ({orig})")

    return receipt


def write_receipt(
    data: dict, path: str, catnum: CatNum, overwrite: bool = False
) -> str:
    """Writes to data to a file

    Parameters
    ----------
    data : dict
        data for the receipt
    path : str
        path to which to write the file
    catnum : CatNum
        catalog number
    overwrite : bool, default=False
        whether to overwrite an existing file at path

    Returns
    -------
    str
        path to file
    """

    # Append filename if path is a directory
    if os.path.isdir(path):
        path = os.path.join(path, f"{to_attribute(str(catnum))}.yml")

    # Ensure that directory exists
    try:
        os.makedirs(os.path.dirname(path))
    except OSError:
        pass

    # Write to file
    try:
        if overwrite:
            raise FileNotFoundError
        open(path)
    except FileNotFoundError:
        with open(path, "w", encoding="utf-8") as f:
            f.write(generate_receipt(data, catnum))

    return path


def wrap_receipt(
    data: dict, path: str, catnum: CatNum, cataloger: str, overwrite: bool = False
) -> dict:
    """Writes to data to a file and creates an EMu record for the file

    Parameters
    ----------
    data : dict
        data
    path : str
        path to which to write the file
    catnum : CatNum
        catalog number
    cataloger : str
        name of the cataloger
    overwrite : bool, default=False
        whether to overwrite an existing file at path

    Returns
    -------
    dict
        emultimedia record for the receipt file
    """
    path = write_receipt(data, path, catnum=catnum, overwrite=overwrite)
    return {
        "MulTitle": f"{catnum} source data",
        "MulCreator_tab": cataloger.split(" and "),
        "MulDescription": f"Verbatim data for {catnum} from cataloging spreadsheet",
        "Multimedia": os.path.realpath(path),
        "DetSource": "Mineral Sciences, NMNH",
        "DetCollectionName_tab": ["Documents and data (Mineral Sciences)"],
        "DetSIRightsStatement": "Usage conditions apply",
        "DetSIRestrictionUser_tab": ["Records not covered by this policy"],
        "DetRights": "Not for publication",
        "AdmPublishWebNoPassword": "No",
        "AdmPublishWebPassword": "No",
    }


def extract_csvs(src, dst=None, prefix="", suffix="", **kwargs) -> list:
    """Extract sheets in an Excel workbook as CSV and returns paths to the CSVs

    Parameters
    ----------
    src : str
        path to Excel workbook
    dst : str, optional
        path to folder for the CSVs. If not provided, the CSVs will be written
        to a subfolder in the directory containing the source file.
    prefix : str, default=""
        prefix to prepend to CSV fileames
    suffix : str, default=""
        suffix to append to CSV filenames before extension
    kwargs :
        parameters to pass to `pd.from_excel()`. Note that dtype is always set to
        str and sheet_name to None.

    Returns
    -------
    list[str]
        list of paths to the CSVs
    """

    params = kwargs.copy()
    params["dtype"] = str
    params["sheet_name"] = None

    basename = os.path.splitext(os.path.basename(src))[0]

    if dst is None:
        dst = str(Path(src).resolve().parent / "csvs")

    try:
        os.mkdir(dst)
    except OSError:
        pass

    with open(src, "rb") as f:
        sheets = pd.read_excel(f, **params)

    paths = []
    for sheet_name, sheet in sheets.items():
        sheet = sheet[(c for c in sheet.columns if not re.match(r"^Unnamed: \d+$", c))]
        path = os.path.join(dst, f"{prefix}{basename}_{sheet_name}{suffix}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            sheet.to_csv(f, index=False)
        paths.append(path)
    return paths


def _pad(lst: list, length: int) -> list:
    """Pads a list to a given length"""
    if len(lst) > 1 and len(lst) != length:
        raise ValueError(f"Invalid length: {lst} (n={length})")
    if len(lst) == 1 and length > 1:
        lst = [lst[0] for _ in range(length + 1)]
    return lst


def _pad_numeric(val: str, length: int) -> str:
    """Pads the leading numeric part of a string to the given length"""
    if val:
        parts = [s for s in re.split(r"(^\d+)", val) if s]
        if parts[0].isnumeric():
            parts[0] = parts[0].zfill(length)
        return "".join(parts)
    return val


def _is_irn(val: str | int, min_val: int = 1000000, max_val: int = 30000000) -> bool:
    """Tests if value appears to be a valid IRN"""
    try:
        val = int(val)
    except ValueError:
        return False
    else:
        return min_val <= val <= max_val


def _split_texture_comments(terms: str) -> tuple[str]:
    """Splits non-texture terms from a list of terms"""
    textures = []
    comments = []
    for term in terms:
        if (
            term in {"altered", "metasomatized", "weathered"}
            or re.match("(after|with) ", term)
            or re.search("ized$", term)
        ):
            comments.append(term)
        else:
            textures.append(term)
    return "; ".join(textures), " | ".join(comments)


def _read_ancillary() -> None:
    """Lazy loads additional files to the ancillary attribute"""
    ImportRecord.ancillary = []
    for source in ImportRecord.job.get("job", {}).get("additional_files", []):
        ImportRecord._add_source(**source)


# Define deferred class attributes
LazyAttr(ImportRecord, "job", Job)
LazyAttr(ImportRecord, "geo", Georeferencer)
LazyAttr(ImportRecord, "gvp", GVPVolcanoes)
LazyAttr(ImportRecord, "tree", get_tree)
LazyAttr(ImportRecord, "ancillary", _read_ancillary)
