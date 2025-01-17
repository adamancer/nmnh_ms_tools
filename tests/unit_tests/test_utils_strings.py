"""Tests string utilities"""

import pytest


from nmnh_ms_tools.utils import (
    add_article,
    as_str,
    capitalize,
    lcfirst,
    overlaps,
    plural,
    same_to_length,
    seq_split,
    singular,
    to_slug,
    std_case,
    to_attribute,
    to_camel,
    to_dwc_camel,
    to_pascal,
    to_digit,
    to_pattern,
    truncate,
    ucfirst,
)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apple", "an apple"),
        ("cherry", "a cherry"),
        ("apples", "apples"),
        ("a apple", "a apple"),
    ],
)
def test_add_article(test_input, expected):
    assert add_article(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("abc", "abc"),
        (["a", "b", "c"], "a | b | c"),
        (None, ""),
        (0, "0"),
        ({"a": "b"}, "{'a': 'b'}"),
    ],
)
def test_as_str(test_input, expected):
    assert as_str(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("abcde", "abcde"),
        ("Abcde", "abcde"),
        ("ABcde", "aBcde"),
        ("ABCDE", "ABCDE"),
        ("12345", "12345"),
    ],
)
def test_lcfirst(test_input, expected):
    assert lcfirst(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("abcde", "Abcde"),
        ("Abcde", "Abcde"),
        ("ABcde", "ABcde"),
        ("ABCDE", "ABCDE"),
        ("12345", "12345"),
    ],
)
def test_ucfirst(test_input, expected):
    assert ucfirst(test_input) == expected
    assert ucfirst(test_input, True) == expected[0] + expected[1:].lower()


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples", "apple"),
        ("cherries", "cherry"),
    ],
)
def test_singular(test_input, expected):
    assert singular(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apple", "apples"),
        ("cherry", "cherries"),
    ],
)
def test_plural(test_input, expected):
    assert plural(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples and oranges", "Apples and oranges"),
        ("APPLES AND ORANGES", "APPLES AND ORANGES"),
    ],
)
def test_capitalize(test_input, expected):
    assert capitalize(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples and oranges", "apples_and_oranges"),
        ("ApplesAndOranges", "apples_and_oranges"),
        ("Apples & oranges", "apples_oranges"),
    ],
)
def test_to_attribute(test_input, expected):
    assert to_attribute(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples and oranges", "apples-and-oranges"),
        ("ApplesAndOranges", "apples-and-oranges"),
        ("Apples & oranges", "apples-oranges"),
    ],
)
def test_to_slug(test_input, expected):
    assert to_slug(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples and oranges", "applesAndOranges"),
        ("ApplesAndOranges", "applesAndOranges"),
        ("Apples & oranges", "applesOranges"),
    ],
)
def test_to_camel(test_input, expected):
    assert to_camel(test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples and oranges", "ApplesAndOranges"),
        ("ApplesAndOranges", "ApplesAndOranges"),
        ("Apples & oranges", "ApplesOranges"),
    ],
)
def test_to_pascal(test_input, expected):
    assert to_pascal(test_input) == expected


def test_to_dwc_camel():
    assert to_dwc_camel("location_id") == "locationID"


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples and oranges", r"\bapples and oranges\b"),
        ("apples (and oranges)", r"\bapples \(and oranges\)\b"),
        ("apples **and** oranges", r"\bapples \*\*and\*\* oranges\b"),
    ],
)
def test_to_pattern(test_input, expected):
    assert to_pattern(test_input).pattern == expected


def test_to_pattern_with_subs():
    assert to_pattern("A1234", subs={r"\d+": r"\\d+"}).pattern == r"\bA\d+\b"


@pytest.mark.parametrize(
    "test_input, length, expected",
    [
        (("apple", "application"), 3, True),
        (("apple", "aptitude"), 3, False),
        (("apple", "apple pie"), None, True),
        (("", "", ""), 3, True),
        (("", "", None), 3, True),
    ],
)
def test_same_to_length(test_input, length, expected):
    if expected:
        assert same_to_length(*test_input, length=length)
    else:
        assert not same_to_length(*test_input, length=length)


def test_same_to_length_strict():
    assert not same_to_length("Apple", "apple", strict=True)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("pleats", True),
        ("oranges", False),
        ("apple pie", True),
    ],
)
def test_overlaps(test_input, expected):
    if expected:
        assert overlaps("apple", test_input)
    else:
        assert not overlaps("apple", test_input)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("Orange", "Apple"),
        ("orange", "apple"),
        ("ORANGE", "APPLE"),
        ("Org", "Apple"),
    ],
)
def test_std_case(test_input, expected):
    assert std_case("apple", test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("One two three", "1 2 3"),
        ("Twelve", "12"),
        ("Twenty-one", "21"),
        ("onetwothree", "onetwothree"),
    ],
)
def test_to_digit(test_input, expected):
    assert to_digit(test_input) == expected


@pytest.mark.parametrize(
    "test_input,suffix,expected",
    [
        ("apples", "", "apple"),
        ("apples", "...", "ap..."),
        ("apple", "...", "apple"),
    ],
)
def test_truncate(test_input, suffix, expected):
    assert truncate(test_input, length=5, suffix=suffix) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("apples | oranges | pears", ["apples", "oranges", "pears"]),
        ("apples; oranges; pears", ["apples", "oranges", "pears"]),
        ("apples, oranges, pears", ["apples", "oranges", "pears"]),
        ("apples and oranges and pears", ["apples", "oranges", "pears"]),
        ("apples, oranges and pears", ["apples", "oranges", "pears"]),
        ("apples, oranges, and pears", ["apples", "oranges", "pears"]),
        ("apples & oranges & pears", ["apples", "oranges", "pears"]),
        ("apples, oranges, & pears", ["apples", "oranges", "pears"]),
        ("apples; oranges & pears", ["apples", "oranges", "pears"]),
        ("apples; oranges, pears", ["apples", "oranges, pears"]),
    ],
)
def test_seq_split(test_input, expected):
    assert seq_split(test_input) == expected
