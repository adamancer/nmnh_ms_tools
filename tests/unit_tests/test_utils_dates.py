"""Tests date functions"""

import pytest
from datetime import date, datetime

from nmnh_ms_tools.utils import add_years, fy, get_fy


def test_fy():
    fy1 = fy(2025)
    fy2 = fy("FY2025")
    assert fy1 is fy2


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("1970-09-30", 1970),
        ("1970-10-01", 1971),
        (date(1970, 9, 30), 1970),
        (date(1970, 10, 1), 1971),
        (datetime(1970, 9, 30), 1970),
        (datetime(1970, 10, 1), 1971),
    ],
)
def test_get_fy(test_input, expected):
    assert get_fy(test_input) == fy(expected)


@pytest.mark.parametrize(
    "dt,fyear,expected",
    [
        ("1970-09-30", 1970, True),
        ("1970-10-01", 1970, False),
        (date(1970, 9, 30), 1970, True),
        (date(1970, 10, 1), 1970, False),
        (datetime(1970, 9, 30), 1970, True),
        (datetime(1970, 10, 1), 1970, False),
    ],
)
def test_in_fy(dt, fyear, expected):
    assert (dt in fy(fyear)) == expected


@pytest.mark.parametrize(
    "test_input,num_years,expected",
    [
        (date(1970, 1, 1), 1, date(1971, 1, 1)),
        (date(1972, 2, 29), 1, date(1973, 3, 1)),
        (date(1972, 2, 29), 4, date(1976, 2, 29)),
    ],
)
def test_add_years(test_input, num_years, expected):
    assert add_years(test_input, num_years) == expected
