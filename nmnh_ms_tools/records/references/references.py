"""Defines class and functions to work with structured bibliography data"""

import logging
import re
from datetime import datetime

from xmu import EMuDate, EMuRecord

from .formatters import CSEFormatter
from ...bots import Bot
from .. import Person, Record, parse_names
from ...utils import LazyAttr

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
    """Class for working with structured bibliography data based on BibTex"""

    # Deferred class attributes are defined at the end of the file
    bot = None
    entry_types = None
    terms = None

    # Normal class attributes
    terms = [
        "entry_type",
        "title",
        "booktitle",
        "journal",
        "series",
        "author",
        "editor",
        "volume",
        "number",
        "chapter",
        "edition",
        "pages",
        "publisher",
        "school",
        "organization",
        "doi",
        "isbn",
        "issn",
        "url",
        "address",
        "note",
        "type",
    ]
    entry_types = {
        "article",
        "book",
        "incollection",
        "inproceedings",
        "mastersthesis",
        "misc",
        "phdthesis",
        "techreport",
    }
    src_to_bib = {
        "book series": "book",
        "chapter": "incollection",
        "manuscript": "unpublished",
        "other": "article",
        "thesis": "mastersthesis",
        "thesis (masters)": "mastersthesis",
        "thesis (phd)": "phdthesis",
        # BHL genres
        "journal": "book",
        "monograph/item": "book",
        "monographic component part": "incollection",
        "serial": "book",
        "serial component part": "article",
        # xDD genres
        "fulltext": "book",
        # Unknown source #1
        "book chapter": "incollection",
        "book review": "article",
        "dataset": "article",
        "journal article": "article",
        "magazine article": "article",
        # Unknown source #2
        "book-chapter": "incollection",
        "component": "incollection",
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
        # RIS
        "chap": "incollection",
        "doctoral thesis": "phdthesis",
        "thesis / dissertation": "phdthesis",
    }
    bib_to_emu = {
        "incollection": "Chapter",
        "phdthesis": "Thesis",
    }
    formatter = CSEFormatter
    irns = {}

    def __init__(self, data):
        self._class_attrs = set(dir(self))
        self._properties = ["month", "year"]
        # Explicitly define defaults for all reported attributes
        self.entry_type = ""
        self.title = ""
        self.booktitle = ""
        self.journal = ""
        self.series = ""
        self.author = []
        self.editor = []
        self.volume = ""
        self.number = ""
        self.chapter = ""
        self.edition = ""
        self.pages = ""
        self.publisher = ""
        self.school = ""
        self.organization = ""
        self.doi = ""
        self.isbn = ""
        self.issn = ""
        self.url = ""
        self.address = ""
        self.note = ""
        self.type = ""
        self._date = None
        self._verbatim_date = None
        super().__init__(data)

    def __str__(self):
        vals = ["@" + self.entry_type + "{" + self.citekey + ","]
        for attr in self.attributes:
            if attr != "entry_type":
                val = getattr(self, attr)
                if val:
                    if isinstance(val, list):
                        val = " & ".join([str(s) for s in val])
                    vals.append(f"    {attr}=" + "{" + str(val) + "}")
        vals.append("}")
        return "\n".join(vals)

    def __bool__(self):
        return bool(self.title or self.year != "????" or self.doi)

    @property
    def citekey(self):
        try:
            return f"{self.author[0].last}_{self.year}"
        except (AttributeError, IndexError):
            return f"Unknown_{self.year}"

    @property
    def date(self):
        return self._date

    @date.setter
    def date(self, val):
        self._date = EMuDate(val)
        self._verbatim_date = val

    @property
    def month(self):
        try:
            return self.date.strftime("%b")
        except (AttributeError, ValueError):
            return ""

    @property
    def year(self):
        try:
            return str(self.date.year)
        except AttributeError:
            return "????"

    def citation(self):
        """Writes a citation based on bibliographic data"""
        return str(self.formatter(self))

    def get_entry_type(self, val: str) -> str:
        """Gets the entry type for the current record

        Parameters
        ----------
        val : str
            entry type

        Returns
        -------
        str
            BibTex entry type corresponding to given value
        """
        val = val.lower()
        return val if val in self.entry_types else self.src_to_bib[val.lower()]

    def parse(self, data: dict | str) -> dict:
        """Parses bibliography data

        Parameters
        ----------
        data : str or dict
            bibliography data (from EMu or bibtex) or a DOI

        Returns
        -------
        dict
            Parsed data either in an intermediary format or as BibTex (for BibTex
            source data only)
        """
        self.verbatim = data
        is_bibtex = False
        if isinstance(data, dict) and "RefTitle" in data:
            parsed = self._parse_emu(data)
        elif isinstance(data, dict) and "entry_type" in data:
            parsed = self._parse_bibtex(data)
            is_bibtex = True
        elif isinstance(data, str):
            if data.startswith("10.") or re.search(r"\bdoi\b", data, flags=re.I):
                parsed = self.resolve_doi(data)
                is_bibtex = True
            elif data.startswith("@"):
                parsed = self._parse_bibtex(data)
                is_bibtex = True
            elif "TI  - " in data or "T1  - ":
                parsed = self._parse_ris(data)
                is_bibtex = True
            else:
                raise ValueError(f"Could not parse {repr(data)}")
        else:
            raise ValueError(f"Could not parse {repr(data)}")

        # Bibtex records can be assigned directlty to attributes. Other records
        # need to be mapped from the intermediate format based on entry type.
        if not is_bibtex:
            if parsed["entry_type"] == "article":
                self.journal = parsed.pop("source")
            elif parsed["entry_type"] == "incollection":
                self.booktitle = parsed.pop("source")

        # Split contriubutor strings into Person objects
        for key in ("author", "editor"):
            try:
                setattr(self, key, parse_names(parsed.pop(key)))
            except KeyError:
                pass

        # The remaining attributes can be mapped directly
        for key, val in parsed.items():
            setattr(self, key, val)

        # Populate other valid fields
        for term in self.terms:
            if not getattr(self, term):
                setattr(self, term, "")

        # Check for custom fields
        custom = set(parsed) == set(self.terms)
        if custom:
            print(custom)

    def resolve_doi(self, doi: str = None) -> dict:
        """Resolves a DOI

        Parameters
        ----------
        doi : str
            the DOI to resolve. If not given, defaults to doi attribute.

        Returns
        -------
        dict
            publication metadata as BibTex

        """
        if doi is None:
            doi = self.doi
        if doi:
            headers = {"Accept": "application/x-bibtex"}
            try:
                verbatim = self.bot.get(
                    format_doi(doi), headers=headers
                ).content.decode("utf-8")
                parsed = self._parse_bibtex(verbatim)
                return parsed
            except ValueError as exc:
                if "user agent" in str(exc).lower():
                    raise
                logger.warning(f"Could not resolve {doi}: {exc}")

    def to_emu(self) -> EMuRecord:
        """Formats the reference for the EMu Bibliography module

        Returns
        -------
        EMuRecord
            publication metadata mapped to EMu 9 format
        """
        rec = {}

        rec["BibRecordType"] = self.bib_to_emu.get(
            self.entry_type, self.entry_type.title()
        )

        if self.entry_type == "article":
            rec["RefJournalBookTitle"] = self.journal
        elif self.entry_type == "book":
            rec["RefJournalBookTitle"] = self.title
        elif self.entry_type == "incollection":
            rec["RefJournalBookTitle"] = self.booktitle

        rec["RefTitle"] = self.title
        rec["RefSeries"] = self.series
        rec["RefDate"] = self.date
        rec["RefDateRange"] = self._verbatim_date
        rec["RefVolume"] = self.volume
        rec["RefIssue"] = self.number
        rec["RefPage"] = self.pages
        if self.url:
            rec["RefWebSiteIdentifier"] = self.url.replace("dx.doi", "doi")

        for person in self.author:
            person = person.to_emu()
            if "irn" not in person:
                person["SecRecordStatus"] = "Unlisted"
            rec.setdefault("RefContributorsRef_tab", []).append(person)
            rec.setdefault("RefContributorsRole_tab", []).append("Author")

        for person in self.editor:
            person = person.to_emu()
            if "irn" not in person:
                person["SecRecordStatus"] = "Unlisted"
            rec.setdefault("RefContributorsRef_tab", []).append(person)
            rec.setdefault("RefContributorsRole_tab", []).append("Editor")

        if self.publisher:
            org = Person(organization=self.publisher).to_emu()
            if "irn" not in org:
                org["SecRecordStatus"] = "Unlisted"
            rec["RefPublisherRef"] = org

        for kind in ("ISBN", "ISSN"):
            val = getattr(self, kind.lower())
            if val:
                rec.setdefault("RefOtherIdentifierSource_tab", []).append(kind)
                rec.setdefault("RefOtherIdentifier_tab", []).append(val)

        if not self.doi and self.url and "doi.org" in self.url:
            self.doi = self.url

        if self.doi:
            rec["AdmGUIDType_tab"] = ["DOI"]
            rec["AdmGUIDValue_tab"] = [format_doi(self.doi)]
            rec["AdmGUIDIsPreferred_tab"] = ["Yes"]

        rec["NteText0"] = [self.verbatim]
        rec["NteDate0"] = [datetime.now()]
        # rec["NteType_tab"] = ["Verbatim Data"]
        rec["NteAttributedToRef_nesttab"] = [[1006206]]

        return EMuRecord(rec, module="ebibliography")

    def _parse_bibtex(self, data: str) -> dict:
        """Parses a BibTex string"""
        # Use BibTex data for verbatim if parsing a DOI
        try:
            self.verbatim = data.strip()
            parsed = parse_bibtex(data)
        except AttributeError:
            self.verbatim = data
            parsed = data.copy()
        # Combine month and year as date
        month = parsed.pop("month", "")
        year = parsed.pop("year", "")
        parsed["date"] = (
            f"{month} {year}" if month.isalpha() else f"{year}-{month}-"
        ).strip()
        # Map less common bibtex fields
        if parsed.get("eprint") and not parsed.get("url"):
            parsed["url"] = parsed.pop("eprint")
        return parsed

    def _parse_ris(self, data: str) -> dict:
        """Parses a RIS string"""
        orig = data

        # Convert str to dict
        data = {}
        for line in orig.strip().splitlines():
            key, val = re.split(" *- *", line, 1)
            if val:
                data.setdefault(key, []).append(val)
        data = {k: v[0] if len(v) == 1 else v for k, v in data.items()}

        mapped = {}
        mapped["entry_type"] = self.src_to_bib[data.pop("TY").lower()]
        mapped["author"] = data.pop("AU", None)
        mapped["url"] = data.pop("UR", None)
        mapped["booktitle"] = data.pop("BT", None)

        pages = {p: None for p in [data.pop("SP", None), data.pop("EP", None)] if p}
        mapped["pages"] = "-".join(pages)

        # Check multikey fields
        titles = _ordered_pop(data, ["TI", "T1"])
        if titles:
            mapped["title"] = titles[0]

        dates = _ordered_pop(data, ["DA", "PY", "Y1"])
        if dates:
            mapped["date"] = dates[0]

        pubs = _ordered_pop(data, ["PB", "DP"])
        if pubs:
            mapped["publisher"] = pubs[0]

        data = {k: v for k, v in data.items() if k not in ["AB"]}
        if data:
            print("Not parsed:", data)

        return mapped


def format_doi(doi: str, url: bool = True) -> str:
    """Formats a DOI

    Intended for either DOIs or doi.org URLs, but will work on any string that
    ends with a DOI.

    Parameters
    ----------
    doi : str
        the DOI string to format
    url : bool
        whether to return the DOI as a full URL

    Returns
    -------
    str
        DOI formatted as specified
    """
    if "10." in doi:
        doi = "10." + doi.split("10.", 1)[1]
        return f"https://doi.org/{doi}" if url else doi
    raise ValueError(f"Invalid DOI: {doi}")


def parse_bibtex(bibtex: str) -> dict:
    """Parses a bibtex record

    Parameters
    ----------
    bibtex : str
        BibTex data

    Returns
    -------
    dict
        the parsed BibTex record
    """
    # Clean up entities
    for key, val in ENTITIES.items():
        bibtex = bibtex.replace(key, val)
    metadata = {"entry_type": bibtex.split("{", 1)[0].lstrip(" @").lower()}
    pat = r"\b([a-z]+ *= *(?:\"\"|[a-z]+|\{.*?\}))(?=,| })"
    for item in re.findall(pat, bibtex, flags=re.I):
        item = re.sub('"",$', "", item)
        key, val = [s.strip() for s in item.split("=")]
        if val:
            if re.match(r"^\{.*?\}$", val):
                val = val[1:-1]
        metadata[key.strip().lower()] = val.strip()
    return metadata


def _ordered_pop(dct: dict, keys: list[str]) -> list:
    """Gets the unique values for a series of keys in a dict"""
    ordered = {dct.pop(k, None): k for k in keys}
    return [s for s in ordered if s]


# Define deferred class attributes
LazyAttr(Reference, "bot", Bot)
