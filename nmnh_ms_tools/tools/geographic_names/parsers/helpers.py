"""Defines functions to classify/parse features using parser objects"""

import csv
import functools
import logging
import os
import re
from collections import namedtuple
from itertools import combinations

from unidecode import unidecode

from .between import BetweenParser
from .border import BorderParser
from .direction import DirectionParser
from .feature import FEATURES, OF_WORDS
from .measurement import MeasurementParser
from .multifeature import MultiFeatureParser
from .plss import PLSSParser
from .simple import SimpleParser
from .uncertain import UncertainParser
from ....config import DATA_DIR
from ....utils import LocStandardizer, as_str, clock, skip_hashed, std_directions


logger = logging.getLogger(__name__)


Feature = namedtuple("Feature", ["name", "parser"])
STD = LocStandardizer(delim=" ")


@clock
def clean_locality(val):
    """Cleans characters from string that may interfere with parsing"""

    def merge_duplicate_punc(match):
        return match.group().strip()[0]

    if isinstance(val, list):
        return [clean_locality(s) for s in val]
    orig = val
    # Convert uppercase string to title case
    if val.isupper():
        val = val.title()
    # Remove diacritics and strip trailing punctuation
    val = unidecode(val).strip(" ,;:|").strip('"').rstrip(".")
    delim = get_delim(val)
    # Remove multiple spaces
    val = re.sub(r"\s+", " ", val)
    # Remove double hyphens
    val = re.sub(r"(?<=[a-z])(-+)(?=[a-z])", "-", val, flags=re.I)
    # Space hyphens if a space on either side
    val = re.sub(r"((?<! )(- )|( -)(?! ))", " - ", val)
    # Remove backticks and possessive apostrophes
    val = re.sub(r"(?<=[a-z])`(?=[a-z])", "", val)
    val = re.sub(r"[`']([a-z]\b)", r"\1", val)
    # Standardize question marks
    val = re.sub(r"( *(\?|\( *\? *\)|\[ *\? *\]))", "?", val)
    # Standardize compass directions
    val = std_directions(val)
    # Remove thousands separators from numbers
    val = re.sub(r"(\d),(\d\d\d)\b", r"\1\2", val)
    # Add delimiter in front of off
    pattern = r"(?<![Dd]rop|[Tt]urn)[- ]([Oo]ff [A-Z][a-z]+)"
    val = re.sub(pattern, delim + r" \1", val)
    # Expand national parks, forests, etc.
    val = re.sub(r"\bNatl\b", "National", val)
    val = re.sub(r"\bN[\. ]*P\.?\b", "National Park", val)
    val = re.sub(r"\bNational For\.?\b", "National Forest", val)
    val = re.sub(r"\b[Cc](?:irc)?a?\.? (\d)", r"\1", val)
    # Expand common abbreviations
    val = debreviate(val)
    # Interpret periods as either delimiters or signaling abbreviations
    val = deperiod(val)
    # Convert n' to n ft
    val = re.sub(r"(\d)\'(\s)", r"\1 ft\2", val)
    # Remove extraneous whitespace and punctuation
    val = re.sub(r"\s+", " ", val)
    val = re.sub(r"( *[|,;:]+){1,}", merge_duplicate_punc, val).strip()
    return val


def debreviate(val):
    """Expands common abbreviations in a string"""
    """
    repls = {
        'approx': 'approximately',
        #'archipel': 'Archipelago',  # interferes with French names
        'cr': 'Creek',
        'dept': 'Department',
        'depto': 'Departmento',
        'dpto': 'Departmento',
        'dist': 'District',
        'distr': 'District',
        'div': 'Division',
        'jct': 'junction',
        'i': 'Island',
        'id': 'Island',
        'is': 'Island',
        'isld': 'Island',
        'mpio': 'Municipio',
        'mun': 'Municipio',
        'prov': 'Province',
        'pt': 'Point',
        'quad': 'Quadrangle',
        #'r': 'River',   # interferes with PLSS parsing
        'rr': 'Railroad',
        'sta': 'Station'
    }
    for find, repl in repls.items():
        val = re.sub(rf'\b{find}\b', repl, val, flags=re.I)
    val = re.sub('department de', 'Departmento de', val, flags=re.I)
    val = re.sub('province de', 'Provincia de', val, flags=re.I)
    """
    # Expand wacky "c." abbreviation for circa
    val = re.sub(r"\bc(?=\.? \d)", "ca", val)
    return val


def deperiod(val, parsers=None):
    """Interprets periods found in a string"""
    if parsers is None:
        parsers = [
            PLSSParser,
            DirectionParser,
            BetweenParser,
            BorderParser,
            MeasurementParser,
            MultiFeatureParser,
        ]
    delim = get_delim(val)
    # Commas are treated as a weak delimiter for things like direction parsing,
    # so replace periods with semicolons if the string uses commas
    if delim == ",":
        delim = ";"
    # Remove periods before question marks
    val = re.sub(r"\.(?= *\(?\?\)?)", "", val, flags=re.I)
    # Add space after non-decimal periods
    val = re.sub(r"(?<=[a-z])\.(?! )", ". ", val, flags=re.I)
    val = re.sub(r"(\b[a-z]{2,3})\.( \d)", r"\1\2", val, flags=re.I)
    # Remove periods before common prepositions
    val = re.sub(r"\.(?= (of|de|du|d|to)\b)", "", val, flags=re.I)
    # Remove periods before end parentheses or brackets
    val = re.sub(r"\.(?=[\)\]])", "", val)
    # Handle periods associated with St or Mt
    pattern = r"(?:[-A-z0-9]+?)?[ \b][SM]t\. [A-Z][a-z]+"
    for match in re.findall(pattern, val):
        if re.match(r"[SM]t\.", match) or not re.match(r"[A-Z]", match):
            val = val.replace(match, match.replace("t.", "t"), 1)
        else:
            val = val.replace(match, match.replace("t.", "t" + delim), 1)
    # Add leading zero to decimals
    val = re.sub(r"(?<!\d)(\.)(?=\d)", r"0\1", val)
    # Remove periods adjacent to other punctuation
    val = re.sub(r"\.([,;:\|\-])", r"\1", val)
    val = re.sub(r"([,;:\|\-])\.", r"\1", val)

    val = re.sub(r"(approx\.?)(?= \d)", "approx", val, flags=re.I)
    val = re.sub(r"(elev\.?)(?= \d)", "elev", val, flags=re.I)

    # Split string on non-decimal periods
    vals = []
    for val in re.split(r"(?<![ \d])\.(?!\d)", val):
        if val.lower() in ABBREVIATIONS:
            vals.append(val)
        elif re.split(r"\W", val)[-1].lower() in ABBREVIATIONS:
            for parser in parsers:
                try:
                    parser(re.split(r"[;,:]", val)[-1])
                    vals.append(val + delim)
                    break
                except ValueError:
                    pass
            else:
                vals.append(val)
        else:
            vals.append(val + delim)
    val = "".join(vals).strip(delim + " ")
    return val


def get_delim(val, options="|;,:", default=";"):
    """Identify a delimiter to use to rejoin string"""
    for delim in options:
        if delim in val:
            return delim
    else:
        return default


def split_localities(vals, **kwargs):
    """Splits a string using common delimiters"""
    if isinstance(vals, list):
        parts = []
        for val in vals:
            parts.extend(split_localities(val))
        return parts
    vals = clean_locality(vals)
    delim = r"([,;:\|]|(?<!\d)\.|\.(?!\d))"
    # Adjust delimiter if both comma and semicolon found
    if "," in vals and ";" in vals:
        delim = delim.replace(",", "", 1)
    delim = re.compile(delim, flags=re.I)
    vals = delim.split(vals, **kwargs)
    return vals


@clock
@functools.lru_cache()
def parse_localities(val, parsers=None, split_phrases=True):
    """Parses individual localities from a complex string"""

    if parsers is None:
        parsers = [
            PLSSParser,
            DirectionParser,
            BetweenParser,
            MeasurementParser,
            MultiFeatureParser,
        ]
    if not val:
        return []
    if isinstance(val, list):
        localities = []
        for val in val:
            localities.extend(parse_localities(val, parsers))
        return localities
    punc = (",", ";", ":", ".", "|", " -", "- ", " /", "/ ")
    w_parens = tuple(list(punc) + ["(", ")"])  # add parens for bound tests
    puncs = "".join(set(punc))
    # Clean and split string
    val = clean_locality(val)
    if not val:
        return []

    if not split_phrases:
        phrases = [val]
    else:
        pattern = r"(\d+(?:\.\d+)|[A-Za-z0-9_\-\']+|(,|;|:|\.|&|\|| / | -|- )])"
        words = [w for w in re.split(pattern, val) if w]
        if len(words) == 1:
            phrases = words[:]
        else:
            # Group variants on a single phrases by stripping punctuation (but
            # preserve the punctuation so it can help split off phrases later)
            grouped = {}
            for i, j in combinations([i for i, _ in enumerate(words)], 2):
                phrase = "".join(words[i : j + 1]).strip()
                grouped.setdefault(phrase.strip(puncs), []).append(phrase)
            # Keep the longest variant on each phrase
            phrases = []
            for vals in grouped.values():
                vals.sort(key=len)
                phrases.append(vals[-1])
            # Sort by length, then move phrases with internal punctuation to end
            phrases = list(set(phrases))
            phrases.sort(key=len, reverse=True)
            for phrase in phrases[:]:
                if set(phrase.strip(puncs)).intersection(set(punc)):
                    phrases.append(phrases.pop(phrases.index(phrase)))
        # The full string always goes first
        phrases.insert(0, phrases.pop(phrases.index(val)))

    localities = {}
    for phrase in phrases:
        logger.debug(f"Parsing {repr(phrase)}")
        orig = phrase
        phrase = phrase.rstrip("?")
        # Get original indices and bounds
        i = val.index(phrase)
        j = i + len(phrase)
        lbound = i == 0 or phrase.startswith(w_parens)
        rbound = j == len(val) or phrase.endswith(w_parens)
        # Recalculate indices without punctuation
        if not re.search(r"\(.*?\)", phrase):
            phrase = phrase.strip(puncs + "()")
        else:
            phrase = phrase.strip(puncs)
        i = val.index(phrase)
        j = i + len(phrase)

        if False:
            print(orig, i, j, lbound, rbound)
            for k, v in localities.items():
                print("+", k)
            print("-" * 40)

        # Only check single words bounded by punctuation or string boundaries
        if split_phrases:
            one_word = re.match(r"^[A-z\-]+$", phrase.strip())
            if one_word and not (lbound and rbound):
                continue
        for parser in parsers:
            try:
                parsed = parser(phrase)
                # PLSS strings have a lot of internal punctuation and the
                # individual components look like route names. As a
                # workaround, always treat PLSS as bound on both sides.
                if parser.kind == "plss":
                    lbound = True
                    rbound = True
                if not parsed.unconsumed and not _overlaps(
                    i, j, lbound, rbound, localities
                ):
                    logger.debug(f"{repr(phrase)} parsed by {parser}")
                    if "?" in orig:
                        parsed = UncertainParser(parsed)
                    localities[(i, j, lbound, rbound)] = parsed
                    break
                raise ValueError("Overlaps better matches")
            except Exception as e:
                # Suppress parsing errors
                if not str(e).startswith(("Could not parse", "Overlaps")):
                    logger.debug("Parsing error: " + phrase, exc_info=e)

    if not localities:
        logger.debug(f"Could not extract features from {repr(val)}")
        try:
            return [SimpleParser(val)]
        except Exception as e:
            if "Could not parse" not in str(e):
                logger.debug("Parsing error: " + val, exc_info=e)
                return []

    # Remove non-localities
    ignore = {"measurement"}
    localities = {k: v for k, v in localities.items() if v.kind not in ignore}

    # Reorder entities to match original string
    ordered = {}
    for loc in localities.values():

        # Filter out Locality Key
        if loc.verbatim.lower() == "locality key":
            continue

        # Strip trailing question mark from uncertain localities
        verbatim = loc.verbatim
        if isinstance(loc, UncertainParser):
            verbatim = verbatim.rstrip("?")

        assert verbatim in val, f"'{verbatim}' not found in '{val}'"
        ordered[val.index(verbatim)] = loc
    localities = [ordered[k] for k in sorted(ordered.keys())]
    logger.debug(f"Extracted {len(localities)} features from {repr(val)}")

    # Remove non-localities
    return localities


def get_proper_names(val, *args, **kwargs):

    # Parse localities if string given
    if isinstance(val, str):
        val = parse_localities(val, *args, **kwargs)

    # Construct pattern to catch generic names at beginning/end of each value
    features = list(FEATURES) + OF_WORDS
    features.extend([f"{f}s" for f in features])
    features = sorted(features, key=lambda w: -len(w))
    pattern = r"(^({0})\b|\b({0})$)".format("|".join(features))

    # Get list of features with generic feature names removed
    names = []
    for loc in val:
        name = re.sub(r"[\(\){}]", "", loc.feature.strip('"'))
        name = re.sub(pattern, "", name, flags=re.I).strip()
        if name:
            names.append(name)
    return names


def get_leftover(val, features=None):
    """Gets data leftover after parsing"""
    if features is None:
        features = parse_localities(val)
    leftover = as_str(clean_locality(val))
    for feature in features:
        leftover = leftover.replace(clean_locality(feature.verbatim), "")
    leftover = leftover.strip(",;:./|- ")
    return leftover


def _overlaps(i, j, lbound, rbound, indexes):
    """Tests if index overlaps ranges that have already been found"""
    overlaps = False
    keys = []
    for ix, jx, lboundx, rboundx in indexes.keys():
        # Supersede shorter strings found earlier. Bounded strings supersede
        # unbounded strings, longer strings supersede shorter strings.
        if (
            i <= ix
            and j > jx
            and (rbound or not rboundx)
            or j >= jx
            and i < ix
            and (lbound or not lboundx)
        ):
            keys.append((ix, jx, lboundx, rboundx))
        elif ix <= i <= jx or ix <= j <= jx:
            overlaps = True
    for key in keys:
        del indexes[key]
    return overlaps and not keys


def read_abbreviations(fp=None):
    """Reads common place name abbreviations from a file"""
    if fp is None:
        fp = os.path.join(DATA_DIR, "geonames", "place_name_abbreviations.csv")
    abbr = []
    with open(fp, "r", encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(skip_hashed(f), dialect="excel")
        keys = next(rows)
        for row in rows:
            rowdict = dict(zip(keys, row))
            if rowdict["soft_delimiter"] == "TRUE":
                abbr.append(rowdict["word"])
    return set(abbr)


ABBREVIATIONS = read_abbreviations()
