"""Contains methods to hash a file or image data from a file"""

from __future__ import unicode_literals

import hashlib
import json
import logging
import os
import shutil
import subprocess
from collections import namedtuple
from pathlib import Path

import yaml
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

    def hashes(self):
        return self._hashes

    @property
    def index(self):
        index = {}
        for path, idx in self._indexes.items():
            index.update({path.parent / k: v for k, v in idx.items()})
        return index

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
        size (int): size of block. Should be multiple of 128.

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


def hash_file_if_exists(path):
    """Returns MD5 hash of a file, returning None if file doesn't exist

    Args:
        path (str): path to image

    Returns:
        Hash as string
    """
    try:
        return hasher(open(path, "rb"))
    except IOError:
        return None


def hash_image_data(path, output_dir="images"):
    """Returns MD5 hash of the image data in a file

    Args:
        path (str): path to image file

    Returns:
        Hash of image data as string
    """
    path = os.path.abspath(path)
    try:
        return hashlib.md5(Image.open(path).tobytes()).hexdigest()
    except IOError:
        # Encountered a file format that PIL can't handle. Convert
        # file to something usable, hash, then delete the derivative.
        # The derivatives can be compared to ensure that the image hasn't
        # been messed up. Requires ImageMagick.
        fn = os.path.basename(path)
        jpeg = os.path.splitext(fn)[0] + "_temp.jpg"
        cmd = 'magick "{}" "{}"'.format(path, jpeg)
        return_code = subprocess.call(cmd, cwd=output_dir)
        if return_code:
            raise IOError("Hash failed: {}".format(fn))
        dst = os.path.join(output_dir, jpeg)
        hexhash = hashlib.md5(Image.open(dst).tobytes()).hexdigest()
        os.remove(dst)
        return hexhash


def fnv1a_64(data):
    """Alternative FNV hash algorithm used in FNV-1a

    Adapted from https://github.com/znerol/py-fnvhash
    """
    hval_init = 0xCBF29CE484222325
    fnv_prime = 0x100000001B3
    fnv_size = 2**64

    hval = hval_init
    for byte in data:
        hval = hval ^ byte
        hval = (hval * fnv_prime) % fnv_size
    return hex(hval)


def fast_hash(data):
    return fnv1a_64(data)


def is_newer(path, other, other_must_exist=False):
    """Tests if file has been modified more recently than another file"""
    path_mtime = get_mtime(path)
    other_mtime = get_mtime(other, other_must_exist)
    return path_mtime > other_mtime


def is_older(path, other, other_must_exist=False):
    """Tests if file has been modified less recently than another file"""
    return not is_newer(other, path, other_must_exist)


def is_different(path, other, compare_image_data=False):
    """Tests if two files are different"""
    if compare_image_data:
        return hash_image_data(path) != hash_image_data(other)
    return hash_file(path) != hash_file(other)


def get_mtime(fp, must_exist=True):
    """Gets the modified time for a file"""
    try:
        return os.path.getmtime(fp)
    except FileNotFoundError:
        if not must_exist:
            return 0
        raise


def copy_if(src, dst, newer=True, different=True):
    """Copies source to destination if criteria given in kwargs are met"""
    assert os.path.isfile(src)
    # Ensure that dst is a file
    if "." not in os.path.basename(dst):
        dst = os.path.join(dst, os.path.basename(src))
    # Ensure that the destination directory exists
    try:
        os.makedirs(os.path.dirname(dst))
    except OSError:
        pass
    # Perform tests
    try:
        open(dst, "r")
    except IOError:
        copy_file = True
    else:
        newer = is_newer(src, dst) if newer else True
        different = is_different(src, dst) if different else True
        copy_file = newer and different
    if copy_file:
        shutil.copy2(src, dst)
        return True
    return False


def load_dict(fp, fp_src=None, encoding="utf-8"):
    """Attempts to load dict from JSON or YML"""
    if fp_src and is_newer(fp_src, fp):
        raise IOError("Source file is newer")
    func = json.load
    if os.path.splitext(fp)[-1] in {".yaml", ".yml"}:
        func = yaml.safe_load
    try:
        with open(fp, "r", encoding=encoding) as f:
            result = func(f)
    except (IOError, OSError, json.JSONDecodeError):
        raise IOError("Could not load {}".format(fp))
    else:
        if result:
            return result
        raise IOError("File empty: {}".format(fp))


def skip_hashed(f):
    """Skips hashed lines at the beginning of a file"""
    seek = 0
    # World's dumbest BOM check
    first_8 = f.read(8)
    f.seek(3)
    if f.read(8) == first_8:
        seek = 3
    # Read the file until first unhashed line
    f.seek(0)
    for line in f:
        if not line.strip('"').startswith("#"):
            break
        seek += len(line)
    f.seek(seek)
    return f
