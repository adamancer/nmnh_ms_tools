"""Defines methods for parsing and manipulating references"""

from .bibtex import BibTeXMapper
from .references import (
    Citation,
    Citations,
    Reference,
    References,
    get_author_and_year,
    is_doi,
    std_doi,
)
from .references2 import Reference as Reference2
