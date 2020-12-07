"""Defines method to parse and work with structured bibliography data"""

import datetime as dt
import logging
import re
from collections import namedtuple

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

from .bibtex import BibTeXMapper
from ..core import Record
from ..people import Person, combine_authors, parse_names
from ...bots import Bot
from ...utils.standardizers import Standardizer

logger = logging.getLogger(__name__)




ENTITIES = {
    r'$\mathsemicolon$': ';',
    r'{\{AE}}': ';',
    r'({IUCr})': ';',
    r'{\textdegree}': ';' ,
    r'{\textquotesingle}': u"'",
    r'\textemdash': ';',
    r'\textendash': ';',
    r'St\u0e23\u0e16ffler': ';',
    r'{\'{a}}': 'a',
    r'$\greater$': '>',
    r'$\less$': '<'
}




class Reference(Record):
    """Defines methods for parsing and manipulating references"""
    bot = Bot()
    _btm = BibTeXMapper()
    terms = [
        'authors',
        'year',
        'title',
        'publication',
        'volume',
        'number',
        'pages',
        'publisher',
        'kind',
        'url',
        'doi',
    ]
    std = Standardizer()


    def __init__(self, data):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        # Explicitly define defaults for all reported attributes
        self.authors = []
        self.kind = ''
        self.number = ''
        self.pages = ''
        self.publication = ''
        self.publisher = ''
        self.title = ''
        self.url = ''
        self.volume = ''
        self.year = ''
        self._doi = ''
        # Initialize instance
        super(Reference, self).__init__(data)


    def __str__(self):
        return self.name


    @property
    def doi(self):
        return self._doi


    @doi.setter
    def doi(self, doi):
        # Split off common DOI prefixes
        if doi:
            doi = doi.split('doi.org/', 1)[-1].split('doi:', 1)[-1].strip()

        # Test if DOI appears to be valid, log a warning if not
        if doi.startswith('10.'):
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


    @property
    def journal(self):
        return self.publication


    @property
    def series(self):
        return self.publication


    @property
    def issue(self):
        return self.number


    @issue.setter
    def issue(self, val):
        self.number = val


    def parse(self, data):
        """Parses data from various sources to populate class"""
        self.reset()
        self.verbatim = data
        is_doi = isinstance(data, str) and data.startswith('10.')
        if is_doi:
            self._parse_doi(data)
        elif 'BibRecordType' in data:
            self._parse_emu(data)
        elif '_gddid' in data:
            self._parse_geodeepdive(data)
        elif 'title' in data:
            self._parse_reference(data)
        elif isinstance(data, self.__class__):
            self._parse_reference(self.to_dict(attributes=attributes))
        else:
            raise ValueError('Could not parse {}'.format(data))
        # Always use publisher data if possible
        if self.doi and not is_doi:
            doi = self.doi
            self.reset()
            self._parse_doi(doi)


    def same_as(self, other, strict=True):
        """Tests if two references are the same"""
        try:
            assert isinstance(other, self.__class__)
            # Ensure that certain basic data is present in both records
            assert self.authors
            assert self.title
            assert self.year
            assert other.authors
            assert other.title
            assert other.year
        except AssertionError:
            return False
        if self.doi and other.doi:
            return self.doi == other.doi
        same_first_author = self.authors[0].first == other.authors[0].first
        same_year = self.year == other.year
        similar_title = self.std.similar(self.title, other.title, minlen=2)
        return same_first_author and same_year and similar_title


    def resolve_doi(self, doi=None):
        """Returns a bibTeX string of metadata for a given DOI.

        Source: https://gist.github.com/jrsmith3/5513926

        Args:
            doi (str): a valid DOI corresponding to a publication

        Returns:
            BibTeX record as a string
        """
        if doi is None:
            doi = self.doi
        if doi:
            url = 'https://doi.org/{}'.format(doi)
            headers = {'Accept': 'application/x-bibtex'}
            try:
                response = self.bot.get(url, headers=headers)
                if response.text.startswith('@'):
                    return response.text
            except ValueError:
                logger.warning(f"Could not resolve {doi}")


    def citation(self):
        """Writes a citation based on bibliographic data"""
        authors = combine_authors(self.authors, delim=', ', conj='&')
        if self.doi:
            url = 'https://doi.org/{}'.format(self.doi)
        elif self.url:
            url = self.url
        else:
            url = ''
        # Theses don't have publications, so provide something here
        publication = self.publication
        if not publication:
            pubs = {
                'book': self.title,
                'mastersthesis': '{} (Masters Thesis)'.format(self.title),
                'misc': self.title,
                'phdthesis': '{} (PhD Dissertation)'.format(self.title),
                'techreport': self.title
            }
            try:
                publication = pubs[self.entry_type]
            except KeyError:
                raise ValueError('No source: {}'.format(self.entry_type))
        # Create the raw citation string
        mask = '{} {} ({}) {}: {}. {}'
        ref = mask.format(authors,
                          publication,
                          self.year,
                          self.volume,
                          self.number,
                          url).strip('. ')
        # Clean up the raw citation string
        ref = re.sub(r' +', ' ', ref).replace(': .', '.') \
                                     .replace(' :', '') \
                                     .replace(' ()', '') \
                                     .replace(' .', '.') \
                                     .rstrip(': ')
        return ref.strip()


    def serialize(self):
        """Summarizes record as a string"""
        return '|'.join([str(self.authors[0]), self.year, self.title, self.doi])


    def deserialize(self, key):
        """Expands a serialized reference into a full Reference"""
        author, year, title, doi = key.split('|')
        return self.__class__({
            'author': Person(author),
            'year': year,
            'title': title,
            'doi': doi,
        })


    def to_emu(self):
        """Formats record for EMu ebibliography module"""
        rec_type = self._btm.emu_record_type(self.entry_type)
        source_type = self._btm.emu_source_type(self.entry_type)
        prefix = self._btm.emu_record_type(self.entry_type, True)
        parent = self._btm.emu_source_type(self.entry_type, True)
        # Populate a bibliography record
        kwargs = {'SecRecordStatus': 'Unlisted'}  # Author names are unlisted
        rec = {
            'BibRecordType': rec_type,
            '{}AuthorsRef_tab': [a.to_emu(**kwargs) for a in self.authors],
            '{}Role_tab': ['Author' for _ in self.authors],
            '{}Title': self.title,
            '{}PublicationDates': self.year,
            '{}Volume': self.volume,
            '{}Issue': self.number,
            '{}Pages': self.pages,
            'NotNotes': self.verbatim
        }

        if parent and self.publication:
            rec['{}ParentRef'] = {
                'BibRecordType': source_type,
                '{}Title'.format(parent): self.publication
            }
        # Add fields specific to or excluded from a given type
        if prefix == 'Oth':
            del rec['{}PublicationDates']
            del rec['{}Volume']
            del rec['{}Issue']
        elif prefix == 'The':
            rec['TheAuthorRef'] = rec['{}AuthorsRef_tab'][0]
            rec['TheThesisType'] = self._btm.emu_thesis_type(self.entry_type)
            rec['ThePublicationDate'] = rec['{}PublicationDate']
            rec['TheOrganisation'] = {
                'NamPartyType': 'Organization',
                'NamOrganisation': self.school
            }
            del rec['{}AuthorsRef_tab']
            del rec['{}PublicationDate']
        # Add GUIDs
        if self.doi:
            rec['AdmGUIDType_tab'] = ['DOI']
            rec['AdmGUIDValue_tab'] = [self.doi]
            rec['NotNotes'] = self.resolve_doi()
        # Assign prefix and remove empty keys
        rec = {k.format(prefix): v for k, v in rec.items() if v}
        return rec


    def _parse_bibtex(self, text):
        """Parses BibTex record returned by DOI resolver

        Args:
            bib (str): a BibTeX record

        Returns:
            Dict containing reference data
        """
        for entity, repl in ENTITIES.items():
            text = text.replace(entity, repl)
        parser = BibTexParser()
        parser.customization = convert_to_unicode
        parsed = bibtexparser.loads(text, parser=parser).entries[0]
        # Check for unhandled LaTeX entities
        braces = re.compile(r'\{([A-z_ \-]+|[\u0020-\uD7FF])\}', re.U)
        for key, val in parsed.items():
            val = braces.sub(r'\1', val)
            if '{' in val:
                raise ValueError('Unhandled LaTeX: {}'.format(val))
        # Map parsed data to Reference
        self.kind = parsed['ENTRYTYPE']
        self.authors = parse_names(parsed.get('author', ''))
        self.title = parsed['title']
        try:
            self.year = self._parse_year(parsed['year'])
        except KeyError:
            self.year = '????'
        # Map parent publication
        for key in ('booktitle', 'journal', 'series'):
            val = parsed.get(key)
            if val:
                self.publication = val
                break
        # Map publisher/school
        self.publisher = parsed.get('publisher', '')
        self.school = parsed.get('school', '')
        # Map volume/issue info
        self.volume = parsed.get('volume', '')
        self.number = parsed.get('number', '')
        self.pages = parsed.get('pages', '').replace('--', '-')
        self.doi = parsed['doi']
        if self.doi:
            self.url = 'https://doi.org/{}'.format(self.doi)
        else:
            self.url = parsed['url']
        self.publisher = parsed['publisher'].rsplit('(', 1)[0].rstrip()


    def _parse_doi(self, doi=None):
        """Retrieves and parses data based on DOI"""
        bibtex = self.resolve_doi(doi)
        if bibtex:
            self._parse_bibtex(bibtex)


    def _parse_emu(self, rec):
        """Parses an EMu ebibliography record"""
        self.kind = rec('BibRecordType')
        if not self.kind:
            raise ValueError('BibRecordType required')
        # Give the specific thesis type
        if self.kind == 'Thesis':
            entry_type = self._btm.parse_thesis(rec('TheThesisType'))
            thesis_type = self._btm.emu_thesis_type(entry_type)
            self.kind = '{} ({})'.format(self.kind, thesis_type)
        src_field = self._btm.source_field(self.entry_type)
        prefix = self._btm.emu_record_type(self.entry_type, True)
        parent = self._btm.emu_source_type(self.entry_type, True)
        # Get basic metadata
        self.authors = []
        try:
            authors = rec('{}AuthorsRef_tab'.format(prefix))
        except KeyError:
            authors = [rec('{}AuthorsRef'.format(prefix))]
        for author in authors:
            for key in ['NamFirst', 'NamMiddle', 'NamLast']:
                author.setdefault(key, '')
            name = '{NamFirst} {NamMiddle} {NamLast}'.format(**author).strip()
            try:
                self.authors.append(Person(name))
            except ValueError as e:
                if name:
                    logger.error(f"Could not parse '{name}'")
        self.title = rec('{}Title'.format(prefix))
        # Parse publishing year from publication date
        pub_date = rec('{}PublicationDates'.format(prefix))
        if not pub_date:
            pub_date = rec('{}PublicationDate'.format(prefix))
        self.year = self._parse_year(pub_date)
        # Get publication metadata
        try:
            pub = rec('{}ParentRef'.format(prefix), '{}Title'.format(parent))
            # Fall back to summary data if source not found
            if not pub:
                summary = rec('{}ParentRef'.format(prefix), 'SummaryData')
                pub = summary.split(']', 1)[-1].strip('. ')
            self.publication = pub
            self.volume = rec('{}Volume'.format(prefix))
            self.number = rec('{}Issue'.format(prefix))
        except KeyError:
            pass
        self.pages = rec('{}Pages'.format(prefix)).replace('--', '-')
        self.doi = rec.get_guid('DOI')
        if self.doi:
            self.url = 'https://doi.org/{}'.format(self.doi)


    def _parse_geodeepdive(self, data):
        """Parses GeoDeepDive article record"""
        self.kind = data.get('type', '').title()
        src_field = self._btm.source_field(self.kind)
        # Get basic metadata
        self.authors = []
        for name in [a['name'] for a in data.get('author', []) if a['name']]:
            self.authors.extend(parse_names(name))
        self.title = data['title']
        self.year = self._parse_year(data.get('year', ''))
        try:
            setattr(self, src_field, data['journal']['name']['name'])
        except TypeError:
            setattr(self, src_field, data['journal'])
        self.volume = data.get('volume', '')
        self.number = data.get('number', '')
        self.pages = data.get('pages', '').replace('--', '-')
        # Get unique identifiers
        identifiers = data.get('identifier', [])
        try:
            self.doi = [b['id'] for b in identifiers if b['type'] == 'doi'][0]
        except IndexError:
            self.url = data.get('url', '')
        else:
            self.url = 'https://doi.org/{}'.format(self.doi)
        self.publisher = data.get('publisher', '')


    def _parse_reference(self, data):
        """Parses a pre-formatted reference"""
        for attr, val in data.items():
            setattr(self, attr, val)


    def _parse_ris(self, text):
        """Parses RIS record"""
        raise NotImplementedError


    def _parse_year(self, val):
        """Parses year from value"""
        if isinstance(val, dt.date):
            return str(val.year)
        try:
            return re.search(r'\d{4}', val).group()
        except AttributeError:
            return '????'




class References:

    def __init__(self, references=None):
        self._references = references if references is not None else []


    def __getattr__(self, attr):
        try:
            return getattr(self._references, attr)
        except AttributeError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{attr}'"
            )


    def __bool__(self):
        return bool(self._references)


    def __contains__(self, ref):
        """Checks if the given reference appears in a list of references"""
        if not isinstance(ref, Reference):
            ref = Reference(ref)
        for ref_ in self.references:
            if ref.similar_to(ref_):
                return True
        return False


    def __iter__(self):
        return iter(self._references)


    def __len__(self):
        return len(self._references)


    def __str__(self):
        return str(self._references)


    @property
    def references(self):
        references = []
        for ref in self._references:
            if not isinstance(ref, Reference):
                ref = Reference(ref)
            references.append(ref)
        self._references = references
        return references


    @references.setter
    def references(self, references):
        self._references = references
