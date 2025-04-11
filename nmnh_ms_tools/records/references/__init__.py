"""Defines methods for parsing and manipulating references"""

from .references import Reference, format_doi
from .bibtex_old import BibTeXMapper
from .references_old import (
    Citation,
    Citations,
    Reference as ReferenceOld,
    References,
    get_author_and_year,
    is_doi,
    std_doi,
)
