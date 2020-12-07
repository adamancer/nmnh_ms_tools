import logging
from collections import namedtuple

from nltk.corpus import stopwords

from ...utils.lists import oxford_comma
from ...utils.strings import to_attribute




logger = logging.getLogger(__name__)
logger.debug('Loading link.py')




ENDINGS = [
    'idae',
    'ian',
    'ide',
    'ine',
    'ia',
    'us',
    's',
    'a',
    'e'
]
REPLACEMENTS = {
    'aeo': 'eo',  # archaeo
    'usc': 'usk'  # mollusk
}
STOPWORDS = [
    'above',
    'along',
    'animalia',
    'beach',
    'boundary',
    'coast',
    'collection',
    'confluence',
    'county',
    'creek',
    'district',
    'early',
    'eastern',
    'family',
    'formation',
    'harbor',
    'indet',
    'island',
    'late',
    'locality',
    'lower',
    'member',
    'middle',
    'mountain',
    'national',
    'north',
    'northern',
    'northeast',
    'northeastern',
    'northwest',
    'northwestern',
    'genus',
    'group',
    'present',
    'province',
    'ridge',
    'river',
    'slide',
    'slope',
    'south',
    'southern',
    'southeast',
    'southeastern',
    'southwest',
    'southwestern',
    'sp',
    'specimen',
    'unknown',
    'upper',
    'valley',
    'western',
    # COLORS
    'blue',
    'green',
    'red',
    'yellow',
    'white',
    'black'
    ]
STOPWORDS.extend(stopwords.words('english'))




class MatchObject:
    """Defines methods to score how well text matches a specimen record"""
    hints = {}

    def __init__(self):
        self.points = 0
        self.penalties = 0
        self.threshold = 1
        self.components = {}


    def __str__(self):
        if self.score <= 1:
            return 'No match'
        matched = []
        only = ''
        count_pos = len([k for k, v in self.components.items() if v > 0])
        for key in self:
            if not key and count_pos == 2:
                only = ' only'
            elif self[key] > 0:
                matched.append(to_attribute(key).replace('_', ' '))
        return 'Matched on {}{}'.format(oxford_comma(sorted(matched)), only)


    def __repr__(self):
        attrs = ['matched', 'score', 'components', 'points', 'penalties']
        ntp = namedtuple(self.__class__.__name__, attrs)
        kwargs = {attr: getattr(self, attr) for attr in attrs}
        return str(ntp(**kwargs))


    def __add__(self, val):
        if val < 0:
            self.penalties += val
        else:
            self.points += val


    def __eq__(self, val):
        return self.score == val


    def __ne__(self, val):
        return self.score != val


    def __gt__(self, val):
        return self.score > val


    def __lt__(self, val):
        return self.score < val


    def __ge__(self, val):
        return self.score >= val


    def __le__(self, val):
        return self.score <= val


    def __getitem__(self, key):
        return self.components[key]


    def __setitem__(self, key, val):
        self.components[key] = val


    def __iter__(self):
        return iter(self.components)


    def __bool__(self):
        return self.matched


    def items(self):
        return self.components.items()


    @property
    def matched(self):
        return self._matched()


    @matched.setter
    def matched(self, _):
        raise AttributeError('Cannot set matched')


    @property
    def score(self):
        return self._score()


    @score.setter
    def score(self, _):
        raise AttributeError('Cannot set score')


    def add(self, name, val):
        """Adds/subtracts given value from the score"""
        try:
            self.components[name] += val
        except KeyError as e:
            self.components[name] = val
        self += val
        return self


    def update(self, score):
        """Updates components dictionary from another score object"""
        for name, val in score.items():
            self.add(name, val)


    def _score(self):
        """Calculates the score of a match"""
        return self.points + self.penalties


    def _matched(self):
        """Calculates whether the score exceeds the threshold (i.e., matches)"""
        return self.score > self.threshold




def filter_specimens(specimens, text, dept=None, taxa=None):
    """Finds the best match in a list of specimens"""
    scores = [s.match_text(text, dept=dept, taxa=taxa) for s in specimens]
    scored = [m for m in zip(specimens, scores) if m[1] > m.threshold]
    if scored:
        max_score = max([m[1] for m in scored])
        return [m for m in scored if m[1] == max_score]
    return []


def validate_dept(dept):
    """Validates and if necessary expands the name of a NMNH department"""
    depts = {
        'an': 'Anthropology',
        'bt': 'Botany',
        'br': 'Vertebrate Zoology: Birds',
        'en': 'Entomology',
        'fs': 'Vertebrate Zoology: Fishes',
        'hr': 'Vertebrate Zoology: Herpetology',
        'iz': 'Invertebrate Zoology',
        'mm': 'Vertebrate Zoology: Mammals',
        'ms': 'Mineral Sciences',
        'pl': 'Paleobiology'
    }
    if dept is not None:
        dept = depts.get(dept.rstrip('*'), dept)
        if dept.rstrip('*') not in list(depts.values()):
            raise ValueError('Bad department: {}'.format(dept))
    return dept
