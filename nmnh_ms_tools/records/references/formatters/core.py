import csv
import json
import os
import re

import inflect
from nltk.corpus import stopwords as nltk_stopwords
from unidecode import unidecode

from nmnh_ms_tools.config import DATA_DIR
from nmnh_ms_tools.utils import AbbrDict



def _load_stopwords(langs):
    words = {}
    for abbr, lang in langs.items():
        try:
            for word in nltk_stopwords.words(lang):
                words.setdefault(word, []).append(abbr)
        except OSError:
            pass
    return {k: set(v) for k, v in words.items()}


def issn_abbrs_to_json(fp):
    """Updates global abbreviation file"""

    abbrs = {}
    with open(fp, "r", encoding="utf-8") as f:
        rows = csv.reader(f, delimiter="\t")
        keys = next(rows)
        for row in rows:
            word, abbr, langs = row
            word = unidecode(word.lower())
            abbr = unidecode(abbr.lower())
            langs = langs.split(', ')
            if abbr == "n.a.":
                abbr = None
            abbrs.setdefault(word, []).append([abbr, langs])

    json_path = os.path.join(DATA_DIR, "issn", "issn_abbrs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(abbrs, f, indent=2, sort_keys=True)




class BaseFormatter:
    with open(os.path.join(DATA_DIR, "issn", "issn_abbrs.json"), "r", encoding="utf-8") as f:
        abbrs = AbbrDict(json.load(f))

    # Maps ISSN language abbrebiations to full names
    languages = {
        "aze": "azerbaijani",
        "dan": "danish",
        "dut": "dutch",
        "eng": "english",
        "fin": "finnish",
        "fre": "french",
        "ger": "german",
        "gre": "greek",
        "hun": "hungarian",
        "ind": "indonesian",
        "ita": "italian",
        "kaz": "kazakh",
        "nor": "norwegian",
        "por": "portuguese",
        "rus": "russian",
        "slo": "slovene",
        "spa": "spanish",
        "swe": "swedish",
        "tur": "turkish",
        "mul": "multiple",
    }

    stopwords = _load_stopwords(languages)



    def __init__(self, reference):
        self.reference = reference
        self.default_langs = {"eng", "fre", "ger", "ita", "spa"}


    def iso_4_title(self, publication=None):
        """Formats title using a loose interpreation of the ISO 4 standard"""
        if publication is None:
            publication = self.reference.title

        # Split into words and remove diacritcs
        words = []
        for word in re.split(r"-?\W+", publication):
            if word.isupper() or len(word) > 2:
                word = unidecode(word.lower()) if not word.isupper() else word
                words.append(word)

        # Do not abbreviate one-word titles
        if len(words) == 1:
            return words[0].title()

        # Check if publication is already abbreviated
        if self.abbrs.is_abbreviation(words):
            return " ".join([f"{w.capitalize()}" for w in words])

        # Guess most likely language based on how abbreviations resolve
        langs = {}
        for word in words:
            try:
                _langs = []
                for _, lang in self.abbrs[word]:
                    _langs.extend(lang)
                _langs = set(_langs)
            except KeyError:
                _langs = self.stopwords.get(word, [])
            finally:
                # Each group includes the languages where the given
                # word is either an abbreviation or a stopword
                for lang in _langs:
                    if lang != "mul":
                        try:
                            langs[lang.strip()] += 1 / len(_langs)
                        except KeyError:
                            langs[lang.strip()] = 1 / len(_langs)

        # Get the stopwords for each possible language
        all_langs = set(langs)
        if all_langs:
            langs = {k for k, v in langs.items() if v == max(langs.values())}
        else:
            langs = self.default_langs
        langs.add("mul")
        stopwords = {w for w, l in self.stopwords.items() if l & langs}

        # Resolve abbreviations using common language
        abbrs = []
        for word in words:

            # Include all-caps words as-is
            if word.isupper():
                abbrs.append(word)
            else:

                # Use the singular form of the word
                singular = inflect.engine().singular_noun(word)
                if singular:
                    word = singular

                # Look for abbreviations in the determined language
                try:
                    matches = self.abbrs[word]

                    # Refine match by language is multiple abbreviations
                    if len({m[0] for m in matches}) > 1:
                        matches = [m for m in matches if set(m[1]) & langs]

                    abbr = [m[0] for m in matches][0]
                except IndexError:
                    print(f"'{word}' not found in {langs}")
                except KeyError:
                    # Include the full word if not a stopword
                    if word not in stopwords:
                        abbrs.append(word.title())
                else:
                    if abbr and abbr.rstrip(".").lower() == word.lower():
                        abbr = abbr.rstrip(".")
                    # Include abbrviation if given or as-is if null
                    if abbr:
                        abbrs.append(abbr.title())
                    else:
                        abbrs.append(word.title())

        return " ".join(abbrs)
