"""Defines containers for various types of natural history data"""
from .catnums import CatNum, get_catnum, parse_catnums
from .classification import get_tree
from .core import write_csv
from .people import Person, parse_names
from .references import Reference, References
from .sites import Site, SEAS
from .specimens import Specimen
from .stratigraphy import (
    ChronostratHierarchy,
    LithostratHierarchy,
    StratUnit,
    parse_strat
)
