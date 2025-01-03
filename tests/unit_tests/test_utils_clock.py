"""Tests clock functions"""

import re

import pytest


from nmnh_ms_tools.utils import (
    clock,
    clock_snippet,
    report,
    clock_all_methods,
)


MASK = "tests.unit_tests.test_utils_clock.fakeclass.<locals>.FakeClass.{}"


@pytest.fixture
def fakeclass():
    class FakeClass:
        def __init__(self, nums=10):
            self.nums = nums

        def __str__(self):
            return ""

        @property
        def fake_property(self):
            return self.nums

        @clock
        def fake_clocked_method(self):
            return sum(range(self.nums))

        def fake_unclocked_method(self):
            return sum(range(self.nums))

        def _fake_private_method(self):
            return sum(range(self.nums))

    return FakeClass


def test_clock(fakeclass):
    inst = fakeclass()
    for i in range(5):
        inst.fake_clocked_method()
        inst.nums *= 10  # increase range to force duration check
    results = report(reset=True)
    assert results[MASK.format("fake_clocked_method")].count == 5


def test_clock_context_manager(fakeclass):
    inst = fakeclass()
    for i in range(5):
        with clock_snippet("clock_context_manager"):
            inst.fake_unclocked_method()
    results = report(reset=True)
    assert results["clock_context_manager"].count == 5


def test_clock_all_methods(fakeclass):
    clock_all_methods(fakeclass, include_private=False)
    inst = fakeclass()
    for i in range(5):
        str(inst)
        inst.fake_clocked_method()
        inst.fake_unclocked_method()
        inst._fake_private_method()
    results = report(reset=True)
    # Private and magic methods excluded so should raise exceptions
    for key in [MASK.format(k) for k in ["__str__", "_fake_private_method"]]:
        with pytest.raises(KeyError):
            assert results[key]
    assert results[MASK.format("fake_clocked_method")].count == 5
    assert results[MASK.format("fake_unclocked_method")].count == 5


def test_report(fakeclass, tmp_path):
    inst = fakeclass()
    for i in range(5):
        inst.fake_clocked_method()
    f = tmp_path / "report.txt"
    results = report(f, reset=False)
    expected = (
        "function,count,total,mean,max\ntotal,1,0.0,0.0,0.0\ntests.unit_tests."
        "test_utils_clock.fakeclass.<locals>.FakeClass.fake_clocked_method,"
        "5,0.0,0.0,0.0\n"
    )
    # Clocked methods sometimes take slightly longer that 0.0 seconds
    result = re.sub(r"\b0\.0\d+", "0.0", f.read_text(encoding="utf-8-sig"))
    assert result == expected
