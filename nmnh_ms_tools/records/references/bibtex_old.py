# pragma: exclude file
try:
    from warnings import deprecated
except ImportError:
    from typing_extensions import deprecated

"""Defines methods for mapping BibTeX to EMu"""

import warnings

from ...utils import Standardizer


@deprecated("Integrated into references.Reference")
class BibTeXMapper:
    """Consolidates functions for mapping to/from BibTeX"""

    entry_types = {
        "article",
        "book",
        "inbook",
        "incollection",
        "inproceedings",
        "manual",
        "mastersthesis",
        "misc",
        "phdthesis",
        "proceedings",
        "techreport",
        "unpublished",
    }

    entry_type_map = {
        "book series": "book",
        "chapter": "inbook",
        "manuscript": "unpublished",
        "other": "article",
        "thesis": "{}thesis",
        "thesis (masters)": "mastersthesis",
        "thesis (phd)": "phdthesis",
        # BHL genres
        "journal": "book",
        "monograph/item": "book",
        "monographic component part": "inbook",
        "serial": "book",
        "serial component part": "article",
        # xDD/xDD genres
        "fulltext": "book",
        #
        "book chapter": "inbook",
        "book review": "article",
        "dataset": "article",
        "journal article": "article",
        "magazine article": "article",
        # Crossref?
        "book-chapter": "inbook",
        "component": "inbook",
        "dissertation": "phdthesis",
        "journal-article": "article",
        "journal-issue": "incollection",
        "monograph": "book",
        "peer-review": "article",
        "posted-content": "misc",
        "proceedings-article": "inproceedings",
        "reference-entry": "misc",
        "report": "techreport",
        "report-component": "techreport",
    }

    _bad_entry_types = set(entry_type_map.values()) - entry_types
    if _bad_entry_types != {"{}thesis"}:
        raise ValueError(f"Invalid entry type mappings: {_bad_entry_types}")
    del _bad_entry_types

    def entry_type(self, kind, modifier=""):
        """Converts custom record type to BibTeX entry type"""
        kind = kind.lower()
        try:
            mask = self.entry_type_map[kind]
        except KeyError:
            mask = kind
            if mask.lower() not in self.entry_types:
                warnings.warn(f"Unrecognized entry_type: {mask}")
        return mask.format(modifier).lower()

    def source_field(self, kind):
        """Returns the BibTeX field for the source/parent publication"""
        type_to_source = {
            "article": "journal",
            "book": "series",
            "inbook": "booktitle",  # non-standard
            "incollection": "booktitle",
            "inproceedings": "booktitle",
            "mastersthesis": None,
            "misc": "journal",
            "phdthesis": None,
            "techreport": "journal",
        }
        return type_to_source[self.entry_type(kind)]

    def emu_prefix(self, kind):
        """Returns the EMu prefix associated with a given entry/source type"""
        field_to_prefix = {"book series": "Bos"}
        rec_type = self.emu_record_type(kind.lower()).lower()
        return field_to_prefix.get(rec_type, rec_type)[:3].title()

    def emu_record_type(self, kind, prefix=False):
        """Converts BibTeX entry type to EMu record type"""
        bibtex_to_emu = {
            "booktitle": "Book",
            "inbook": "Chapter",
            "incollection": "Chapter",
            "inproceedings": "Chapter",
            "mastersthesis": "Thesis",
            "misc": "Article",  # USGS uses this for PP(!)
            "phdthesis": "Thesis",
            "series": "Book Series",
            "techreport": "Article",  # USGS uses this for maps
        }
        rec_type = bibtex_to_emu.get(kind.lower(), kind).title()
        return self.emu_prefix(rec_type.lower()) if prefix else rec_type

    def emu_source_type(self, kind, prefix=False):
        """Converts BibTeX source field to EMu record type"""
        bibtex_to_emu = {"booktitle": "Book", "series": "Book Series"}
        src_field = self.source_field(kind)
        if src_field is not None:
            src_type = bibtex_to_emu.get(src_field, src_field).title()
            return self.emu_prefix(src_type) if prefix else src_type

    def emu_thesis_type(self, kind):
        """Converts BibTeX entry type to EMu thesis type"""
        bibtex_to_emu = {"mastersthesis": "Masters", "phdthesis": "PhD"}
        return bibtex_to_emu[self.entry_type(kind)]

    @staticmethod
    def parse_thesis(val):
        """Determines type of thesis from EMu record"""
        if val:
            stdval = Standardizer(minlen=1, delim="")(val)
            if "phd" in stdval:
                return "phdthesis"
            if stdval.startswith("m"):
                return "mastersthesis"
            raise ValueError(f"Could not map {repr(val)} to thesis type")
        return ""
