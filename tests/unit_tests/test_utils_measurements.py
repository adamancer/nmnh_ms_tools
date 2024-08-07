"""Tests geography helper functions"""

import pytest

from nmnh_ms_tools.utils import parse_measurement, parse_measurements


def test_measurement_repr():
    assert repr(parse_measurement("1 g")) == (
        "Measurement(from_val: '1', from_mod: '', to_val: '1', to_mod: '',"
        " unit: 'grams', short_unit: 'g', verbatim: '1 g')"
    )


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("1 cm", "1 cm"),
        ("1 centimeter", "1 cm"),
        ("1 to 2 cm", "1 to 2 cm"),
        ("1-2 cm", "1 to 2 cm"),
        ("12 inches", "12 in"),
        ("-1g to -2g", "-1 to -2 g"),
        ("~1cm", "~1 cm"),
    ],
)
def test_parse_measurements(test_input, expected):
    assert parse_measurements(test_input).text == expected


def test_parse_measurements_kwargs():
    assert str(parse_measurements(1, 2, "g", " - ")) == "1 - 2 g"


def test_parse_measurement_from_measurement():
    meas = parse_measurement("10.0 g")
    assert str(meas) == str(parse_measurement(meas))


def test_parse_measurements_kwargs():
    meas = parse_measurements(1, 2, "g")
    assert f"{meas:.1f}" == "1.0 to 2.0 g"


def test_copy():
    meas_orig = parse_measurements(1, 2, "g")
    meas_copy = meas_orig.copy()
    assert meas_orig == meas_copy and meas_orig is not meas_copy


def test_unknown_unit():
    with pytest.raises(ValueError, match="Could not parse measurement"):
        parse_measurement("1 gribble")


def test_inconsistent_unit():
    with pytest.raises(ValueError, match="Inconsistent units"):
        parse_measurement("1g", "kg")


def test_multiple_ranges():
    with pytest.raises(ValueError, match="Inconsistent measurements"):
        parse_measurements("1-2", "3-4", "g")


def test_multiple_units():
    with pytest.raises(ValueError, match="Inconsistent units"):
        parse_measurements("1g", "2kg")
