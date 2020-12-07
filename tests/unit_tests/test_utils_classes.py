"""Tests dictionary helper functions"""
import pytest


from nmnh_ms_tools.utils.classes import str_class, repr_class


class FakeClass:

    def __init__(self):
        self.attributes = ['a', 'b', 'c']
        self.a = 'a'
        self.b = ['b']
        self.c = None




@pytest.mark.parametrize(
    'test_input,expected',
    [
        (None, 'class: FakeClass\na    : a\nb    : b'),
        (['a'], 'class: FakeClass\na    : a'),
    ],
)
def test_str_class(test_input, expected):
    assert str_class(FakeClass(), attributes=test_input) == expected


@pytest.mark.parametrize(
    'test_input,expected',
    [
        (None, "FakeClass(a=a, b=['b'], c=None)"),
        (['a'], 'FakeClass(a=a)'),
    ],
)
def test_repr_class(test_input, expected):
    assert repr_class(FakeClass(), attributes=test_input) == expected
