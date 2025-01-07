"""Defines simple actions to run when preparing an import"""

from functools import cache

from ...records import Person, Reference
from ...utils import ucfirst


def run_action(val, action):
    """Runs the specified action

    Supported actions include
    - fill_reference (to fill a reference from a DOI)
    - to_emu (to map data to EMu XML)
    - any built-in string method

    Parameters
    ----------
    val : str
        the value to run the action on
    action : list
        the name of a supported action followed by any additional arguments

    Returns
    -------
    Any
        the result of the specified action on the specified value
    """

    # Check if this action is a built-in method of the specified object
    try:
        return getattr(val, action[0])(*action[1:])
    except AttributeError as exc:
        if val is None:
            return val
        if (
            str(exc)
            != f"{repr(type(val).__name__)} object has no attribute {repr(action[0])}"
        ):
            raise

    functions = {
        "fill_reference": fill_reference,
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
    """Fills out a reference from a DOI or integer and returns it in EMu XML format

    Parameters
    ----------
    val : str | int
        a DOI (for a new reference) or EMu IRN (for an existing reference)

    Returns
    -------
    EMuRecord
        an EMu record for the specified reference
    """
    if isinstance(val, int) or val.isnumeric():
        return val
    return Reference(val).to_emu()


def to_emu(val, module):
    """Create an EMu record for the specified value

    Parameters
    ----------
    val : Any
        the data to format for EMu
    module : str
        the name of an EMu module. Currently only eparties is supported.

    Returns
    -------
    EMuRecord
        an EMu record based on the specified module
    """
    return {"eparties": Person}[module](val).to_emu()
