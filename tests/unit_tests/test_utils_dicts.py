"""Tests dictionary helper functions"""
import pytest


from nmnh_ms_tools.utils.dicts import (
    AttrDict,
    IndexedDict,
    NamedDict,
    StaticDict,
    combine,
    get_common_items,
    get_first,
    get_all,
    dictify,
    nameddict,
    prune,
)


def test_attrdict_get_methods():
    obj = AttrDict({"key": "val"})
    assert obj.key == "val"
    assert obj["key"] == "val"


def test_nameddict_factory():
    factory = nameddict("DictName", keys=["key"])
    obj = factory("val")
    assert obj.key == "val"
    assert obj["key"] == "val"


def test_nameddict_from_list():
    factory = nameddict("DictName", keys=["key1", "key2"])
    obj = factory("val1", "val2")
    assert obj.key1 == "val1"
    assert obj["key1"] == "val1"
    assert obj[0] == "val1"
    assert obj.key2 == "val2"
    assert obj["key2"] == "val2"
    assert obj[1] == "val2"


def test_nameddict_from_dict():
    factory = nameddict("DictName", keys=["key1", "key2"])
    obj = factory({"key1": "val1", "key2": "val2"})
    assert obj.key1 == "val1"
    assert obj["key1"] == "val1"
    assert obj.key2 == "val2"
    assert obj["key2"] == "val2"


def test_indexeddict_item_methods():
    dct = IndexedDict()
    dct[1000] = 1
    dct[1001] = 1
    assert dct[1000] == 1
    assert dct[1001] == 1
    del dct[1000]
    del dct[1001]
    assert not dct


def test_indexeddict_from_dict():
    dct = IndexedDict({"1": 1, "2": 2})
    assert dict(dct) == {"001": {"1": 1}, "002": {"2": 2}}


def test_indexeddict_from_indexeddict():
    dct = IndexedDict({"001": {"1": 1}, "002": {"2": 2}})
    assert dict(dct) == {"001": {"1": 1}, "002": {"2": 2}}


def test_staticdict_change_existing_key():
    dct = StaticDict({"key1": "val1"})
    with pytest.raises(KeyError):
        dct["key1"] = "val2"


def test_staticdict_delete_key():
    dct = StaticDict({"key1": "val1"})
    with pytest.raises(KeyError):
        del dct["key1"]


def test_combine():
    dct1 = {"key1": "val1", "key2": "val2"}
    dct2 = {"key2": "val4", "key3": "val3"}
    expected = {"key1": ["val1"], "key2": ["val2", "val4"], "key3": ["val3"]}
    assert combine(dct1, dct2) == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ({"key1": "val1"}, {"key1": "val1"}),
        ([{"key1": "val1"}], [{"key1": "val1"}]),
    ],
)
def test_dictify(test_input, expected):
    assert dictify(test_input) == expected


def test_get_all():
    dct = {"key1": "val1", "key2": "val2", "key3": "val3"}
    assert get_all(dct, ["key2", "key3"]) == ["val2", "val3"]


def test_get_all_required_missing():
    dct = {"key1": "val1"}
    with pytest.raises(KeyError):
        get_all(dct, ["key1", "key2"])


def test_get_all_required_false():
    dct = {"key1": "val1"}
    assert get_all(dct, ["key1", "key2"], required=False) == ["val1"]


def test_get_common_items():
    dct1 = {"key1": "val1", "key2": "val2"}
    dct2 = {"key2": "val2", "key3": "val3"}
    assert get_common_items(dct1, dct2) == {"key2": "val2"}


def test_get_first():
    dct = {"key1": "val1", "key2": "val2", "key3": "val3"}
    assert get_first(dct, ["key2", "key3"]) == "val2"


def test_prune():
    dct = {
        "key1": "",
        "key2": {"key21": {"key211": None, "key212": "val212"}},
        "key3": {"key31": []},
    }
    assert prune(dct) == {"key2": {"key21": {"key212": "val212"}}}
