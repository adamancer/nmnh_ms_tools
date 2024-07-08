"""Defines SQLite databases used throughout this package"""

from .helpers import init_helper, time_query

from .. import _ImportClock

with _ImportClock("databases"):
    from .helpers import init_helper
