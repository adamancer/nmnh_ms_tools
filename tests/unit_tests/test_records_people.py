"""Tests Person"""

import pytest

from nmnh_ms_tools.records import Person, combine_names, parse_names


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("Homer Simpson", {"first": "Homer", "last": "Simpson"}),
        ("Homer J. Simpson", {"first": "Homer", "last": "Simpson", "middle": "J"}),
        ("Homer Jay Simpson", {"first": "Homer", "last": "Simpson", "middle": "Jay"}),
        (
            "Mr. and Mrs. Homer J. Simpson",
            {
                "title": "Mr. and Mrs.",
                "first": "Homer",
                "last": "Simpson",
                "middle": "J",
            },
        ),
        (
            "Lieutenant Commander Homer Simpson",
            {"title": "Lt. Cmdr.", "first": "Homer", "last": "Simpson"},
        ),
        (
            "Homer Simpson, Junior",
            {"first": "Homer", "last": "Simpson", "suffix": "Jr"},
        ),
        ("HJ Simpson", {"first": "H", "last": "Simpson", "middle": "J"}),
        ("HS", {"first": "H", "last": "S"}),
        ("HJS", {"first": "H", "last": "S", "middle": "J"}),
    ],
)
def test_parse_string(test_input, expected):
    result = parse_names(test_input)[0]
    assert result.title == expected.get("title", "")
    assert result.first == expected.get("first", "")
    assert result.middle == expected.get("middle", "")
    assert result.last == expected.get("last", "")
    assert result.suffix == expected.get("suffix", "")


def test_parse_emu():
    assert Person({"NamFirst": "Homer", "NamLast": "Simpson"}) == Person(
        "Homer Simpson"
    )


def test_to_emu():
    assert Person("Mr. Homer J. Simpson, Jr.").to_emu() == {
        "NamPartyType": "Person",
        "NamTitle": "Mr.",
        "NamFirst": "Homer",
        "NamMiddle": "J",
        "NamLast": "Simpson",
        "NamSuffix": "Jr",
    }


@pytest.mark.parametrize(
    "test_input",
    [
        ("Homer Simpson", "Homer J. Simpson"),
        ("Homer Simpson", "H. Simpson"),
        ("Homer Simpson", "H. J. Simpson"),
        ("Homer Simpson", "Mr. H. J. Simpson"),
    ],
)
def test_names_are_similar(test_input):
    person, other = [Person(t) for t in test_input]
    assert person.similar_to(other)


@pytest.mark.parametrize(
    "test_input",
    [
        ("Homer Simpson", "Marge Simpson"),
        ("Homer J. Simpson", "Homer Q. Simpson"),
    ],
)
def test_names_are_different(test_input):
    person, other = [Person(t) for t in test_input]
    assert not person.similar_to(other)


def test_combine_names():
    names = "Simpson, HJ, Simpson, M, Simpson, B, Simpson, LM, and Simpson, M"
    assert (
        combine_names(names, delim=", ", max_names=5)
        == "H. J. Simpson, M. Simpson, B. Simpson, L. M. Simpson, and M. Simpson"
    )


def test_combine_names_max():
    names = "Simpson, HJ, Simpson, M, Simpson, B, Simpson, LM, and Simpson, M"
    assert combine_names(names, delim=", ") == "H. J. Simpson, M. Simpson, et al."
