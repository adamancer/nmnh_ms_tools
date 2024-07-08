import re
from datetime import datetime

import yaml

from .lists import as_list, oxford_comma


def create_note(text, module=None, mod="+", maxlen=80, **kwargs):
    """Creates a note explaining a change

    The note should be formatted as follows:

    Short description of why change was made
    - Field1: Added/removed/changed
    - Field2: Added/removed/changed

    Long description if needed

    Parameters
    ----------
    text : str
        note formatted as a markdown list.
    module : str
        name of the module. If None, may not generate a valid note.

    Returns
    -------
    dict
        note formated as an append
    """
    mappings = {
        "ecatalogue": {
            "text": "NotNmnhText0",
            "date": "NotNmnhDate0",
            "kind": "NotNmnhType_tab",
            "by": "NotNmnhAttributedToRef_nesttab",
            "publish": "NotNmnhWeb_tab",
        }
    }

    try:
        mapping = mappings[module]
    except KeyError:
        mapping = {
            "text": "NteText0",
            "date": "NteDate0",
            "kind": "NteType_tab",
            "by": "NteAttributedToRef_nesttab",
            "publish": "NteMetadata_tab",
        }

    text = text.strip()
    lines = text.splitlines()
    if len(lines) > 1 and maxlen and len(lines[0]) > maxlen:
        raise ValueError(
            f"First line should be {maxlen} characters or fewer (length={len(lines[0])})"
        )
    elif len(lines) > 1 and maxlen is None:
        text = "\n\n".join([l.strip() for l in lines if l.strip()])

    params = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "Data Manager Remarks",
        "by": 1006206,
        "publish": "No",
    }
    params.update(kwargs)

    note = {"text": [text]}
    for key, val in params.items():
        note[key] = [as_list(val)] if "nesttab" in mapping[key] else [val]

    if mod:
        mod = "(" + mod.strip("()") + ")"
    return {f"{mapping[k]}{mod}": v for k, v in note.items()}


def create_markdown_note(data, text, **kwargs):
    """Creates a note explaining a change

    The note should be formatted as follows:

    Short description of why change was made
    - Field1: Added/removed/changed
    - Field2: Added/removed/changed

    Long description if needed

    Parameters
    ----------
    text : str
        note formatted as a markdown list.
    module : str
        name of the module. If None, may not generate a valid note.

    Returns
    -------
    dict
        note formatted as an append
    """
    kwargs.setdefault("maxlen", 240)
    content = [text]
    for change in data:

        try:
            key, old, new = change
        except ValueError:
            key, val = change
            content.append(f"- {key}: {val}")
        else:
            if isinstance(old, list) or isinstance(new, list):
                change = []

                removed = [f'"{s}"' for s in old if s not in new]
                if removed:
                    change.append(f"removed {oxford_comma(removed)}")

                added = [f'"{s}"' for s in new if s not in old]
                if added:
                    change.append(f"added {oxford_comma(added)}")

                if change:
                    change[0] = change[0][0].upper() + change[0][1:]
                    change = " and ".join(change)
                    content.append(f"- {key}: {change}")

            elif old and not new:
                content.append(f'- {key}: Removed "{old}"')
            elif new and not old:
                content.append(f'- {key}: Added "{new}"')
            elif new != old:
                content.append(f'- {key}: Changed "{old}" to "{new}"')

    return create_note("\n".join(content), **kwargs)


def create_yaml_note(data, text, quote_numeric=False, **kwargs):
    content = [f"# {text.lstrip('# ')}"]
    flow_style = any(isinstance(v, list) for v in data.values())
    if flow_style:
        flow_style = None
    yml = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=flow_style
    )
    if not quote_numeric:
        yml = re.sub(r"'(-?\d+(\.\d+)?)'", r"\1", yml)
    content.append(yml)
    return create_note("\n".join(content), **kwargs)
