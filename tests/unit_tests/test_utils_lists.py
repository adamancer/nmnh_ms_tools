"""Tests dictionary helper functions"""
import pytest


from nmnh_ms_tools.utils.lists import (
    as_list,
    as_set,
    dedupe,
    most_common,
    oxford_comma
)


def test_dedupe_list_of_strings():
    assert dedupe(['a', 'a', 'b', 'c']) == ['a', 'b', 'c']


def test_dedupe_list_of_strings_to_lower():
    assert dedupe(['a', 'A', 'b', 'c']) == ['a', 'b', 'c']


def test_as_list_simple_string():
    assert as_list('abc') == ['abc']


def test_as_list_delimited_string():
    assert as_list('a|b|c') == ['a', 'b', 'c']


def test_as_set_delimited_string():
    assert as_set('a|b|c') == {'a', 'b', 'c'}


def test_most_common():
    assert most_common(['a', 'a', 'b', 'c']) == 'a'


def test_oxford_comma():
    assert oxford_comma(['a', 'b', 'c']) == 'a, b, and c'
