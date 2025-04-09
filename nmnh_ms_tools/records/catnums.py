"""Defines tools to parse and display NMNH catalog numbers"""

import logging
import re
from collections import namedtuple

from xmu import EMuRecord

from .core import Record
from ..tools.specimen_numbers.parsers import Parser
from ..tools.specimen_numbers.specnum import SpecNum
from ..utils import del_immutable, mutable, set_immutable


logger = logging.getLogger(__name__)

PARSER = Parser(clean=True, require_code=False, parse_order=["spec_num"])
MULTIPARSER = Parser(clean=True, require_code=False)
ANTARCTIC_PREFIXES = [
    "ALH",
    "AMU",
    "BEC",
    "BOW",
    "BTN",
    "BUC",
    "CMS",
    "CRA",
    "CRE",
    "DAV",
    "DEV",
    "DNG",
    "DEW",
    "DOM",
    "DRP",
    "EET",
    "FIN",
    "GDR",
    "GEO",
    "GRA",
    "GRO",
    "HOW",
    "ILD",
    "KLE",
    "LAP",
    "LAR",
    "LEW",
    "LON",
    "MAC",
    "MBR",
    "MCY",
    "MET",
    "MIL",
    "ODE",
    "NOD",
    "OTT",
    "PAT",
    "PCA",
    "PGP",
    "PRA",
    "PRE",
    "QUE",
    "RBT",
    "RKP",
    "SAN",
    "SCO",
    "STE",
    "SZA",
    "TEN",
    "TIL",
    "TYR",
    "WIS",
    "WSG",
]


FakeSpecNum = namedtuple("FakeSpecNum", ["code", "prefix", "number", "suffix", "delim"])


class CatNum(Record):
    """Defines methods for parsing and manipulating NMNH catalog numbers

    Attributes
    ----------
    coll_id : str
        the three-letter abbreviation for the collecting unit

    Properties
    ----------
    code : str
        a code for the collecting organization, e.g., USNM or NMNH
    prefix : str
        an alpha prefix prepended to the catalog number
    number : int
        the numeric part of the catalog number
    suffix : str
        an alphanumeric suffix appended to the main catalog number following a delimiter
    delim : str
        the delimiter used before the suffix
    """

    # Normal class attributes
    terms = ["coll_id"]

    def __init__(self, data, parser=None):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ["code", "prefix", "number", "suffix", "delim"]
        # Explicitly define defaults for all reported attributes
        self.coll_id = ""
        # Define other attributes
        self._spec_num = FakeSpecNum("", "", "", "", "")
        self.parser = parser if parser is not None else PARSER

        super().__init__(data)

    def __getattr__(self, attr):
        if attr != "_spec_num":
            try:
                return getattr(self._spec_num, attr)
            except AttributeError:
                pass
        raise AttributeError(
            f"{repr(self.__class__.__name__)} object has no attribute {repr(attr)}"
        )

    def __setattr__(self, attr, val):
        set_immutable(self, attr, val)

    def __delattr__(self, attr):
        del_immutable(self, attr)

    @property
    def code(self):
        return self._spec_num.code

    @property
    def prefix(self):
        return self._spec_num.prefix

    @property
    def number(self):
        return self._spec_num.number

    @property
    def suffix(self):
        return self._spec_num.suffix

    @property
    def delim(self):
        return self._spec_num.delim

    @property
    def parent(self):
        return self.__class__(self._spec_num.parent).modcopy(coll_id=self.coll_id)

    def __str__(self):
        if self.is_antarctic():
            space = " " if len(self.prefix) == 3 else ""
            return f"{self.prefix}{space}{self.number},{self.suffix}".rstrip(",")
        else:
            val = f"{self.code} {self.prefix}{self.number}{self.delim}{self.suffix} ({self.coll_id})"
            return val.replace(" ()", "").strip(f" {self.delim}")

    def __eq__(self, other):
        try:
            return self._spec_num == other._spec_num and self.coll_id == other.coll_id
        except AttributeError:
            return False

    def __add__(self, val):
        if self.suffix:
            raise ValueError("Addition not supported if suffix present")
        return self.__class__(self._spec_num + val).modcopy(coll_id=self.coll_id)

    def __sub__(self, val):
        if self.suffix:
            raise ValueError("Subtraction not supported if suffix present")
        return self.__class__(self._spec_num - val).modcopy(coll_id=self.coll_id)

    def copy(self):
        """Creates a copy of the instance

        Returns
        -------
        CatNum
            a copy of the current instance
        """
        return self.__class__(self._spec_num.copy())

    def modcopy(self, **kwargs):
        """Creates a copy of the instance modifed with the values in kwargs

        Arguments
        ---------
        kwargs :
            key-value pair where each key is an attribute to modify

        Returns
        -------
        CatNum
            CatNum modifed by the data in kwargs
        """
        coll_id = kwargs.pop("coll_id", None)
        copy_ = self.__class__(self._spec_num.modcopy(**kwargs))
        if coll_id:
            with mutable(copy_):
                copy_.coll_id = coll_id
        return copy_

    def parse(self, data):
        """Parses data passed to the class when it is created

        Arguments
        ---------
        data : str | dict | SpecNum
            a string, EMu record, or SpecNum that can be parsed by the class

        Returns
        -------
        None
        """
        if isinstance(data, SpecNum):
            spec_num = data
        elif isinstance(data, str):
            spec_num = self.parser.parse_spec_num(data)
        elif isinstance(data, dict) and set(data) & {"CatNumber", "MetMeteoriteName"}:
            spec_num = self._parse_emu(data)

        with mutable(spec_num):
            # Check for collection ID in trailing parenthetical
            pattern = r"\(([A-Z]{3}(?::[A-Z]{3})?)\)$"
            match = re.search(pattern, spec_num.suffix)
            if not match and isinstance(data, str):
                match = re.search(pattern, data)
            if match:
                self.coll_id = match.group(1)
                spec_num.suffix = re.sub(pattern, "", spec_num.suffix).strip()

        self._spec_num = spec_num

    def to_emu(self):
        """Converts the catalog number to an EMu XML record

        Returns
        -------
        EMuRecord
            the catalog number formatted for EMu
        """
        rec = {
            "CatMuseumAcronym": self.code,
            "CatPrefix": self.prefix,
            "CatNumber": self.number,
            "CatSuffix": self.suffix,
        }
        if self.coll_id:
            try:
                main, taxon = self.coll_id.split(":")
            except ValueError:
                main = self.coll_id
            else:
                taxon = {"CPX": "Clinopyroxene", "OPX": "Orthopyroxene"}[taxon]
                rec["IdeTaxonRef_tab"] = [{"ClaScientificName": taxon}]
            finally:
                rec.update(
                    {
                        "GEM": {"CatDivision": "Mineralogy", "CatCatalog": "Gems"},
                        "MET": {"CatDivision": "Meteorites"},
                        "MIN": {"CatDivision": "Mineralogy", "CatCatalog": "Minerals"},
                        "PET": {"CatDivision": "Petrology & Volcanology"},
                        "REF": {
                            "CatDivision": "Petrology & Volcanology",
                            "CatCollectionName_tab": ["Reference Standards Collection"],
                        },
                        "SMS": {
                            "CatDivision": "Petrology & Volcanology",
                            "CatCollectionName_tab": [
                                "Smithsonian Microbeam Standards"
                            ],
                        },
                    }[main]
                )
        return EMuRecord(rec, module="ecatalogue")

    def reset(self) -> None:
        """Placeholder function required by parent class

        Originally intended to reset all attributes to default values.
        """
        return

    def as_separate_numbers(self, **kwargs) -> list["CatNum"]:
        """Returns the catalog number and suffix as separate catalog numbers

        Parameters
        ----------
        kwargs :
            keyword arguments to pass to
            `nmnh_ms_tools.tools.specimen_numbers.SpecNum.as_separate_numbers()`

        Returns
        -------
        list[CatNum]
            list of catalog numbers
        """
        return [
            self.__class__(s).modcopy(coll_id=self.coll_id)
            for s in self._spec_num.as_separate_numbers(**kwargs)
        ]

    def as_range(self, **kwargs) -> list["CatNum"]:
        """Returns catalog numbers with the suffix interpreted as a range

        Parameters
        ----------
        kwargs :
            keyword arguments to pass to
            `nmnh_ms_tools.tools.specimen_numbers.SpecNum.as_range()`

        Returns
        -------
        list[CatNum]
            list of catalog numbers
        """
        return [
            self.__class__(s).modcopy(coll_id=self.coll_id)
            for s in self._spec_num.as_range(**kwargs)
        ]

    def is_antarctic(self) -> bool:
        """Tests if instance appears to be a NASA meteorite number

        Returns
        -------
        bool
            True if string is consistent with NASA meteorite number format
        """
        return is_antarctic(f"{self.prefix}{self.number}")

    def _parse_emu(self, data):
        """Parses a catalog number from an EMu record"""
        metname = data.get("MetMeteoriteName", "")
        if is_antarctic(metname):
            self.parse(metname.replace(",", "-"))
            with mutable(self._spec_num):
                self._spec_num.delim = ","
            return self._spec_num
        code = data.get("CatMuseumAcronym", "")
        prefix = data.get("CatPrefix", "")
        number = data.get("CatNumber", "")
        suffix = data.get("CatSuffix", "")
        spec_num = SpecNum(
            code=code, kind="", prefix=prefix, number=number, suffix=suffix
        )
        # Get catalog
        self.coll_id = self._set_coll_id(data)
        return spec_num

    def _set_coll_id(self, rec: dict = None) -> str:
        """Determines the collection identifier based on the EMu record

        Collection identifiers are based on detailed specimen info, including
        collection names and primary classifications. They are primarily used
        to distinguish samples in the Petrology Reference Standards collection
        when sharing data based on the full catalog record.

        Parameters
        ----------
        rec : dict
            an EMu record containing a catalog number and related metadata

        Returns
        -------
        str
            the abbreviation for the department, division, catalog, or collection
        """
        name = "Smithsonian Microbeam"
        if any((c for c in rec.get("CatCollectionName_tab", []) if c.startswith(name))):
            return "SMS"

        # Petrology has an unfortunate habit of assigning children the same
        # catalog number as their parents. This shows up especially in the
        # Reference Standards Collection, where you additionally run into
        # multiple children with the same catalog number (for example, the
        # OPX and CPX fractions from a sample may be assigned the same
        # number). These need to be sorted out manually.
        name = "Reference Standards"
        if any((c for c in rec.get("CatCollectionName_tab", []) if c.startswith(name))):
            ambiguous = {
                "116610-5",
                "116610-15",
                "116610-16",
                "116610-18",
                "116610-21",
                "117213-5",
            }
            catnum = f"{rec.get("CatPrefix", "")}{rec.get("CatNumber", "")}-{rec.get("CatSuffix", "")}"
            if catnum in ambiguous:
                try:
                    primary = rec["IdeTaxonRef_tab"][0]["ClaScientificName"]
                except (IndexError, KeyError):
                    raise ValueError(f"Could not map {catnum} (taxon not provided)")
                else:
                    if primary == "Clinopyroxene":
                        return "REF:CPX"
                    if primary == "Orthopyroxene":
                        return "REF:OPX"
                raise ValueError(f"Could not map {catnum} (primary={repr(primary)})")
            return "REF"

        coll = rec.get("CatDivision")
        if coll == "Mineralogy":
            coll = rec.get("CatCatalog", coll)
        if coll:
            return coll[:3].upper()

    def _sortable(self):
        """Returns a sortable version of the catalog number"""
        vals = []
        for attr in ("code", "coll_id", "prefix", "number", "suffix"):
            vals.append(str(getattr(self, attr)).zfill(16))
        return "-".join(vals)


def parse_catnums(val: str, parser: Parser = MULTIPARSER) -> list[CatNum]:
    """Parses catalog numbers from a string

    Parameters
    ----------
    val : str
        text containing one or more catalog numbers
    parser: nmnh_ms_tools.tools.specimen_numbers.Parser
        a specimen number parser

    Returns
    -------
    list[CatNum]
        list of parsed catalog numbers
    """
    catnums = []
    for vals in parser.extract(val).values():
        catnums.extend([CatNum(c) for c in vals])
    return catnums


def parse_catnum(
    val: str, parser: Parser = PARSER, force_hyphen: bool = True
) -> CatNum:
    """Parses a single catalog number from a string

    Parameters
    ----------
    val : str
        a single catalog number as text
    parser: nmnh_ms_tools.tools.specimen_numbers.Parser
        a specimen number parser
    force_hyphen : bool
        whether to standardize the delimiter between the number and suffix to a hyphen
        before parsing. This allows the parser to handle well-formed catalog numbers
        that otherwise would be interpreted as two separate numbers.

    Returns
    -------
    CatNum
        the parsed catalog number
    """
    if force_hyphen and isinstance(val, str):
        val = re.sub(r"(?<=\d)([,/ ]+)(?=[A-Za-z0-9]+$)", "-", val)
    try:
        return CatNum(val, parser=parser)
    except ValueError:
        if is_antarctic(val):
            return CatNum(val.replace(",", "-"), parser=parser).modcopy(delim=",")
        raise


def is_antarctic(val: str | dict) -> bool:
    """Tests if value appears to be a NASA meteorite number

    Arguments
    ---------
    val : str | dict
        a catalog number or an EMu record containing MetMeteoriteName

    Returns
    -------
    bool
        True if string is consistent with NASA meteorite number format
    """
    if isinstance(val, dict):
        try:
            val = val["MetMeteoriteName"]
        except KeyError:
            return False
    return bool(
        re.match(r"(" + "|".join(ANTARCTIC_PREFIXES) + r")[A ]?\d{5,6}(?=[^\d]|$)", val)
    )
