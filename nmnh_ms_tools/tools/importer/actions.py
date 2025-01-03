from functools import cache

from ...records import Person, Reference
from ...utils import ucfirst


def run_action(val, action):
    methods = {"zfill": "zfill"}
    try:
        return getattr(val, methods[action[0]])(*action[1:])
    except KeyError as exc:
        if str(exc)[1:-1] != action[0]:
            raise
    except AttributeError:
        if val is None:
            return val
        raise

    functions = {
        "add_direction": add_direction,
        "fill_reference": fill_reference,
        "flip_sign": flip_sign,
        "to_emu": to_emu,
        "ucfirst": ucfirst,
    }
    try:
        return functions[action[0]](val, *action[1:])
    except KeyError as exc:
        if str(exc)[1:-1] != action[0]:
            raise
    except AttributeError:
        if val is None:
            return val
        raise

    raise ValueError(f"Could not run action on {repr(val)}: {action}")


@cache
def fill_reference(val):
    if isinstance(val, int) or val.isnumeric():
        return val
    return Reference(val).to_emu()


def flip_sign(val):
    if isinstance(val, str):
        return val[1:] if val.startswith("-") else f"-{val}"
    return val * -1


def to_emu(val, module):
    return {"eparties": Person}[module](val).to_emu()


def add_direction(val, dir):
    return f"{val} {dir}"
