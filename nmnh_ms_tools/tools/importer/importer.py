import logging
import os
import re
import warnings
from copy import deepcopy
from itertools import zip_longest
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from xmu import (
    EMuDate,
    EMuRecord,
    EMuLatitude,
    EMuLongitude,
    is_tab,
    is_ref,
    write_import,
)

from .actions import run_action, to_emu
from .attachments import Attachment, CollectionEvent, Location
from .validator import Validator
from ...databases.gvp import GVPVolcanoes
from ...records import (
    CatNum,
    Person,
    Reference,
    Site,
    get_tree,
    parse_catnums,
    parse_names,
)
from ...tools.georeferencer import Georeferencer
from ...utils import (
    BaseDict,
    LazyAttr,
    as_list,
    create_note,
    create_yaml_note,
    parse_measurements,
    to_attribute,
    ucfirst,
)

logger = logging.getLogger(__name__)

RANGE_DELIMS = [r"\b-+\b", r"\bto\b", r"\bthrough\b", r"\bthru\b"]


class Job(BaseDict):

    def __init__(self, path="job.yml"):
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

    def load(self, path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def save(self, path="job.yml"):
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, sort_keys=False, indent=4, allow_unicode=True)

    @cached_property
    def source_fields(self):
        fields = []
        for field_info in self.get("fields", {}).values():
            for props in field_info.values():
                fields.extend(as_list(props.get("src", [])))
        return fields

    @property
    def unused(self):
        return set(Source.missing) - set(Source.found)

    def import_source_files(self, path):
        """Write import for source files"""
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

        name = self["job"]["name"]
        rec = {
            "MulTitle": f"Batch import spreadsheet for the {name}",
            "MulCreator_tab": [self["fields"]["cataloging"]["cataloged_by"]["default"]],
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

    def tailor(self, path="job.yml"):

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


class Source(BaseDict):

    found = {}
    defaults = {}
    missing = {}

    def pop(self, *args):
        if not args or len(args) > 2:
            raise ValueError(f"pop accepts 1-2 arguments (got {args})")
        key = args[0]
        try:
            val = super().pop(key)
            if val == "--":
                val = ""
            self.__class__.found[key] = True
            return val
        except KeyError:
            if len(args) > 1:
                self.__class__.defaults[key] = True
                return args[1]
            else:
                self.__class__.missing[key] = True
                raise KeyError(f"'{key}' not found in source")

    def format_key(self, key):
        return str(key).casefold()

    def to_dict(self):
        return {self._keymap[k]: v for k, v in self.items()}


class ImportRecord(EMuRecord):

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
        self._source = None

        # Read mapped attachments
        for module, cl in self.module_classes.items():
            irns = self.job.get("irns", {}).get(module, {})
            if not cl.irns and irns and any(irns.values()):
                cl.irns = {k: v for k, v in irns.items() if v}

    @property
    def catnum(self):
        catnum = CatNum(self)
        self.records.setdefault(str(catnum), []).append(self)
        return catnum

    @property
    def cataloger(self):
        cataloger = self.job["fields"]["cataloging"]["cataloged_by"]["default"]
        try:
            return Person(cataloger)
        except ValueError:
            return Attachment(
                cataloger, irns=self.job.get("irns", {}).get("eparties", {})
            )

    @property
    def cataloged_date(self):
        return self["CatDateCataloged"]

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, val):

        self.data = self._check_data(val)
        self._source = Source(deepcopy(self.data))

        if any(self._source.values()):
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
                    self._map_props(props, field=field)

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
                    evt["LocContinent"] = (
                        Site({"country": evt["LocCountry"]}).map_continent().continent
                    )
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

    def to_emu_record(self):
        pass

    def pop(self, *args):
        return self._source.pop(*args)

    def unmapped(self):
        return sorted({k for k, v in self.source.items() if v})

    def attach(self, src, dst):
        """Maps a string"""
        module = self.schema.get_field_info(self.module, dst)["RefTable"]
        self[dst] = Attachment(
            self.pop(src, src), irns=self.job.get("irns", {}).get(module, {})
        ).to_emu()

    def map_age(self, src):
        keys = [
            "AgeGeologicAgeEra_tab",
            "AgeGeologicAgeSystem_tab",
            "AgeGeologicAgeSeries_tab",
            "AgeGeologicAgeStage_tab",
        ]
        vals = self.pop(src).split(" > ")
        for key, val in zip_longest(keys, vals):
            self.setdefault(key, []).append(val)

    def map_associated_taxa(
        self, src, named_part="Associated", texture_structure=None, comments=None
    ):
        named_part = self.pop(named_part, named_part)
        if not named_part.startswith("Associated"):
            named_part = f"Associated {named_part}"
        return self.map_taxa(src, named_part, texture_structure, comments)

    def map_catalog_number(self, number, prefix="", suffix="", delim="-"):
        prefix = self.pop(prefix, prefix)
        number = self.pop(number)
        suffix = self.pop(suffix, suffix)
        verbatim = f"{prefix}{number}{delim}{suffix}".rstrip(delim)
        catnum = CatNum(verbatim).to_emu()
        try:
            for key, val in catnum.items():
                self.setdefault(key, val)
        except TypeError:
            raise ValueError(f"Could not coerce value to catalog number: '{verbatim}'")

    def map_coordinates(self, *args, **kwargs):
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
        self, src_from, dst_from, src_to=None, dst_to=None, dst_verbatim=None
    ):
        val_from = self.pop(src_from).replace(" 00:00:00", "")
        if src_to:
            val_to = self.pop(src_to).replace(" 00:00:00", "")
            vals = [val_from]
            if val_to != val_from:
                vals.append(val_to)
            verbatim = " to ".join([v.strip() for v in vals])
        elif val_from:
            verbatim = val_from
            val_to = val_from
            for delim in RANGE_DELIMS:
                try:
                    vals = re.split(delim, val_from, flags=re.I)
                    val_from, val_to = [EMuDate(v.strip()) for v in vals]
                    break
                except ValueError:
                    pass
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
        self, src_from, unit=None, src_to=None, water_depth=True, bottom_depth=False
    ):
        val_from = self.pop(src_from)
        val_to = self.pop(src_to) if src_to else None
        if val_from:

            meas = parse_measurements(val_from, val_to, unit=unit)

            suffix = {
                "fathoms": "Fath",
                "feet": "Ft",
                "meters": "Met",
            }[meas.unit]

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
        self, src, dst="", key=None, mask='"{}"', raise_on_error=False
    ):
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

    def map_elevations(self, src_from, unit=None, src_to=None):
        val_from = self.pop(src_from)
        val_to = self.pop(src_to) if src_to else None
        if val_from:

            meas = parse_measurements(val_from, val_to, unit=unit)

            suffix = {
                "feet": "Ft",
                "meters": "Met",
            }[meas.unit]

            evt = self.setdefault("BioEventSiteRef", {})
            evt._set_path(f"TerElevationFrom{suffix}", meas.from_val)
            evt._set_path(f"TerElevationTo{suffix}", meas.from_val)

            verbatim = meas.text
            if re.search(r"[a-z]", meas.verbatim, flags=re.I):
                verbatim = meas.verbatim
            evt._set_path("TerVerbatimElevation", verbatim)

    def map_measurements(
        self,
        src_from,
        kind,
        src_to=None,
        unit=None,
        by=None,
        date=None,
        remarks=None,
        current="Yes",
    ):
        val_from = self.pop(src_from)
        val_to = self.pop(src_to) if src_to else None
        if val_from:

            unit = self.pop(unit, unit)
            by = self.pop(by, by)
            date = self.pop(date, date)
            current = self.pop(current, current)
            remarks = self.pop(remarks, remarks)

            if by:
                by = to_emu(by, "eparties")

            meas = parse_measurements(val_from, val_to, unit=unit)
            vals = [meas.from_val]
            if meas.to_val != meas.from_val:
                vals.append(meas.to_val)
            vals.sort(key=float)

            if len(vals) > 1:
                if remarks:
                    remarks += f" ({meas.text})"
                else:
                    remarks = meas.text

            for val in vals:
                self._set_path("MeaType_tab", kind)
                self._set_path("MeaVerbatimValue_tab", val)
                self._set_path("MeaVerbatimUnit_tab", unit)
                self._set_path("MeaByRef_tab", by)
                self._set_path("MeaDate0", date if date else self.cataloged_date)
                self._set_path("MeaRemarks_tab", remarks)
                self._set_path("MeaCurrent_tab", current)

    def map_notes(
        self,
        src,
        dst=None,
        date=None,
        kind="Comments",
        by=None,
        publish="No",
        delim="|",
    ):
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
                by = self["CatCatalogedByRef"]

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

    def map_parties(self, src, dst, related=None):
        for val in parse_names(self.pop(src)):
            self._set_path(dst, [val.to_emu()])
            for key, val in (related if related else {}).items():
                self._set_path(key, val)

    def map_prep(self, src, prep, remarks=None, remarks_only=False):
        remarks = self.pop(remarks, remarks)
        for key in as_list(src):
            try:
                val = self.pop(key)
            except KeyError:
                pass
            else:
                if val:
                    orig = val
                    val = val.lstrip("0")
                    if val and not val.isnumeric():
                        if remarks:
                            remarks = (
                                f"{val.rstrip('. ')}. {ucfirst(remarks).strip('. ')}."
                            )
                        else:
                            remarks = val
                        val = None
                    if val or remarks and remarks_only:
                        self.setdefault("ZooPreparationCount_tab", []).append(val)
                        self.setdefault("ZooPreparation_tab", []).append(prep)
                        self.setdefault("ZooPreparationRemarks_tab", []).append(remarks)
                return
        raise KeyError(f"'{src}' not found in source")

    def map_preps(self, src, preps):
        keys = as_list(src)
        missed = []
        for key in keys:
            try:
                vals = [s[0] for s in split(self.pop(key))]
            except KeyError:
                missed.append(KeyError)
            else:
                preps = {k.casefold(): v for k, v in preps.items()}
                for val in vals:
                    try:
                        prep, remarks = preps[val.casefold()]
                    except KeyError:
                        prep = val
                        remarks = ""
                    self.setdefault("ZooPreparation_tab", []).append(prep)
                    self.setdefault("ZooPreparationRemarks_tab", []).append(remarks)
        if missed == keys:
            raise KeyError(f"'{src}' not found in source")

    def map_primary_taxa(
        self, src, named_part="Primary", texture_structure=None, comments=None
    ):
        named_part = self.pop(named_part, named_part)
        if not named_part.startswith("Primary"):
            named_part = f"Primary {named_part}"
        return self.map_taxa(src, named_part, texture_structure, comments)

    def map_related(self, src, relationship):
        val = self.pop(src)
        if val:
            for val, _ in split(val):

                try:
                    val = parse_catnums(val)[0]
                    if val.prefix and val.prefix not in {"B", "C", "G", "M", "S", "R"}:
                        raise IndexError
                    if not val.code:
                        val.code = "NMNH"
                    kind = "NMNH catalog number"
                    ref = val.to_emu()
                except IndexError:
                    val = val
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
        self, site_num, source="Collector", name=None, rec_class="Event"
    ):
        evt = self.setdefault("BioEventSiteRef", {})
        evt["LocSiteStationNumber"] = self.pop(site_num, site_num)
        evt["LocSiteNumberSource"] = self.pop(source, source)
        evt["LocRecordClassification"] = self.pop(rec_class, rec_class)
        if name is not None:
            evt["LocSiteName_tab"] = self.pop(name, name)

    def map_storage_location(self, building, room_pod, case_shelves, drawer_shelf):
        """Maps storage location to permanent and current locations

        Parameters
        ----------
        building : str
            name of column containing the building
        room_pod : str
            name of column containing the room or pod
        case_shelves : str
            name of column containing the case or shelves
        drawer_shelf : str
            name of column containing the drawer or shelf

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
        if self["CatDivision"] in ("Mineralogy", "Petrology & Volcanology"):

            if loc["LocLevel3"] and loc["LocLevel3"].isnumeric():
                loc["LocLevel3"] = loc["LocLevel3"].zfill(3)

            if loc["LocLevel4"] and loc["LocLevel4"].isnumeric():
                loc["LocLevel4"] = loc["LocLevel4"].zfill(2)

        loc = Location(loc).to_emu()

        self["LocPermanentLocationRef"] = loc
        self["LocLocationRef_tab"] = [loc]

    def map_taxa(
        self, src, named_part="Associated", texture_structure=None, comments=None
    ):

        # Record whether arguments are fields or verbatim
        part_is_field = named_part in self._source
        texture_is_field = texture_structure in self._source
        comment_is_field = comments in self._source

        # Split values
        for src in as_list(src):
            taxa = split(self.pop(src))
            if taxa:
                break
        parts = split(self.pop(named_part, named_part))
        textures = split(self.pop(texture_structure, texture_structure), "|")
        comments = split(self.pop(comments, comments))

        if taxa:

            # Remove the delimiter from the split values
            taxa = [t[0] for t in taxa]
            parts = [p[0] for p in parts]
            textures = [t[0] for t in textures]
            comments = [c[0] for c in comments]

            # Repeat value in associated fields if verbatim
            if not part_is_field and len(parts) == 1:
                if parts[0].startswith("Primary"):
                    parts += [parts[0].replace("Primary", "Associated")] * (
                        len(taxa) - 1
                    )
                else:
                    parts = parts * len(taxa)
            if not texture_is_field and len(parts) == 1:
                textures = textures * len(taxa)
            if not comment_is_field and len(parts) == 1:
                comments = comments * len(taxa)

            parts += [None] * (len(taxa) - len(parts))
            textures += [None] * (len(taxa) - len(textures))
            comments += [None] * (len(taxa) - len(comments))

            for taxon, part, texture, comment in zip(taxa, parts, textures, comments):

                # Handle parentheticals
                if taxon.endswith(")"):
                    taxon, parens = [s.strip() for s in taxon.rstrip(")").split("(")]
                    textures = []
                    for paren, _ in split(parens):
                        if paren in {"TAS"} or paren.startswith("var."):
                            taxon = f"{taxon} ({paren})"
                        elif paren in {"vein", "xenolith"}:
                            if not part in {"Primary", "Associated"}:
                                raise ValueError(
                                    f"Taxon includes part, but part was already"
                                    f" provided: {taxon}, part={part}"
                                )
                            part = f"{part} {paren.title()}"
                        else:
                            textures.append(paren)

                    if textures:
                        if texture:
                            raise ValueError(
                                f"Taxon includes texture, but texture was already"
                                f" provided: {taxon}, texture={texture}"
                            )
                        texture = "; ".join(textures)

                taxon = self.tree.place(taxon).to_emu()
                if "irn" in taxon:
                    taxon = {"irn": taxon["irn"]}
                self.setdefault("IdeTaxonRef_tab", []).append(taxon)
                self.setdefault("IdeNamedPart_tab", []).append(part)
                self.setdefault("IdeTextureStructure_tab", []).append(texture)
                self.setdefault("IdeComments_tab", []).append(comment)

    def map_volcano(self, src_name=None, src_num=None, src_feature=None):
        vols = []
        missed = False

        # Get country to improve match quality
        evt = self.get("BioEventSiteRef", {})
        country = evt.get("LocCountry")

        vname = None
        if src_name:
            vname = self.pop(src_name)
            if vname:
                try:
                    vols.extend(self.gvp.find(vname, country=country))
                except ValueError:
                    missed = True

        vnum = None
        if src_num:
            vnum = self.pop(src_num, None)
            if vnum:
                try:
                    vols.extend(self.gvp.find(vnum, country=country))
                except ValueError:
                    missed = True

        fname = None
        if src_feature:
            fname = self.pop(src_feature, None)
            if fname:
                try:
                    vols.extend(self.gvp.find(fname, country=country))
                except ValueError:
                    missed = True

        if vols and not missed:
            vnames = [v.gvp_volcano for v in vols]
            vnums = [v.gvp_number for v in vols]
            fnames = [v.name for v in vols if v.kind != "volcano"]
            if len(set(vnames)) == 1 and len(set(vnums)) == 1 and len(set(fnames)) <= 1:
                evt["VolVolcanoName"] = vnames[0]
                evt["VolVolcanoNumber"] = vnums[0]
                if fnames:
                    evt["VolSubfeature"] = fnames[0]
                return

        if vname:
            evt["VolVolcanoName"] = vname
        if vnum:
            evt["VolVolcanoNumber"] = vnum
        if fname:
            evt["VolSubfeature"] = fname

    def map_contingent(self, src, dst, contingent):
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

    def map_to_yaml(self, dst, **kwargs):
        kwargs = {k: self.pop(v) for k, v in kwargs.items()}
        kwargs = {k: v for k, v in kwargs.items() if v}
        if kwargs:
            self._set_path(dst, yaml.dump(kwargs))

    def add_receipt(self, data=None, path=None):
        """Adds receipt to record

        Parameters
        ----------
        path : str
            path to receipt file

        Returns
        -------
        None
        """

        data = data if data else self.data

        # Exclude ignored fields from receipt
        ignore = {s.lower() for s in self.job.get("ignore", [])}
        data = {k: v for k, v in data.items() if k.lower() not in ignore}

        # Test receipt even if not writing it
        if self.test:
            return generate_receipt(data, str(self.catnum))

        if path is None:
            path = f"receipts/{self.catnum.slug()}.txt"

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
            str(self.catnum),
            str(self.cataloger),
            overwrite=not self.test,  # always overwrite if not a test
        )
        self.setdefault("MulMultiMediaRef_tab", []).insert(0, receipt)

    def georeference(
        self, lats, lons, crs, src, method, det_by, det_date, radius, radius_unit, notes
    ):
        """Updates record with a manual georeference

        Parameters
        ----------
        lats : mixed
            latitude as string or list of strings
        lons : mixed
            longitude as string or list of strings
        crs : str
            coordinate reference system
        src : list
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

        if isinstance(src, list):
            src = " | ".join(src)
        evt.setdefault("LatDetSource_tab", []).append(src)

        evt.setdefault("LatLatLongDetermination_tab", []).append(method)

        det_by = Person(det_by).to_emu() if det_by else None
        evt.setdefault("LatDeterminedByRef_tab", []).append(det_by)

        evt.setdefault("LatDetDate0", []).append(det_date)

        if radius:
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
    def csvs(src=None, **kwargs):
        """Converts workbook sheets to CSV"""
        if src is None:
            src = ImportRecord.job["job"]["import_file"]
        dst = os.path.join(os.path.dirname(src), "csvs")
        kwargs = ImportRecord.job["job"].get("open_kwargs", {}).copy()
        return extract_csvs(src, dst, **kwargs)

    @staticmethod
    def compare(orig_path=None, clean_path=None, ignore_case=True, ignore_spaces=True):
        def _describe_move(val, other, other_row, direction):
            if val and not other and other_row.isin([val]).any():
                keys = []
                for key, val_ in other_row.items():
                    if val == val_:
                        keys.append(key)
                return f"Moved {direction} {keys[0]}"
            return ""

        if orig_path is None:
            orig_path = ImportRecord.job["job"]["orig_import_file"]

        if clean_path is None:
            clean_path = ImportRecord.job["job"]["import_file"]

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
                                    "note": move if move else "",
                                }
                            )

        return pd.DataFrame(changes)

    @staticmethod
    def validate(path, *args, **kwargs):
        return Validator(path).validate(*args, **kwargs)

    def _add_source(self, path, join_key):
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

    @staticmethod
    def _check_data(data):
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
    def _keyer(val):
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
    def _combine_dicts(*dcts):
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

    def _map_props(self, props, field=None, **kwargs):
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

    def _set_path(self, path, vals, delim=None):
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
                delim_ = [v[1] for v in existing if v[1]][0]
                existing = [v[0] for v in existing]
                obj[last] = (delim_ if delim_ else delim).join(existing + vals)
            except KeyError:
                obj[last] = (
                    vals[0] if len(vals) == 1 else delim.join([v for v in vals if v])
                )
            except TypeError:
                print(path, vals, delim, existing)
                raise

    def _suppressible(self, exc, key):
        return str(exc).strip("'") in set([key] + self.job.source_fields)


def format_val(val):
    """Removes extra whitespace from a string

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


def split(vals, delim="|;", trim=True):
    """Splits a string into a list using common delimiters

    Parameters
    ----------
    vals : mixed
        string to split or list of values to format
    delim : str
        delimiters to use to split a string in order of priority. Stops
        splitting at the first matching delimiter.
    trim : bool
        whether or not to trim values after splitting

    Returns
    -------
    list of str
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
    split_parens = False
    for val in vals:
        if "(" in combined[-1] and ")" not in combined[-1]:
            combined[-1] += delim + val
            split_parens = True
        else:
            combined.append(val)
    vals = combined

    # Strip whitespace from values
    if trim:
        vals = [s.strip() if isinstance(s, str) else s for s in vals]

    # Standardize spacing on delimiter
    delim = {"|": " | ", ";": "; ", ",": ", ", "": ""}[delim]

    return [(s, delim if len(vals) > 1 else "") for s in vals]


def generate_receipt(row, catnum):

    # Clear empty, non-zero keys
    row = {k: v.strip() for k, v in row.items() if (v or v == 0)}

    # Create YAML receipt
    receipt = f"# Verbatim data for {catnum} from cataloging spreadsheet\n"
    receipt += yaml.dump(row, sort_keys=False, allow_unicode=True, width=1e6)

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
            raise ValueError(f"Receipt contains line with no key: {receipt} ({row})")

    # Check for additional quoted vales
    if ": '" in receipt:
        orig = yaml.dump(row, sort_keys=False, allow_unicode=True, width=1e6)
        warnings.warn(f"Quoted values in receipt: {receipt} ({orig})")

    return receipt


def write_receipt(row, path, catnum, overwrite=False):
    """Writes to data to a file

    Parameters
    ----------
    row : dict
        data
    path : str
        path to which to write the file
    catnum : str
        catalog number
    overwrite : bool
        whether to overwrite an existing file at path

    Returns
    -------
    str
        path to file
    """

    # Append filename if path is a directory
    if os.path.isdir(path):
        path = os.path.join(path, f"{to_attribute(catnum)}.yml")

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
            f.write(generate_receipt(row, catnum))

    return path


def wrap_receipt(row, path, catnum, cataloger, overwrite=False):
    """Writes to data to a file and creates an emultimedia record for the file

    Parameters
    ----------
    row : dict
        data
    path : str
        path to which to write the file
    catnum : str
        catalog number
    cataloger : str
        name of the cataloger
    overwrite : bool
        whether to overwrite an existing file at path

    Returns
    -------
    dict
        emultimedia record for the receipt file
    """
    path = write_receipt(row, path, catnum=catnum, overwrite=overwrite)
    return {
        "MulTitle": f"{catnum} source data",
        "MulCreator_tab": [cataloger],
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


def extract_csvs(src, dst="csvs", prefix="", suffix="", **kwargs):

    params = kwargs.copy()
    params["dtype"] = str
    params["sheet_name"] = None

    try:
        os.mkdir(dst)
    except OSError:
        pass

    basename = os.path.splitext(os.path.basename(src))[0]

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


def _pad(val, length):
    if len(val) > 1 and len(val) != length:
        raise ValueError(f"Invalid length: {val} (n={length})")
    if len(val) == 1 and length > 1:
        val = [val[0] for _ in range(length + 1)]
    return val


def _is_irn(val, min_val=1000000, max_val=30000000):
    try:
        val = int(val)
    except ValueError:
        return False
    else:
        return min_val <= val <= max_val


def _read_ancillary():
    ImportRecord.ancillary = []
    for source in ImportRecord.job.get("job", {}).get("additional_files", []):
        ImportRecord._add_source(**source)


# Define deferred class attributes
LazyAttr(ImportRecord, "job", Job)
LazyAttr(ImportRecord, "geo", Georeferencer)
LazyAttr(ImportRecord, "gvp", GVPVolcanoes)
LazyAttr(ImportRecord, "tree", get_tree)
LazyAttr(ImportRecord, "ancillary", _read_ancillary)
