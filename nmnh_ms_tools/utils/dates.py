"""Defines helper functions for working with dates"""

import re
from datetime import date, datetime, timedelta
from functools import cached_property, total_ordering

from xmu import EMuDate

from . import del_immutable, set_immutable


@total_ordering
class FiscalYear:
    """Container for checking dates against the federal fiscal year

    Parameters
    ----------
    dt : datetime.date | datetime.datetime | str
        date or year to map to a fiscal year

    Attributes
    ----------
    year : int
        the fiscal year
    """

    def __init__(self, dt):
        dt = EMuDate(dt)
        self.year = dt.year + (1 if dt.month in (10, 11, 12) else 0)

    def __setattr__(self, attr, val):
        return set_immutable(self, attr, val)

    def __delattr__(self, attr):
        return del_immutable(self, attr)

    def __str__(self):
        return f"FY{self.year}"

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.year == FiscalYear(other).year

    def __lt__(self, other):
        return self.year < FiscalYear(other).year

    def __contains__(self, dt):
        if isinstance(dt, str):
            return dt in str(self)
        try:
            return self.start_date <= dt <= self.end_date
        except TypeError:
            try:
                return self.start_date <= dt.date() <= self.end_date
            except AttributeError:
                try:
                    return (
                        self.start_date
                        <= datetime.fromisoformat(dt).date()
                        <= self.end_date
                    )
                except:
                    pass
        raise ValueError(f"Could not determine if {str(self)} contains {repr(dt)}")

    def __add__(self, val):
        return self.__class__(self.year + val)

    def __sub__(self, val):
        return self.__class__(self.year - val)

    @cached_property
    def start_date(self):
        return date(year=self.year - 1, month=10, day=1)

    @cached_property
    def end_date(self):
        return date(year=self.year, month=9, day=30)


class DateRange:
    """Parses dates and date ranges

    Attributes
    ----------
    from_val : EMuDate
        the earlier date in a range
    to_val : EMuDate
        the later date in a range
    conj : EMuDate
        the word or character used to join a date range
    verbatim : Any
        the verbatim data

    Parameters
    ----------
    from_val : str | EMuDate | DateRange
        the earlier date in a range
    to_val : str | EMuDate | DateRange, optional
        the later date in a range. If omitted, this date is parsed from from_val
        instead.
    """

    def __init__(self, from_val: str | EMuDate, to_val: str = None):
        if isinstance(from_val, DateRange):
            from_val = from_val.verbatim
        if to_val:
            vals = [from_val]
            if to_val != from_val:
                vals.append(to_val)
            self.verbatim = " to ".join([v.strip() for v in vals])
            from_val = _remove_time(vals[0])
            to_val = _remove_time(vals[-1])
        else:
            self.verbatim = from_val
            from_val = _remove_time(from_val)
            to_val = from_val
            pattern = r"(\b\s*-+\s*\b|\b\s*to\s*\b|\b\s*through\s*\b|\b\s*thru\s*\b)"
            try:
                from_val, conj, to_val = re.split(pattern, from_val)
            except ValueError:
                pass
            else:
                # Add month if missing from half of a short range
                months = _get_months(self.verbatim)
                if not _get_months(from_val):
                    from_val += f" {months[0]}"
                if not _get_months(to_val):
                    to_val += f" {months[0]}"

                # Add year if missing from half of a short range
                years = _get_years(self.verbatim)
                if not _get_years(from_val):
                    from_val += f" {years[0]}"
                if not _get_years(to_val):
                    to_val += f" {years[0]}"

        self.from_val = EMuDate(from_val)
        self.to_val = EMuDate(to_val)
        self.conj = "to"

    def __setattr__(self, attr, val):
        return set_immutable(self, attr, val)

    def __delattr__(self, attr, val):
        return del_immutable(self, attr, val)

    def __str__(self):
        if self.from_val == self.to_val:
            return str(self.from_val)
        conj = f" {self.conj} " if self.conj.isalpha() else self.conj
        return f"{self.from_val}{conj}{self.to_val}"

    def __repr__(self):
        return (
            f"DateRange("
            f"from_val={repr(self.from_val)}, "
            f"to_val={repr(self.to_val)}, "
            f"conj={repr(self.conj)}, "
            f"verbatim={repr(self.verbatim)}"
            f")"
        )


def add_years(dt: date | datetime, num_years: int) -> date | datetime:
    """Adds the specified number of years to a date, accounting for Feb 29

    Parameters
    ----------
    dt : date | datetime
        a date
    num_years : int
        the number of years to add

    Returns
    -------
    date | datetime
        new instance of original class with the specified number of years added
    """
    try:
        return dt.__class__(dt.year + num_years, dt.month, dt.day)
    except ValueError:
        # Shift Feb 29 to Mar 1 if new year is not a leap year
        dt += timedelta(days=1)
        return dt.__class__(dt.year + num_years, dt.month, dt.day)


def _remove_time(val: str) -> str:
    """Removes the time from a date"""
    return re.split(r"\d+:", val)[0].strip()


def _get_years(val: str) -> list[str]:
    """Finds all years in a string"""
    return re.findall(r"\b\d{4}\b", val)


def _get_months(val: str) -> list[str]:
    """Finds all month names in a string"""
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    months += [m[:3] for m in months]
    months += ["Sept"]
    pattern = r"\b(" + "|".join(months) + r")\b"
    return [m[:3] for m in re.findall(pattern, val, flags=re.I)]
