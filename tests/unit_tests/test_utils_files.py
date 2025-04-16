"""Tests the PrefixedNum class"""

import time
from pathlib import Path

import pytest
from PIL import Image

from nmnh_ms_tools.utils import (
    HashCheck,
    get_citrix_path,
    get_windows_path,
    hasher,
    hash_file,
    hash_image_data,
    is_different,
    is_newer,
    fast_hash,
    skip_hashed,
    ucfirst,
)


@pytest.fixture(scope="session")
def output_dir(tmpdir_factory):
    return Path(tmpdir_factory.mktemp("test_utils_files"))


@pytest.fixture(scope="session")
def paths(output_dir):
    paths = [output_dir / f"{i}.txt" for i in range(1, 4)]
    with open(paths[0], "w") as f:
        f.write("abc")
    time.sleep(0.01)
    with open(paths[1], "w") as f:
        f.write("def")
    time.sleep(0.01)
    with open(paths[2], "w") as f:
        f.write("abc")
    return {
        paths[0]: "900150983cd24fb0d6963f7d28e17f72",
        paths[1]: "4ed9407630eb1000c0f6b63842defa7d",
        paths[2]: "900150983cd24fb0d6963f7d28e17f72",
    }


@pytest.fixture(scope="session")
def black_image(output_dir):
    path = output_dir / "black.png"
    Image.new("RGB", (1, 1), "black").save(path)
    return path


@pytest.fixture(scope="session")
def white_image(output_dir):
    path = output_dir / "white.png"
    Image.new("RGB", (1, 1), "white").save(path)
    return path


@pytest.fixture(scope="function")
def hashcheck(output_dir):
    hashcheck = HashCheck()
    hashcheck.filename = "hashes.json"
    hashcheck.get_hashes(output_dir)
    return hashcheck


def test_get_path(hashcheck, paths):
    for path, hash_ in paths.items():
        assert hashcheck[path][0].hash == hash_


def test_get_hash(hashcheck, paths):
    for path, hash_ in paths.items():
        assert path in [h.path for h in hashcheck[hash_]]


def test_get_name(hashcheck, paths):
    for path in paths:
        assert path in [h.path for h in hashcheck[path.name]]


def test_iter(hashcheck, paths):
    for p1, p2 in zip(hashcheck, paths):
        assert p1 == p2


def test_index(hashcheck, paths):
    assert hashcheck.index == {p.resolve(): h for p, h in paths.items()}


def test_hashes(hashcheck, paths):
    hashes = {}
    for path, hash_ in paths.items():
        hashes.setdefault(hash_, []).append(path)
    assert hashcheck.hashes() == hashes


def test_get_duplicates(hashcheck, paths):
    hash_ = "900150983cd24fb0d6963f7d28e17f72"
    dupes = hashcheck.get_duplicates()
    assert dupes[hash_] == [p for p, h in paths.items() if h == hash_]


def test_hash_one(hashcheck, paths):
    for path, hash_ in paths.items():
        hashcheck.get_hashes(path, overwrite=True)
        assert hashcheck[path][0].hash == hash_


@pytest.mark.parametrize(
    "test_input,expected",
    [("abc", "e71fa2190541574b"), ("ábc", "b0fd30c6c92a8ad6")],
)
def test_fast_hash(test_input, expected):
    assert fast_hash(test_input, encoding="utf-8") == expected


def test_skip_hashed(output_dir):
    path = output_dir / "skiphashed.txt"
    with open(path, "w") as f:
        f.writelines(["# Hashed\n"] * 1000 + ["Not hashed"])
    with open(path) as f:
        assert skip_hashed(f).read() == "Not hashed"


def test_newer(paths):
    paths = list(paths)
    assert is_newer(paths[1], paths[0])
    assert is_newer(paths[2], paths[1])
    assert is_newer(paths[0], "fakepath.txt")


def test_hash_image(black_image, white_image):
    assert hash_file(black_image) == "73acd0b4a2391d4bbd9765aca5db19dc"
    assert hash_image_data(black_image) == "693e9af84d3dfcc71e640e005bdc5e2e"
    assert hash_file(white_image) == "a1cf09b59e5060f3beccdcf7a37189f0"
    assert hash_image_data(white_image) == "8597d4e7e65352a302b63e07bc01a7da"


def test_is_different(paths):
    paths = list(paths)
    assert is_different(paths[0], paths[1])
    assert is_different(paths[1], paths[2])
    assert not is_different(paths[0], paths[2])


def test_is_different_image(black_image, white_image):
    assert is_different(black_image, white_image, compare_image_data=True)
    assert not is_different(black_image, black_image, compare_image_data=True)
    assert not is_different(white_image, white_image, compare_image_data=True)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (r"A:\PATH\TO\FILE.TXT", r"\\Client\A$\PATH\TO\FILE.TXT"),
        (r"B:\PATH\TO\FILE.TXT", r"\\Client\B$\PATH\TO\FILE.TXT"),
        (r"C:\PATH\TO\FILE.TXT", r"\\Client\C$\PATH\TO\FILE.TXT"),
        (r"D:\PATH\TO\FILE.TXT", r"\\Client\D$\PATH\TO\FILE.TXT"),
        (r"a:\path\to\file.txt", r"\\Client\A$\path\to\file.txt"),
        (r"b:\path\to\file.txt", r"\\Client\B$\path\to\file.txt"),
        (r"c:\path\to\file.txt", r"\\Client\C$\path\to\file.txt"),
        (r"d:\path\to\file.txt", r"\\Client\D$\path\to\file.txt"),
    ],
)
def test_citrix_path(test_input, expected):
    path = get_citrix_path(test_input)
    assert str(path) == expected
    assert str(get_windows_path(test_input)) == ucfirst(test_input)
    assert str(get_windows_path(path)) == ucfirst(test_input)


def test_missing_hash(hashcheck):
    with pytest.raises(KeyError):
        hashcheck["abc"]


def test_invalid_size(paths):
    with pytest.raises(ValueError, match="Size must be a multiple of 128"):
        for path in paths:
            with open(path, "rb") as f:
                hasher(f, size=127)
