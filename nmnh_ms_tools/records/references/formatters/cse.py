"""Roughly formats reference string according to CSE guidelines"""
import re

from .core import BaseFormatter




class CSEFormatter(BaseFormatter):


    def __str__(self):
        masks = {
            "article": "{authors}. {year}. {title}. {publication}. {volume}({number}):{pages}. Available from: {url}. doi:{doi}.",
            "book": "{authors}. {year}. {title}. {volume}({number}). {city} ({state}): {publisher} {pages} p.",
            "chapter": "{authors}. {year}. {title}. In: {publication}. {pages}.",
            "mastersthesis": "{authors}. {year}. {title} [thesis]. {publisher}. {pages} p.",
            "phdthesis": "{authors}. {year}. {title} [thesis]. {publisher}. {pages} p.",
        }
        try:
            mask = masks[self.reference.entry_type]
        except KeyError:
            mask = masks["book"]

        ref = self.reference.to_dict()
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

        # Clean up string
        formatted = mask.format(**ref)
        formatted = re.sub(r" +", " ", formatted)
        formatted = re.sub(r"\. +\.", ".", formatted)
        formatted = re.sub(r"(?<=[^\d]) p\.$", ".", formatted)
        formatted = formatted.replace(" Available from: .", "") \
                             .replace(" DOI: .", "") \
                             .replace(": .", ".") \
                             .replace(" :", "") \
                             .replace(" ()", "") \
                             .replace("()", "") \
                             .replace(" .", ".") \
                             .replace(".:", ".") \
                             .lstrip(". ") \
                             .rstrip(":. ") + "."
        formatted = re.sub(r"\.\. ", ". ", formatted)

        return formatted


    def _format_publication(self):
        publication = self.reference.publication
        # Abbreviate journal titles according to the ISO 4 standard
        if self.reference.entry_type == "article":
            return self.iso_4_title(publication).replace("." , "")
        return publication


    def _format_authors(self):
        author_string = self.reference.author_string(
            max_names=10, delim=", ", conj="", mask="{last} {first} {middle}"
        )
        author_string = author_string.replace(". et al", ", et al")
        return re.sub(r"\. *", "", author_string)
