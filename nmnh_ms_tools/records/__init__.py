"""Defines containers for various types of natural history data"""

from .. import _ImportClock

with _ImportClock("records"):
    from .catnums import CatNum, parse_catnum, parse_catnums, is_antarctic
    from .catnums_old import CatNums
    from .classification import (
        TaxaList,
        TaxaNamer,
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
    from .sites import Site, SEAS, sites_to_geodataframe
    from .specimens import Specimen
    from .stratigraphy import StratPackage, StratUnit, parse_strat_units
