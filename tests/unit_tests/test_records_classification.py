"""Tests classification tools"""

import os

import pytest

from nmnh_ms_tools.records import TaxaParser, get_tree


@pytest.fixture
def tree():
    # FIXME: Test is using local versions of tree and indexes
    tree = get_tree()
    for idx in ["name_index", "stem_index"]:
        try:
            continue
            os.remove(getattr(tree, idx).path)
        except FileNotFoundError:
            pass
    return tree


def test_parse_variety():
    parsed = TaxaParser("Beryl (var. aquamarine)")
    assert parsed.parents() == ["beryl"]


def test_parse_complex_rock_name():
    parsed = TaxaParser("Gray-green foliated white-mica schist")
    assert parsed.colors == ["gray-green"]
    assert parsed.indexed == "whit-mica-schist"
    assert parsed.textures == ["foliated"]


def test_preferred(tree):
    assert tree["sphene"].preferred()["name"] == "Titanite"


@pytest.mark.parametrize(
    "taxa,setting,expected",
    [
        (["Diamond"], "Necklace", "Diamond necklace"),
        (["Diamond", "Ruby"], "Bracelet", "Diamond and ruby bracelet"),
        (["Corundum", "Sapphire", "Ruby"], None, "Sapphire and ruby"),
        (["Sphene"], None, "Titanite"),
        (["Titanite", "Sphene"], None, "Titanite"),
        (["Garnet-biotite schist", "Garnet", "Biotite"], None, "Garnet-biotite schist"),
    ],
)
def test_name_item(tree, taxa, setting, expected):
    tree.name_item(taxa, setting) == expected
