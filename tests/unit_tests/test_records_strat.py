"""Tests stratigraphy classes"""

import pytest

from nmnh_ms_tools.records import StratPackage, StratUnit


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
        ("Very top of Named Member", "Named Member (Top)"),
        ("Named Member (top)", "Named Member (Top)"),
        ("Named Member (top of)", "Named Member (Top)"),
        ("Named Member, top", "Named Member (Top)"),
        ("Named Member, top of", "Named Member (Top)"),
        ("Named Member, top half", "Named Member (Top Half)"),
        ("Named Member, top third of", "Named Member (Top Third)"),
        ("Low in Named Member", "Named Member (Lower)"),
        ("Lowest Named Member", "Named Member (Lower)"),
        ("Center Named Member", "Named Member (Middle)"),
        ("High in Named Member", "Named Member (Upper)"),
        ("Highest Named Member", "Named Member (Upper)"),
        ("Topmost Named Member", "Named Member (Top)"),
        ("Uppermost Named Member", "Named Member (Upper)"),
        ("Lowermost Named Member", "Named Member (Lower)"),
        ("Bottommost Named Member", "Named Member (Base)"),
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
        # Multiple units for a given rank
        (["Named 1 Group", "Named 2 Group"], "(Named 1 Group | Named 2 Group)"),
        (
            ["Named Group", "Named 1 Formation", "Named 2 Formation"],
            "Named Group > (Named 1 Formation | Named 2 Formation)",
        ),
        (
            ["Named Group", "Named Formation", "Named 1 Member", "Named 2 Member"],
            "Named Group > Named Formation > (Named 1 Member | Named 2 Member)",
        ),
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
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named Group; Named Formation; Named Member; top of Named Bed",
            },
        ),
        (
            "Named Group? | Named Formation",
            {
                "AgeLithostratGroup": "Named Gp",
                "AgeLithostratFormation": "Named Fm",
                "AgeLithostratUncertain": "Yes",
                "AgeVerbatimStratigraphy": "Named Group? | Named Formation",
            },
        ),
        (
            "Named Siltstone Formation | Unit 1A",
            {
                "AgeLithostratFormation": "Named Fm",
                "AgeOtherTermsRank_tab": ["Unit"],
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
                "AgeOtherTermsRank_tab": ["Unit"],
                "AgeOtherTermsValue_tab": ["Named Unit"],
                "AgeLithostratLithology": "siltstone",
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named Siltstone | Named Unit",
            },
        ),
        (
            ["Named 1 Limestone", "Named 2 Limestone"],
            {
                "AgeLithostratFormation": "Named 1 Fm | Named 2 Fm",
                "AgeLithostratLithology": "limestone",
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named 1 Limestone | Named 2 Limestone",
            },
        ),
        (
            ["Named Siltstone", "Named 1 Unit", "Named 2 Unit"],
            {
                "AgeLithostratFormation": "Named Fm",
                "AgeOtherTermsRank_tab": ["Unit", "Unit"],
                "AgeOtherTermsValue_tab": ["Named 1 Unit", "Named 2 Unit"],
                "AgeLithostratLithology": "siltstone",
                "AgeLithostratUncertain": "No",
                "AgeVerbatimStratigraphy": "Named Siltstone | Named 1 Unit | Named 2 Unit",
            },
        ),
    ],
)
def test_to_emu(test_input, expected):
    assert StratPackage(test_input).to_emu() == expected


def test_remarks():
    assert StratPackage("Named Group; Named Formation", remarks="Remarks").to_emu() == {
        "AgeLithostratGroup": "Named Gp",
        "AgeLithostratFormation": "Named Fm",
        "AgeLithostratUncertain": "No",
        "AgeStratigraphyRemarks": "Remarks",
        "AgeVerbatimStratigraphy": "Named Group; Named Formation",
    }


def test_same_as():
    assert StratUnit("Named Formation").same_as(StratUnit("Named Fm"))


def test_similar():
    assert StratUnit("Named Sandstone").similar_to(StratUnit("Named Fm"))
