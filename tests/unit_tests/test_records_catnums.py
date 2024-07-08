"""Tests DirectionParser"""

# FIXME: Test is_antarctic

import pytest

from nmnh_ms_tools.records.people import (
    Person,
    combine_names,
    combine_authors,
    parse_names,
)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("Homer Simpson", {"first": "Homer", "last": "Simpson"}),
        ("Homer J. Simpson", {"first": "Homer", "last": "Simpson", "middle": "J"}),
        ("Homer Jay Simpson", {"first": "Homer", "last": "Simpson", "middle": "Jay"}),
    ],
)
def test_person(test_input, expected):
    result = Person(test_input)
    assert result.last == expected.get("last", "")
    assert result.first == expected.get("first", "")
    assert result.middle == expected.get("middle", "")


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
