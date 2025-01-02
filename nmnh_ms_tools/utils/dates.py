"""Defines helper functions for working with dates"""

from datetime import date, datetime, timedelta
from functools import cache, cached_property, total_ordering

from . import del_immutable, set_immutable


@total_ordering
class FiscalYear:
    """Container for checking dates against the federal fiscal year

    Parameters
    ----------
    year : int
        the fiscal year

    Attributes
    ----------
    year : int
        the fiscal year
    """

    def __init__(self, year):
        self.year = year

    def __setattr__(self, attr, val):
        return set_immutable(self, attr, val)

    def __delattr__(self, attr):
        return del_immutable(self, attr)

    def __str__(self):
        return f"FY{self.year}"

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.year == other.year

    def __lt__(self, other):
        return self.year < other.year

    def __contains__(self, dt):
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


@cache
def fy(year: int) -> FiscalYear:
    """Creates a fiscal year object

    Parameters
    ----------
    year : int | str
        the full fiscal year as either an integer or a string ending with YYYY

    Returns
    -------
    FiscalYear
        a FiscalYear object representing the given year
    """
    if isinstance(year, str):
        return fy(int(year[-4:]))
    return FiscalYear(year)


def get_fy(dt: date | datetime | str):
    """Get the fiscal year for the specified date

    Parameters
    ----------
    dt : datetime.date | datetime.datetime | str
        date to check

    Returns
    -------
    FiscalYear
        the FiscalYear corresponding to the specified date
    """
    try:
        fyear = fy(dt.year)
    except AttributeError as exc:
        try:
            return get_fy(datetime.fromisoformat(dt))
        except:
            raise exc
    else:
        return fyear if dt in fyear else fyear + 1


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
