import re

import pytest

from nmnh_ms_tools.tools.specimen_numbers.parsers import (
    Parser,
    is_spec_num,
    parse_spec_num,
)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("1", True),
        ("12", True),
        ("123", True),
        ("1234", True),
        ("12345", True),
        ("123456", True),
        ("1234567", True),
        ("12345678", False),
        ("123456-1", True),
        ("123456-10", True),
        ("123456-100", True),
        ("123456-1000", True),
        ("123456-10000", False),
        ("123456-1", True),
        ("123456,1", True),
        ("123456 1", True),
        ("123456/1", True),
        ("123456.0001", True),
        ("A123456", True),
        ("A 123456", True),
        ("A2-00", True),
        ("A2-01", True),
        ("123456A", True),
        ("123456 A", True),
        ("123456/1", True),
        ("123456 1-10", False),
        ("123456/A-B", False),
    ],
)
def test_is_spec_num(test_input, expected):
    try:
        spec_num = parse_spec_num(test_input)
    except ValueError:
        assert False == expected
    else:
        assert (
            is_spec_num(test_input) == expected
            or (spec_num.is_valid() and not spec_num.is_range()) == expected
        )


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("A2 00", "A2"),
        ("A2 1", "A2-1"),
        ("A2 01", "A2-1"),
        ("A2 001", "A2-1"),
        ("A2.0001", "A2-1"),
    ],
)
def test_spec_num_key(test_input, expected):
    assert parse_spec_num(test_input).key() == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("19383-85/87/90-91", ["19383", "19384", "19385", "19387", "19390", "19391"]),
        ("496302 03 04 498278 79", ["496302", "496303", "496304", "498278", "498279"]),
    ],
)
def test_group(test_input, expected):
    parts = re.split(r"([,/& ]+)", test_input)
    parts_ = [(None, parts.pop(0))]
    while parts:
        parts_.append((parts.pop(0), parts.pop(0)))
    assert [str(s) for s in Parser().group(parts_)] == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("23 1376 231377", "231376 231377"),
        ("201 1 17, 201 1 19, 201 120", "201117, 201119, 201120"),
        ("504332 571257 and 5 7 12 5 8", "504332 571257 and 571258"),
    ],
)
def test_squash(test_input, expected):
    assert Parser().squash(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("USNM 1", ["USNM 1"]),
        ("USNM 12", ["USNM 12"]),
        ("USNM 123", ["USNM 123"]),
        ("USNM 1234", ["USNM 1234"]),
        ("USNM 12345", ["USNM 12345"]),
        ("USNM 123456", ["USNM 123456"]),
        ("USNM 123456-1", ["USNM 123456-1"]),
        ("USNM 123456-10", ["USNM 123456-10"]),
        ("USNM 123456-100", ["USNM 123456-100"]),
        ("USNM 123456-1000", ["USNM 123456-1000"]),
        ("USNM 123456-5000", ["USNM 123456-5000"]),
        ("USNM 12345-1", ["USNM 12345-1"]),
        ("USNM 12345 1", ["USNM 12345-1"]),
        ("USNM 12345,1", ["USNM 12345-1"]),
        ("USNM 12345/1", ["USNM 12345-1"]),
        ("USNM 12345, 12346 and 12347", ["USNM 12345", "USNM 12346", "USNM 12347"]),
        ("USNM 12345/6/7", ["USNM 12345", "USNM 12346", "USNM 12347"]),
        ("USNM 12345 46 47", ["USNM 12345", "USNM 12346", "USNM 12347"]),
        ("USNM 12345, 46, 47", ["USNM 12345", "USNM 12346", "USNM 12347"]),
        ("USNM 12345/46/47", ["USNM 12345", "USNM 12346", "USNM 12347"]),
        ("USNM 12345, 23456 and 345678", ["USNM 12345", "USNM 23456", "USNM 345678"]),
        ("USNM 12345-1 and 12345-2", ["USNM 12345-1", "USNM 12345-2"]),
        ("USNM 12345-1, -2, -3", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345-1, 2, & 3", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345/1-3", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345/6-8", ["USNM 12345", "USNM 12346", "USNM 12347", "USNM 12348"]),
        ("USNM 12345-1 to 3", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345(1-3)", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345-(1-3)", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345- (1-3)", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345/1 & 2-3", ["USNM 12345-1", "USNM 12345-2", "USNM 12345-3"]),
        ("USNM 12345A and 12345B", ["USNM 12345A", "USNM 12345B"]),
        ("USNM 12345A, -B, & -C", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345A, B, & C", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345A-C", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345/A-C", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345A to C", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345(A-C)", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345-(A-C)", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345- (A-C)", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM 12345/A & B-C", ["USNM 12345A", "USNM 12345B", "USNM 12345C"]),
        ("USNM type no. 1234", ["USNM type no. 1234"]),
        ("USNM type # 1234", ["USNM type no. 1234"]),
        ("USNM slide no. 1234", ["USNM slide no. 1234"]),
        ("USNM 12345-7-2", ["USNM 12345-7-2"]),
        ("USNM A2-00", ["USNM A2-00"]),
        ("USNM 12345, 12346, NMNH 12347", ["USNM 12345", "USNM 12346", "NMNH 12347"]),
        ("1234, 1235 (USNM), 1236 (NMNH)", ["USNM 1234", "USNM 1235", "NMNH 1236"]),
    ],
)
def test_extract_clean(test_input, expected):
    vals = []
    for vals_ in Parser(clean=True).extract(test_input).values():
        vals.extend(vals_)
    assert vals == expected


@pytest.mark.parametrize(
    "test_input,hints,expected",
    [
        (
            "NMNH 123456, 123, A1, B2, and C3",
            {",": "spec_num"},
            ["NMNH 123456", "NMNH 123", "NMNH A1", "NMNH B2", "NMNH C3"],
        ),
    ],
)
def test_extract_with_hints(test_input, hints, expected):
    vals = []
    for vals_ in Parser(clean=True, hints=hints).extract(test_input).values():
        vals.extend(vals_)
    assert vals == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("USNM 12345/1-10", 10),
        ("USNM 12345/1-100", 100),
        ("USNM 12345/1-1000", 1000),
    ],
)
def test_extract_clean_ranged_suffix(test_input, expected):
    vals = []
    for vals_ in Parser(clean=True).extract(test_input).values():
        vals.extend(vals_)
    assert len(vals) == expected
