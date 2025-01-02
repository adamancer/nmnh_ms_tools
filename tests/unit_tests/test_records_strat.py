"""Tests stratigraphy classes"""

import pytest

from nmnh_ms_tools.records.stratigraphy import StratPackage, StratUnit


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("Named Supergroup", "Named Supergroup"),
        ("Named Group", "Named Group"),
        ("Named Subgroup", "Named Subgroup"),
        ("Named Formation", "Named Formation"),
        ("Named Member", "Named Member"),
        ("Named Bed", "Named Bed"),
        # Unofficial ranks
        ("Named Layer", "Named Layer"),
        ("Named Series", "Named Series"),
        ("Named Unit", "Named Unit"),
        # Short ranks
        ("Named SupGp", "Named Supergroup"),
        ("Named Gp", "Named Group"),
        ("Named SubGp", "Named Subgroup"),
        ("Named Fm", "Named Formation"),
        ("Named Mbr", "Named Member"),
        ("Named Bd", "Named Bed"),
        # Modifiers and qualifiers
        ("Named Group?", "Named Group?"),
        ("Named Group(?)", "Named Group?"),
        ("Named Group (Upper)", "Named Group (Upper)"),
        ("Upper Named Group", "Named Group (Upper)"),
        ("Upper-middle Named Group", "Named Group (Upper-Middle)"),
        ("Top Named Member", "Named Member (Top)"),
        ("Top of Named Member", "Named Member (Top)"),
        ("Top of the Named Member", "Named Member (Top)"),
        ("Top part of the Named Member", "Named Member (Top)"),
        ("Top part Named Member", "Named Member (Top)"),
        ("Named Member (top)", "Named Member (Top)"),
        ("Named Member (top of)", "Named Member (Top)"),
        ("Named Member, top", "Named Member (Top)"),
        ("Named Member, top of", "Named Member (Top)"),
        ("Named Member, top half", "Named Member (Top Half)"),
        ("Named Member, top third of", "Named Member (Top Third)"),
        # Packages
        ("Named Group > Named Formation", "Named Group > Named Formation"),
        (
            "Named Group | Named Formation | Named Member",
            "Named Group > Named Formation > Named Member",
        ),
        (
            "Named Group, Named Formation, Named Member, Named Bed",
            "Named Group > Named Formation > Named Member > Named Bed",
        ),
        (
            "Upper Named Group > Named Formation",
            "Named Group (Upper) > Named Formation",
        ),
        (
            "Named Group > Named Formation (lower)",
            "Named Group > Named Formation (Lower)",
        ),
        ("Named Group > Named Formation", "Named Group > Named Formation"),
        ("Named Group > Named Formation?", "Named Group > Named Formation?"),
        ("Named Group? > Named Formation", "Named Group? > Named Formation"),
        ("Named Member of the Named Formation", "Named Formation > Named Member"),
        (
            "Upper Named Member of the Named Formation",
            "Named Formation > Named Member (Upper)",
        ),
        # Lithologies
        ("Named Sandstone", "Named Formation"),
        # Order
        (
            "Named Bed, Named Member, Named Formation, Named Group",
            "Named Group > Named Formation > Named Member > Named Bed",
        ),
        # StratUnit
        (StratUnit("Named Formation"), "Named Formation"),
        ([StratUnit("Named Formation")], "Named Formation"),
        (["Named Formation"], "Named Formation"),
    ],
)
def test_parse_units(test_input, expected):
    assert str(StratPackage(test_input)) == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        (
            "Named Group; Named Formation; Named Member; top of Named Bed",
            {
                "AgeLithostratGroup": "Named Gp",
                "AgeLithostratFormation": "Named Fm",
                "AgeLithostratMember": "Named Mbr",
                "AgeLithostratBed": "Named Bd (Top)",
                "AgeLithostratLithology": "",
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named Group; Named Formation; Named Member; top of Named Bed",
            },
        ),
        (
            "Named Group? | Named Formation",
            {
                "AgeLithostratGroup": "Named Gp",
                "AgeLithostratFormation": "Named Fm",
                "AgeLithostratLithology": "",
                "AgeLithostratUncertain": "Yes",
                "AgeVerbatimStratigraphy": "Named Group? | Named Formation",
            },
        ),
        (
            "Named Siltstone Formation | Unit 1A",
            {
                "AgeLithostratFormation": "Named Fm",
                "AgeOtherTermsRank_tab": ["Other"],
                "AgeOtherTermsValue_tab": ["Unit 1A"],
                "AgeLithostratLithology": "siltstone",
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named Siltstone Formation | Unit 1A",
            },
        ),
        (
            "Named Siltstone | Named Unit",
            {
                "AgeLithostratFormation": "Named Fm",
                "AgeOtherTermsRank_tab": ["Other"],
                "AgeOtherTermsValue_tab": ["Named Unit"],
                "AgeLithostratLithology": "siltstone",
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named Siltstone | Named Unit",
            },
        ),
    ],
)
def test_to_emu(test_input, expected):
    assert StratPackage(test_input).to_emu() == expected


def test_same_as():
    assert StratUnit("Named Formation").same_as(StratUnit("Named Fm"))


def test_similar():
    assert StratUnit("Named Sandstone").similar_to(StratUnit("Named Fm"))
