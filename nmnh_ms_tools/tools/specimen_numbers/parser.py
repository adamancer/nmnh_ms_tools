"""Defines methods to work with USNM catalog numbers and specimen data"""
import functools
import json
import logging
import math
import os
import re
import time
from collections import namedtuple

import requests
import yaml
from unidecode import unidecode

from .cluster import Cluster
from ...config import CONFIG_DIR




logger = logging.getLogger(__name__)
logger.debug('Loading parser.py')




IndexedSnippet = namedtuple('IndexedSnippet', ['text', 'start', 'end'])
SpecNum = namedtuple('SpecNum', ['code', 'prefix', 'number', 'suffix'])




class Parser:
    """Parses and interprets USNM catalog numbers in text"""

    def __init__(self, expand_short_ranges=True, from_ocr=True):
        fp = os.path.join(CONFIG_DIR, 'config_specimen_numbers.yml')
        with open(fp, 'r') as f:
            self.regex = yaml.safe_load(f)
        self.regex['catnum'] = self.regex['catnum'].format(**self.regex)
        self.mask = re.compile(self.regex['mask'].format(**self.regex), flags=re.I)
        self.simple = re.compile(self.regex['simple'])
        self.discrete = re.compile(self.regex['discrete_mask'].format(**self.regex))
        self.suf_range = re.compile(r'(([A-z])' + self.regex['join_range'].format(**self.regex) + r'([A-z]))')
        self.range = re.compile(self.regex['range_mask'].format(**self.regex))
        self.code = ''
        self.codes = [s.strip() for s in self.regex['code'].strip('()').split('|')]
        self.metadata = []
        self.expand_short_ranges = expand_short_ranges
        self.from_ocr = from_ocr
        self._cluster = Cluster()


    def cluster(self, val):
        """Clusters lists of numbers and expands alpha suffixes"""
        if self.from_ocr:
            return self._cluster.cluster(self.fix_ocr_errors(val))
        return val


    def findall(self, text):
        """Finds all likely catalog numbers within the given string"""
        #logger.debug('Search "%s"', text)
        matches = []
        for match in {m[0] for m in self.mask.findall(text)}:
            if re.search(r'\d', match):
                matches.append(match)
        matches.sort()
        logger.debug('Found catalog numbers: %s"', matches)
        return sorted(matches, key=len)


    def clean_text(self, text, split_codes=True):
        """Removes periods and spaces from museum codes in text"""
        def clean_codes(match):
            if match.group().count(".") == 1 and match.group().endswith("."):
                return text
            return re.sub(r'[^A-z]', '', match.group()).upper()

        codes = [r"\.? *".join(c) for c in self.codes]
        pattern = r"\b({})(\.|\b)".format("|".join(codes))
        text = re.sub(pattern, clean_codes, text, flags=re.I)

        # Split text on codes. Useful for matching but disrupts the string.
        if split_codes:
            pattern = r'({})'.format('|'.join(self.codes))
            parts = re.split(pattern, text)
            combined = []
            for i, part in enumerate(parts[1:]):
                if parts[i] in self.codes:
                    coded = f'{parts[i]}{part}'.strip(';. ')
                    coded = re.sub(r'(?<=\d)([\. ]+)(?=[A-Z]$)', '-', coded)
                    combined.append(coded)
            return '; '.join(combined)

        return text


    def snippets(self,
                 text,
                 mask=None,
                 num_chars=32,
                 highlight=True,
                 clean=False,
                 pages=None):
        """Find all occurrences of a pattern in text"""
        if mask is None:
            mask = self.mask
        elif isinstance(mask, str):
            mask = re.compile(mask)

        orig = text
        if clean:
            text = self.clean_text(text, split_codes=False)

        snippets = {}
        for match in mask.finditer(text):
            val = match.group()
            start = match.start()

            if val.startswith('-'):
                continue

            # Get index for start of string based on the number of characters,
            # seeking backwards to find the nearest word break
            i = start - num_chars
            num_chars_before = num_chars
            if i < 0:
                num_chars_before += i
                i = 0
            while i > 0:
                if re.match(r'\W', text[i], flags=re.U):
                    break
                i -= 1

            # Get index for start of string based on the number of characters,
            # seeking forward to find the nearest word break.
            j = min([i + len(val) + num_chars_before + num_chars, len(text)])
            while j < len(text):
                if re.match(r'\W', text[j], flags=re.U):
                    break
                j += 1

            # Compile snippet with ellipses to indicate where snippets were
            # pulled from mid-text. Also neatens up the snppets by stripping
            # non-alphanumeric characters from each end.
            # FIXME: Do not strip closing parentheses
            snippet = ''.join([
                '...' if i > 0 else '',                      # leading ellipsis
                re.sub(r'(^\W+|\W+$)', "", text[i:j]),
                '...' if j < len(text) else ''               # trailing ellpsis
            ])

            if highlight:
                snippet = snippet.replace(val, '**' + val + '**')
            snippet = IndexedSnippet(snippet, start, start + len(val))

            # Add snippet if not identical to existing
            existing = snippets.setdefault(val, [])
            if snippet.text not in {s.text for s in existing}:
                existing.append(snippet)

        return snippets


    @functools.lru_cache()
    def parse(self, val, expand_short_ranges=None):
        """Parses catalog numbers from a string"""
        if expand_short_ranges is not None:
            esr = self.expand_short_ranges
            self.expand_short_ranges = expand_short_ranges
        orig = val
        # Remove thousands separators`
        val = re.sub(r'(\d),(\d\d\d)\b', r'\1\2', val)
        # Move trailing codes to beginning of string
        for code in self.codes:
            if val.endswith('({})'.format(code)):
                val = code + ' ' + val[:-(len(code) + 2)].strip()
                logger.debug('Moved "%s" to front of string', code)
            val = val.replace(code, code + ' ').replace('  ', ' ')
        # Use snippets to get a list of candidates
        val = '|'.join(self.snippets(val))
        # Try to split the value on strings that look like museum codes,
        # defined here as capitalized alpha strings of 3 or more letters.
        words = [w for w in re.split(r'([A-Z]{3,} ?)', val)
                 if w and w not in '()']
        code = ''
        held = []
        for i, word in enumerate(words):
            if word.strip() in self.codes:
                code = word.strip()
                held.append([word])
                logger.debug('Found museum code "{}"'.format(word.strip()))
            elif word.strip().isalpha() and i and words[i - 1].strip() != code:
                code = ''
            elif code and word.strip():
                held[-1].append(word)
        vals = []
        for val in held:
            if len(val) > 1:
                val = ''.join(val).strip('|;, ')
                try:
                    parsed = self._parse(val)
                except Exception as e:
                    logger.warning(f"Parse failed: {str(e)}")
                    logger.debug("Parse traceback", exc_info=e)
                else:
                    vals.extend(parsed)
                    logger.debug('Parsed "{}" as {}'.format(val, parsed))
            else:
                logger.warning('Museum code only: %s', orig)
        if expand_short_ranges is not None:
            self.expand_short_ranges = esr
        return sorted(vals)


    def _parse(self, val):
        """Parses catalog numbers from a string"""
        logger.debug('Parsing "{}"...'.format(val))
        # Clean up the string a little to simplify parsing
        val = val.replace('--', '-') \
                 .replace('^', '') \
                 .strip('()[],;&? ')
        val = re.sub(r'\band\b', '&', val)
        val = val.strip('()[],;&? ')
        # Remove the museum code, wherever it may be
        try:
            self.code = re.findall(self.regex['code'], val)[0].strip()
        except IndexError:
            pass
        # Clean up special numbers so they're easier to recognize
        pattern = r'(?<=[A-Z] )(loc(\.|ality)?|slide|type)(?= \d)'
        val = re.sub(pattern, r"\1 no.", val)
        # Check for high-quality numbers and bail
        if self.simple.search(val):
            return [val]
        self.metadata = []
        nums = []
        for match in [m[0] for m in self.mask.findall(val)]:
            # The museum code interferes with parsing, so strip it here
            match = self.remove_museum_code(match)
            nums.extend(self.parse_mixed(match))
            nums.extend(self.parse_discrete(match))
            nums.extend(self.parse_ranges(match))
        if not nums and self.is_range(val):
            logger.debug('Parsed as simple range: %s', val)
            nums = self.fill_range(val)
        if not nums:
            logger.debug('Parsed as catalog number: %s', val)
            val = self.remove_museum_code(val)
            clustered = [n.strip() for n in self.cluster(val).split(';')]
            nums = [self.parse_num(n) for n in clustered if n]
        # Are the lengths in the results reasonable?
        if len(nums) > 1:
            minlen = min([len(str(n.number)) for n in nums])
            if minlen < 4:
                maxlen = max([len(str(n.number)) for n in nums])
                nums = [n for n in nums if n.number > 10**(maxlen - 2)]

        nums = [self.stringify(n) for n in nums]
        nums = [n for i, n in enumerate(nums) if n not in nums[:i]]

        # Catch special numbers that look like catalog numbers
        pat = r'\b(loc(\.|ality)?|slide|type) *(?:#|no\.?|num(ber))'
        try:
            kind = re.search(pat, val, flags=re.I).group(1).lower().strip('.')
        except AttributeError:
            pass
        else:
            kind = {'loc': 'locality'}.get(kind, kind)
            nums = [n.replace(' ', f' {kind} no. ', 1) for n in nums]

        return nums


    @staticmethod
    def stringify(spec_num):
        delim_prefix = ' '
        delim_suffix = '-'
        if not spec_num.prefix:
            delim_prefix = ''
        elif len(spec_num.prefix) > 1:
            delim_prefix = ' '
        if ((spec_num.suffix.isalpha() and len(spec_num.suffix) == 1)
            or re.match(r'[A-Za-z]-\d+', spec_num.suffix)):
            delim_suffix = ''
        return '{} {}{}{}{}{}'.format(spec_num.code,
                                      spec_num.prefix,
                                      delim_prefix,
                                      spec_num.number,
                                      delim_suffix,
                                      spec_num.suffix).rstrip(delim_suffix) \
                                                      .strip()


    def parse_discrete(self, val):
        """Returns a list of discrete specimen numbers"""
        logger.debug('Looking for discrete numbers in "{}"...'.format(val))
        orig = val

        #val = re.sub(self.regex['filler'], '', val, flags=re.I)
        pattern = self.regex['filler'] + r"(?=[A-Z]{,3}\d{3,})"
        val = re.sub(pattern, '', val, flags=re.I)
        #prefix = re.match(r'\b(' + self.regex['prefix'] + r')(?![a-zA-z])', val)
        #prefix = prefix.group() if prefix is not None else ''
        discrete = self.discrete.search(val)
        if discrete is None:
            val = self.cluster(val)
            discrete = self.discrete.search(val)
        nums = []
        if discrete is not None:
            val = discrete.group().strip()
            val = self.cluster(val)
            if self.is_range(val):
                nums.extend(self.get_range(val))
            elif self.is_catnum(val):
                # Check if value is actually a single catalog number
                nums.append(self.parse_num(val.replace(' ', '')))
            else:
                # Chunk the original string into individual catalog numbers.
                # Two primary ways of doing this have been considered:
                # Splitting on (1) the catnum regex or (2) the join_discrete
                # regex. Option 1 can break up ranges. Option 2 can break up
                # prefixed catalog numbers (e.g., PAL 76012). The code below
                # uses option 2 to reconstruct ranges in option 1.
                #
                # Test if split on common delimiters yields usable numbers.
                # This helps prevent catalog numbers from grabbing an alpha
                # prefix from the succeeding catalog number.
                spec_nums = [s.strip() for s in re.split(r'(?:,|;| and | & )', val)]
                for spec_num in spec_nums:
                    if not self.is_catnum(spec_num):
                        spec_nums = re.findall(self.regex['catnum'], val)
                        spec_nums = [s for s in spec_nums if self.is_catnum(s)]
                        break
                # Clean up suffixes after chunking into discrete parts
                for chunk in re.split(self.regex['join_discrete'], val):
                    if self.is_range(chunk):
                        rng = [self.stringify(n) for n in self.fill_range(chunk)]
                        spec_nums.extend(rng)
                        # Ensure that this chunk is not in spec_nums
                        spec_nums = [n for n in spec_nums if n != chunk]
                # Fill numbers
                prefix = None
                for spec_num in spec_nums:
                    spec_num = self.remove_museum_code(spec_num)

                    # Check for prefix
                    if spec_num[0].isalpha():
                        num = self.parse_num(spec_num)
                        prefix = (num.prefix, len(str(num.number)))

                    # Apply the prefix from the previous number if similar
                    elif prefix is not None:
                        num = self.parse_num(spec_num)
                        if len(str(num.number)) == prefix[1]:
                            num.prefix = prefix[0]
                            spec_num = self.stringify(num)
                        else:
                            prefix = None

                    if self.is_range(spec_num):
                        nums.extend(self.fill_range(spec_num))
                    elif self.is_catnum(spec_num.strip()):
                        nums.append(self.parse_num(spec_num.replace(' ', '')))
                    else:
                        nums.append(self.parse_num(spec_num))

                nums = [n for i, n in enumerate(nums) if n not in nums[:i]]
        if nums:
            num_strings = [self.stringify(n) for n in nums]
            logger.debug('Parsed discrete: %s', num_strings)
        else:
            logger.debug('No discrete numbers found')
        return nums


    def parse_ranges(self, val):
        """Returns a list of specimen numbers given in ranges"""
        logger.debug('Looking for ranges in "{}"...'.format(val))
        val = self.cluster(val)
        ranges = self.range.search(val)
        nums = []
        if ranges is not None:
            spec_num = ranges.group().strip()
            if self.is_range(spec_num):
                nums.extend(self.fill_range(spec_num))
            else:
                # Catch legitimate specimen numbers. Short ranges are caught
                # above, so anything that parses should be excluded here.
                try:
                    self.parse_num(spec_num)
                except ValueError:
                    # Finds ranges joined by something other than a dash
                    try:
                        n1, n2 = re.findall(self.regex['catnum'], spec_num)
                        n1, n2 = [n for n in (n1, n2) if self.is_catnum(n)]
                        n1, n2 = [self.parse_num(n) for n in (n1, n2)]
                    except ValueError:
                        pass
                    else:
                        nums.extend(self.fill_range(n1, n2))
        if nums:
            num_strings = [self.stringify(n) for n in nums]
            logger.debug('Parsed range: %s', num_strings)
        else:
            logger.debug('No ranges found')
        return nums


    def parse_mixed(self, val):
        """Returns specimen numbers from string with discrete and ranged nums"""

        if not ('-' in val and '/' in val):
            return []

        parts = [s for s in re.split(r'([-/]\d+)', val)]
        parts = [p.strip() for p in parts if p.strip()]
        nums = []
        if all([re.match(r'[-/]\d+$', p) for p in parts[1:]]):
            nums.append(self.parse_num(parts[0]))
            for i, part in enumerate(parts[1:]):

                # Fill ranges for hyphen-delimited parts
                if part.startswith('-'):
                    num = self.stringify(nums[-1])
                    nums.extend(self.fill_range(f'{num}{part}'))

                # Fill discrete by substituting last few characters of
                # previous number with the current part
                else:
                    part = part.strip('/')
                    num = self.stringify(nums[-1])
                    nums.append(self.parse_num(num[:-len(part)] + part))

        return nums


    @staticmethod
    def validate_trailer(vals):
        val = vals[-1].strip()
        refval = vals[0].strip()
        # Always ditch the trailer after a semicolon
        if len(vals) > 1 and ';' in vals[-2] and len(vals[-1]) <= 2:
            return False
        # Keep one-letter trailers if refval also ends with a letter
        if refval[-1].isalpha() and val.isalpha() and len(val) == 1:
            return True
        # Strongly considering ditching the trailer after a comma
        if (len(vals) > 1
            and ',' in vals[-2]
            and vals[-1].startswith(' ')
            and len(vals[-1]) <= 3):
                return False
        # Discard all-letter trailers longer than one character
        if re.search(r'^[A-z]{2,4}$', val):
            return False
        # Compare numeric portions
        try:
            nval = re.search(r'[\d ]+', val).group().replace(' ', '').strip()
            nref = re.search(r'[\d ]+', refval).group().replace(' ', '').strip()
        except AttributeError:
            pass
        else:
            if ((len(nval) > 2 and len(nval) - len(nref) <= 1)
                or len(nval) + len(nref) == 6):
                return True
        return False


    def remove_museum_code(self, val):
        """Strips the museum code from the beginning of a value"""
        if self.code:
            return val.replace(self.code, '', 1).replace('()', '').strip(' -')
        return re.sub(self.regex['code'], '', val).replace('()', '').strip(' -')


    def parse_quick(self, val, mask=None):
        """Parses a single well-formed catalog number"""
        if mask is None:
            mask = (r'^(?:(?P<code>NMNH|USNM) )?'
                    r'(?P<prefix>(?:[A-Z]{1,4}))? ?'
                    r'(?P<number>\d+)'
                    r'(?P<suffix>(?:(?:[-, ](?:[A-Z0-9]+))|[A-Z])?'
                    r'(?: \((?:[A-Z:]+)\))?)$')
        return SpecNum(**re.search(mask, val, flags=re.I).groupdict())


    def parse_num(self, val):
        """Parses a catalog number into prefix, number, and suffix"""
        orig = val
        # Find and extract the museum code
        try:
            code = re.findall(self.regex['code'], val)[0].strip()
        except IndexError:
            code = self.code
        val = self.remove_museum_code(val.strip())

        pattern = self.regex['filler'] + r"(?=[A-Z]{,3}\d{3,})"
        val = re.sub(pattern, '', val, flags=re.I)

        # Identify prefix and number
        try:
            prefix = re.match(r'\b[A-Z ]+', val).group()
        except AttributeError:
            prefix = ''
        else:
            prefix = self.fix_ocr_errors(prefix, True)
            if prefix.isnumeric():
                prefix = ''
        # Format number
        number = val[len(prefix):].strip(' -')
        # Identify suffix
        delims = ('--', ' - ', '-', ',', '/', '.')
        suffix = ''
        for delim in delims:
            try:
                number, suffix = number.rsplit(delim, 1)
            except ValueError:
                delim = ''
            else:
                # A value after a spaced out hyphen is unlikely to be a suffix
                if delim == ' - ':
                    suffix = ''

                # A value containing slashes is unlikely to be a suffix
                if '/' in suffix:
                    raise ValueError(f'Could not parse: {val} (bad suffix)')

                strip_chars = ''.join(delims) + ' '
                number = number.rstrip(strip_chars)
                suffix = suffix.strip(strip_chars)
                break

        # Clean up stray OCR errors in the number now suffix has been removed
        if (not number.isdigit()
            and not (number[:-1].isdigit() and len(number) > 6)):
                number = ''.join([self.fix_ocr_errors(c) for c in number])

        # Identify trailing letters, wacky suffixes, etc.
        if not number.isdigit():
            try:
                trailing = re.search(self.regex['suffix2'], number).group()
            except AttributeError:
                pass
            else:
                suffix = (trailing + delim + suffix).strip()
                number = number.rstrip(trailing)

        prefix = prefix.strip()
        number = self.fix_ocr_errors(number)
        if len(number) < 6:
            suffix = self.fix_ocr_errors(suffix.strip(), match=True)
        # Disregard unlikely suffixes
        stopwords = {
            'and',
            'but',
            'in',
            'for',
            'not',
            'of',
            'on',
            'so',
            'the',
            'was'
        }
        if (
            len(suffix) > 3 and suffix.isalpha()
            or len(suffix) > 5
            or re.search(r'fig.*\d', suffix, flags=re.I)
            or suffix in stopwords
        ):
            suffix = ''
        else:
            # Strip stopwords that directly follow a number
            pattern = r'(?<=\d)({})'.format('|'.join(stopwords))
            suffix = re.sub(pattern, "", suffix)
        try:
            return SpecNum(code, prefix, int(number), suffix.upper())
        except ValueError as e:
            raise ValueError(f'Could not parse: {val} ({e})')


    def fix_ocr_errors(self, val, match=False):
        """Attempts to fix common OCR errors in a specimen number"""
        if not self.from_ocr:
            return val

        common_ocr_errors = {
            'i': '1',
            'I': '1',
            'l': '1',
            'O': '0',
            'S': '5'
        }

        if match:
            return common_ocr_errors.get(val, val)
        else:
            # Trim unlikely suffixes that get garbled by the OCR check
            try:
                part, last_word = val.split(' ', 1)
            except ValueError:
                pass
            else:
                if last_word.lower() in ('el', 'is', 'la', 'le'):
                    val = part

            # Fix common errors where leading or between numbers
            for find, repl in common_ocr_errors.items():
                pattern = r'(^|\d){}(\d)'.format(find)
                val = re.sub(pattern, r'\g<1>{}\g<2>'.format(repl), val)

            # Filter out likely strings
            words = []
            for word in re.split(r'(\W+)', val):
                filtered = word
                for key in common_ocr_errors:
                    filtered = filtered.replace(key, '')
                if not filtered[:-1].isalpha():
                    for find, repl in common_ocr_errors.items():
                        word = word.replace(find, repl)
                words.append(word)

            return ''.join(words)


    def fill_range(self, n1, n2=None):
        """Fills a catalog number range"""
        derived_n2 = False
        if n2 is None:
            n1, n2 = self.get_range(n1)
            derived_n2 = True
        if n1.prefix and not n2.prefix:
            n2 = SpecNum(n2.code, n1.prefix, n2.number, n2.suffix)
        if self.is_range(n1, n2):
            return [SpecNum(self.code, n1.prefix, n, '')
                    for n in range(n1.number, n2.number + 1)]
        # Range parse failed!
        return [n1, n2] if not derived_n2 else [n1]


    def get_range(self, n1, n2=None):
        """Gets the endpoints of a range"""
        if n2 is None:
            n1, n2 = self.split_num(n1)
        if not self._is_range(n1, n2):
            n1, n2 = self.short_range(n1, n2)
        return n1, n2


    def split_num(self, val, delim='-'):
        """Splits the catalog number and suffix for range testing"""
        n1, n2 = [n.strip() for n in val.strip().split(delim)]
        n1, n2 = [self.parse_num(n) for n in (n1, n2)]
        if n1.prefix and not n2.prefix:
            n2 = SpecNum(n2.code, n1.prefix, n2.number, n2.suffix)
        return n1, n2


    def is_range(self, n1, n2=None):
        """Tests if a given value is likely to be a range"""
        if n1 is None and n2 is None:
            return False
        if n2 is None:
            # Only expand numbers if they include a hyphen
            if '-' not in str(n1):
                return False
            try:
                n1, n2 = self.split_num(n1)
            except ValueError:
                return False
        is_range = self._is_range(n1, n2)
        if not is_range and self.expand_short_ranges:
            is_range = self._is_range(*self.short_range(n1, n2))
        return is_range


    def _is_range(self, n1, n2=None):
        """Tests if a given pair of numbes are likely to be a range"""
        if n2 is None:
            n1, n2 = self.split_num(n1)
        same_prefix = n1.prefix == n2.prefix
        big_numbers = n1.number > 100 and n2.number > 100
        small_diff = (n2.number - n1.number) < 500
        no_suffix = not n1.suffix and not n2.suffix
        n2_bigger = n2.number > n1.number
        return (same_prefix
                and (big_numbers or small_diff)
                and small_diff
                and no_suffix
                and n2_bigger)


    def is_catnum(self, val):
        """Tests if the given value looks like a catalog number"""
        return (
            re.match('^' + self.regex['catnum'] + '$', val)
            and not val.strip().isalpha()
        )


    def short_range(self, n1, n2):
        """Expands numbers to test for short ranges (e.g., 123456-59)"""
        x = 10 ** len(str(n2.number))
        num = int(math.floor(n1.number / x) * x) + n2.number
        n2 = SpecNum(n2.code, n2.prefix, num, n2.suffix)
        return n1, n2


    def short_discrete(self, n1, n2):
        """Expands shorthand numbers (e.g., 194383-85/87/92/93/99)"""
        raise NotImplementedError
