"""Defines class and methods to parse and manipulate specimen data"""

import re

from .core import Record, read_dwc_terms
from .catnums import CatNum, parse_catnum, parse_catnums, is_antarctic
from .references import Reference
from .sites import Site
from .stratigraphy import LithoStrat
from ..tools.geographic_names.parsers.helpers import parse_localities
from ..tools.specimen_numbers_old.link import (
    MatchMaker,
    MatchObject,
    validate_dept,
    ENDINGS,
    STOPWORDS,
    REPLACEMENTS,
)
from ..tools.specimen_numbers_old.parser import Parser
from ..utils import as_list, dedupe, to_attribute, to_camel, to_pattern
from ..utils.standardizers import Standardizer


class Specimen(Record):
    """Defines methods for parsing and manipulating specimen data"""

    parser = Parser()
    _site_attrs = Site({}).attributes
    _strat_attrs = LithoStrat({}).attributes
    _to_attr = {}
    terms = read_dwc_terms()

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.institution_code = ""
        self.collection_code = ""
        self.basis_of_record = ""
        self.occurrence_id = ""
        self.catalog_number = CatNum("")
        self.field_number = []
        self.record_number = []
        self.lab_number = []  # custom
        self.meteorite_name = ""  # custom
        self.meteorite_number = ""  # custom
        self.associated_references = []

        self.taxon_id = []
        self.higher_classification = []
        self.kingdom = ""
        self.phylum = ""
        self.class_ = ""
        self.order = ""
        self.family = ""
        self.genus = ""
        self.subgenus = ""
        self.scientific_name = []
        self.vernacular_name = ""

        self.location_id = ""
        self.higher_geography = []
        self.continent = ""
        self.country = ""
        self.state_province = []
        self.county = []
        self.municipality = ""
        self.island = ""
        self.island_group = ""
        self.water_body = []
        self.mining_district = ""  # custom
        self.mine = ""  # custom
        self.volcano = ""  # custom
        self.maps = []  # custom
        self.features = []  # custom
        self.locality = ""
        self.verbatim_locality = ""
        self.verbatim_latitude = ""
        self.verbatim_longitude = ""
        self.georeference_sources = ""
        self.georeference_remarks = ""

        self.geological_context_id = ""
        self.group = ""
        self.formation = ""
        self.member = ""
        self.earliest_era_or_lowest_erathem = ""
        self.earliest_period_or_lowest_system = ""
        self.earliest_epoch_or_lowest_series = ""
        self.earliest_age_or_lowest_stage = ""
        self.latest_era_or_highest_erathem = ""
        self.latest_period_or_highest_system = ""
        self.latest_epoch_or_highest_series = ""
        self.latest_age_or_highest_stage = ""

        self.type_status = ""

        self._site = None
        self._strat = None
        self._references = None

        # Initialize instance
        super().__init__(*args, **kwargs)

    # def __str__(self):
    #    return self.name

    @property
    def name(self):
        return str(self.catalog_number)

    def parse(self, data):
        """Parses data from various sources to populate class"""
        self.reset()
        if "basisOfRecord" in data:
            self._parse_dwc(data)
        elif "CatNumber" in data:
            self._parse_emu(data)
        else:
            raise ValueError("Could not parse {}".format(data))

        # FIXME: Standardize department names more generally
        self.collection_code = self.collection_code.replace(
            "Herpetology", "Amphibians & Reptiles"
        )

        # Remove department prefixes (e.g., PAL for Paleobiology specimens)
        if self.catalog_number.prefix[:3].upper() == self.collection_code[:3].upper():
            self.catalog_number.prefix = ""

        # Construct or integrate site info
        attrs = [a for a in self.attributes if a in self._site_attrs]
        if not self._site:
            self._site = Site({a: getattr(self, a) for a in attrs})
        else:
            for attr in attrs:
                setattr(self, attr, getattr(self._site, attr))

        # Construct or integrate strat info
        attrs = [a for a in self.attributes if a in self._strat_attrs]
        if not self._strat:
            strat = {a: getattr(self, a) for a in attrs}
            if any(strat.values()):
                self._strat = LithoStrat(strat)
        else:
            for attr in attrs:
                setattr(self, attr, getattr(self._strat, attr))

    def match_text(
        self,
        text,
        dept=None,
        spec_nums=None,
        spec_num_only=False,
        context_only=False,
        **kwargs,
    ):
        """Tests if specimen is cited in given text

        Args:
          text (str): the string to check against
          dept (str): name of department
          spec_nums (list): list of catnums parsed from the text
          spec_num_only (bool): specifies whether spec_num must appear
          context_only (bool): specifies whether context must match
          kwargs: additional scoring to pass to MatchObject as kwarg=score

        Returns:
           MatchObject summarizing the quality of the match
        """
        std = Standardizer(
            minlen=5,
            stopwords=STOPWORDS,
            replace_endings=ENDINGS,
            replace_words=REPLACEMENTS,
        )
        score = MatchObject()
        score.record = self
        score.threshold = 1

        # Catalog number must appear in the list of specimen numbers if given
        # FIXME: This is a very loose check, does that make sense?
        if spec_nums:
            for spec_num in spec_nums:
                if self.catalog_number.number == spec_num.number:
                    break
            else:
                print(self.catalog_number, "NOT IN", spec_nums)
                return score

        # Add scores from kwarg dict. This accounts for context beyond the
        # specific text (for example, if the author of the article matches
        # the donor/collector of the specimen).
        for key, val in kwargs.items():
            score.add(key, val)

        # Check text for identifiers if not previously vetted
        if not spec_nums and not context_only:

            score.penalties = -1

            # The snippet parser wraps catalog numbers with **, which
            # confuses the parser here. Strip paired ** to fix this.
            # FIXME: Address underlying issue in parser
            match = re.search(r"\*\*([^\*]+)\*\*", text)
            id_string = match.group(1) if match else text

            # Check if catalog number appears in text
            catnums = [CatNum(c) for c in self.parser.parse(id_string)]
            for catnum in catnums:
                if catnum.similar_to(self.catalog_number) or catnum.similar_to(
                    self.meteorite_number
                ):
                    score.add("catalogNumber", 1)
                    break

            # Match other identifiers if catalog number check fails
            if score < 0:
                other_nums = {
                    "fieldNumber": self.field_number,
                    "recordNumber": self.record_number,
                }
                stop = False
                for field_name, spec_nums in other_nums.items():
                    # Collector-assigned identifiers may be formatted
                    # differently than citations, so standardize format
                    # by removing common delimiters
                    subs = {r"[ \-]+": r"[ \-]+"}
                    for spec_num in sorted(spec_nums, key=lambda s: -len(s)):
                        pattern = to_pattern(spec_num, subs=subs, flags=re.I)
                        if pattern.search(id_string):

                            # Penalize short or numeric identifiers
                            val = 1
                            if len(spec_num) < 6 or spec_num.isnumeric():
                                val = 0.5
                            score.add(field_name, val)

                            # If spec_num_only is set to True, update
                            # threshold so match evaluates to True
                            if spec_num_only:
                                score.threshold = 0
                                score.penalties = 0

                            stop = True
                            break
                    if stop:
                        break

            # Abort match if no identifier found
            if score < -0.5:
                return score

        elif spec_nums or not context_only:
            # Default field_name to catalogNumber if numbers given as list
            if isinstance(spec_nums, list):
                spec_nums = {"catalogNumber": n for n in spec_nums}

            for field_name, spec_num in spec_nums.items():

                # Convert string to CatNum object. The regular expression
                # strips descriptions like "type no." from catalog numbers.
                if not isinstance(spec_num, CatNum):
                    spec_num = re.sub(r"\b[a-z]+( [a-z]+)*\.? ", "", spec_num)
                    spec_num = parse_catnums(spec_num)[0]

                # Note but do not score the field_name
                score.add(field_name, 0)

                # Compare prefix. Published prefixes are unreliable so this
                # check only has a weak effect on the outcome unless the
                # prefix corresponds to a specific deparment (PAL, ENT, etc.)
                if spec_num.prefix == self.catalog_number.prefix:
                    score.add("_prefix", 0.01)
                elif (
                    self.collection_code
                    and spec_num.prefix
                    and self.collection_code.upper().startswith(spec_num.prefix)
                ):
                    score.add("collectionCode", 0.51)

                # Compare suffix. Citations often either include suffixes
                # that do not correspond to a specific catalog record or
                # exclude suffixes that do, so this is configured as a bonus
                # to select between otherwise good matches.
                if (
                    self.catalog_number.suffix
                    and spec_num.suffix == self.catalog_number.suffix
                ):
                    score.add("_suffix", 0.01)

        # Department must match if given
        if self.collection_code and dept:
            depts = {validate_dept(d) for d in as_list(dept)}
            if len(depts) == 1:
                val = 1 if self.collection_code in depts else -1000
            else:
                val = 0.5 if self.collection_code in depts else -1000
            score.add("collectionCode", val)

        # Compare record against context from string
        if text:

            # Delimit text to simplify some of the matching operations
            delimited_text = std.delimit(text)

            # Compare taxonomy/classification
            if self.collection_code != "Mineral Sciences":
                for val in self.higher_classification:
                    if std.same_as(val, text, "any"):
                        score.add("higherClassification", 2)

                for val in self.scientific_name:
                    if std.same_as(val, text, "any"):
                        score.add("scientificName", 2)

                val = self.vernacular_name
                if std.same_as(val, text, "all"):
                    score.add("vernacularName", 3)

            if not self.higher_classification:
                for val in self.scientific_name:
                    if std.same_as(val, text, "any", replace_endings=["ic", "s", "y"]):
                        score.add("scientificName", 2)

            # Compare stratigraphy
            if self.collection_code in ["Mineral Sciences", "Paleobiology"]:

                # Compare chronostratigraphy
                for attr in ["group", "formation", "member"]:
                    val = getattr(self, attr)
                    if std.same_as(val, text, "any"):
                        score.add("lithostratigraphy", 3)

                # Compare chronostratigraphy
                for attr in [
                    "earliest_period_or_lowest_system",
                    "earliest_epoch_or_lowest_series",
                    "earliest_age_or_lowest_stage",
                    "latest_period_or_highest_system",
                    "latest_epoch_or_highest_series",
                    "latest_age_or_highest_stage",
                ]:
                    val = getattr(self, attr)
                    if std.same_as(val, text, "any"):
                        score.add("chronostratigraphy", 1)

            # Compare type status
            if self.type_status:
                pattern = r"\b{}s?\b".format(self.type_status)
                if re.search(pattern, text, flags=re.I):
                    score.add("typeStatus", 0.51)

            # Compare country
            if self.country:
                pattern = r"\b{}\b".format(re.escape(std.delimit(self.country)))
                if re.search(pattern, delimited_text):
                    score.add("country", 0.51)

            # Compare state/province
            for state_prov in [s for s in self.state_province if s]:
                pattern = r"\b{}\b".format(re.escape(std.delimit(state_prov)))
                if re.search(pattern, delimited_text):
                    score.add("stateProvince", 0.51)

            # Compare DwC locality fields
            attrs = [
                "county",
                "features",
                "island",
                "island_group",
                "locality",
                "municipality",
                "sea_gulf",
                "water_body",
            ]
            for attr in attrs:
                for val in as_list(getattr(self._site, attr)):
                    if val and std.same_as(val, text, "any"):
                        score.add(to_camel(attr), 1)

            # Compare custom locality fields
            attrs = [
                "mine",
                "mining_district",
                "volcano",
            ]
            for attr in attrs:
                for val in as_list(getattr(self._site, attr)):
                    if val and std.same_as(val, text, "any"):
                        score.add(to_camel(attr), 1)

            # Extract features from verbatim locality
            if self.verbatim_locality:
                for loc in parse_localities(self.verbatim_locality):
                    for name in loc.names():
                        pattern = "\b{}\b".format(re.escape(std.delimit(name)))
                        if re.search(pattern, delimited_text):
                            score.add("verbatimLocality", 1)
                        break

        return score

    def match_texts(self, sources, *args, **kwargs):
        """Tests if specimen is cited in a set of related texts"""
        score = MatchMaker()
        for source, text in sources.items():
            match = self.match_text(text, **kwargs)

            if match:
                match.source = source
                score.append(match)

                # Once there is a specimen identifier matches, that check
                # is ignored for the rest of the texts. This allows for
                # pure context matches on publication titles, etc.
                if re.search(r"[a-z]Number\b", str(match)):
                    kwargs["context_only"] = True

        return score

    def _parse_dwc(self, data):
        """Parses data from a Simple Darwin Core record"""
        for key, val in data.items():
            attr = to_attribute(key)

            # Coerece catalog numbers to CatNum type
            if attr == "catalog_number":

                # Meteorite names sometimes appear in the catalog number
                # field in DwC records from the portal. Move these to the
                # appropriate custom field.
                try:
                    val = self._split_meteorite_names(val)
                except ValueError:
                    # Some departments include the museum code as part of
                    # the catalog number prefix. Those confuse the parser,
                    # so strip them where found.
                    code = data.get("institutionCode", "")
                    if code and val.startswith(code):
                        val = val[len(code) :].strip()

                    val = CatNum(val)

            elif attr == "class":
                attr = "class_"

            setattr(self, attr, val)

    def _parse_emu(self, rec):
        """Parses data from the EMu ecatalogue module"""
        self.occurrence_id = rec.get_guid("EZID")
        if not self.occurrence_id:
            self.occurrence_id = rec["irn"]
        self.basis_of_record = "OtherSpecimen"
        self.collection_code = rec("CatDepartment")
        self.catalog_number = parse_catnum(rec)
        if self.collection_code:
            self.catalog_number.department = self.collection_code
        elif rec("CatDivision"):
            self.catalog_number.division = rec("CatDivision")[:3].upper()
        self.field_number = rec.get_field_numbers()
        self.lab_number = rec.get_other_numbers("Lab No")
        # Get taxonomic info
        self.scientific_name = rec("IdeTaxonRef_tab", "ClaScientificName")
        # Get references
        self.associated_references = []
        for ref in rec("BibBibliographyRef_tab"):
            try:
                self.associated_references.append(Reference(ref))
            except (AttributeError, ValueError):
                citation = ref["SummaryData"].split("]", 1)[-1].strip()
                self.associated_references.append(citation)
        self.associated_references = dedupe(self.associated_references)
        # Construct a site from the EMu record and back-populate those fields
        self._site = Site(rec("BioEventSiteRef"))
        self._strat = LithoStrat(rec)

    def _parse_mongo(self, rec):
        self.occurrence_id = rec["admid"]

    def _split_meteorite_names(self, val):
        if self.collection_code == "Mineral Sciences":
            catnums = []
            for val in as_list(val):
                try:
                    catnum = CatNum(val)
                    if is_antarctic(val):
                        self.meteorite_number = val
                    else:
                        catnums.append(catnum)
                except ValueError:
                    self.meteorite_name = val
            if len(catnums) > 1:
                raise ValueError(f"Too many catalog numbers: {val}")
            return catnums[0]
        raise ValueError("Not a Mineral Sciences record")
