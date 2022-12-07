"""Defines containers for various types of natural history data"""
from .catnums import CatNum, CatNums, parse_catnum, parse_catnums, is_antarctic
from .classification import get_tree
from .core import write_csv
from .people import Person, People, parse_names
from .references import (
    Citation, Citations, Reference, References, get_author_and_year
)
from .sites import Site, SEAS, sites_to_geodataframe
from .specimens import Specimen
from .stratigraphy import (
    ChronoStrat,
    LithoStrat,
    StratUnit,
    parse_chronostrat,
    parse_lithostrat
)
