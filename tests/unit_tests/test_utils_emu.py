"""Tests functions in AdamancerBot class"""

import pytest


from nmnh_ms_tools.utils import create_markdown_note, create_yaml_note


def test_create_markdown_note():
    data = [
        ("Simple Change", "A", "B"),
        ("Manual Change", "Change recorded manually"),
        ("Item Added", "", "A"),
        ("Item Removed", "A", ""),
        ("List Item Added", ["A"], ["A", "B"]),
        ("List Item Removed", ["A", "B"], ["A"]),
    ]
    assert create_markdown_note(data, "Markdown note", date="1970-01-01") == {
        "NteAttributedToRef_nesttab(+)": [[1006206]],
        "NteDate0(+)": ["1970-01-01"],
        "NteMetadata_tab(+)": ["No"],
        "NteText0(+)": [
            'Markdown note\n- Simple Change: Changed "A" to "B"\n- Manual Change: Change recorded manually\n- Item Added: Added "A"\n- Item Removed: Removed "A"\n- List Item Added: Added "B"\n- List Item Removed: Removed "B"'
        ],
        "NteType_tab(+)": ["Data Manager Remarks"],
    }


def test_create_yaml_note():
    data = {"a": 1, "b": 2, "c": 3}
    assert create_yaml_note(data, "YAML note", date="1970-01-01") == {
        "NteAttributedToRef_nesttab": [[1006206]],
        "NteDate0": ["1970-01-01"],
        "NteMetadata_tab": ["No"],
        "NteText0": ["# YAML note\na: 1\nb: 2\nc: 3"],
        "NteType_tab": ["Structured Note"],
    }


def test_long_first_line():
    with pytest.raises(ValueError):
        create_markdown_note([("k", "o", "v")], "Long first line", maxlen=1)
