import logging
from collections import namedtuple

from nltk.corpus import stopwords

from ..geographic_names.parsers.feature import FEATURES, OF_WORDS
from ...utils.lists import oxford_comma


logger = logging.getLogger(__name__)
logger.debug("Loading link.py")


ENDINGS = ["idae", "ian", "ide", "ine", "ia", "us", "s", "a", "e"]

REPLACEMENTS = {"aeo": "eo", "usc": "usk"}  # archaeo  # mollusk

STOPWORDS = [
    "above",
    "along",
    "animalia",
    "boundary",
    "collection",
    "confluence",
    "early",
    "east",
    "eastern",
    "family",
    "formation",
    "group",
    "harbor",
    "indet",
    "isla",
    "late",
    "locality",
    "member",
    "nacional",
    "national",
    "north",
    "northern",
    "northeast",
    "northeastern",
    "northwest",
    "northwestern",
    "genus",
    "group",
    "present",
    "slide",
    "south",
    "southern",
    "southeast",
    "southeastern",
    "southwest",
    "southwestern",
    "sp",
    "species",
    "specimen",
    "unknown",
    "west",
    "western",
    # STRAT
    "lower",
    "upper",
    "early",
    "late",
    "mid",
    "middle",
    # COLORS
    "black",
    "blue",
    "green",
    "orange",
    "purple",
    "red",
    "violet",
    "yellow",
    "white",
    # TAXA
    "animalia",
    "chordata",
    "vertebrata",
    "synapsida",
]
STOPWORDS.extend(stopwords.words("english"))
STOPWORDS.extend(stopwords.words("spanish"))
STOPWORDS.extend(FEATURES)
STOPWORDS.extend(OF_WORDS)


class MatchObject:
    """Defines methods to score how well text matches a specimen record"""

    hints = {}

    def __init__(self, source=None, text=None):
        self.source = source
        self.text = text
        self.record = None
        self.points = 0
        self.penalties = 0
        self.threshold = 1
        self.components = {}

    def __str__(self):
        if not self:
            return "No match"
        if not self.components:
            return "Matched {}".format(self.source)

        # Look for public fields that have been matched
        matched = []
        for key, val in self.items():
            if self[key] > 0 and not key.startswith("_"):
                matched.append(key)

        # Add "only" keyword if match is on a single public field
        only = " only" if len(matched) == 1 else ""

        mask = "Matched {} on {}{}" if self.source else "Matched on {1}{2}"
        return mask.format(self.source, oxford_comma(sorted(matched)), only)

    def __repr__(self):
        attrs = ["score", "threshold", "components", "points", "penalties"]
        ntp = namedtuple(self.__class__.__name__, attrs)
        kwargs = {attr: getattr(self, attr) for attr in attrs}
        return str(ntp(**kwargs))

    def __add__(self, val):
        if val < 0:
            self.penalties += val
        else:
            self.points += val
        return self

    def __sub__(self, val):
        if val > 0:
            self.penalties -= val
        else:
            self.points -= val
        return self

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
        return self.score > self.threshold

    def __len__(self):
        return len(self.components)

    def items(self):
        return self.components.items()

    @property
    def score(self):
        return self._score()

    @score.setter
    def score(self, _):
        raise AttributeError("Cannot set score")

    def add(self, name, val):
        """Adds/subtracts given value from the score"""
        try:
            self.components[name] += val
        except KeyError:
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


class MatchMaker(list):
    def __init__(self):
        self.threshold = 1

    def __str__(self):
        if not self:
            return "No match"

        # Since we're interested in combining multiple contexts, include all
        # scores with positive values, not just those that exceed the
        # threshold for that particular match. To keep the individual matches
        # valid while generating the match strings, set the threshold for
        # each match to zero, then restore it once the string has been created.
        matches = []
        for match in self:
            threshold = match.threshold
            match.threshold = 0
            if match:
                matches.append(lcfirst(str(match)) if matches else str(match))
            match.threshold = threshold

        return oxford_comma(matches, delim="; ")

    def __bool__(self):
        return self.score >= self.threshold

    @property
    def record(self):
        if len({m.record.occurrence_id: m.record for m in self}) != 1:
            raise ValueError("MatchMaker includes multiple different records!")
        return self[0].record

    @property
    def score(self):
        return self._score()

    @score.setter
    def score(self, _):
        raise AttributeError("Cannot set score")

    def add(self, source, text, score=1):
        match = MatchObject(source, text)
        match.points += score
        self.append(match)

    def _score(self):
        score = 0
        for item in self:
            score += item.points - item.penalties
        return score


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
        "an": "Anthropology",
        "bt": "Botany",
        "br": "Vertebrate Zoology: Birds",
        "en": "Entomology",
        "fs": "Vertebrate Zoology: Fishes",
        "hr": "Vertebrate Zoology: Amphibians & Reptiles",
        "iz": "Invertebrate Zoology",
        "mm": "Vertebrate Zoology: Mammals",
        "ms": "Mineral Sciences",
        "pl": "Paleobiology",
    }
    if dept is not None:
        dept = depts.get(dept.rstrip("*"), dept)
        if dept.rstrip("*") not in list(depts.values()):
            raise ValueError("Bad department: {}".format(dept))
    return dept
