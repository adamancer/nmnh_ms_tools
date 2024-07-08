"""Tests dictionary helper functions"""

import pytest


from nmnh_ms_tools.config import CONFIG


codes = [
    ("PPL", 8),
    ("PPLA", 8),
    ("PPLA2", 8),
    ("PPLA3", 8),
    ("PPLA4", 8),
    ("PPLA5", 8),
    ("PPLC", 8),
    ("PPLCH", 8),
    ("PPLF", 8),
    ("PPLG", 8),
    ("PPLH", 8),
    ("PPLL", 8),
    ("PPLQ", 8),
    ("PPLR", 8),
    ("PPLS", 16),
    ("PPLW", 8),
    ("PPLX", 4),
    ("STLMT", 8),
]


def test_filter_codes():
    assert set(CONFIG.filter_codes("P")) == {c[0] for c in codes}


@pytest.mark.parametrize("test_input", codes)
def test_filter_sizes(test_input):
    assert test_input[0] in CONFIG.filter_codes(min_size=4, max_size=16)


def test_sizes():
    assert CONFIG.min_size([c[0] for c in codes]) == 4
    assert CONFIG.max_size([c[0] for c in codes]) == 16


def test_get_feature_classes():
    assert CONFIG.get_feature_classes([c[0] for c in codes]) == ["P"]


@pytest.mark.parametrize("test_input", codes)
def test_get_feature_class(test_input):
    assert CONFIG.get_feature_class(test_input[0]) == "P"


def test_get_feature_codes():
    assert set(CONFIG.get_feature_codes("P")) == {c[0] for c in codes}


@pytest.mark.parametrize("test_input,expected", codes)
def test_get_feature_radius(test_input, expected):
    assert CONFIG.get_feature_radius(test_input) == expected
