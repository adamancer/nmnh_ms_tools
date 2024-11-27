"""Roughly formats reference string according to CSE guidelines"""

import re

from .core import BaseFormatter
from ....records.people import combine_names


class CSEFormatter(BaseFormatter):

    def __str__(self):
        masks = {
            "article": "{authors}. {year}. {title}. {publication}. {volume}({number}):{pages}. Available from: {url}; doi:{doi}.",
            "book": "{authors}. {year}. {title}. {volume}({number}). {city} ({state}): {publisher} {pages} p.",
            "inbook": "{authors}. {year}. {title}. In: {publication}. {pages}.",
            "mastersthesis": "{authors}. {year}. {title} [thesis]. {publisher}. {pages} p.",
            "phdthesis": "{authors}. {year}. {title} [thesis]. {publisher}. {pages} p.",
        }
        try:
            mask = masks[self.ref.entry_type]
        except KeyError:
            mask = masks["article"]

        ref = self.ref.to_dict()
        ref["authors"] = self._format_authors()
        ref["title"] = ref["title"].rstrip(".")
        ref["publication"] = self._format_publication()

        # Publication locality not captured but is included above
        ref["city"] = ""
        ref["state"] = ""

        # Clear URL if a DOI exists
        if ref["doi"]:
            ref["url"] = ""

        # Explicitly set null values to an empty string
        ref = {k: v if v else "" for k, v in ref.items()}
        ref["year"] = self.ref.year

        # Clean up string
        formatted = mask.format(**ref)
        formatted = re.sub(r" +", " ", formatted)
        formatted = re.sub(r"\. +\.", ".", formatted)
        formatted = re.sub(r"(?<=[^\d]) p\.$", ".", formatted)
        formatted = (
            formatted.replace(" Available from: ;", "")
            .replace(" doi:.", ".")
            .replace(": .", ".")
            .replace(" :", "")
            .replace(" ()", "")
            .replace("()", "")
            .replace(" .", ".")
            .replace(".:.", ".")
            .replace(".:", ". ")
            .lstrip(". ")
            .rstrip(";:. ")
            + "."
        )
        formatted = re.sub(r"\.\. ", ". ", formatted)

        return formatted

    def _format_publication(self) -> str:
        """Formats the publication name, abbreviating it if necessary"""
        try:
            pub = self.ref.publication
        except AttributeError:
            pub = {
                "article": self.ref.journal,
                "incollection": self.ref.booktitle,
            }.get(self.ref.entry_type)
        # Abbreviate journal titles according to the ISO 4 standard
        if self.ref.entry_type == "article":
            return self.iso_4_title(pub).replace(".", "")
        return pub

    def _format_authors(self) -> str:
        """Formats the author string"""
        try:
            author = self.ref.author
        except AttributeError:
            author = self.ref.authors

        author_string = combine_names(
            author, max_names=10, delim=", ", conj="", mask="{last} {first} {middle}"
        )
        author_string = author_string.replace(". et al", ", et al")
        return re.sub(r"\. *", "", author_string)
