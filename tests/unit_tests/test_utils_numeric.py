"""Tests functions in AdamancerBot class"""

import pytest


from nmnh_ms_tools.utils import (
    as_numeric,
    base_to_int,
    int_to_base,
    frange,
    num_dec_places,
)


@pytest.mark.parametrize(
    "test_input,expected",
    [("1", 1), ("0.5", 0.5), ("1/2", 0.5), (0, 0)],
)
def test_as_numeric(test_input, expected):
    assert as_numeric(test_input) == pytest.approx(expected)


@pytest.mark.parametrize(
    "test_input",
    [None, "", []],
)
def test_as_numeric_exception(test_input):
    with pytest.raises(ValueError):
        as_numeric(test_input)


def test_base_to_int():
    assert base_to_int(10, base=2) == 2


@pytest.mark.parametrize(
    "test_input,base,expected", [(2, 2, "10"), (-2, 2, "-10"), (0, 2, "0")]
)
def test_int_to_base(test_input, base, expected):
    assert int_to_base(test_input, base=base) == expected


def test_frange():
    assert list(frange(0, 0.3, 0.1)) == [0, 0.1, 0.2]


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("1.000", 3),
        (1.23, 2),
        (1.2345678, 5),
        (1, 0),
        (1.000, 0),
    ],
)
def test_num_dec_places(test_input, expected):
    assert num_dec_places(test_input, max_dec_places=5) == expected
