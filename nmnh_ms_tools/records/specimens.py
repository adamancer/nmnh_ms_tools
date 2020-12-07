"""Defines class and methods to parse and manipulate specimen data"""
import re

from .core import Record
from .catnums import CatNum, get_catnum
from .references import Reference
from .sites import Site
from .stratigraphy import LithostratHierarchy
from ..tools.specimen_numbers.link import (
    MatchObject,
    validate_dept,
    ENDINGS,
    STOPWORDS,
    REPLACEMENTS,
)
from ..tools.specimen_numbers.parser import Parser
from ..utils import dedupe, to_attribute, to_pattern
from ..utils.standardizers import Standardizer




class Specimen(Record):
    """Defines methods for parsing and manipulating specimen data"""
    parser = Parser()
    _site_attrs = Site({}).attributes
    _strat_attrs = LithostratHierarchy({}).attributes


    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.institution_code = ''
        self.collection_code = ''
        self.basis_of_record = ''
        self.occurrence_id = ''
        self.catalog_number = CatNum('')
        self.field_number = []
        self.lab_number = []            # custom
        self.record_number = []
        self.associated_references = []
        self.taxon_id = []
        self.higher_classification = []
        self.scientific_name = []
        self.vernacular_name = ''
        self.location_id = ''
        self.higher_geography = []
        self.continent = ''
        self.country = ''
        self.state_province = []
        self.county = []
        self.municipality = ''
        self.island = ''
        self.island_group = ''
        self.water_body = []
        self.mining_district = ''      # custom
        self.mine = ''                 # custom
        self.volcano = ''              # custom
        self.maps = []                 # custom
        self.features = []             # custom
        self.locality = ''
        self.verbatim_locality = ''
        self.verbatim_latitude = ''
        self.verbatim_longitude = ''
        self.georeference_sources = ''
        self.georeference_remarks = ''
        self.geological_context_id = ''
        self.group = ''
        self.formation = ''
        self.member = ''
        self.earliest_era_or_highest_erathem = ''
        self.earliest_period_or_highest_system = ''
        self.earliest_epoch_or_highest_series = ''
        self.earliest_age_or_highest_stage = ''
        self.latest_era_or_highest_erathem = ''
        self.latest_period_or_highest_system = ''
        self.latest_epoch_or_highest_series = ''
        self.latest_age_or_highest_stage = ''
        self._site = None
        self._strat = None
        # Initialize instance
        super(Specimen, self).__init__(*args, **kwargs)


    #def __str__(self):
    #    return self.name


    @property
    def name(self):
        return str(self.catalog_number)


    def parse(self, data):
        """Parses data from various sources to populate class"""
        self.reset()
        if 'basisOfRecord' in data:
            self._parse_dwc(data)
        elif 'CatNumber' in data:
            self._parse_emu(data)
        else:
            raise ValueError('Could not parse {}'.format(data))
        # Construct or integrate site info
        attrs = [a for a in self.attributes if a in self._site_attrs]
        if not self._site:
            self._site = Site({a: getattr(self, a) for a in attrs})
        else:
            for attr in attrs:
                setattr(self, attr, getattr(self._site, attr))
        # Construct or re-integrate strat info
        attrs = [a for a in self.attributes if a in self._strat_attrs]
        if not self._strat:
            self._strat = LithostratHierarchy({a: getattr(self, a)
                                              for a in attrs})
        else:
            for attr in attrs:
                setattr(self, attr, getattr(self._strat, attr))


    def cited_in(self, text, dept=None, taxa=None, id_only=False):
        """Tests if specimen occurs in given text"""
        assert text, 'no text provided'

        score = MatchObject()
        score.penalties = -1

        # Match on either the catalog or field number (required)
        for candidate in self.parser.parse(text):
            catnum = get_catnum(candidate)
            if self.catalog_number.similar_to(catnum):
                score.add('catalogNumber', 1)
                break
        else:
            # Match field number
            subs = {r'[ \-]+': r'[ \-]+'}
            for field_num in self.field_number:
                pattern = to_pattern(field_num, subs=subs, flags=re.I)
                if pattern.search(text):
                    val = 1
                    if len(field_num) < 6 or field_num.isnumeric():
                        val = 0.5
                    score.add('recordNumber', val)
                    break
        if score < -0.5:
            return score

        # Check additional context from the text
        score.update(self.match_context(text, dept=dept, taxa=taxa))

        # Force to return if either a catalog or field number matches. This
        # allows the user to match text that doesn't include information that
        # overlaps with the catalog record (for example, if the author of a
        # paper is known to have collected a given sample)
        if id_only and -0.5 <= score <= score.threshold:
            score.add('', score.threshold - score.points + 1.01)

        return score


    def match_context(self, text, dept=None, taxa=None):
        """Tests if specimen occurs in given text

        Args:
          text (str): the string to check against
          dept (str): hint for the likely department represented in the string
          taxa (list): list of taxa extracted from the string

        Returns:
           MatchObject summarizing the quality of the match
        """
        std = Standardizer(minlen=5,
                           stopwords=STOPWORDS,
                           replace_endings=ENDINGS,
                           replace_words=REPLACEMENTS)
        dept = validate_dept(dept)
        score = MatchObject()
        score.threshold = 1

        # Compare department
        if self.collection_code and dept:
            val = 1 if self.collection_code == dept else -100
            score.add('collectionCode', val)

        # Compare record against context from string
        if text:

            # Compare taxonomy/classification
            if self.collection_code != 'Mineral Sciences':
                for val in self.higher_classification:
                    if std.same_as(val, text, 'any'):
                        score.add('higherClassification', 2)
                    for taxon in taxa:
                        if std.same_as(val, taxon, 'any'):
                            score.add('higherClassification', 2)
                val = self.vernacular_name
                if std.same_as(val, text, 'all'):
                    score.add('vernacularName', 3)

            if not self.higher_classification:
                for val in self.scientific_name:
                    if std.same_as(val, text, 'any',
                                   replace_endings=['ic', 's', 'y']):
                        score.add('scientificName', 2)

            # Compare stratigraphy
            if self.collection_code in ['Mineral Sciences', 'Paleobiology']:
                for attr in ['group', 'formation', 'member']:
                    val = getattr(self, attr)
                    if std.same_as(val, text, 'any'):
                        score.add('stratigraphy', 3)

            # Compare political geography
            if std.same_as(self.country, text, 'exact', minlen=0):
                score.add('country', 0.51)

            for val in self.state_province:
                if std.same_as(val, text, 'exact', minlen=0):
                    score.add('stateProvince', 0.51)

            # Locality
            attrs = [
                'county',
                'features',
                'island',
                'island_group',
                'locality',
                'municipality',
                'mine',
                'mining_district',
                'sea_gulf',
                'volcano',
                'water_body'
            ]
            for attr in attrs:
                vals = getattr(self._site, attr)
                if any(vals):
                    if not isinstance(vals, list):
                        vals = [vals]
                    for val in vals:
                        #kind = 'any'if attr == 'locality' else 'exact'
                        if val and std.same_as(val, text, 'any'):
                            score.add('locality', 1)
        return score


    def _parse_dwc(self, data):
        """Parses data from a Simple Darwin Core record"""
        for key, val in data.items():
            attr = to_attribute(key)
            if attr == 'catalog_number':
                val = CatNum(val, suppress_parsing_errors=True)
            setattr(self, attr, val)


    def _parse_emu(self, rec):
        """Parses data from the EMu ecatalogue module"""
        self.occurrence_id = rec.get_guid('EZID')
        self.basis_of_record = 'OtherSpecimen'
        self.collection_code = rec('CatDepartment')
        self.catalog_number = get_catnum(rec)
        if self.collection_code:
            self.catalog_number.department = self.collection_code
        elif rec('CatDivision'):
            self.catalog_number.division = rec('CatDivision')[:3].upper()
        self.field_number = rec.get_field_numbers()
        self.lab_number = rec.get_other_numbers('Lab No')
        # Get taxonomic info
        self.scientific_name = rec('IdeTaxonRef_tab', 'ClaScientificName')
        # Get references
        self.associated_references = []
        for ref in rec('BibBibliographyRef_tab'):
            try:
                self.associated_references.append(Reference(ref))
            except (AttributeError, ValueError):
                citation = ref['SummaryData'].split(']', 1)[-1].strip()
                self.associated_references.append(citation)
        self.associated_references = dedupe(self.associated_references)
        # Construct a site from the EMu record and back-populate those fields
        self._site = Site(rec('BioEventSiteRef'))
        self._strat = LithostratHierarchy(rec)


    def _parse_mongo(self, rec):
        self.occurrence_id = rec['admid']
