"""Standardizes strings for comparison"""

import logging
import re

import pandas as pd
from unidecode import unidecode


logger = logging.getLogger(__name__)


class Standardizer:
    hints = {}

    def __init__(
        self,
        force_lower=True,
        force_ascii=True,
        force_alphanumeric=True,
        minlen=2,
        delim="-",
        stopwords=None,
        stripwords=None,
        strip_first=None,
        strip_last=None,
        strip_parentheticals=None,
        replace_endings=None,
        replace_words=None,
        stemmer=None,
        move_to_beginning=None,
        move_to_end=None,
        allow_numbers=False,
        sort_terms=False,
    ):
        self.force_lower = force_lower
        self.force_ascii = force_ascii
        self.force_alphanumeric = force_alphanumeric
        self.minlen = minlen
        self.delim = delim
        self.stopwords = stopwords
        self.stripwords = stripwords
        self.strip_first = strip_first
        self.strip_last = strip_last
        self.strip_parentheticals = strip_parentheticals
        self.replace_endings = replace_endings
        self.replace_words = replace_words
        self.stemmer = stemmer
        self.sort_terms = sort_terms
        self.move_to_beginning = move_to_beginning
        self.move_to_end = move_to_end
        self.allow_numbers = allow_numbers

        if isinstance(self.replace_endings, (list, set, tuple)):
            self.replace_endings = {s: "" for s in self.replace_endings}

        self.params = {
            "force_lower": bool,
            "force_ascii": bool,
            "force_alphanumeric": bool,
            "minlen": int,
            "delim": str,
            "stopwords": set,
            "stripwords": set,
            "strip_first": set,
            "strip_last": set,
            "strip_parentheticals": bool,
            "replace_endings": dict,
            "replace_words": dict,
            "stemmer": None,
            "move_to_beginning": set,
            "move_to_end": set,
            "allow_numbers": bool,
            "sort_terms": bool,
        }
        for attr, kind in self.params.items():
            if kind is not None:
                if getattr(self, attr) is None:
                    setattr(self, attr, kind())
                val = getattr(self, attr)
                if not isinstance(val, kind):
                    # Coerce mismatched iterables
                    iterables = (list, set, tuple)
                    if kind in iterables and isinstance(val, iterables):
                        setattr(self, attr, kind(val))
                    else:
                        raise TypeError("{} is {}".format(attr, val))

    def __call__(self, *args, **kwargs):
        return self.std(*args, **kwargs)

    def get_params(self, kwargs):
        for key in kwargs:
            kind = self.params[key]
            if kind is not None:
                val = kwargs[key]
                if val is None:
                    val = kind()

                if key == "replace_endings" and isinstance(val, (list, set, tuple)):
                    val = {s: "" for s in val}
                    kwargs[key] = val

                if not isinstance(val, kind):
                    mask = "{}={} (type must be {})"
                    raise TypeError(mask.format(key, val, kind))
        params = {k: getattr(self, k) for k in self.params}
        params.update(kwargs)
        return params

    def std(self, val, pre=None, post=None, **kwargs):
        cacheable = pre is None and post is None and not kwargs
        if cacheable:
            try:
                return self.hints["std"][str(val)]
            except KeyError:
                pass
        msg = f"Could not standardize {repr(val)}"
        st_val = self._std(val, pre=pre, post=post, **kwargs)
        try:
            st_val = self._std(val, pre=pre, post=post, **kwargs)
            if cacheable:
                self.hints.setdefault("std", {})[str(val)] = st_val
            return st_val
        except ValueError as e:
            logger.warning(msg)
        except Exception as e:
            logger.error(msg, exc_info=e)
        raise ValueError(msg)

    def same_as(self, val, other, kind="exact", **kwargs):
        """Checks if two values are the same or similar"""
        assert kind in {"all", "any", "exact", "in"}
        # Evaluates to False if either value is empty
        if not val or not other:
            return False

        # Check for exact match on a simple standardization
        st_val = re.sub(r"[^A-Za-z0-9]", "", val).lower()
        st_other = re.sub(r"[^A-Za-z0-9]", "", other).lower()
        if st_val == st_other:
            return True

        # Exact string comparison. Wrapped in a try-except to catch
        # values that can't be standardized.
        try:
            st_val = self(val, **kwargs)
            st_other = self(other, **kwargs)
            if kind == "exact":
                return st_val == st_other
        except ValueError:
            return False

        # Compare sets
        st_val = set(st_val.split(self.delim))
        st_other = set(st_other.split(self.delim))
        if kind == "any":
            xtn = st_val & st_other
            # This is a very permissive comparison, but matches that consist
            # of a single short number are unreliable and are disregarded
            if not all([s.isnumeric() and len(s) < self.minlen for s in xtn]):
                return bool(xtn)

        return st_val == st_other

    def words(self, val, use_delim=True):
        if isinstance(val, str):
            if use_delim:
                return val.split(self.delim), False

            # Split on non-alphanumeric characters if not using delimiter
            val = re.sub(r"([a-z])'([a-z])", r"\1\2", val)
            return [w for w in re.split(r"[^A-z0-9]+", val) if w], False

        return val, True

    def delimit(self, val, lower=True):
        """Returns a delimited version of the string"""
        delimited = self.delim.join(self.words(val, use_delim=False)[0])
        return delimited.lower() if lower else delimited

    def move(self, val, terms, index=0):
        words, as_list = self.words(val)
        move = set(words).intersection(set(terms))
        if move:
            words = [w for w in words if w not in move]
            move = sorted(list(move))
            if index is None:
                words.extend(move)
            else:
                words = move + words
        return words if as_list else self.delim.join(words)

    def move_if_last(self, val, terms):
        words, as_list = self.words(val)
        if words and words[-1] in terms:
            words.insert(0, words.pop())
        return words if as_list else self.delim.join(words)

    def remove(self, val, terms):
        """Removes terms from beginning or end of word"""
        words, as_list = self.words(val)
        while words and words[0] in terms:
            words = words[1:]
        while words and words[-1] in terms:
            words = words[:-1]
        # words = [w for w in words if w not in terms]
        return words if as_list else self.delim.join(words)

    def replace(self, val, terms):
        words, as_list = self.words(val)
        words = [terms.get(w, w) for w in words]
        return words if as_list else self.delim.join(words)

    def stem(self, val, stemmer):
        """Stems a value using the given stemmer"""
        if stemmer:
            if isinstance(val, list):
                return [self.stem(s, stemmer) for s in val]
            try:
                return stemmer.stem(val)
            except AttributeError:
                return stemmer.lemmatize(val)
        return val

    def similar(self, val, other, minlen=3, min_words=12, threshold=0.9):
        """Tests if two strings are similar"""
        words = re.findall(r"(\w+)", self(val, minlen=minlen))
        other_words = re.findall(r"(\w+)", self(other, minlen=minlen))
        if words != other_words:
            num_words = len(words) + len(other_words)
            words_common = len([w for w in words if w in other_words])
            other_common = len([w for w in other_words if w in words])
            ratio = (words_common + other_common) / num_words
            return (
                num_words > min_words
                and ratio > threshold
                and words[0] == other_words[0]
            )
        return True

    def validate(self, val):
        return bool(val.strip())

    def _std(self, val, pre=None, post=None, **kwargs):
        # val = 'test_simple_locality'
        if isinstance(val, (list, tuple)):
            return [self.std(s, pre=pre, post=post, **kwargs) for s in val]
        # Get job parameters
        params = self.get_params(kwargs)
        if params["allow_numbers"]:
            try:
                float(val)
                return val
            except ValueError:
                pass
        if not val or pd.isna(val):
            return val
        if not isinstance(val, str) or val.isnumeric():
            raise ValueError("Could not standardize '{}'".format(val))
        orig = val
        # Make basic changes to the string
        val = val.strip()
        if params["force_lower"]:
            val = val.lower()
        if params["force_ascii"]:
            val = unidecode(val)
        # Stopwords allowed if the whole string is made of them
        pattern = r"^(?:{0})([- ](?:{0}))*$".format("|".join(self.stopwords))
        if re.match(pattern, val.strip(), flags=re.I):
            return re.sub(r" +", self.delim, val)
        # Strip paired parentheses at the ends of the strings
        if val:
            open_paren = "([{"
            close_paren = ")]}"
            while (
                val
                and val[0] in open_paren
                and val[-1] == close_paren[open_paren.index(val[0])]
            ):
                val = val[1:-1]
        if params["strip_parentheticals"]:
            val = re.sub(r"\(.*?\)", "", val)
        # Remove apostrophes from words like Hawai'i
        val = re.sub(r"([a-z])'([a-z])", r"\1\2", val)
        # Replace ampersands with and
        val = re.sub(r" *& *", " and ", val)
        # Split val into words
        words = []
        # for i, word in enumerate(re.split(r'\W', val)):
        pattern = r"\b[A-Za-z0-9+]+(?:\.|\b)"
        for i, word in enumerate(re.findall(pattern, val.replace("_", "-"))):
            period = "." if word.endswith(".") else ""
            if params["force_alphanumeric"]:
                word = "".join([c for c in word if c.isalnum()])
            if not word:
                continue
            # Standardize endings
            word = self._replace_endings(word, params["replace_endings"])
            word = self.stem(word, self.stemmer)
            word = params["replace_words"].get(word + period, word)
            # Skip words that are too short or stopwords
            first_word = i == 0
            last_word = i == len(words) - 1
            if (
                not word
                or not word.isnumeric()
                and len(word) < params["minlen"]
                or word in params["stopwords"]
                or not i
                and word in params["strip_first"]
                or i == (len(words) - 1)
                and word in params["strip_last"]
            ):
                continue
            words.append(word)
        if params["move_to_beginning"]:
            words = self.move_if_last(words, params["move_to_beginning"])
        if params["move_to_end"]:
            raise AttributeError("move_to_end not implemented")
            # words = self.move(words, params['move_to_end'])
        if params["sort_terms"]:
            words.sort()
        result = self.delim.join(words)
        if self.validate(result):
            return result
        raise ValueError(f"Could not standardize {repr(orig)} (result={repr(result)})")

    def _replace_endings(self, word, endings):
        for key in sorted(endings, key=len):
            if word.endswith(key):
                return word[: -len(key)] + endings[key]
        return word


def std_names(names, std_func):
    st_names = []
    for name in names:
        try:
            st_names.append(std_func(name))
        except ValueError as e:
            logger.warning(str(e))
    return set(st_names)
