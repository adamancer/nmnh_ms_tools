"""Contains methods to hash files and image data"""

import hashlib
import json
import logging
import os
from collections import namedtuple
from pathlib import Path

import pandas as pd
from PIL import Image


logger = logging.getLogger(__name__)

HashedFile = namedtuple("HashedFile", ("path", "hash"))


class HashCheck:

    def __init__(self):
        self.filename = "hashes.json"
        self._indexes = {}
        self._filepaths = {}
        self._filenames = {}
        self._hashes = {}

    def __getitem__(self, key):
        # Key is a file path
        try:
            path = Path(key).resolve()
            return [HashedFile(path, self._filepaths[path])]
        except KeyError:
            pass

        # Key is a hash
        try:
            return [HashedFile(p, key) for p in self._hashes[key]]
        except KeyError:
            pass

        # Key is a file name
        try:
            return [HashedFile(p, self._filepaths[p]) for p in self._filenames[key]]
        except KeyError:
            pass

        raise KeyError(f"Could not resolve key: {key}")

    def __iter__(self):
        return iter(self._filepaths)

    @property
    def index(self):
        index = {}
        for path, idx in self._indexes.items():
            index.update({path.parent / k: v for k, v in idx.items()})
        return index

    def hashes(self):
        return self._hashes

    def hash_file(self, path, overwrite=True):
        path = Path(path).resolve()
        idx_path, index = self.load_index(path)
        try:
            if overwrite:
                raise KeyError
            index[path.name]
        except KeyError:
            logger.info(f"Hashing {path}")
            index[path.name] = hash_file(path)
            with open(idx_path, "w") as f:
                json.dump(index, f, indent=2, sort_keys=True)
            self._update_lookups()
        return HashedFile(path, index[path.name])

    def get_hashes(self, path, pattern="*.*", overwrite=False):
        path = Path(path).resolve()
        if path.is_file():
            self.hash_file(path, overwrite=overwrite)
        else:
            for path in path.glob(f"**/{pattern}"):
                if path.is_file() and path.name != self.filename:
                    self.hash_file(path, overwrite=overwrite)
        self._update_lookups()
        return self

    def get_duplicates(self):
        return {k: v for k, v in self._hashes.items() if len(v) > 1}

    def load_index(self, path):
        parent = Path(path).resolve()
        if parent.is_file():
            parent = parent.parent

        idx_path = parent / self.filename
        try:
            index = self._indexes[idx_path]
        except KeyError:
            try:
                with open(idx_path) as f:
                    index = json.load(f)
            except FileNotFoundError:
                index = {}
            else:
                # Remove files that do not exist
                names = set(index) & set([p.name for p in parent.iterdir()])
                index = {k: v for k, v in index.items() if k in names}

                # Sort and update index file
                sorted_index = dict(sorted(index.items(), key=lambda kv: kv[0]))
                if list(index) != list(sorted_index):
                    with open(idx_path, "w") as f:
                        json.dump(sorted_index, f)
            finally:
                self._indexes[idx_path] = index

        return (idx_path, index)

    def _update_lookups(self):
        self._filepaths = {}
        self._filenames = {}
        self._hashes = {}
        for idx_path, index in self._indexes.items():
            for fn, hash_ in index.items():
                path = Path(idx_path.parent) / fn
                self._filepaths[path] = hash_
                self._filenames.setdefault(path.name, []).append(path)
                self._hashes.setdefault(hash_, []).append(path)


def hasher(filestream, size=8192):
    """Generate MD5 hash for a file

    Args:
        filestream (file): stream of file to hash
        size (int): size of block. Must be multiple of 128.

    Return:
        MD5 hash of file
    """
    if size % 128:
        raise ValueError("Size must be a multiple of 128")
    md5_hash = hashlib.md5()
    while True:
        chunk = filestream.read(size)
        if not chunk:
            break
        md5_hash.update(chunk)
    return md5_hash.hexdigest()


def hash_file(path):
    """Returns MD5 hash of a file

    Args:
        path (str): path to image

    Returns:
        Hash as string
    """
    with open(path, "rb") as f:
        return hasher(f)


def hash_image_data(path):
    """Returns MD5 hash of the image data in a file

    Args:
        path (str): path to image file

    Returns:
        Hash of image data as string
    """
    return hashlib.md5(Image.open(os.path.abspath(path)).tobytes()).hexdigest()


def fnv1a_64(val, encoding=None):
    """Hashes value according to alternative FNV hash algorithm used in FNV-1a

    Adapted from https://github.com/znerol/py-fnvhash.

    Args:
        val (bytes): the value to hash. If a string is given, the function will
            try to coerce it to bytes.
        encoding (bool): the encoding to use when decoding a str. Required if val
            is a string containing non-ASCII characters.

    Returns:
        Hash as hex string
    """
    if isinstance(val, str):
        val = bytes(val, "ascii") if val.isascii() else bytes(val, encoding=encoding)

    hval_init = 0xCBF29CE484222325
    fnv_prime = 0x100000001B3
    fnv_size = 2**64

    hval = hval_init
    for byte in val:
        hval = hval ^ byte
        hval = (hval * fnv_prime) % fnv_size
    return hex(hval)[2:]


def fast_hash(*args, **kwargs):
    return fnv1a_64(*args, **kwargs)


def is_newer(path, other, missingok=True):
    """Tests if file has been modified more recently than another file

    Returns:
        True if path is newer or missingok is True and the other file does not exist
    """
    mtime1 = os.path.getmtime(path)
    try:
        mtime2 = os.path.getmtime(other)
    except FileNotFoundError:
        if missingok:
            return True
        raise
    return mtime1 > mtime2


def is_different(path, other, compare_image_data=False):
    """Tests if two files are different"""
    if compare_image_data:
        return hash_image_data(path) != hash_image_data(other)
    return hash_file(path) != hash_file(other)


def skip_hashed(f):
    """Skips hashed lines at the beginning of a file"""
    size = 0
    for i, line in enumerate(f):
        if line.startswith("#") or not i and line[1] == "#":
            size += len(line)
        else:
            break
    f.seek(0)
    f.read(size)
    return f


def read_csv(*args, **kwargs):
    """Convenience function a read a CSV file

    Parameters
    ---------
    args, kwargs :
        parameters to pass to pd.read_csv()

    Returns:
    list[dict]
        content of CSV as list of records
    """
    kwargs.setdefault("comment", "#")
    kwargs.setdefault("dtype", "str")
    return pd.read_csv(*args, **kwargs).to_dict("records")


def read_tsv(*args, **kwargs):
    """Convenience function a read a TSV file

    Parameters
    ---------
    args, kwargs :
        parameters to pass to pd.read_csv()

    Returns:
    list[dict]
        content of CSV as list of records
    """
    kwargs.setdefault("delimiter", "\t")
    return read_csv(*args, **kwargs)


def read_json(fp: str | Path, encoding: str = "utf-8", **kwargs):
    """Convenience function a read a JSON file

    Parameters
    ----------
    fp : str | Path
        path to JSON file
    encoding : str
        encoding of JSON file
    kwargs:
        parametets to pass to json.load()
    """
    with open(fp, encoding=encoding) as f:
        return json.load(f, **kwargs)
