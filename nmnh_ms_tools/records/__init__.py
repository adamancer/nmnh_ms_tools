"""Defines containers for various types of natural history data"""

from .. import _ImportClock

with _ImportClock("records"):
    from .catnums import (
        CatNum,
        parse_catnum,
        parse_catnums,
        is_antarctic,
        PARSER as CATNUM_PARSER,
        MULTIPARSER as CATNUM_MULTIPARSER,
    )
    from .catnums_old import CatNums
    from .classification import (
        TaxaList,
        TaxaParser,
        TaxaTree,
        Taxon,
        get_tree,
    )
    from .core import Record, RecordEncoder, write_csv
    from .people import Person, People, combine_names, parse_names
    from .references import (
        Citation,
        Citations,
        Reference,
        ReferenceOld,
        References,
        get_author_and_year,
        is_doi,
        std_doi,
    )
    from .sites import Site, sites_to_geodataframe, SEAS
    from .specimens import Specimen
    from .stratigraphy import StratPackage, StratUnit, parse_strat_units
