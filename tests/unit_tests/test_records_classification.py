"""Tests classification tools"""
import pytest

from nmnh_ms_tools.records.classification import TaxaParser, Taxon, get_tree


def test_parse_variety():
    parsed = TaxaParser("Beryl (var. aquamarine)")
    assert parsed.parents() == ["beryl"]


def test_parse_complex_rock_name():
    parsed = TaxaParser("Gray-green foliated white-mica schist")
    assert parsed.colors == ["gray-green"]
    assert parsed.indexed == "whit-mica-schist"
    assert parsed.textures == ["foliated"]


def test_find_name():
    parsed = TaxaParser("Hilgardite-3tc")
    tree = get_tree()
