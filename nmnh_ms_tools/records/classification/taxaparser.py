"""Defines a class for parsing and guessing parent of a rock or mineral name"""

import os
import pprint as pp
import re
from collections import namedtuple

import yaml
from unidecode import unidecode

from ...config import CONFIG_DIR
from ...utils import LazyAttr, slugify


Part = namedtuple("Part", ["word", "stem", "index", "pos", "kind"])
Phrase = namedtuple("Phrase", ["phrase", "taxon", "start", "end"])


class TaxaParser:
    """Analyzes and segments a rock name"""

    # Deferred class attributes are defined at the end of the file
    config = None
    _colors = None
    _modifiers = None
    _textures = None
    _endings = None

    # Populated by get_tree()
    tree = None

    def __init__(self, name):
        if not isinstance(name, str):
            name = str(name)
        if not name:
            name = "Unidentified"
        self.verbatim = name.strip()
        self.name = self.verbatim
        self.host = None
        self.alteration = []
        self.textures = []
        self.colors = []
        self.parts = []
        self.keywords = []
        self.indexed = None
        self.parse()

    def __str__(self):
        return pp.pformat(
            {
                "verbatim": self.verbatim,
                "name": self.name,
                "host": self.host,
                "textures": self.textures,
                "alteration": self.alteration,
                "colors": self.colors,
                "parts": self.parts,
                "keywords": self.keywords,
                "indexed": self.indexed,
            }
        )

    def __repr__(self):
        return pp.pformat(
            {
                "verbatim": self.verbatim,
                "name": self.name,
                "host": self.host,
                "textures": self.textures,
                "alteration": self.alteration,
                "colors": self.colors,
                "parts": self.parts,
                "keywords": self.keywords,
                "indexed": self.indexed,
            }
        )

    def key(self, key=None):
        """Returns a standardized form of the name"""
        if key is None:
            key = self.name
        return slugify(str(key)).replace("_", "-") if key else ""

    def patternize(self, val, **kwargs):
        """Constructs a regex pattern including modifiers"""
        modifiers = "|".join(self._modifiers)
        pattern = rf"\b((({modifiers})[ \-]){{0,4}}{val})\b"
        return re.compile(pattern, **kwargs)

    def parse(self):
        """Parses physical descriptors from a rock name"""
        self.name = self.verbatim.lower()
        self._parse_colors()
        self._parse_textures()
        self._parse_alteration()
        self._parse_stopwords()
        self.parts = self.segment()
        self._parse_keywords()
        self.name = self._clean_name()
        self.indexed = self.name
        if any(self.keywords):
            primary = self.keywords[0]
            associated = self.keywords[1:] if len(self.keywords) > 1 else []
            self.indexed = (f"{"-".join(associated)} {primary}").strip()
        self.indexed = self.key(self.indexed)

    def segment(self):
        """Segments a name into words or phrases"""
        name = unidecode(self.name.lower())
        # Parse mineral varieties
        if re.search(r"\(var", name):
            mineral, variety = [n.strip(" .)") for n in name.split("(var")]
            return [
                self.part(mineral, 0, kind="mineral"),
                self.part(variety, 1, kind="variety"),
            ]
        # Look for multiword names at the beginning of the name
        if self.tree is None:
            self.parts = self.find_simple_names(name)
        else:
            self.parts = self.find_compound_names(name)
        return self.parts

    def find_simple_names(self, name):
        """Splits a name into main name and modifier"""
        name = unidecode(self.name.lower())
        try:
            mod, main = name.rsplit(" ", 1)
        except ValueError:
            return self.construct_parts([name])
        return self.construct_parts([mod, main])

    def find_compound_names(self, name):
        """Splits a list of words while looking for multiword names"""
        name = unidecode(self.name.lower())
        words = self.split(name)
        # Look for multiword names at the beginning of the name
        from_start = [" ".join(words[: x + 1]) for x in range(len(words) - 1)]
        startswith = []
        for phrase in from_start:
            try:
                taxon = self.tree.find_one(phrase)
            except KeyError:
                pass
            else:
                startswith.append(Phrase(phrase, taxon, 0, len(phrase)))
        # Look for multiword names at the end of the name
        from_end = [" ".join(words[-(x + 1) :]) for x in range(len(words) - 1)]
        endswith = []
        for phrase in from_end:
            try:
                taxon = self.tree.find_one(phrase)
            except KeyError:
                pass
            else:
                start = len(name) - len(phrase)
                endswith.append(Phrase(phrase, taxon, start, len(name)))
        # Handle overlapping names
        try:
            first, last = self._reconcile_compound_names(startswith, endswith)
        except (AssertionError, ValueError):
            return self.find_simple_names(name)
        if first:
            name = name[len(first) :]
        if last:
            name = name[: -len(last)]
        name = name.strip()
        taxa = [s for s in ([first] + self.split(name) + [last]) if s]
        # If the parsing produces a single result for a string with multiple
        # words, revert to the simple parser. This is intended to catch things
        # like "Basalt breccia" that show up in the tree but (1) are not
        # official names and (2) would be better understood in terms of parts.
        if len(taxa) == 1 and len(words) > 1:
            try:
                taxon = self.tree.find_one(taxa[0])
            except KeyError:
                return self.find_simple_names(name)
        return self.construct_parts(taxa)

    def construct_parts(self, names):
        """Converts a list of words/phrases to parts"""
        main, mod = self.prioritize_names(names)
        # Process main taxon
        parts = [self.part(main, 0)]
        # Process additional taxa
        exclude = ["", "var"] + self._modifiers + self._textures + self._colors
        if isinstance(mod, str):
            mod = re.split(r"\W", mod)
        words = [w for w in mod if not self.key(w) in exclude]
        for i, word in enumerate(words):
            parts.append(self.part(word, i + 1))
        return parts

    def prioritize_names(self, names):
        """Identifies the primary classification"""
        if self.tree and len(names) > 1:
            # Deprioritize less useful taxa
            deprioritize = {
                "breccia",
                "dike rock",
                "dyke rock",
                "lava",
                "nodule",
                "sand",
                "spatter",
                "xenolith",
            }
            if names[-1].lower().replace("-", " ") in deprioritize:
                try:
                    taxon = self.tree.find_one(names[0])
                except KeyError:
                    pass
                else:
                    if not taxon.is_mineral():
                        return names[0], names[1:]
        return names[-1], names[:-1]

    def stem(self, val):
        """Stems a value"""
        # Exclude numerics (e.g., Dana groups)
        if val and val[0].isdigit():
            return val
        # Handle multiword values
        pattern = re.compile(r"([ -])")
        if not isinstance(val, list) and pattern.search(val):
            vals = pattern.split(val)
            for i, word in enumerate(vals):
                if len(word) > 1:
                    stemmed = self.stem(word)
                    if stemmed:
                        vals[i] = stemmed
            return "".join(vals)
        endings = self._endings[:] + [""]
        for ending in endings:
            if val.endswith(ending):
                stem = val[: -len(ending)] if ending else val
                if val != stem:  # and self.find(stem):
                    return stem
        return val

    def compare_to(self, other):
        """Scores the similarity to another name"""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        try:
            words = re.split(r"\W", self.stem(self.verbatim.lower()))
            other = re.split(r"\W", self.stem(other.verbatim.lower()))
        except TypeError:
            words = re.split(r"\W", self.verbatim.lower())
            other = re.split(r"\W", other.verbatim.lower())
        score = len(set(words) & set(other)) / len(set(words + other))
        return score

    def same_as(self, other):
        """Tests if this parse is the same as another"""
        return self.key(self.verbatim) == self.key(other.verbatim)

    def similar_to(self, other):
        """Tests whether this name is similar to another name"""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        return set(self.keywords) == set(other.keywords)

    def part(self, word, index, **kwargs):
        """Constructs a part, referencing the hierarchy if it exists"""
        stem = kwargs.pop("stem", self.stem(word))
        noun_pattern = re.escape(stem) + "[ae]?$"
        part = {
            "word": word,
            "stem": stem,
            "index": index,
            "pos": "noun" if re.match(noun_pattern, word) else "adj",
            "kind": None,
        }
        if self.tree:
            for wordlike in (part["word"], part["stem"]):
                try:
                    taxon = self.tree.find_one(wordlike)
                except KeyError:
                    pass
                else:
                    part["kind"] = taxon.rank
        part.update(**kwargs)
        return Part(**part)

    def parents(self, parts=None):
        """Constructs a list of parents from most to least specific"""
        if parts is None:
            parts = self.parts if self.parts else self.segment()
        parts = [p.stem for p in parts]
        if None in parts:
            return []
        parents = [parts[0]]
        for i in range(len(parts)):
            modifiers = "-".join(parts[1 : i + 2])
            parents.append((f"{modifiers} {parts[0]}").strip())
        parents = [self.key(p) for p in parents]
        parents = [p for p in parents if p != self.indexed]
        parents = [p for i, p in enumerate(parents) if p not in parents[:i]]
        # Remove indexed from parent list unless texutres, etc. were parsed
        if not (self.alteration or self.colors or self.textures):
            parents = [p for p in parents if p != self.indexed]
        parents.sort(key=len, reverse=True)
        return parents

    def parent_key(self, parts=None):
        """Converts a list of parts to a key"""
        if parts is None:
            parts = self.parts if self.parts else self.segment()
        return "|".join([f"{p.index}-{p.stem}" for p in parts])

    @staticmethod
    def split(name):
        """Splits a name based on common delimiters"""
        return name.split(" " if " " in name else "-")

    def _parse_textures(self):
        """Parses texturural terms from a rock name"""
        for texture in self._textures:
            pattern = self.patternize(texture)
            matches = pattern.search(self.name)
            if matches is not None:
                self.name = pattern.sub("", self.name)
                self.textures.append(matches.group())
        self.textures.sort()
        return self

    def _parse_alteration(self):
        """Parses alteration terms from a rock name"""
        pattern = self.patternize(r"\b[a-z]+ized\b", flags=re.I)
        matches = pattern.search(self.name)
        if matches is not None:  # and matches.group() != 'characterized':
            self.name = pattern.sub("", self.name)
            self.alteration.append(matches.group())
        self.alteration.sort()
        return self

    def _parse_colors(self):
        """Parses color terms from a rock name"""
        colors = "|".join(self._colors)
        val = rf"({colors})(([ \-]and[ \-]|-)({colors}))?(?!-)"
        pattern = self.patternize(val)
        matches = pattern.search(self.name)
        if matches is not None:
            self.name = pattern.sub("", self.name)
            self.colors.append(matches.group())
        self.colors.sort()
        return self

    def _parse_stopwords(self):
        """Strips stopwords from a rock name"""
        # Check for stopwords
        self.name = self.name.strip()
        for stopword in self.config["stopwords"]:
            if self.name.startswith(f"{stopword} "):
                self.name = self.name[len(stopword) :].strip()
            if self.name.endswith(f" {stopword}"):
                self.name = self.name[: -len(stopword)].strip()
        # Check for host rock
        pattern = re.compile(r"^([a-z]+)-hosted\b")
        matches = pattern.search(self.name)
        if matches is not None:
            self.name = pattern.sub("", self.name)
            self.host = matches.group(1)
        return self

    def _parse_keywords(self):
        """Parses keywords from a list of parts"""
        keywords = []
        if [p for p in self.parts if p.stem is None]:
            self.keywords = []
            return self
        for part in self.parts:
            keywords.extend([self.stem(kw) for kw in self._kw_split(part.stem)])
        self.keywords = [kw for kw in keywords if kw]
        return self

    def _clean_name(self):
        """Cleans up a name string"""
        self.name = re.sub(r" +", " ", self.name).strip()
        if not self.name:
            self.name = "Unidentified"
        return self.name

    @staticmethod
    def _kw_split(val):
        """Splits known prefixes from a value and rejoins them with a hyphen"""
        prefixes = ["meta"]
        for prefix in prefixes:
            if val.startswith(prefix) and val != prefix:
                val = f"{prefix}-{val[len(prefix) :]}"
        return val.split("-")

    @staticmethod
    def _reconcile_compound_names(startswith, endswith):
        """Reconciles overlapping compound names"""
        while startswith and endswith and startswith[-1].end > endswith[-1].start:
            if startswith[-1].taxon.is_official():
                endswith.pop()
            elif endswith[-1].taxon.is_official():
                startswith.pop()
            else:
                raise ValueError(
                    f"Could not reconcile"
                    f" startswith={[s.phrase for s in startswith]},"
                    f" endswith={[s.phrase for s in endswith]}"
                )
        first = startswith[-1].phrase if startswith else ""
        last = endswith[-1].phrase if endswith else ""
        assert first or last
        return first, last


# Deferred class attributes are defined at the end of the file
LazyAttr(TaxaParser, "config", os.path.join(CONFIG_DIR, "config_classification.yml"))
LazyAttr(
    TaxaParser,
    "_colors",
    lambda: sorted(TaxaParser.config["colors"], key=len, reverse=True),
)
LazyAttr(
    TaxaParser,
    "_modifiers",
    lambda: sorted(TaxaParser.config["modifiers"], key=len, reverse=True),
)
LazyAttr(
    TaxaParser,
    "_textures",
    lambda: sorted(TaxaParser.config["textures"], key=len, reverse=True),
)
LazyAttr(
    TaxaParser,
    "_endings",
    lambda: sorted(TaxaParser.config["endings"], key=len, reverse=True),
)

config = yaml.safe_load(
    open(os.path.join(CONFIG_DIR, "config_classification.yml"), "r")
)
