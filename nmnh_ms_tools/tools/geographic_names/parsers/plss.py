"""Defines methods for parsing and geolocating PLSS localities"""

import logging
import re

from .core import Parser


logger = logging.getLogger(__name__)


class PLSSParser(Parser):
    """Parses and formats PLSS locality from a string"""

    kind = "plss"
    attributes = [
        "kind",
        "verbatim",
        "unconsumed",
        "feature",
        "twp",
        "rng",
        "sec",
        "qtr",
        "boxes",
    ]
    quote = True

    def __init__(self, *args, **kwargs):
        self.state = None
        self.twp = None
        self.rng = None
        self.sec = None
        self.qtr = None
        self.boxes = []
        # Define patterns used to identify and parse PLSS patterns
        bad_prefixes = r"((loc)|(hole)|(hwy)|(quads?:?)|(us)|#)"
        centers = r"(cen\.?(ter)?)"
        quarters = (
            r"(([NS][EW] *((1?/4)|(cor\.?(ner)?|(q(uarter)?)))?" r"( of)?)(?![c0-9]))"
        )
        halves = r"([NSEW] *((1?/[23])|half))"
        townships = r"(((T(ownship)?\.? *)?[0-9]{1,3} *[NS])\.?(?![NSEW]))"
        ranges = r"(((R(ange)?\.? *)?[0-9]{1,3} *[EW])\.?(?![NSEW]))"
        sections = (
            r"((?<!/)(((((s(ection)?)|(se?ct?s?))\.? *)"
            r"|\b)[0-9]{1,3})(?!(-\d+[^NEWS]|\.\d)))"
        )
        # Define quarter section
        qtr = (
            r"\b((((N|S|E|W|NE|SE|SW|NW)[, \-]*)"
            r"((cor\.?|corner|half|q(uarter)?|(1?/[234]))"
            r"[, /\-]*(of *)?)?)+)\b"
        )
        qtr_sections = (
            r"((|[0-9]+){0}|{0}(?:(sec|[0-9]+[, /\-]" r"|T\.? *[0-9]|R\.? *[0-9])))"
        ).format(qtr)
        # Create full string baed on patterns
        pattern = [bad_prefixes, centers, quarters, halves, townships, ranges, sections]
        combined = r"|".join(["(" + s + r"[,;: /\.\-]*" + ")" for s in pattern])
        full = r"\b((" + combined + r")+)\b"
        # Define attributes for each pattern
        self._sec_twn_rng = re.compile(full, re.I)
        self._townships = re.compile(townships, re.I)
        self._ranges = re.compile(ranges, re.I)
        # self._sections = re.compile(sections + '[^\d]', re.I)
        self._sections = re.compile(sections, re.I)
        self._quarter_sections = re.compile(qtr_sections, re.I)
        self._bad_prefixes = re.compile(bad_prefixes + " ?[0-9]+", re.I)
        super(PLSSParser, self).__init__(*args, **kwargs)

    def name(self):
        """Returns a string describing the parsed locality"""
        qtr = " ".join(self.qtr)
        feature = " ".join([qtr, self.sec, self.twp, self.rng]).strip()
        return '"{}"'.format(feature)

    def parse(self, text):
        """Parse section-township-range from a string"""
        if not self.is_plss_string(text):
            raise ValueError('Could not parse "{}" (not PLSS)'.format(text))
        self.verbatim = text
        matches = [
            m[0]
            for m in self._sec_twn_rng.findall(text)
            if "n" in m[0].lower() or "s" in m[0].lower()
        ]
        msg = None
        first_match = None
        # Iterate through matches, longest to shortest
        for match in sorted(matches, key=lambda s: len(s), reverse=True):

            # Strip bad prefixes (hwy, loc, etc.) that can be mistaken for
            # section numbers
            match = self._bad_prefixes.sub("", match)
            verbatim = self._format_verbatim(match)

            # Clean up match to make parsing quarter sections easier
            pattern = r"\b([TR])\.? *(\d{1,2})\.? *([NSEW])\.?"
            match = re.sub(pattern, r"\1\2\3", match, flags=re.I)

            # Parse the string
            self.twp = self._format_township(match)
            self.rng = self._format_range(match)
            self.sec = self._format_section(match)
            self.qtr = self._format_quarter_section(match)

            # Catch bad parses where the number components of each part
            # are more than three digits long
            for part in (self.twp, self.rng, self.sec):
                if re.search(r"\d{3,}", part):
                    break
            else:
                self.specific = True
                logger.debug('Parsed "{}"'.format(text))
                return self

        raise ValueError('Could not parse "{}"'.format(text))

    def is_plss_string(self, val):
        """Tests if the given value is a clean PLSS string"""
        try:
            plss = self._sec_twn_rng.match(val).group()
            if self._bad_prefixes.search(plss):
                return False
            return True
        except AttributeError:
            return False

    def _format_verbatim(self, match):
        """Formats the verbatim string containing a PLSS locality"""
        cleaned = self._townships.sub("", match)
        cleaned = self._ranges.sub("", cleaned)
        matches = self._sections.findall(match)
        if matches:
            sec = sorted([val[0] for val in matches], key=len, reverse=True)[0]
            cleaned = cleaned.replace(sec, "")
        cleaned = self._quarter_sections.sub("", cleaned)
        cleaned = cleaned.strip(" ,;.")
        return match.replace(cleaned, "").strip(" ,;.")

    def _format_township(self, match):
        """Formats township as T4N"""
        sre_match = self._townships.search(match)
        val = None
        if sre_match is not None:
            val = sre_match.group(0)
            twp = "T" + val.strip("., ").upper().lstrip("TOWNSHIP. ")
            return twp
        mask = "Could not parse: {} (township={})"
        raise ValueError(mask.format(val, match))

    def _format_range(self, match):
        """Formats range as R4W"""
        sre_match = self._ranges.search(match)
        val = None
        if sre_match is not None:
            val = sre_match.group(0)
            rng = "R" + val.strip("., ").upper().lstrip("RANGE. ")
            return rng
        mask = "Could not parse: {} (range={})"
        raise ValueError(mask.format(val, match))

    def _format_section(self, match):
        """Formats section as Sec. 30"""
        # Format section. This regex catches some weird stuff sometimes.
        matches = self._sections.findall(match)
        sec = None
        if matches:
            sec = sorted([val[0] for val in matches], key=len, reverse=True)[0]
            sec = "Sec. " + sec.strip("., ").upper().lstrip("SECTION. ")
            return sec
        mask = "Could not parse: {} (section={})"
        raise ValueError(mask.format(sec, match))

    def _format_quarter_section(self, match):
        """Formats quarter section as NW SE NE"""
        matches = self._quarter_sections.findall(match)
        if len(matches) == 1:
            qtrs_1 = [val[0] for val in matches if val[0]]
            qtrs_2 = [val for val in matches if "/" in val]
            qtrs = [qtrs for qtrs in (qtrs_1, qtrs_2)]
            try:
                qtr = qtrs[0][0]
            except IndexError:
                # Not an error. Quarter section is not required
                pass
            else:
                # Clean up strings that sometimes get caught by this regex
                qtr = (
                    qtr.upper()
                    # .replace(' ', '')
                    .replace(",", "")
                    .replace("QUARTER", "")
                    .replace("CORNER", "")
                    .replace("COR", "")
                    .replace("HALF", "2")
                    .replace("SEC", "")
                    .replace("1/4", "")
                    .replace("1/", "")
                    .replace("/2", "2")
                    .replace("/3", "3")
                    .replace("/4", "")
                    .replace("OF", "")
                    .replace("Q", "")
                    .replace(".", "")
                )
                # If no illegal characters, return list of quarter sections
                if not qtr.strip("NEWS23 "):
                    return qtr.strip().split()
            mask = "Could not parse: {} (quarter section={})"
            raise ValueError(mask.format(match, matches))
        return []
