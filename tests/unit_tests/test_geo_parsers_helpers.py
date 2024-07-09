"""Tests DirectionParser"""

import pytest

from nmnh_ms_tools.tools.geographic_names.parsers.helpers import (
    clean_locality,
    debreviate,
    deperiod,
)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("cönvert to ascii", "convert to ascii"),
        ('"remove trailing punctuation.";', "remove trailing punctuation"),
        ("remove  multiple  spaces", "remove multiple spaces"),
        ("remove double--hyphens", "remove double-hyphens"),
        ("standardize N.N.W.", "standardize NNW"),
        ("remove commas from 1,000", "remove commas from 1000"),
        ("delimit off Named Feature", "delimit; off Named Feature"),
        ("expand Natl", "expand National"),
        ("convert 2' to 2 ft", "convert 2 ft to 2 ft"),
    ],
)
def test_clean_locality(test_input, expected):
    assert clean_locality(test_input) == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        pytest.param("Fake I.", "Fake Island", marks=pytest.mark.xfail),
        pytest.param("Fake Is.", "Fake Island", marks=pytest.mark.xfail),
        pytest.param("Fake Cr.", "Fake Creek", marks=pytest.mark.xfail),
    ],
)
def test_debreviate(test_input, expected):
    assert debreviate(test_input).strip(".") == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("leave 1.00 alone", "leave 1.00 alone"),
        ("prepend 0 to .1", "prepend 0 to 0.1"),
        ("remove before. of", "remove before of"),
        ("remove from Mt. Fake", "remove from Mt Fake"),
        ("Fake Mt. Replace if more text", "Fake Mt; Replace if more text"),
        ("remove from Mr. Fake and Dr. Fake", "remove from Mr Fake and Dr Fake"),
    ],
)
def test_deperiod(test_input, expected):
    assert deperiod(test_input) == expected
