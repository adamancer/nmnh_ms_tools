"""Tests catalog number parser tools"""

import pytest
from xmu import EMuRecord

from nmnh_ms_tools.records.catnums2 import is_antarctic, parse_catnum, parse_catnums


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("123456", "123456"),
        ("123456-1", "123456-1"),
        ("123456-01", "123456-01"),
        ("123456.0001", "123456.0001"),
        ("123456A", "123456A"),
        ("123456-A", "123456A"),
        ("123456.0001 (PET)", "123456.0001 (PET)"),
        ("A123456", "A123456"),
        ("AB123456", "AB123456"),
        ("ABC123456", "ABC123456"),
        ("A 123456", "A123456"),
        ("AB 123456", "AB123456"),
        ("ABC 123456", "ABC123456"),
        ("NMNH 123456", "NMNH 123456"),
        ("NMNH 123456-1", "NMNH 123456-1"),
        ("NMNH 123456-01", "NMNH 123456-01"),
        ("NMNH 123456.0001", "NMNH 123456.0001"),
        ("NMNH A123456", "NMNH A123456"),
        ("NMNH AB123456", "NMNH AB123456"),
        ("NMNH ABC123456", "NMNH ABC123456"),
        ("NMNH A 123456", "NMNH A123456"),
        ("NMNH AB 123456", "NMNH AB123456"),
        ("NMNH ABC 123456", "NMNH ABC123456"),
        # NASA meteorite numbers
        ("ALH 12345", "ALH 12345"),
        ("ALHA12345", "ALHA12345"),
        ("ALH 123456", "ALH 123456"),
        ("ALH 123456,1", "ALH 123456,1"),
        ("ALH 123456,A", "ALH 123456,A"),
        ("ALH 123456,1A", "ALH 123456,1A"),
        ("ALH 123456,A1", "ALH 123456,A1"),
        ({"MetMeteoriteName": "ALH 123456,A1"}, "ALH 123456,A1"),
    ],
)
def test_parse_catnum(test_input, expected):
    assert str(parse_catnum(test_input)) == str(expected)


@pytest.mark.parametrize(
    "test_input",
    [
        "NMNH 123456-8",
        "NMNH 123456-58",
        "NMNH 123456-458",
        "NMNH 123456 123457 123458",
        "NMNH 123456, 123457, 123458",
        "NMNH 123456; 123457; 123458",
        "NMNH 123456|123457|123458",
    ],
)
def test_parse_catnums(test_input):
    assert [str(c) for c in parse_catnums(test_input)] == [
        "NMNH 123456",
        "NMNH 123457",
        "NMNH 123458",
    ]


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("NMNH 123456-78", "NMNH 123456"),
        ("NMNH A123456A", "NMNH A123456"),
        ("NMNH 123456A (PET)", "NMNH 123456 (PET)"),
    ],
)
def test_parent(test_input, expected):
    assert str(parse_catnum(test_input).parent) == expected


def test_as_range():
    catnums = parse_catnum("123456-7").as_range()
    assert catnums[0] == parse_catnum("123456")
    assert catnums[1] == parse_catnum("123457")


def test_as_separate_numbers():
    catnums = parse_catnum("123456-7").as_separate_numbers()
    assert catnums[0] == parse_catnum("123456")
    assert catnums[1] == parse_catnum("7")


@pytest.mark.parametrize(
    "test_input, val, expected",
    [
        ("NMNH A123456 (PET)", 1, "NMNH A123457 (PET)"),
        ("NMNH A123456 (MET)", 10, "NMNH A123466 (MET)"),
        ("ALH 84001", 100, "ALH 84101"),
    ],
)
def test_add(test_input, val, expected):
    assert str(parse_catnum(test_input) + val) == expected


@pytest.mark.parametrize(
    "test_input, val, expected",
    [
        ("NMNH A123456 (PET)", 1, "NMNH A123455 (PET)"),
        ("NMNH A123456 (MET)", 10, "NMNH A123446 (MET)"),
        ("ALH 84001", 100, "ALH 83901"),
    ],
)
def test_sub(test_input, val, expected):
    assert str(parse_catnum(test_input) - val) == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("GRO 02001", True),
        ("LEW 061004,22", True),
        ("ALHA84001,1", True),
        ("ALHA84001,A", True),
        ("ALHA84001,1A", True),
        ("ALHA84001,A1", True),
    ],
)
def test_is_antarctic(test_input, expected):
    assert (
        is_antarctic(test_input) == parse_catnum(test_input).is_antarctic() == expected
    )


@pytest.mark.parametrize(
    "div, cat, coll, expected",
    [
        ("Meteorites", "", "", "MET"),
        ("Mineralogy", "Gems", "", "GEM"),
        ("Mineralogy", "Minerals", "", "MIN"),
        ("Petrology & Volcanology", "", "", "PET"),
        ("Petrology & Volcanology", "", "Smithsonian Microbeam Standards", "SMS"),
        ("Petrology & Volcanology", "", "Reference Standards Collection", "REF"),
    ],
)
def test_emu_roundtrip(div, cat, coll, expected):
    rec = {
        "CatMuseumAcronym": "NMNH",
        "CatPrefix": "",
        "CatNumber": "123456",
        "CatSuffix": "",
    }
    if div:
        rec["CatDivision"] = div
    if cat:
        rec["CatCatalog"] = cat
    if coll:
        rec["CatCollectionName_tab"] = [coll]
    catnum = parse_catnum(rec)
    assert catnum.coll_id == expected
    assert catnum.to_emu() == EMuRecord(rec, module="ecatalogue")


@pytest.mark.parametrize(
    "taxon, expected",
    [
        ("Clinopyroxene", "REF:CPX"),
        ("Orthopyroxene", "REF:OPX"),
    ],
)
def test_ref_cpx(taxon, expected):
    rec = {
        "CatMuseumAcronym": "NMNH",
        "CatPrefix": "",
        "CatNumber": "116610",
        "CatSuffix": "15",
        "CatDivision": "Petrology & Volcanology",
        "CatCollectionName_tab": ["Reference Standards Collection"],
        "IdeTaxonRef_tab": [{"ClaScientificName": taxon}],
    }
    catnum = parse_catnum(rec)
    assert catnum.coll_id == expected
    assert catnum.to_emu() == EMuRecord(rec, module="ecatalogue")


def test_copy():
    catnum = parse_catnum("123456-78")
    assert catnum == catnum.copy()


def test_sort():
    catnums = [parse_catnum(n) for n in ["123457", "123456", "A123455"]]
    catnums.sort()
    assert [str(n) for n in catnums] == ["123456", "123457", "A123455"]


def test_eq_diff_class():
    assert not parse_catnum("123456") == "123456"


def test_parse_bad_catnum():
    with pytest.raises(ValueError, match="Could not parse "):
        parse_catnum("Not a catnum")


def test_parse_add_with_suffix():
    with pytest.raises(ValueError, match="Addition not supported if suffix present"):
        parse_catnum("123456-78") + 1


def test_parse_sub_with_suffix():
    with pytest.raises(ValueError, match="Subtraction not supported if suffix present"):
        parse_catnum("123456-78") - 1
