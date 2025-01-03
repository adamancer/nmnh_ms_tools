"""Tests dictionary helper functions"""

import pytest


from nmnh_ms_tools.utils import (
    del_immutable,
    set_immutable,
    str_class,
    repr_class,
)


class FakeClass:

    def __init__(self):
        self.attributes = ["a", "b", "c"]
        self.a = "a"
        self.b = ["b"]
        self.c = None

    def __setattr__(self, attr, val):
        set_immutable(self, attr, val)

    def __delattr__(self, attr):
        del_immutable(self, attr)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (None, "class: FakeClass\na    : a\nb    : b"),
        (["a"], "class: FakeClass\na    : a"),
    ],
)
def test_str_class(test_input, expected):
    assert str_class(FakeClass(), attributes=test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (None, "FakeClass(a='a', b=['b'], c=None)"),
        (["a"], "FakeClass(a='a')"),
    ],
)
def test_repr_class(test_input, expected):
    assert repr_class(FakeClass(), attributes=test_input) == expected


def test_set_immutable():
    with pytest.raises(AttributeError, match="Cannot modify immutable attribute"):
        FakeClass().a = None


def test_del_immutable():
    with pytest.raises(AttributeError, match="Cannot delete immutable attribute"):
        del FakeClass().a
