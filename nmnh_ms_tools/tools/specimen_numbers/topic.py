"""Defines methods for determining the subject area of a string"""
import glob
import json
import logging
import os
import pprint as pp
import re
import time

from collections import OrderedDict, namedtuple
from lxml import etree
import requests
from unidecode import unidecode

from ...bots import GNRDBot, ITISBot
from ...utils.standardizers import Standardizer




logger = logging.getLogger(__name__)
logger.debug('Loading topic.py')




Mapping = namedtuple('Mapping', ['rank', 'value', 'dept'])


class TaxonLookup:
    """Matches taxa to a collecting department"""
    std = Standardizer(minlen=1)
    custom = {
        'Corosaurus': 'pl',
        'Phiomys': 'pl',
        'Tetheopsis': 'pl',
        'Tenuipteria': 'pl'
    }

    def __getattribute__(self, attr):
        if attr == 'taxa':
            try:
                object.__getattribute__(self, attr)
            except AttributeError:
                logger.debug('Reading taxa...')
                # FIXME: nmnh.json not included in the package
                fp = os.path.join(os.path.dirname(__file__), 'files', 'nmnh.json')
                self.__class__.taxa = json.load(open(fp, 'r'))
                for taxon, dept in self.custom.items():
                    self[taxon] = {dept: 10}
        return object.__getattribute__(self, attr)


    def __getitem__(self, taxon):
        taxon = self.std(taxon)
        index = taxon[:3]
        return self.taxa[index][taxon]


    def __setitem__(self, taxon, depts):
        taxon = self.std(taxon)
        index = taxon[:3]
        self.taxa.setdefault(index, {}).setdefault(taxon, {})
        for dept, count in depts.items():
            try:
                self.taxa[index][taxon][dept] += count
            except KeyError:
                self.taxa[index][taxon][dept] = count


    def score(self, taxon):
        """Scores a taxon"""
        if isinstance(taxon, list):
            return [self.score(t) for t in taxon]
        key = self.std(taxon)
        try:
            depts = self[key]
        except KeyError:
            return {}
        total = sum([v for v in depts.values()])
        points = 1 if total >= 10 * len(depts) else (total / (10 * len(depts)))
        # Species bonus
        if len(depts) == 1 and key.count('-') == 1:
            points = 1
        result = {k: (points * v / total) for k, v in depts.items()}
        return result


    def get_department(self, taxa):
        """Returns the most likely department for the given taxa"""
        scored = {}
        for taxon in sorted(set(taxa)):
            for dept, score in self.score(taxon).items():
                logger.debug(taxon, dept, score)
                try:
                    scored[dept] += score
                except KeyError:
                    scored[dept] = score
        total = sum([v for v in scored.values()])
        if total >= 1:
            result = {k: (v / total) for k, v in scored.items()}
            try:
                return [k for k, v in result.items() if v >= 0.85][0]
            except IndexError:
                try:
                    return [k for k, v in result.items() if v >= 0.75][0] + '?'
                except IndexError:
                    logger.debug(result)
            else:
                return dept


class Topicker:
    depts = {
        'an': 'Anthropology',
        'bt': 'Botany',
        'br': 'Vertebrate Zoology: Birds',
        'en': 'Entomology',
        'fs': 'Vertebrate Zoology: Fishes',
        'hr': 'Vertebrate Zoology: Amphibians & Reptiles',
        'iz': 'Invertebrate Zoology',
        'mm': 'Vertebrate Zoology: Mammals',
        'ms': 'Mineral Sciences',
        'pl': 'Paleobiology'
    }
    mappings = [
        Mapping('kingdom', 'Plantae', 'bt'),
        Mapping('class', 'Arachnida', 'en'),
        Mapping('class', 'Aves', 'br'),
        Mapping('class', 'Amphibia', 'hr'),
        Mapping('class', 'Insecta', 'en'),
        Mapping('class', 'Mammalia', 'mm'),
        Mapping('class', 'Reptilia', 'hr'),
        Mapping('phylum', 'Chordata', 'fs'),  # assign remaining verts to fs
        Mapping('phylum', '!Chordata', 'iz')  # assign remaining inverts to iz
    ]
    lookup = TaxonLookup()
    itis_bot = ITISBot()
    gnrd_bot = GNRDBot()


    def __init__(self):
        try:
            with open('hints.json', 'r') as f:
                self.hints = json.load(f)
        except IOError:
            self.hints = {}
        self.keywords = self._read_keywords()


    def _read_keywords(self):
        script_dir = os.path.dirname(__file__)
        keywords = {}
        for fp in glob.iglob(os.path.join(script_dir, 'files', '*.txt')):
            dept = os.path.basename(fp)[:-4]
            with open(fp, 'r') as f:
                patterns = [p.strip() for p in f.readlines() if p.strip()]
                keywords[dept] = patterns
        ordered = OrderedDict()
        for dept in ['an', 'pl', 'ms']:
            ordered[dept] = keywords.pop(dept)
        for dept in sorted(keywords):
            ordered[dept] = keywords[dept]
        return ordered


    def get_names(self, text, **kwargs):
        """Returns taxonomic names fouind in the given text"""
        logger.debug('Seeking taxonomic names in "{}"'.format(text))
        sci_names = []
        text = self.clean_text(text)
        response = self.gnrd_bot.find_names(text)
        if response.status_code == 200:
            names = response.json().get('names', [])
            sci_names = self.clean_names([n['scientificName'] for n in names])
        logger.debug('Found {} names: {}'.format(len(sci_names), ', '.join(sci_names)))
        return sorted({n for n in sci_names if n})


    def resolve_names(self, names, **kwargs):
        """Resolve taxonomic names"""
        logger.debug('Resolving taxonomic names "{}"'.format(names))
        sci_names = []
        params = {'with_context': True, 'with_vernaculars': True}
        params.update(**kwargs)
        response = self.gnrd_bot.resolve_names(names, **params)
        if response.status_code == 200:
            for results in response.json().get('data', []):
                if results['is_known_name']:
                    for row in results['results']:
                        vernaculars = row.get('vernaculars', [])
            sci_names = self.clean_names([n['scientificName'] for n in names])
        logger.debug('Found {} names: {}'.format(len(sci_names), ', '.join(sci_names)))
        return sci_names


    def get_tsns(self, name, **kwargs):
        """Returns TSNs matching the given name"""
        logger.debug('Seeking TSNs for "{}"'.format(name))
        response = self.itis_bot.get_taxon(name, **kwargs)
        tsns = []
        if response.status_code == 200:
            root = response
            for child in response:
                for tag in child.iter('{*}tsn'):
                    tsns.append(tag.text)
        logger.debug('Found {} TSNs'.format(len(tsns)))
        if len(tsns) > 100:
            logger.debug('Limited results to first 100 TSNs')
            tsns = tsns[:100]
        return tsns


    def get_hierarchy(self, tsn, **kwargs):
        """Returns the taxonomic hierarchy for a given TSN"""
        logger.debug('Retrieving hierarchy for {}'.format(tsn))
        response = self.itis_bot.get_hierarchy(tsn, **kwargs)
        if response.status_code == 200:
            root = response
            for child in root:
                ranks = OrderedDict()
                for item in child.iter('{*}hierarchyList'):
                    rank = item.findtext('{*}rankName')
                    name = item.findtext('{*}taxonName')
                    if rank is not None:
                        #logger.debug('{} == {}'.format(rank.upper(), name))
                        ranks[rank.lower()] = name.lower()
                return ranks


    def map_to_department(self, hierarchy):
        """Maps a taxonomic hierarchy to an NMNH department"""
        # Ensure that the hierarchy has at least one of the keys needed for
        # the comparison to NMNH departments
        avail = {mp.rank for mp in self.mappings}
        if not [k for k in avail if k in hierarchy]:
            logger.debug('Not enough info to place the following taxon:')
            for rank in hierarchy:
                logger.debug('{} == {}'.format(rank.upper(), hierarchy[rank]))
            return
        # Assign to a division based on the mapping
        for mp in self.mappings:
            eq = hierarchy.get(mp.rank) == mp.value.strip('!').lower()
            if mp.value.startswith('!'):
                eq = not eq
            if eq:
                logger.debug('Mapped to {}'.format(mp.dept))
                return mp.dept
        else:
            # Log failures
            logger.debug('Could not classify the following taxon:')
            for rank in hierarchy:
                logger.debug('{} == {}'.format(rank.upper(), hierarchy[rank]))


    def match_dept_keywords(self, text, i=None, j=None):
        """Matches a list of keywords"""
        words = [w for w in re.split(r'\W', text.lower())]
        for dept in list(self.keywords.keys())[i:j]:
            for pattern in self.keywords[dept]:
                for word in words:
                    if re.match('^' + pattern + '$', word, flags=re.I):
                        if len(word) < 3:
                            raise ValueError('Bad pattern in {}: {}'.format(dept, pattern))
                        logger.debug('Matched {} on keyword {}={}'.format(dept, pattern, word.lower()))
                        return dept, word.lower()
        return None, None


    @staticmethod
    def clean_text(text):
        orig = text[:]
        text = text.rstrip('|. ')
        patterns = {
            r'([A-z]{3,})aetes?(?:\b)': 'aeta',
            r'([A-z]{3,})ceans?(?:\b)': 'cea',
            r'([A-z]{3,})derms?(?:\b)': 'dermata',
            r'([A-z]{3,})odes?(?:\b)': 'oda',
            r'([A-z]{3,})oids?(?:\b)': 'oidea',
            r'([A-z]{3,})pods?(?:\b)': 'poda',
            r'([A-z]{3,})saurs?(?:\b)': 'saurus',
            r'([A-z]{3,})(?<!o)(?:us)(?:\b)': 'ia'
        }
        names = []
        for pattern, ending in patterns.items():
            try:
                stems = re.findall(pattern, text + ' | '.join(names))
            except AttributeError:
                pass
            else:
                for stem in {s.capitalize() for s in stems}:
                    names.append(stem + ending)
        if names:
            text += ' | ' + ' | '.join(names)
        # Add a trailing anchor to the text string
        return text + ' |'


    @staticmethod
    def clean_names(names):
        """Standardizes the formatting of a list of names"""
        cleaned = []
        for name in names:
            cleaned.extend([s.strip() for s in re.split(r'[:\(\)]', name)])
        return sorted({n for n in cleaned if n})


    @staticmethod
    def score_match(names, taxon):
        names = [s.lower() for s in names]
        for key in ['class', 'order', 'family']:
            for name in names:
                if name == taxon.get(key, '').lower():
                    logger.debug('Scored match at {0:.1f} points'.format(1))
                    return 1
        taxon = [s.lower() for s in list(taxon.values())]
        logger.debug('Names: {}'.format('; '.join(names)))
        logger.debug('Taxon: {}'.format('; '.join(taxon)))
        score = 0
        for name in names:
            if name in taxon:
                score += 1
            elif any([(name in s) for s in taxon]):
                score += 0.5
        score = score / len(names)
        logger.debug('Scored match at {0:.1f} points'.format(score))
        return score


    @staticmethod
    def guess_department(depts):
        counts = {}
        for dept, score in list(depts.items()):
            try:
                counts[dept] += score
            except KeyError:
                counts[dept] = score
        return [dept for dept, count in counts.items()
                if count == max(counts.values())][0]


    def get_department(self, text, taxa=None, **kwargs):
        logger.debug('Matching department in "{}"'.format(text))
        # Check keyword lists for non-biological collections, including paleo
        dept, match = self.match_dept_keywords(text, j=3)
        if dept:
            return dept
        # Check mappings and hints for a previously encountered match
        words = [s.lower() for s in re.split(r'\W', text) if s]
        for mapping in self.mappings:
            if mapping.value.lower() in words:
                return mapping.dept
        for key, dept in list(self.hints.items()):
            if key.lower() in [s.lower() for s in words]:
                logger.debug('Matched {}={} in hints'.format(key, dept))
                return dept
        # Check taxa for department
        if taxa:
            dept = self.get_department_from_taxa(taxa)
            if dept:
                return dept
        # Proceed with the more complex search since no easy match was found
        stop = False
        depts = {}
        names = self.get_names(text, **kwargs)
        for name in [n for n in names if len(n) > 6]:
            score = 0
            tsns = self.get_tsns(name)
            logger.debug('Found {:,} TSNs'.format(len(tsns)))
            for tsn in tsns:
                hierarchy = self.get_hierarchy(tsn)
                # Exclude matches if exact search term not found
                for taxon in hierarchy.values():
                    if name.lower() in taxon:
                        break
                else:
                    #logger.debug(name, hierarchy)
                    continue
                # Exclude matches on species if more than one result
                species = hierarchy.get('species', '').lower()
                if (len(tsns) > 1
                    and name.lower() in species
                    and not species.startswith(name.lower())):
                        logger.debug(name, hierarchy)
                        continue
                if hierarchy:
                    # One more check against hints
                    for key in {mp.rank for mp in self.mappings}:
                        try:
                            return self.hints[hierarchy[key]]
                        except KeyError:
                            pass
                    # No match, so try to determine the department
                    dept = self.map_to_department(hierarchy)
                    try:
                        logger.debug('Dept: {}'.format(self.depts[dept]))
                    except KeyError:
                        pass
                    else:
                        score = self.score_match(names, hierarchy)
                        try:
                            depts[dept] += score
                        except KeyError:
                            depts[dept] = score
                        msg = 'Cumulative score: {}={}'.format(dept, depts[dept])
                        logger.debug(msg)
                        if (score >= 0.8 or
                            depts[dept] >= 8 or
                            len(depts) == 1 and depts[dept] >= 5):
                                depts = {dept: score}
                                self.add_hint(hierarchy, dept)
                                stop = True
                                break
            if stop:
                break
        if depts:
            dept = self.guess_department(depts)
            logger.debug('Matched to {}'.format(self.depts[dept]))
            return dept
        # Check keyword lists for biological collections
        dept, match = self.match_dept_keywords(text, i=3)
        if dept:
            return dept


    def add_hint(self, hierarchy, dept):
        # Add order and family to hints
        for rank in ['phylum', 'order', 'suborder', 'family']:
            try:
                name = hierarchy[rank].lower()
            except KeyError:
                pass
            else:
                if name not in ['arthropoda', 'chordata']:
                    self.hints[name] = dept
                    with open('hints.json', 'w') as f:
                        json.dump(self.hints, f, indent=4, sort_keys=True)
                    msg = 'Added {}={} to hints'.format(name, dept)
                    logger.debug(msg)


    def get_department_from_taxa(self, taxa):
        if any(taxa):
            taxa = list(set(taxa))
            for taxon in taxa[:]:
                try:
                    genus, _ = taxon.split(' ')
                except ValueError:
                    pass
                else:
                    if len(genus.strip('.')) > 1:
                        taxa.append(genus)
            return self.lookup.get_department(sorted(set(taxa)))
