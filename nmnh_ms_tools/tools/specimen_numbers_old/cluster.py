"""Defines functions to cluster and expand catalog numbers found by regex"""

import functools
import logging
import os
import re

import yaml

from .utils import combine_vals, is_spec_num, parse_spec_num
from ...config import CONFIG_DIR
from ...utils import as_list


logger = logging.getLogger(__name__)
logger.debug("Loading cluster.py")


class Cluster:
    """Clusters ranges of catalog numbers"""

    def __init__(self, from_ocr=False):
        fp = os.path.join(CONFIG_DIR, "config_specimen_numbers.yml")
        with open(fp, "r") as f:
            self.regex = yaml.safe_load(f)
        self.regex["catnum"] = self.regex["catnum"].format(**self.regex)
        self.mask = re.compile(self.regex["mask"].format(**self.regex))
        self.simple = re.compile(self.regex["simple"])
        self.discrete = re.compile(self.regex["discrete_mask"].format(**self.regex))
        self.suf_range = re.compile(
            r"(([A-z])" + self.regex["join_range"].format(**self.regex) + r"([A-z]))"
        )
        self.range = re.compile(self.regex["range_mask"].format(**self.regex))
        self.code = ""
        self.codes = [s.strip() for s in self.regex["code"].strip("()").split("|")]
        self.metadata = []
        self.from_ocr = from_ocr

        # A valid last number is any catalog number, suffix, or range. However,
        # the regexes defined in 'regex'.yml are less selective than is needed
        # here. We'll limit a "good" value to a subset of high-quality matches.
        catnum = r"([A-Z]{1,3} ?\d{2,6}|\d{4,6})"
        self.p_catnum = r"^{catnum}(-{catnum})?$".format(catnum=catnum)
        # self.p_catnum = r'^([A-Z]{1,3} ?)?\d{4,6}((-[A-Z]{1,3} ?)?\d{4,6})?$'
        self.p_suffix = r"^(\d{1,4}|[a-z](-[a-z]|[a-z]+)|[a-z]\d|\d[a-z])$"
        self.p_alpha_suffix = r"^([a-z](-[a-z]|[a-z]+)?|[a-z]\d|\d[a-z])$"

    @functools.lru_cache()
    def cluster(self, val, minlen=4, maxlen=6, related=None):
        """Clusters related digits to better resemble catalog numbers"""
        if re.search(r"^[a-zA-Z \-]$", val):
            logger.debug("Cluster aborted: Value is alpha")
            return val

        orig = val

        # Set related after the parts check to avoid breaking the cache
        if related is None:
            related = []

        # Format string to simplify matches
        callback = lambda match: match.group(1).lower().strip(" -")
        val = re.sub(r"-? ?([A-z], ?[A-z](, ?[A-Z]))", callback, val)

        # Treat ampersand as a hard delimiter
        val = re.sub(r" *& *", "; ", val)

        # Check if all numbers are followed by one or more spaces
        if len(re.findall(r"\d ", val)) == len(re.findall(r"\d", val)):
            val = re.sub(r"(\d) ", r"\1", val)

        # Check if numbers are well formed
        vals = re.split(r"([- ]+)", val)
        for val_ in vals:
            if re.search("[A-z0-9]", val_):
                try:
                    if parse_spec_num(val_).number <= 1000:
                        break
                except ValueError:
                    break
        else:
            logger.debug("Cluster aborted: Original values are well formed")
            return "".join((s if s.strip() else ", " for s in vals))

        # Split off questionable numbers after the last delimiter. Earlier
        # versions of this part included the hyphen (-), but that doesn't work
        # well. A hyphen denotes a range, not a list, so it has a different
        # sense than the other delimiters.
        val = self.trim_bad_values(val)

        # Strip stopwords appearing at the end of the string
        stopwords = ("and", "but", "in", "for", "not", "of", "on", "so", "the", "was")
        val = re.sub(f"(\b{'|'.join(stopwords)})$", "", val, flags=re.I).rstrip(",;|")

        # Check for hyphens and spaces likely to be OCR issues
        if self.from_ocr:

            # Mash likely specimen numbers together
            vals = []
            for val in self.split_on_delim(val):
                despaced = re.sub(
                    r"\d( +\d)+", lambda s: s.group().replace(" ", ""), val
                ).strip()
                if is_spec_num(despaced) or self.ends_with_range(despaced):
                    val = despaced
                    logger.debug(f"Stripped spaces: {repr(val)}")
                else:
                    val = val.strip()
                    if val in ",;|":
                        val = val + " "
                vals.append(val)
            val = "".join(vals)

            # Mash values separated by spaces as well
            vals = combine_vals(vals, from_ocr=True)

            # Toss decimals
            vals = [s for s in vals if not re.match(r"\d+\.\d+$", s)]

            # Rejoin values as a string
            val = re.sub(f"(\d) ([A-Z]?\d)", r"\1, \2", " ".join(vals))

            # Check for stray hyphens
            if re.search(r"\d-[A-Z]?\d", val):
                n1, n2 = [s.strip() for s in val.split("-")]

                if parse_spec_num(n1).is_range(n2):
                    logger.debug("Cluster aborted: Value looks like a range")
                    return val
                elif len(n1) + len(n2) <= 6:
                    val = n1 + n2
                    logger.debug("Removing bad hyphen: %s", val)
                else:
                    logger.debug("Cluster aborted: Ambiguous hyphen")
                    return val

            logger.debug(f"Cleaned OCR errors: {val}")

        # Don't try to cluster single numbers
        if re.search(r"^\d+[a-z]?$", val):
            logger.debug("Cluster aborted: Value appears to be a single number")
            return val

        # Don't try to cluster across different prefixes
        prefixes = re.findall(r"([A-Z]+(?:[- ][A-Z])*) *\d", val)
        if len(set(prefixes)) > 1:
            logger.debug("Cluster aborted: Value mixes prefixed and unprefixed numbers")
            return val

        # Expand values with multiple suffixes
        try:
            number, delim, suffixes = re.split(r"([-/])", val)
            catnums = []
            for suffix in as_list(suffixes, delims=",;"):
                catnum = "{}{}{}".format(number, delim, suffix)
                if is_spec_num(catnum):
                    catnums.append(catnum)
                else:
                    break
            else:
                return "; ".join(catnums)
        except ValueError:
            pass

        # Split on common delimiters and check for valid catalog numbers
        parts = [s for s in re.split(r" *[,;] *", val) if s]
        logger.debug("Parts: {}".format(parts))
        valid = []
        for part in parts:
            if is_spec_num(part):
                valid.append(part)
            else:
                # Look for slash-delimited, ranged suffixes
                try:
                    number, suffix = part.split("/")
                except ValueError:
                    break
                else:
                    suffixes = self.expand_suffix(suffix)
                    if not suffixes:
                        break
                    for suffix in suffixes:
                        valid.append("{}/{}".format(number, suffix))
        else:
            if valid:
                logger.debug("Cluster aborted: All values are valid catalog numbers")
                return "; ".join(valid)

        # Cluster ranges separately
        if (
            re.search(self.regex["join_range"], val)
            and self.suf_range.search(val) is None
        ):
            # Are substrings well formed?
            vals = re.split(r"( +)", val)
            if all((is_spec_num(s) for s in vals if s.strip())):
                logger.debug(
                    "Cluster aborted: Values are well formed (space-delimited)"
                )
                return "".join((s if s.strip() else ", " for s in vals))

            vals = re.split(r"([- ]+)", val)
            if all((is_spec_num(s) for s in vals if re.search("A-z0-9", s))):
                logger.debug(
                    "Cluster aborted: Values are well formed (space- and hyhpen-delimited)"
                )
                print(val)
                return "".join((s if s.strip() else ", " for s in vals))

            # Try to clean up simple ranges
            parts = re.split(self.regex["join_range"], val)
            if len(parts) == 3 and "/" not in parts[-1]:
                vals = []
                for part in parts:
                    clustered = self.cluster(part)
                    vals.append(clustered if clustered else part)
                return "".join(vals)
            else:
                # Punt on anything complicated
                logger.debug("Cluster aborted: Value appears to be a range")
                return val

        # Split into runs of alphanumeric characters
        pattern = r"([a-z]\-[a-z]\b|[a-z]+\d+|\d+[a-z]+(?!-)|\d+|[a-z]+)"
        parts = [str(s) for s in re.split(pattern, val, flags=re.I) if s.strip()]
        logger.debug("Parts (alphanum): {}".format(parts))
        if parts:
            parts = self.combine(
                self.clean(parts), minlen=minlen, maxlen=maxlen, related=related
            )
        clustered = self.join(parts)
        logger.debug("Clustered: %s", parts)
        return clustered

    def split_on_delim(self, val, delim=r"(,|;|&| and |(?<!\d)\.(?!\d))"):
        """Splits string on common delimiters"""
        return re.split(delim, val)

    def split_into_catnums(self, val):
        """Splits string based on catalog number regular expression"""
        raise NotImplementedError

    def join(self, vals):
        """Joins values, adjusting spacing for punctuation"""
        delims = ";,"
        for delim in delims:
            if any([re.search(r"[^A-z0-9]", val) for val in vals]):
                joined = []
                for val in vals:
                    if val == delim:
                        joined[-1] += val
                    else:
                        joined.append(val)
                return " ".join(vals).strip()
        return "; ".join(vals)

    def ends_with_range(self, val):
        """Tests if value ends with a range"""
        return bool(re.search(r"[a-z]-[a-z]$", val))

    def trim_bad_values(self, val):
        """Trims unlikely catalog numbers/suffixes from a list"""
        logger.debug(f'Trimming bad values from "{val}"')
        orig = val
        # Trim a single number following a 5-6 digit number
        if re.match(r"^[A-Z]* ?\d{5,6} \d$", val):
            return val.split(" ")[0]
        # Trim a single trailing number following a spaced hyphen
        val = re.split(r" +\- +\d$", val)[0]
        # Check if value could be a catalog number with multiple suffixes
        try:
            num, suf = re.split(r"[-/]", val)
            for suffix in as_list(suf, delims=",;"):
                if re.match(r"^[a-z]{3,}$", suffix, flags=re.I) or not is_spec_num(
                    "{}-{}".format(num, suffix)
                ):
                    break
            else:
                return val
        except ValueError:
            pass
        # Strip out filler
        pattern = self.regex["filler"] + r"(?=[A-Z]{,3}\d{3,})"
        val = re.sub(pattern, "", val, flags=re.I)
        # Split on common delimiters
        vals = self.split_on_delim(val)
        # Iteratively trim last value
        while vals and not self._validate_last(vals):
            vals = vals[:-1]
        # Go forward through the values, stopping at the first stray alpha
        if vals:
            for i, val in enumerate(vals):
                if val.strip().isalpha() and len(val.strip()) > 1:
                    logger.debug('Trimmed "%s" (alphabetic)', val)
                    break
            vals = vals[: i + 1]
        val = self.join(vals).rstrip(" ,;&")
        # Trim single letters after a comma
        val = re.sub(r"(?<=\d) *, *[a-z]$", "", val, flags=re.I)
        # Log if val has changed
        if val != orig:
            logger.debug("Trimmed to %s", vals)
        return val

    def _validate_last(self, vals):
        """Checks if last value in list appears to be a cat number or suffix"""
        logger.debug(f"Checking last character in {vals}...")
        # Mash the last number together
        val = vals[-1].strip("# ")
        despaced = re.sub(
            r"\d( +\d)+", lambda s: s.group().replace(" ", ""), val
        ).strip()
        if is_spec_num(despaced) or self.ends_with_range(despaced):
            val = despaced
            logger.debug(f"Stripped spaces: {repr(val)}")
        # Always trim non-alphanumeric characters
        if re.match(r"[^A-z0-9]", val):
            logger.debug('Trimmed "%s" (not alphanumeric)', val)
            return False
        # If multiple values, consider the preceding delimiter. Semicolons
        # and commas are hard delimiters, and values after these characters
        # shoulder only be kept if they are either alpha suffixes or obvious
        # catalog numbers.
        is_valid = is_spec_num(val)
        is_digit = val.isdigit()
        is_suffix = bool(re.match(self.p_suffix, val))
        is_alpha_suffix = bool(re.match(self.p_alpha_suffix, val))
        is_alpha_range = bool(self.expand_alpha_suffix(val))
        logger.debug(
            "%s: is_valid=%s, is_digit=%s," " is_suffix=%s, is_alpha_suffix=%s",
            val,
            is_valid,
            is_digit,
            is_suffix,
            is_alpha_suffix,
        )
        if len(vals) > 2:
            delim = vals[-2].strip()
            if delim in ",;":
                # Log each case separately for troubleshooting purposes
                if is_alpha_suffix and (len(val) > 1 or val not in "lIO"):
                    logger.debug('"%s" is a valid alpha suffix', val)
                elif is_alpha_range:
                    logger.debug('"%s" has a valid alpha range', val)
                elif is_valid and not is_digit:
                    logger.debug('"%s" is an alphanumeric catnum', val)
                elif is_valid and is_digit and len(val) >= 4:
                    logger.debug('"%s" is a numeric catnum 4 digits or longer', val)
                else:
                    logger.debug('Trimmed "%s" (weak post-delim value)', val)
                    return False
            elif delim == "." and is_alpha_suffix:
                return False
        logger.debug('Stopped trimming at "%s"', val)
        return True

    def expand_suffix(self, val):
        suffixes = self.expand_alpha_suffix(val)
        if not suffixes:
            suffixes = self.expand_numeric_suffix(val)
        return suffixes

    def expand_alpha_suffix(self, val):
        """Expands ranges of alphabetic suffixes"""
        # Get suffixes
        letters = "abcdefghijklmnopqrstuvwxyz"
        # Look for suffix ranges (123456a-c)
        suf_range = self.suf_range.findall(val)
        if suf_range:
            i = letters.index(suf_range[0][1].lower())
            j = letters.index(suf_range[0][3].lower())
            suffixes = letters[i : j + 1]
        else:
            # Find discrete suffixes (123456a,b,d)
            suffixes = re.findall(r"(?<![A-z])([A-z])(?![A-z])", val)
        if suffixes:
            logger.debug('Alpha suffixes in "%s": %s', val, suffixes)
        return suffixes

    def expand_numeric_suffix(self, val):
        """Expands ranges of numeric suffixes"""
        try:
            n1, n2 = [int(n.strip()) for n in val.split("-")]
            if n2 - n1 < 50:
                suffixes = list(range(n1, n2 + 1))
                logger.debug('Numeric suffixes in "%s": %s', val, suffixes)
                return suffixes
        except ValueError:
            return []

    def clean(self, vals):
        """Cleans up a list of candidates"""
        assert isinstance(vals, list)
        # Clean up the formatting of parts
        cleaned = []
        for val in vals:
            stripped = val.strip()

            # Remove words
            val = re.sub(r"[A-z]{2,}\.?", "", val)

            # Isolate ranges
            for suffix in self.suf_range.findall(val):
                cleaned.append(suffix[0])
                val = val.replace(suffix[0], "")

            if len(val) > 1 and not (
                stripped.isalpha()
                or stripped.isnumeric()
                or re.match(self.p_catnum, stripped)
            ):
                cleaned.append(val)

            elif val:
                cleaned.append(val)

        logger.debug("Cleaned: {}".format(cleaned))
        return cleaned

    def combine(self, vals, minlen=None, maxlen=None, related=None):
        """Combines fragments and expands suffix ranges

        Numbers are a mix of short and long numbers. This may be a spacing
        issue, so try combining the numbers semi-intelligently.
        """
        if related is None:
            related = []

        # Remove empty values
        vals = [val for val in vals if val.strip()]

        # Are all values valid catalog numbers?
        if all((is_spec_num(s) for s in vals)):
            logger.debug("Cluster aborted: Numbers are already valid")
            return vals

        # Calculate maximum length based on current and related numbers
        if maxlen is None:
            pattern = r"^(\d+[A-z]?|[A-z](-[A-z])?)$"
            nums = [p for p in vals if re.search(pattern, p)]
            related += nums
            maxlen = max([len(n) for n in related])

        # Can shorter fragments be combined into that length?
        clustered = []
        fragment = ""
        breaker = False
        for i, val in enumerate(vals):

            # Get root for suffixes
            root = fragment
            if clustered:
                root = re.sub(r"[A-z]+$", "", clustered[-1])

            # Check if the current fragment is a valid length
            frag_valid = minlen <= len(fragment) <= maxlen

            # Stop processing when breaking punctuation is followed by a
            # a string that is not a catalog number but does contain letters
            # if the preceding entry did not include a suffix. So "1234a, b"
            # is valid but "1234, ab" is not.
            if breaker:
                if (
                    not is_spec_num(val)
                    and re.search(r"[A-z]", val)
                    and not re.search(r"[A-z]+$", clustered[-1])
                ):
                    break
                breaker = False

            # Turn on breaker when comma/semicolor encountered
            if val in ",;":
                breaker = True

            # Append numbers to the current fragment
            elif val.isnumeric() and fragment:
                fragment += val

            # Iterate last value in clustered if current value is similar to
            # last few digits of last value
            elif (
                val.isnumeric()
                and len(val) < minlen
                and clustered
                and clustered[-1][-1].isnumeric()
                and int(val) - int(clustered[-1][-len(val) :]) == 1
            ):
                clustered.append(clustered[-1][: -len(val)] + val)

            # Create new fragment from a number
            elif val.isnumeric():
                fragment += val

            # Append single letters to either the current fragment or,
            # failing that, the last value added to clustered
            elif len(val) == 1 and val.isalpha():
                clustered.append(root + val)
                clustered = [n for n in clustered if n != root]
                fragment = ""

            # Combine alphanumeric strings with fragment if result is valid
            elif is_spec_num(fragment + val):
                clustered.append(fragment + val)
                fragment = ""

            # Expand ranges of alpha suffixes
            elif re.match(r"^[a-z]-[a-z]$", val, flags=re.I):
                for suffix in self.expand_alpha_suffix(val):
                    clustered.append(root + suffix)
                clustered = [n for n in clustered if n != root]
                fragment = ""

            # Add fragment to clustered when it reaches the maximum allowed
            # length, then reset the fragment
            if len(fragment) == maxlen:
                clustered.append(fragment)
                fragment = ""
        else:
            # Add fragment to clustered if length is valid
            if minlen <= len(fragment) <= maxlen:
                clustered.append(fragment)

        nums = clustered

        logger.debug("Combined: %s", nums)
        return nums
