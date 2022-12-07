"""Defines methods for mapping BibTeX to EMu"""
from ...utils.standardizers import Standardizer


class BibTeXMapper:
    """Consolidates functions for mapping to/from BibTeX"""

    def entry_type(self, kind, modifier=""):
        """Converts custom record type to BibTeX entry type"""
        custom_to_bibtex = {
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
            "monographic component part": "chapter",
            "serial": "book",
            "serial component part": "article",
            # GeoDeepDive/xDD genres
            "fulltext": "book",
        }
        return custom_to_bibtex.get(kind.lower(), kind).format(modifier).lower()

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
            raise ValueError("Could not map {} to thesis type".format(val))
        return ""
