"""Tests functions in the standardizer submodule"""

import pytest


from nmnh_ms_tools.utils.standardizers import LocStandardizer


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("Fake Bay", "bay-fake"),
        ("Fake Mtn", "fake-mountain"),
        ("St. Fake", "saint-fake"),
        ("Fake Town (parenthetical)", "fake-town"),
    ],
)
def test_loc_standardizer(test_input, expected):
    assert LocStandardizer()(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("Fake Bay", "std_bay"),
        ("Fake City", "std_municipality"),
        ("Fake County", "std_admin"),
        ("Fake Island", "std_island"),
        ("Fake Lake", "std_lake"),
        ("Fake Mountain", "std_mountain"),
        ("Isle of Fake", "std_island"),
        ("Mt. Fake", "std_mountain"),
    ],
)
def test_std_features_functions(test_input, expected):
    std = LocStandardizer()
    func = std.guess_std_function(test_input)
    assert func.__name__ == expected
    assert func(test_input) == std.std_feature(test_input) == "fake"


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("Fake Bay", {"standard": "bay-fake", "bay": "fake"}),
        (
            "Fake I.",
            {
                "standard": "fake-i",
                "expanded": "fake-island",
                "island": "fake",
            },
        ),
    ],
)
def test_variants(test_input, expected):
    assert LocStandardizer().variants(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [("Middle of Fake Town", "Fake Town"), ("Just N of Fake Island", "Fake Island")],
)
def test_sitify(test_input, expected):
    assert LocStandardizer().sitify(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("Mine No. 1", "mine-1"),
        ("Station #11", "station-11"),
        ("Sample Site Num. 12", "sample-site-12"),
    ],
)
def test_numbered_strings(test_input, expected):
    assert LocStandardizer().std(test_input) == expected
