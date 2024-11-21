import pprint
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import yaml

from ..specimen_numbers import parse_spec_num
from ...utils import hash_file, hash_image_data, oxford_comma, to_attribute


class MetadataField:

    def __init__(self, read_fields, write_fields, group=None, length=32, escape=False):
        self.read_fields = read_fields
        self.write_fields = write_fields
        self.group = group
        self.length = length
        self.escape = escape

    def __str__(self):
        return (
            f"MetadataField("
            f"read_fields={repr(self.read_fields)}, "
            f"write_fields={repr(self.write_fields)}, "
            f"length={repr(self.length)}"
        )

    def __repr__(self):
        return str(self)

    def read(self, metadata):
        for field in self.read_fields:
            val = metadata.get(field)
            if val:
                return val

    def write(self, vals):
        if not isinstance(vals, (list, tuple)):
            vals = [vals]
        args = {}
        for val in vals:
            if len(val) > self.length:
                warnings.warn(
                    f"Value too long: {self.write_fields} == {repr(val)} (max={self.length})"
                )
            if self.escape:
                val = val.replace(",", "|,")
            for field in self.write_fields:
                args.setdefault(self.group, []).append((field, val))
        return args


class MediaFile:

    with open(
        Path.home() / "data" / "nmnh_ms_tools" / "metadata" / "metadata.yml"
    ) as f:
        fields = {k: MetadataField(**v) for k, v in yaml.safe_load(f).items()}

    def __init__(self, data, **kwargs):

        self._path = None
        self._metadata = None
        self._mapped = None
        self._kwargs = kwargs

        if isinstance(data, (str, Path)):
            self.path = data
        else:
            self.path = data["Multimedia"]
            self._metadata = {}
            self._mapped = self.from_emu(data)

    def __str__(self):
        return pprint.pformat(self.mapped)

    def __repr__(self):
        return repr(self.mapped)

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, path):
        self._path = Path(path).resolve()

    @property
    def metadata(self):
        if self._metadata is None:
            self._metadata = self.read_metadata(**self._kwargs)
        return self._metadata

    @property
    def mapped(self):
        if self._mapped is None:
            self._mapped = self.from_file()
        return self._mapped

    @property
    def exists(self):
        try:
            open(self._path)
        except FileNotFoundError:
            return False
        return True

    def hash(self):
        return hash_file(self.path)

    def hash_image_data(self):
        return hash_image_data(self.path)

    def read_metadata(self, **kwargs):
        cmd = ["exiftool", self.path]
        for key, val in kwargs.items():
            cmd.extend([f"-{key}", val])
        result = subprocess.run(cmd, capture_output=True)
        metadata = {}
        for line in re.split(rb"(?:\r\n|\n)", result.stdout):
            try:
                key, val = [s.strip() for s in line.split(b":", 1)]
            except ValueError:
                pass
            else:
                # Fix bizarro encoding
                val = val.replace(b"\xd2", b'"')
                val = val.replace(b"\xd3", b'"')
                val = val.replace(b"\xd5", b"'")
                val = val.replace(b"\xe2\x80\x99", b"'")
                try:
                    metadata[key.decode()] = val.decode(kwargs.get("charset", "utf-8"))
                except UnicodeDecodeError as exc:
                    raise ValueError(
                        f"Could not decode metadata in {self.path}: {key} => {val}"
                    ) from exc

        self.metadata = metadata

        return metadata

    def rename(self, dst=None):
        """Renames the file based on available metadata"""
        dst = self._get_std_name(dst)
        self._path.rename(dst)
        return self.copy_metadata_to(dst)

    def copy_to(self, dst=None):
        dst = self._get_std_name(dst)
        shutil.copy2(self._path, dst)
        return self.copy_metadata_to(dst)

    def copy_metadata_to(self, path):
        mm = self.__class__(path)
        mm._mapped = self.mapped.copy()
        mm.mapped["unique_id"] = None
        return mm

    def digest(self):
        return self.metadata

    def embed_metadata(self, path=None, **kwargs):
        command = ["exiftool"]

        if not kwargs:
            raise ValueError("No metadata provided")

        structures = {}
        for key, field in self.fields.items():
            vals = kwargs.get(key)
            if vals:
                for group, vals in field.write(vals).items():
                    for field, val in vals:
                        if group is None:
                            command.append(f"-{field}={str(val)}")
                        else:
                            structures.setdefault(group, {}).setdefault(
                                field, []
                            ).append(val)

        # Group structures into rows
        rows = {}
        for group, items in structures.items():
            rows[group] = []
            for key, vals in items.items():
                for i, val in enumerate(vals):
                    val = str(val)
                    try:
                        rows[group][i].append(f"{key}={val}")
                    except IndexError:
                        rows[group].append([f"{key}={val}"])

        for group, rows in rows.items():
            val = "[" + ",".join(["{" + ",".join(row) + "}" for row in rows]) + "]"
            command.append(f"-{group}={val}")

        if len(command) > 1:
            path = Path(path).resolve() if path else self.path
            if path != self.path:
                try:
                    open(path)
                except FileNotFoundError:
                    shutil.copy2(self.path, path)

            command.extend(["-overwrite_original", str(path)])
            result = subprocess.run(command, capture_output=True)
            if result.returncode:
                raise ValueError(f"Failed to embed metadata: {result}")
            return True
        raise ValueError(f"Invalid command: {command}")

    def from_file(self):
        return self._clean_mapped(
            {k: v.read(self.metadata) for k, v in self.fields.items()}
        )

    def from_emu(self, rec):

        # Get identifier
        ids = {}
        try:
            grid = rec.grid("AdmGUIDType_tab")
        except KeyError:
            pass
        else:
            for row in grid:
                ids[row["AdmGUIDType_tab"]] = row["AdmGUIDValue_tab"]

        title = ids.get("Photographer Number", ids.get("EZIDMM"))
        unique_id = ids.get("EZIDMM")

        creator = oxford_comma(rec.get("MulCreator_tab", ""))
        credit = creator
        if creator in {
            "Chip Clark",
            "Greg Polley",
        }:
            credit += ", NMNH"

        licenses = {
            "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
        }

        headline = rec.get("MulTitle")

        # Extract a single, well-formed catalog number from the headline
        obj_source_ids = []
        obj_sources = []
        if headline:
            try:
                catnum = parse_spec_num(headline.split("(")[1].rstrip(")"))
            except ValueError:
                pass
            else:
                obj_source_ids = [str(catnum)]
                obj_sources = ["Smithsonian NMNH"]

        return self._clean_mapped(
            {
                "caption": rec.get("MulDescription"),
                "copyright": rec.get("DetSIRightsStatement"),
                "creator": creator,
                "credit": credit,
                "headline": headline,
                "license": licenses.get(rec.get("DetSIRightsStatement")),
                "jobid": rec.get("AdmImportIdentifier", ""),
                "keywords": rec.get("DetSubject_tab", []),
                "obj_source_ids": obj_source_ids,
                "obj_sources": obj_sources,
                "source": rec.get("DetSource"),
                "subjectcode": None,
                "title": title,
                "unique_id": unique_id,
            }
        )

    def _clean_mapped(self, mapped):
        for key in self.fields:
            if not mapped.get(key):
                mapped[key] = None

        for key in (
            "keywords",
            "obj_sources",
            "obj_source_ids",
            "obj_titles",
        ):
            val = mapped[key]
            if not val:
                val = []
            elif not isinstance(val, list):
                val = val.split(", ")
            mapped[key] = val

        return mapped

    def _get_std_name(self, dst=None, keys=("headline", "creator", "title")):
        if dst is None:
            dst = self._path.parent
        dst = Path(dst)
        if dst.is_dir():
            parts = [self.mapped[k] for k in keys]
            stem = "_".join((to_attribute(p).replace("_", "-") for p in parts if p))
            dst = dst / f"{stem}{self._path.suffix}"

            # Exiftool has a max path length of 246 characters in Windows. Adjust
            # the filename if it's longer than 240 to account for duplicates.
            while len(str(dst.resolve())) >= 240:
                dst = dst.parent / (dst.stem.rsplit("_", 1)[0] + dst.suffix)

            for i in range(1, 10):
                try:
                    open(dst)
                except FileNotFoundError:
                    break
                else:
                    parts = dst.stem.split("_")
                    try:
                        last = int(parts[-1])
                    except ValueError:
                        pass
                    else:
                        if 1 <= last <= 9:
                            parts.pop(-1)
                    dst = dst.parent / f"{'_'.join(parts)}_{i}{dst.suffix}"
        return dst
