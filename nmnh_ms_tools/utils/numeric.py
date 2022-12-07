"""Defines helper functions for working with floats and ints"""
import re


def as_numeric(val):
    """Converts string representation of number to float or int"""
    if isinstance(val, (float, int)):
        return val
    if not val:
        raise ValueError("Cannot convert '{}' to float or int".format(val))
    # Remove thousands separators
    val = val.replace(",", "")
    # Add coefficient of 0 to fractions
    if val and "/" in val and not " " in val:
        val = "0 {}".format(val)
    # Convert value to float or int
    try:
        coefficient, fraction = val.split(" ")
    except (AttributeError, ValueError):
        return float(val) if "." in val else int(val)
    else:
        numerator, denominator = fraction.split("/")
        return int(coefficient) + int(numerator) / int(denominator)


def base_to_int(i, base):
    """Converts integer in specified base to base 10"""
    assert isinstance(i, (int, str)), "expected int or str"
    return int(str(i), base)


def int_to_base(i, base):
    """Converts base 10 integer to specified base"""
    digs = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if i == 0:
        return "0"
    sign = 1 if i >= 0 else -1
    i *= sign
    digits = []
    while i:
        digits.append(digs[i % base])
        i = int(i / base)
    if sign < 0:
        digits.append("-")
    digits.reverse()
    return "".join(digits).upper()


def frange(start, stop, step):
    """Mimics functionality of xrange for floats

    From http://stackoverflow.com/questions/477486/

    Args:
        start (int or float): first value in range (inclusive)
        stop (int or float): last value in range (exclusive)
        step (float): value by which to increment start
    """
    rng = start
    while rng < stop:
        yield rng
        rng += step


def num_dec_places(val, max_dec_places=5):
    """Counts the number of digits after the decimal point"""
    try:
        if isinstance(val, float):
            val = re.sub(r"\.0*$", "", str(val))
        _, dec = str(val).split(".")
        return len(dec) if len(dec) < max_dec_places else max_dec_places
    except ValueError:
        return 0
