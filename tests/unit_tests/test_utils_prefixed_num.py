"""Tests the PrefixedNum class"""

import pytest

from nmnh_ms_tools.utils import PrefixedNum


@pytest.mark.parametrize(
    "test_input,exp_prefix,exp_number",
    [
        ("R1234", "R", 1234),
        ("R-1234", "R", 1234),
        ("R 1234", "R", 1234),
        ("R01234", "R", 1234),
        ("RRR1234", "RRR", 1234),
        ("1234", "", 1234),
    ],
)
def test_prefix_number(test_input, exp_prefix, exp_number):
    pnum = PrefixedNum(test_input)
    assert pnum.prefix == exp_prefix
    assert pnum.number == exp_number


def test_str():
    assert str(PrefixedNum("R1234")) == "R1234"


def test_repr():
    assert repr(PrefixedNum("R1234")) == "PrefixedNum(prefix='R', number=1234)"


def test_identity():
    pnum = PrefixedNum("R1234")
    orig_id = id(pnum)

    pnum += 1
    assert str(pnum) == "R1235"
    assert id(pnum) != orig_id


def test_bool():
    pnum = PrefixedNum("R1234")
    assert bool(pnum)


def test_eq():
    pnum1 = PrefixedNum("R1234")
    pnum2 = PrefixedNum("R1233") + 1
    assert pnum1 == pnum2 and pnum1 is not pnum2


def test_sub():
    pnum = PrefixedNum("R1234")
    pnum -= 1
    assert str(pnum) == "R1233"


@pytest.mark.parametrize(
    "test_input_1,test_input_2,expected",
    [
        ("R1234", "R1233", False),
        ("R1234", "R1234", False),
        ("R1234", "R1235", True),
        ("A1234", "R01234", True),
        ("Z1234", "R01234", False),
    ],
)
def test_sort(test_input_1, test_input_2, expected):
    assert (PrefixedNum(test_input_1) < PrefixedNum(test_input_2)) == expected
    assert (PrefixedNum(test_input_1) < test_input_2) == expected


def test_copy():
    pnum_orig = PrefixedNum("R1234")
    pnum_copy = pnum_orig.copy()
    assert pnum_orig == pnum_copy and pnum_orig is not pnum_copy


def test_invalid_number():
    with pytest.raises(ValueError, match="Invalid prefixed number"):
        PrefixedNum("123A")


def test_change_prefix():
    pnum = PrefixedNum("R1234")
    with pytest.raises(AttributeError, match="Cannot modify existing attribute"):
        pnum.prefix = "A"


def test_change_number():
    pnum = PrefixedNum("R1234")
    with pytest.raises(AttributeError, match="Cannot modify existing attribute"):
        pnum.number += 1
