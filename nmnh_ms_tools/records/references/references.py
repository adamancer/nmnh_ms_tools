"""Defines method to parse and work with structured bibliography data"""

import datetime as dt
import html
import logging
import re

import bibtexparser
import pandas as pd
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode
from unidecode import unidecode

from .bibtex import BibTeXMapper
from .formatters import CSEFormatter
from ..core import Record, Records
from ..people import People, Person, combine_authors, parse_names
from ...bots import Bot
from ...utils.standardizers import Standardizer

logger = logging.getLogger(__name__)


ENTITIES = {
    r"$\mathsemicolon$": ";",
    r"$\mathplus$": "+",
    r"{\{AE}}": "Æ",
    r"{\textdegree}": "°",
    r"{\textquotesingle}": "'",
    r"\textemdash": "—",
    r"\textendash": "–",
    r"{\'{a}}": "a",
    r"$\greater$": ">",
    r"$\less$": "<",
    r"$\prime$": "'",
}


class Reference(Record):
    """Defines methods for parsing and manipulating references"""

    bot = Bot()
    _btm = BibTeXMapper()
    terms = [
        "authors",
        "year",
        "title",
        "publication",
        "publication_url",
        "volume",
        "number",
        "pages",
        "publisher",
        "kind",
        "url",
        "doi",
    ]
    std = Standardizer()
    irns = {}

    def __init__(self, data=None, resolve_parsed_doi=True):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.authors = []
        self.kind = ""
        self.number = ""
        self.pages = ""
        self.publication = ""
        self.publication_url = ""
        self.publisher = ""
        self.title = ""
        self.url = ""
        self.volume = ""
        self.year = ""
        self._doi = ""

        # Initialize instance
        super().__init__()
        self.resolve_parsed_doi = resolve_parsed_doi
        self.formatter = CSEFormatter

        # Convert pandas data to dict
        if isinstance(data, pd.Series):
            data = {k: v if not pd.isna(v) else "" for k, v in data.to_dict().items()}

        if data:
            try:
                self.parse(data)
            except Exception as exc:
                raise ValueError(f"Could not parse reference: {data}") from exc

    def __str__(self):
        return self.name

    @property
    def doi(self):
        return self._doi

    @doi.setter
    def doi(self, doi):
        # Split off common DOI prefixes
        if doi:
            doi = doi.split("doi.org/", 1)[-1].split("doi:", 1)[-1].strip()
        # Test if DOI appears to be valid, log a warning if not
        if doi.startswith("10."):
            self._doi = doi
        elif doi:
            logger.warning(f"Invalid doi: {doi}")

    @property
    def name(self):
        return self.citation()

    @property
    def entry_type(self):
        return self._btm.entry_type(self.kind)

    @property
    def booktitle(self):
        return self.publication

    @booktitle.setter
    def booktitle(self, val):
        self.publication = val

    @property
    def journal(self):
        return self.publication

    @journal.setter
    def journal(self, val):
        self.publication = val

    @property
    def series(self):
        return self.publication

    @series.setter
    def series(self, val):
        self.publication = val

    @property
    def issue(self):
        return self.number

    @issue.setter
    def issue(self, val):
        self.number = val

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, val):
        val = html.unescape(re.sub("<.*?>", "", val.rstrip(". ")))
        while val and val == '"' and val[-1] == '"':
            val = val[1:-1].rstrip(". ")
        self._title = val

    def parse(self, data):
        """Parses data from various sources to populate class"""
        self.reset()
        self.verbatim = data
        is_doi_ = is_doi(data)
        parse_doi = self.resolve_parsed_doi and not is_doi_
        if is_doi_:
            self._parse_doi(data)
        elif isinstance(data, str):
            self._parse_string(data)
        elif "BibRecordType" in data:
            self._parse_emu(data)
        elif "ItemID" in data or "PartID" in data:
            self._parse_bhl(data)
            parse_doi = False
        elif "_gddid" in data:
            self._parse_xdd(data)
        elif "provider" in data:
            self._parse_jstor(data)
        elif "item_type_name" in data or "item_type" in data:
            self._parse_sro(data)
        elif "references-count" in data:
            self._parse_crossref(data)
        elif "Title" in data:
            self._parse_google_scholar(data)
        elif "title" in data:
            self._parse_reference(data)
        elif isinstance(data, self.__class__):
            self._parse_reference(self.to_dict(attributes=attributes))
        else:
            raise ValueError("Could not parse {}".format(data))

        # Always use publisher data if possible
        if self.doi and parse_doi:
            doi = self.doi
            self.reset()
            self._parse_doi(doi)

        # Clean up trailing puntuation
        for attr in self.attributes:
            val = getattr(self, attr)
            if isinstance(val, str):
                setattr(self, attr, val.strip(";,. "))

        # Clean up duplicated information
        if self.volume == self.year:
            self.volume = ""

    def same_as(self, other, strict=True):
        """Tests if two references are the same"""

        if self.doi and other.doi:
            return self.doi == other.doi

        try:
            assert isinstance(other, self.__class__)
            # Ensure that certain basic data is present in both records
            assert self.title
            assert self.year
            assert other.title
            assert other.year
        except AssertionError:
            return False

        # Compare titles
        titles = []
        for val in (self.title, other.title):
            val = "".join([w for w in re.split(r"\W+", unidecode(val).casefold())])
            # Catch some common OCR/transcription errors
            for find, repl in {
                "0": "o",
                "1": "l",
                "5": "s",
                "8": "b",
                "9": "g",
            }.items():
                val = val.replace(find, repl)
            titles.append(val)
        similar_title = len(set(titles)) == 1

        same_year = self.year[:4] == other.year[:4]

        same_first_author = None
        if self.authors and other.authors:
            same_first_author = self.authors[0].last == other.authors[0].last

        # Match on title-year if authors on one or both are missing
        if not strict and same_first_author is None:
            return same_year and similar_title

        return same_first_author and same_year and similar_title

    def match_doi(self, threshold=80):
        if self.doi:
            return self.doi
        resp = self.bot.get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": str(self),
                "mailto": "mansura@si.edu",
            },
        )
        items = resp.json()["message"]["items"]
        for item in items:
            if float(item["score"]) > threshold:
                other = self.__class__(item, resolve_parsed_doi=False)
                if self.score_similarity(other) >= 2:
                    break
        else:
            item = items[0]
        if float(item["score"] > threshold):
            return self.__class__(item), item["score"]
        raise ValueError(f"Could not match reference to DOI: {self}")

    def score_similarity(self, other):
        score = {}
        for attr in (
            "title",
            "authors",
            "year",
            "publication",
            "volume",
            "issue",
            "pages",
        ):
            vals = []
            for ref in (self, other):
                val = getattr(ref, attr)
                if isinstance(val, list):
                    val = "|".join([s.last for s in val])
                vals.append("".join(re.split(r"\W+", unidecode(val.casefold()))))
            vals = [s for s in vals if s]
            if len(vals) > 1:
                score[attr] = 1 if len(set(vals)) == 1 else -1

        logging.info(f"Ref 1: {self}")
        logging.info(f"Ref 2: {other}")
        logging.info(f"Score: {sum(score.values())} ({score})")

        return sum(score.values())

    def resolve_doi(self, doi=None):
        """Resolves a DOI

        Args:
            doi (str): a valid DOI corresponding to a publication

        Returns:
            Bibliographic record as a string
        """
        if doi is None:
            doi = self.doi
        if doi:
            headers = {"Accept": "application/json"}
            try:
                verbatim = self.bot.get(std_doi(doi), headers=headers).json()
                parsed = self._parse_crossref(verbatim)
                self.verbatim = verbatim
                return parsed
            except ValueError as exc:
                if "user agent" in str(exc).lower():
                    raise
                logger.warning(f"Could not resolve {doi}: {exc}")

    def author_string(self, max_names=20, delim=", ", conj="&", **kwargs):
        """Converts list of authors objects to a string"""
        return combine_authors(
            self.authors, max_names=max_names, delim=delim, conj=conj, **kwargs
        )

    def citation(self):
        """Writes a citation based on bibliographic data"""
        return str(self.formatter(self))

    def serialize(self):
        """Summarizes record as a string"""
        return "|".join([str(self.authors[0]), self.year, self.title, self.doi])

    def deserialize(self, key):
        """Expands a serialized reference into a full Reference"""
        author, year, title, doi = key.split("|")
        return self.__class__(
            {
                "author": Person(author),
                "year": year,
                "title": title,
                "doi": doi,
            }
        )

    def _to_emu(self):

        try:
            rec_type = self._btm.emu_record_type(self.entry_type)
            source_type = self._btm.emu_source_type(self.entry_type)
            prefix = self._btm.emu_record_type(self.entry_type, True)
            parent = self._btm.emu_source_type(self.entry_type, True)
        except KeyError:
            raise ValueError(
                f"Could not map entry_type {repr(self.entry_type)} to EMu ({repr(self.verbatim)})"
            )

        try:
            key = f"[{rec_type}] {self}"
            irn = self.__class__.irns[key]
            if irn:
                return {"irn": int(irn)}
        except KeyError:
            self.__class__.irns[key] = None

        # Prepare list of authors
        authors = []
        for author in self.authors:
            author = author.to_emu()
            if "irn" not in author:
                # New author names are unlisted to avoid cluttering parties
                author["SecRecordStatus"] = "Unlisted"
            authors.append(author)
        # Populate a bibliography record
        rec = {
            "RefPublicationType": rec_type,
            "RefAuthorsRef_tab": authors,
            "RefAuthorsRole_tab": ["Author" for _ in self.authors],
            "RefTitle": self.title,
            "{}PublicationDates": self.year,
            "RefVolume": self.volume,
            "RefIssue": self.number,
            "RefPages": self.pages,
        }
        if isinstance(self.verbatim, str):
            rec["NotNotes"] = self.verbatim

        if parent and self.publication:
            key = f"[{source_type}] {self.publication}"
            try:
                irn = self.__class__.irns[key]
                if irn:
                    rec["{}ParentRef"] = {"irn": irn}
            except KeyError:
                self.__class__.irns[key] = None
                rec["{}ParentRef"] = {
                    "BibRecordType": source_type,
                    "{}Title".format(parent): self.publication,
                }

        # Adjust fields based on publication type
        if prefix == "Oth":
            del rec["{}PublicationDates"]
            del rec["{}Volume"]
            del rec["{}Issue"]
        elif prefix == "The":
            rec["TheAuthorRef"] = rec["{}AuthorsRef_tab"][0]
            rec["TheThesisType"] = self._btm.emu_thesis_type(self.entry_type)
            rec["ThePublicationDate"] = rec["{}PublicationDate"]
            rec["TheOrganisation"] = {
                "NamPartyType": "Organization",
                "NamOrganisation": self.school,
            }
            del rec["{}AuthorsRef_tab"]
            del rec["{}PublicationDate"]
        # Add GUIDs
        if self.doi:
            rec["AdmGUIDIsPreferred_tab"] = ["Yes"]
            rec["AdmGUIDType_tab"] = ["DOI"]
            rec["AdmGUIDValue_tab"] = [self.doi]
            rec["NotNotes"] = self.resolve_doi()
        # Assign prefix and remove empty keys
        rec = {k.format(prefix): v for k, v in rec.items() if v}
        return rec

    def _to_emu_6(self):
        """Formats record for EMu ebibliography module"""

        try:
            rec_type = self._btm.emu_record_type(self.entry_type)
            source_type = self._btm.emu_source_type(self.entry_type)
            prefix = self._btm.emu_record_type(self.entry_type, True)
            parent = self._btm.emu_source_type(self.entry_type, True)
        except KeyError:
            raise ValueError(
                f"Could not map entry_type {repr(self.entry_type)} to EMu ({repr(self.verbatim)})"
            )

        try:
            key = f"[{rec_type}] {self}"
            irn = self.__class__.irns[key]
            if irn:
                return {"irn": int(irn)}
        except KeyError:
            self.__class__.irns[key] = None

        # Prepare list of authors
        authors = []
        for author in self.authors:
            author = author.to_emu()
            if "irn" not in author:
                # New author names are unlisted to avoid cluttering parties
                author["SecRecordStatus"] = "Unlisted"
            authors.append(author)
        # Populate a bibliography record
        rec = {
            "BibRecordType": rec_type,
            "{}AuthorsRef_tab": authors,
            "{}Role_tab": ["Author" for _ in self.authors],
            "{}Title": self.title,
            "{}PublicationDates": self.year,
            "{}Volume": self.volume,
            "{}Issue": self.number,
            "{}Pages": self.pages,
        }
        if isinstance(self.verbatim, str):
            rec["NotNotes"] = self.verbatim

        if parent and self.publication:
            key = f"[{source_type}] {self.publication}"
            try:
                irn = self.__class__.irns[key]
                if irn:
                    rec["{}ParentRef"] = {"irn": irn}
            except KeyError:
                self.__class__.irns[key] = None
                rec["{}ParentRef"] = {
                    "BibRecordType": source_type,
                    "{}Title".format(parent): self.publication,
                }

        # Adjust fields based on publication type
        if prefix == "Oth":
            del rec["{}PublicationDates"]
            del rec["{}Volume"]
            del rec["{}Issue"]
        elif prefix == "The":
            rec["TheAuthorRef"] = rec["{}AuthorsRef_tab"][0]
            rec["TheThesisType"] = self._btm.emu_thesis_type(self.entry_type)
            rec["ThePublicationDate"] = rec["{}PublicationDate"]
            rec["TheOrganisation"] = {
                "NamPartyType": "Organization",
                "NamOrganisation": self.school,
            }
            del rec["{}AuthorsRef_tab"]
            del rec["{}PublicationDate"]
        # Add GUIDs
        if self.doi:
            rec["AdmGUIDIsPreferred_tab"] = ["Yes"]
            rec["AdmGUIDType_tab"] = ["DOI"]
            rec["AdmGUIDValue_tab"] = [self.doi]
            rec["NotNotes"] = self.resolve_doi()
        # Assign prefix and remove empty keys
        rec = {k.format(prefix): v for k, v in rec.items() if v}
        return rec

    def _parse_bhl(self, rec):
        """Parses a JSON record from BHL"""
        self.kind = rec["Genre"]
        # Map type-specific metadata
        if "PartID" in rec:
            self.url = f'https://biodiversitylibrary.org/part/{rec["PartID"]}'
            self.publication = rec.get("ContainerTitle").rstrip(". ")
        elif "ItemID" in rec:
            self.url = f'https://biodiversitylibrary.org/item/{rec["ItemID"]}'
        else:
            raise ValueError("Invalid BHLType: {}".format(bhl_type))
        # Map common metadata
        self.authors = [Person(a["Name"]) for a in rec.get("Authors", [])]
        self.title = rec.get("Title", "").rstrip(". ")
        self.volume = rec.get("Volume", "")
        self.number = rec.get("Issue", "")
        self.pages = rec.get("PageRange", "").replace("--", "-")
        for key in ("Year", "PublicationDate", "Date"):
            try:
                self.year = self._parse_year(rec[key])
                if self.year:
                    break
            except KeyError:
                pass
        else:
            self.year = "????"
        self.doi = rec.get("Doi", "")
        self.publisher = rec.get("PublisherName", "")
        self.publication_url = self.publication_url.replace("www.", "", 1)

        # Volume sometimes include extra information
        if self.volume and not self.volume.isnumeric() and not self.number:
            without_year = re.sub(r" *\(\d{4}\)$", "", self.volume)
            nums = re.findall(r"[a-z]+\.(\d+)", without_year)
            if 0 < len(nums) <= 3:
                self.volume = nums[0]
                self.number = "-".join(nums[1:])

    def _parse_bibtex(self, text):
        """Parses BibTex record returned by DOI resolver

        Args:
            bib (str): a BibTeX record

        Returns:
            Dict containing reference data
        """
        self.verbatim = text
        for entity, repl in ENTITIES.items():
            text = text.replace(entity, repl)
        parser = BibTexParser()
        parser.customization = convert_to_unicode
        parsed = bibtexparser.loads(text, parser=parser).entries[0]
        # Check for unhandled LaTeX entities
        braces = re.compile(r"\{([A-z_ \-]+|[\u0020-\uD7FF])\}", re.U)
        for key, val in parsed.items():
            val = braces.sub(r"\1", val)
            if "{" in val:
                raise ValueError("Unhandled LaTeX: {}".format(val))
        # Map parsed data to Reference
        self.kind = parsed["ENTRYTYPE"]
        self.authors = parse_names(parsed.get("author", ""))
        try:
            self.title = re.sub(r"\s+", " ", parsed["title"])
        except KeyError:
            logger.warning("No title: {}".format(parsed))
            self.title = "[NO TITLE PROVIDED]"
        try:
            self.year = self._parse_year(parsed["year"])
        except KeyError:
            self.year = "????"
        # Map parent publication
        for key in ("booktitle", "journal", "series"):
            val = parsed.get(key)
            if val:
                self.publication = val
                break
        # Map publisher/school
        self.publisher = parsed.get("publisher", "")
        self.school = parsed.get("school", "")
        # Map volume/issue info
        self.volume = parsed.get("volume", "")
        self.number = parsed.get("number", "")
        self.pages = parsed.get("pages", "").replace("--", "-")
        self.doi = parsed["doi"]
        if self.doi:
            self.url = "https://doi.org/{}".format(self.doi)
        else:
            self.url = parsed["url"]
        self.publisher = parsed["publisher"].rsplit("(", 1)[0].rstrip()

    def _parse_doi(self, doi=None):
        """Retrieves and parses data based on DOI"""
        return self.resolve_doi(doi)

    def parse_emu(self, rec):
        """Parses an EMu ebibliography record"""
        self.kind = rec.get("BibRecordType")
        if not self.kind:
            raise ValueError("BibRecordType required")
        # Give the specific thesis type
        if self.kind == "Thesis":
            entry_type = self._btm.parse_thesis(rec.get("TheThesisType"))
            thesis_type = self._btm.emu_thesis_type(entry_type)
            self.kind = "{} ({})".format(self.kind, thesis_type)
        prefix = self._btm.emu_record_type(self.entry_type, True)
        parent = self._btm.emu_source_type(self.entry_type, True)
        # Get basic metadata
        self.authors = []
        for author in rec.get("RefAuthorsRef_tab", []):
            for key in ["NamFirst", "NamMiddle", "NamLast"]:
                author.setdefault(key, "")
            name = "{NamFirst} {NamMiddle} {NamLast}".format(**author).strip()
            try:
                self.authors.append(Person(name))
            except ValueError as e:
                if name:
                    logger.error(f"Could not parse '{name}'")
        self.title = rec.get("RefTitle")
        # Parse publishing year from publication date
        pub_date = rec.get("{}PublicationDates".format(prefix))
        if not pub_date:
            pub_date = str(rec.get("{}PublicationDate".format(prefix)))
        self.year = self._parse_year(pub_date)
        # Get publication metadata
        try:
            pub = rec.get("RefParentRef.RefTitle".format(prefix, parent))
            # Fall back to summary data if source not found
            if not pub:
                summary = rec.get("{}ParentRef.SummaryData".format(prefix), "")
                pub = summary.split("]", 1)[-1].strip(". ")
            self.publication = pub
            self.volume = rec.get("{}Volume".format(prefix))
            self.number = rec.get("{}Issue".format(prefix))
        except KeyError:
            pass
        # Get pages. Articles in EMu may store pages in either ArtPages or
        # ArtIssuePages, the other publication types have only one field.
        pages = []
        for mask in ("{}Pages", "{}IssuePages"):
            key = mask.format(prefix)
            try:
                pages.append(rec.get(key).replace("--", "-"))
            except (AttributeError, KeyError):
                pass
        pages = list(set([p for p in pages if p]))
        # Keep the range if both a range and a count found
        if len(pages) > 1:
            hyphenated = [p for p in pages if "-" in p]
            if not hyphenated:
                raise ValueError(f"Multiple page counts found: {pages}")
            pages = hyphenated
        self.pages = pages[0] if pages else ""
        # Get the DOI
        try:
            self.doi = rec.grid("AdmGUIDValue_tab").query(
                "AdmGUIDValue_tab", {"AdmGUIDType_tab": "DOI"}
            )[0]
        except IndexError:
            self.doi = None
        if self.doi:
            self.url = "https://doi.org/{}".format(self.doi)

    def _parse_emu_6(self, rec):
        """Parses an EMu ebibliography record"""
        self.kind = rec.get("BibRecordType")
        if not self.kind:
            raise ValueError("BibRecordType required")
        # Give the specific thesis type
        if self.kind == "Thesis":
            entry_type = self._btm.parse_thesis(rec.get("TheThesisType"))
            thesis_type = self._btm.emu_thesis_type(entry_type)
            self.kind = "{} ({})".format(self.kind, thesis_type)
        prefix = self._btm.emu_record_type(self.entry_type, True)
        parent = self._btm.emu_source_type(self.entry_type, True)
        # Get basic metadata
        self.authors = []
        try:
            authors = rec.get("{}AuthorsRef_tab".format(prefix), [])
        except KeyError:
            author = rec.get("{}AuthorsRef".format(prefix))
            if author:
                authors.append(author)
        for author in authors:
            for key in ["NamFirst", "NamMiddle", "NamLast"]:
                author.setdefault(key, "")
            name = "{NamFirst} {NamMiddle} {NamLast}".format(**author).strip()
            try:
                self.authors.append(Person(name))
            except ValueError as e:
                if name:
                    logger.error(f"Could not parse '{name}'")
        self.title = rec.get("{}Title".format(prefix))
        # Parse publishing year from publication date
        pub_date = rec.get("{}PublicationDates".format(prefix))
        if not pub_date:
            pub_date = str(rec.get("{}PublicationDate".format(prefix)))
        self.year = self._parse_year(pub_date)
        # Get publication metadata
        try:
            pub = rec.get("{}ParentRef.{}Title".format(prefix, parent))
            # Fall back to summary data if source not found
            if not pub:
                summary = rec.get("{}ParentRef.SummaryData".format(prefix), "")
                pub = summary.split("]", 1)[-1].strip(". ")
            self.publication = pub
            self.volume = rec.get("{}Volume".format(prefix))
            self.number = rec.get("{}Issue".format(prefix))
        except KeyError:
            pass
        # Get pages. Articles in EMu may store pages in either ArtPages or
        # ArtIssuePages, the other publication types have only one field.
        pages = []
        for mask in ("{}Pages", "{}IssuePages"):
            key = mask.format(prefix)
            try:
                pages.append(rec.get(key).replace("--", "-"))
            except (AttributeError, KeyError):
                pass
        pages = list(set([p for p in pages if p]))
        # Keep the range if both a range and a count found
        if len(pages) > 1:
            hyphenated = [p for p in pages if "-" in p]
            if not hyphenated:
                raise ValueError(f"Multiple page counts found: {pages}")
            pages = hyphenated
        self.pages = pages[0] if pages else ""
        # Get the DOI
        try:
            self.doi = rec.grid("AdmGUIDValue_tab").query(
                "AdmGUIDValue_tab", {"AdmGUIDType_tab": "DOI"}
            )[0]
        except IndexError:
            self.doi = None
        if self.doi:
            self.url = "https://doi.org/{}".format(self.doi)

    def _parse_xdd(self, data):
        """Parses xDD article record"""
        self.kind = data.get("type", "").title()
        src_field = self._btm.source_field(self.kind)
        # Get basic metadata
        self.authors = []
        for name in [a["name"] for a in data.get("author", []) if a["name"]]:
            self.authors.extend(parse_names(name))
        self.title = data["title"]
        self.year = self._parse_year(data.get("year", ""))
        try:
            setattr(self, src_field, data["journal"]["name"]["name"])
        except TypeError:
            setattr(self, src_field, data["journal"])
        self.volume = data.get("volume", "")
        self.number = data.get("number", "")
        self.pages = data.get("pages", "").replace("--", "-")
        # Get unique identifiers
        identifiers = data.get("identifier", [])
        try:
            self.doi = [b["id"] for b in identifiers if b["type"] == "doi"][0]
        except IndexError:
            if data.get("url"):
                self.url = data["url"]
            else:
                self.url = f'https://xdd.org/api/articles?docid={data["_gddid"]}'
        else:
            self.url = "https://doi.org/{}".format(self.doi)
        self.publisher = data.get("publisher", "")

    def _parse_jstor(self, data):
        """Parses JSTOR/Portico/Constellate article record"""
        self.kind = data["docType"]
        # Get item metadata
        self.authors = []
        for name in [a["name"] for a in data.get("creators", []) if a["name"]]:
            self.authors.extend(parse_names(name))
        self.title = data["title"]
        self.year = data["publicationYear"]
        self.publication = data["isPartOf"]
        self.volume = data["volumeNumber"]
        self.number = data["issueNumber"]
        self.pages = "-".join([data["pageStart"], data["pageEnd"]])
        self.publisher = data["publisher"]

        # Get DOI
        self.doi = data["doi"]
        if not self.doi and "doi.org" in data["url"]:
            self.doi = data["url"].split("doi.org/")[-1]
        if self.doi:
            self.url = "https://doi.org/{}".format(self.doi)
        elif data["url"]:
            self.url = data["url"]
        elif data["id"].startswith("ark:"):
            # NOTE: At least some Portico arks don't resolve
            self.url = "https://n2t.net/{}".format(data["id"])

    def _parse_sro(self, rec):
        """Parses JSON record from Smithsonian Research Online"""
        try:
            self.kind = rec["item_type_name"]
        except KeyError:
            self.kind = rec["item_type"]
        self.authors = [
            Person(a["name"]) for a in rec.get("agents", []) if a["role"] == "author"
        ]
        self.title = html.unescape(
            re.sub("<.*?>", "", rec.get("title", "").rstrip(". "))
        )
        self.year = rec.get("year", "")
        for key in ["journal_title", "book_title", "series_title"]:
            self.publication = rec.get(key, "")
            if self.publication:
                break
        self.volume = rec.get("volume", "")
        self.number = rec.get("issue", "")
        self.pages = rec.get("pages", "").replace("--", "-")
        self.doi = rec.get("doi", "")
        self.publisher = rec.get("publisher", "")
        self.publication_url = rec.get("url", "")

    def _parse_string(self, rec):
        """Parses a string contianing a DOI"""
        candidates = re.findall(r"\b10\.[A-Za-z0-9/\.\-]+", rec)
        if len(candidates) == 1:
            return self._parse_doi(candidates[0].rstrip("."))
        raise ValueError(f"Could not extract a DOI for {repr(rec)}")

    def _parse_google_scholar(self, rec):
        """Parses record from Google Scholar"""
        self.kind = "Article"
        self.authors = [Person(a.strip()) for a in rec.get("Authors", "").split(";")]
        self.title = rec.get("Title", "").rstrip(". ")
        self.year = rec.get("Year", "")
        self.publication = rec.get("Publication", "")
        self.volume = rec.get("Volume", "")
        self.number = rec.get("Issue", "")
        self.pages = rec.get("Pages", "").replace("--", "-")
        self.publisher = rec.get("Publisher", "")

    def _parse_crossref(self, rec):
        """Parses JSON record from CrossRef API"""

        def take_first_item(val):
            return val[0] if isinstance(val, list) else val

        self.kind = rec["type"]
        self.authors = []
        for author in rec.get("author", []):
            try:
                author = author["name"]
            except KeyError:
                try:
                    author = f"{author['family']}, {author.get('given', '')}".rstrip(
                        ", "
                    )
                except KeyError:
                    # Empty author slot
                    pass
            self.authors.append(Person(author))
        self.title = take_first_item(rec.get("title", ""))
        self.year = rec.get("published", {}).get("date-parts", [[""]])[0][0]
        self.publication = take_first_item(rec.get("container-title", ""))
        self.volume = rec.get("volume", "")
        # HACK: USGS places series info in alternative-id
        if not self.volume and rec["prefix"] == "10.3133":
            self.volume = take_first_item(rec.get("alternative-id", ""))
        self.issue = rec.get("issue", "")
        self.pages = rec.get("page", "")
        self.doi = rec.get("DOI", "")
        self.publisher = rec.get("publisher", "")
        self.publication_url = (
            rec.get("'resource", {}).get("primary", {}).get("url", "")
        )

    def _parse_reference(self, data):
        """Parses a pre-formatted reference"""
        for attr, val in data.items():
            if attr == "authors":
                val = parse_names(val)
            setattr(self, attr, val)

    def _parse_ris(self, text):
        """Parses RIS record"""
        raise NotImplementedError

    def _parse_year(self, val):
        """Parses year from value"""
        if not val:
            return ""
        if isinstance(val, dt.date):
            return str(val.year)
        try:
            return re.search(r"\d{4}( *-+ *\d{4})?", val).group()
        except AttributeError:
            return ""


class References(Records):
    item_class = Reference


class Citation(Record):
    terms = [
        "text",
        "reference",
        "matches",
    ]

    def __init__(self, text, reference, matches=None):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))

        # Initialize instance
        super().__init__((text, reference, matches))

        self.emu_note_mask = "This citation mentions the following specimens:\n{}"

    def __str__(self):
        text = self.text.strip('"')
        return f'"{text}" ({str(self.reference)})'

    def parse(self, data):
        text, reference, matches = data

        if not isinstance(text, (list, tuple)):
            text = text.split("|")
        self.text = "\n".join(['"...{}..."'.format(s.strip('". ')) for s in text])

        self.reference = reference
        self.matches = matches if matches is not None else []

    def same_as(self, other, strict=True):
        if not isinstance(other, self.__class__):
            return False
        return self.text == other.text and self.reference == other.reference

    def _to_emu(self):
        def zfill(match):
            return match.group().zfill(16)

        # Inherit authors from reference
        kwargs = {"SecRecordStatus": "Unlisted"}
        authors = [a.to_emu(**kwargs) for a in self.reference.authors]

        self.matches.sort(key=lambda v: re.sub(r"\d+", zfill, v))

        return {
            "BibRecordType": "Citation",
            "CitCitingText": self.text,
            "CitAuthorsRef_tab": authors,
            "CitRole_tab": ["Author" for _ in self.reference.authors],
            "CitParentRef": self.reference.to_emu(),
            "NotNotes": self.emu_note_mask.format("\n".join(self.matches)),
        }


class Citations(Records):
    item_class = Citation


def get_author_and_year(ref):
    """Extracts the first author and year from a reference"""
    if isinstance(ref, Reference):
        return (ref.authors[0], ref.year)
    try:
        authors, year, _ = [
            s.strip(". ") for s in re.split(r"\b(\d{4}[a-zA-Z]?)\b", ref, 1)
        ]
        # Strip dates from end of author string
        pattern = (
            r"\b(\d{,2} )?(Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sep|Oct|Nov|Dec) *$"
        )
        authors = re.sub(pattern, "", authors).strip()
        if authors:
            return (People(authors)[0], year)
    except:
        raise
    raise ValueError(f"Could not extract author/year from {ref}")


def std_doi(val, as_url=True):
    """Formats a DOI as a URL or string"""
    if not isinstance(val, str):
        raise TypeError(f"DOI must be a string: {repr(val)}")
    if not "10." in val:
        raise ValueError(f"Value does not appear to be a DOI: {val}")
    val = "10." + val.split("10.", 1)[1]
    return f"https://doi.org/{val}" if as_url else val


def is_doi(val):
    """Tests if a value appears to be a DOI"""
    if not isinstance(val, str):
        return False
    return std_doi(val, as_url=False).startswith("10.")
