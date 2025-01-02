"""Defines containers for various types of natural history data"""

from .. import _ImportClock

with _ImportClock("records"):
    from .catnums import CatNum, CatNums, parse_catnum, parse_catnums, is_antarctic
    from .classification import get_tree
    from .core import Record, RecordEncoder, write_csv
    from .people import Person, People, parse_names
    from .references import (
        Citation,
        Citations,
        Reference,
        Reference2,
        References,
        get_author_and_year,
        is_doi,
        std_doi,
    )
    from .sites import Site, SEAS, sites_to_geodataframe
    from .specimens import Specimen
    from .stratigraphy import (
        ChronoStrat,
        LithoStrat,
        StratPackage,
        StratUnit,
        parse_chronostrat,
        parse_lithostrat,
    )
