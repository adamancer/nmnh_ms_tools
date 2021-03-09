"""Defines miscellaneous helper functions"""
import csv
import datetime as dt
import json
import logging
import os
import re
import sys
from textwrap import fill

from pytz import timezone

from .lists import as_list



logger = logging.getLogger(__name__)




class ABCEncoder(json.JSONEncoder):
    """Defines methods to encode ABC and datetime objects as JSON"""

    def __init__(self, *args, **kwargs):
        super(ABCEncoder, self).__init__(*args, **kwargs)


    def default(self, val):
        try:
            return val.obj
        except AttributeError:
            if isinstance(val, dt.date):
                return val.strftime('%Y-%m-%d')
            return json.JSONEncoder.default(self, val)




class NoFontScoreFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith('findfont: ')




def prompt(text, validator, confirm=False,
           helptext='No help text provided', errortext='Invalid response!'):
    """Prompts for and validates text provided by user

    Args:
        text (str): the prompt to present to the user
        validator (mixed): the dict, list, or string used to validate the
            repsonse
        confirm (bool): if true, user will be prompted to confirm value
        helptext (str): text to show if user response is "?"
        errortext (str): text to return if user response does not validate

    Return:
        Validated response to prompt
    """
    # Prepare string
    text = '{} '.format(text.rstrip())
    # Prepare validator
    if isinstance(validator, str):
        validator = re.compile(validator, re.U)
    elif isinstance(validator, dict) and sorted(validator.keys()) == ['n', 'y']:
        text = '{} '.format(text, '/'.join(list(validator.keys())))
    elif isinstance(validator, dict):
        keys = list(validator.keys())
        keys.sort(key=lambda s: s.zfill(100))
        options = ['{} '.format(key, validator[key]) for key in keys]
    elif isinstance(validator, list):
        options = ['{} '.format(i + 1, val) for
                   i, val in enumerate(validator)]
    else:
        raise ValueError('Validator must be dict, list, or str')
    # Validate response
    loop = True
    num_loops = 0
    while loop:
        # Print options
        try:
            options
        except UnboundLocalError:
            pass
        else:
            print('-' * 60 + '\nOPTIONS\n-------')
            for option in options:
                print(option)
            print('-' * 60)
        # Prompt for value
        val = input(text)
        if val.lower() == 'q':
            print('User exited prompt')
            sys.exit()
        elif val.lower() == '?':
            print(fill(helptext))
            loop = False
        elif isinstance(validator, list):
            try:
                result = validator[int(val) - 1]
            except IndexError:
                pass
            else:
                if num_loops >= 0:
                    loop = False
        elif isinstance(validator, dict):
            try:
                result = validator[val]
            except KeyError:
                pass
            else:
                loop = False
        else:
            try:
                validator.search(val).group()
            except AttributeError:
                pass
            else:
                result = val
                loop = False
        # Confirm value, if required
        if confirm and not loop:
            try:
                result = str(result)
            except UnicodeEncodeError:
                result = str(result)
            loop = prompt('Is this value correct: "{}"?'.format(result),
                          {'y' : False, 'n' : True}, confirm=False)
        elif loop:
            print(fill(errortext))
        num_loops += 1
    # Return value as unicode
    return result


def localize_datetime(timestamp, timezone_id='US/Eastern',
                      mask='%Y-%m-%dT%H:%M:%S'):
    """Localize timestamp to specified timezone

    Returns:
        Localize datetime as string formatted according to the mask
    """
    localized = timezone(timezone_id).localize(timestamp)
    if mask is not None:
        return localized.strftime(mask)
    return localized


def write_emu_search(vals, field='irn', operator='=',
                     mask=None, output='search.txt'):
    """Writes EMu search string"""
    vals = sorted({s.strip() for s in vals if s.strip()})
    if mask is None:
        mask = os.path.join(os.path.dirname(__file__), 'files', 'mask.txt')
    if mask.endswith('.txt'):
        mask = open(mask, 'r').read()
    search = []
    for val in vals:
        if isinstance(val, str):
            val = val.replace("'", r"\'")
        if re.match(r'[a-z]', val, flags=re.I) or operator != '=':
            val = "'{}'".format(val)
        search.append('\t(\n\t\t{} {} {}\n\t)'.format(field, operator, val))
    with open(output, 'w') as f:
        f.write(mask.format('\n\tor\n'.join(search)))


def nullify(val, remove_empty=True):
    """Coerces string nulls to None"""
    nulls = {
        'empty',
        'n/a',
        'none',
        'not applicable',
        'not provided',
        'not given',
        'not stated',
        'null'
    }
    if isinstance(val, list):
        vals = [nullify(val) for val in val]
        return [val for val in vals if val] if remove_empty else vals
    return None if str(val).lower().strip(' .[]') in nulls else val


def coerce(val, coerce_to, delim=' | '):
    """Coereces val to another data type"""
    val = nullify(val)
    if isinstance(val, type(coerce_to)) or coerce_to is None:
        if isinstance(val, str):
            return val.strip()
        return val

    cast_from = type(val)
    cast_to = type(coerce_to)

    # Cast to custom class
    if cast_to == type:
        try:
            return coerce_to(val)
        except TypeError:
            if not val:
                return None
            raise

    # Complex cast (lists of types)
    try:
        cast_to_inner = type(coerce_to[0])
    except (IndexError, TypeError):
        pass
    else:
        val = coerce(val, cast_to(), delim=delim)
        val = [cast_to_inner(s) if s else None for s in val]
        if any(val):
            return cast_to(val)
        return cast_to([])
    # Return default if no value provided
    if val is None:
        return coerce_to
    # String to float
    if isinstance(val, str) and isinstance(coerce_to, (int, float)):
        return cast_to(val) if val else cast_to()
    # String to list/tuple
    if isinstance(val, str) and isinstance(coerce_to, (list, tuple)):
        val = [s.strip() for s in val.split(delim.strip())]
        return cast_to(val) if any(val) else cast_to()
    # Int/float to string
    if isinstance(val, (int, float)) and isinstance(coerce_to, (str)):
        return cast_to(val) if val is not None else cast_to()
    # Int/float to list
    if isinstance(val, (int, float)) and isinstance(coerce_to, (list, tuple)):
        return [val] if isinstance(coerce_to, list) else tuple([val])
    # List/tuple to string
    if isinstance(val, (list, tuple)) and isinstance(coerce_to, str):
        return delim.join([str(s) for s in val])
    # List/tuple to various
    types = (str, int, float)
    if isinstance(val, (list, tuple)) and isinstance(coerce_to, types):
        val = [cast_to(s) for s in val if not isinstance(val, cast_to)]
        return cast_from(val) if any(val) else cast_from()
    raise TypeError('Could not coerce {} to {}'.format(repr(val), cast_to))


def configure_log(name=None, level='DEBUG', stream=True):
    """Convenience function that configures a simple log"""
    if name is None:
        name = __name__
    fn = name if name.lower().endswith('.log') else '{}.log'.format(name)
    handlers = [logging.FileHandler(fn, 'w', encoding='utf-8')]
    if stream:
        handlers.append(logging.StreamHandler())
    # Filter matplotlib font check from debug
    for handler in handlers:
        handler.addFilter(NoFontScoreFilter())
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=getattr(logging, level.upper()),
        handlers=handlers,
    )


def read_dwc_archive(fp, limit=None):
    """Reads a DwC archive"""
    with open(fp, 'r', encoding='utf-8') as f:
        rows = csv.reader(f, delimiter='\t')
        keys = next(rows)
        for i, row in enumerate(rows):
            if limit and i > limit:
                return
            yield dict(zip(keys, row))


def validate_direction(direction):
    """Validates a compass direction"""
    full = r'[Nn]orth|[Ss]outh|[Ee]ast|[Ww]est'
    patterns = [
        r'^[NSEW]$',
        r'^[NS][EW]$',
        r'^[NSEW][NS][NSEW]$',
        r'^[NS]\d{1,2}(\.\d+)?[EW]$',
        r'^({0})(-?({0})){{,2}}$'.format(full)
    ]
    match = None
    for pattern in patterns:
        if re.match(pattern, direction):
            return True
    else:
        msg = 'Invalid direction: {}'.format(direction)
        #logger.debug(msg)
        raise ValueError(msg)


def get_ocean_name(ocean):
    """Gets the base name of an ocean"""
    pattern = r'\b(north|south|ocean)\b'
    try:
        return re.sub(pattern, '', ocean, flags=re.I).strip().lower()
    except TypeError:
        return


def clear_empty(val):
    """Cleans common phrases signifying that no data is present (e.g., not given)"""
    vals = as_list(val)
    # Split values on hyphen or slash
    delim = r'(?: (\-|/|or) )'
    if len(vals) == 1 and re.search(delim, vals[0]):
        vals = re.split(delim, vals[0])
    # Remove strings used to denote missing data
    blacklist = [
        r'([a-z]+ )?((not |il)legible|not stated|(not |un)determined|unknown)',
        r'locality in multiple [a-z]+',
    ]
    for pattern in blacklist:
        pattern = r'^\[?{}\]?$'.format(pattern)
        vals = [s for s in vals if not re.search(pattern, s, flags=re.I)]
    if vals:
        return vals[0] if isinstance(val, str) else vals
    # Return empty of same class as original value
    return type(val)()
