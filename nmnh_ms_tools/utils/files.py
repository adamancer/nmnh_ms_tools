"""Contains methods to hash a file or image data from a file"""
from __future__ import unicode_literals

import csv
import hashlib
import json
import os
import shutil
import subprocess

import yaml
from PIL import Image




def hasher(filestream, size=8192):
    """Generate MD5 hash for a file

    Args:
        filestream (file): stream of file to hash
        size (int): size of block. Should be multiple of 128.

    Return:
        MD5 hash of file
    """
    if size % 128:
        raise ValueError('Size must be a multiple of 128')
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
    with open(path, 'rb') as f:
        return hasher(f)


def hash_file_if_exists(path):
    """Returns MD5 hash of a file, returning None if file doesn't exist

    Args:
        path (str): path to image

    Returns:
        Hash as string
    """
    try:
        return hasher(open(path, 'rb'))
    except IOError:
        return None


def hash_image_data(path, output_dir='images'):
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
        jpeg = os.path.splitext(fn)[0] + '_temp.jpg'
        cmd = 'magick "{}" "{}"'.format(path, jpeg)
        return_code = subprocess.call(cmd, cwd=output_dir)
        if return_code:
            raise IOError('Hash failed: {}'.format(fn))
        dst = os.path.join(output_dir, jpeg)
        hexhash = hashlib.md5(Image.open(dst).tobytes()).hexdigest()
        os.remove(dst)
        return hexhash


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
    if '.' not in os.path.basename(dst):
        dst = os.path.join(dst, os.path.basename(src))
    # Ensure that the destination directory exists
    try:
        os.makedirs(os.path.dirname(dst))
    except OSError:
        pass
    # Perform tests
    try:
        open(dst, 'r')
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


def load_dict(fp, fp_src=None, encoding='utf-8'):
    """Attempts to load dict from JSON or YML"""
    if fp_src and is_newer(fp_src, fp):
        raise IOError('Source file is newer')
    func = json.load
    if os.path.splitext(fp)[-1] in {'.yaml', '.yml'}:
        func = yaml.safe_load
    try:
        with open(fp, 'r', encoding=encoding) as f:
            result = func(f)
    except (IOError, OSError, json.JSONDecodeError):
        raise IOError('Could not load {}'.format(fp))
    else:
        if result:
            return result
        raise IOError('File empty: {}'.format(fp))


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
        if not line.strip('"').startswith('#'):
            break
        seek += len(line)
    f.seek(seek)
    return f
