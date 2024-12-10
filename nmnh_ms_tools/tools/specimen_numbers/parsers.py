import logging
import os
import re

from .specnum import SpecNum, expand_range, is_spec_num, parse_spec_num

logger = logging.getLogger(__name__)


class Parser:

    def __init__(self, clean=True, require_code=True, hints=None, parse_order=None):
        self._parse_order = ["spec_num_strict", "range", "short", "suffix", "spec_num"]
        if parse_order:
            self.parse_order = parse_order
        self._hints = {}
        if hints:
            self.hints = hints
        self.clean = clean
        self.min_num = 1000
        self.max_diff = 100
        self.max_suffix = 10000
        self.require_code = require_code
        if self.clean:
            self.min_num = 1
            self.max_diff = 1e10

    @property
    def parse_order(self):
        return self._parse_order

    @parse_order.setter
    def parse_order(self, vals):
        if self._parse_order and set(vals) - set(self._parse_order):
            raise ValueError(
                f"parse_order can only include the following values: {self._parse_order}"
            )
        self._parse_order = vals

    @property
    def hints(self):
        return self._hints

    @hints.setter
    def hints(self, val):
        unrecognized = set(val.values()) - set(self.parse_order)
        if unrecognized:
            raise ValueError(
                f"Each hint must be one of the following values: {self._parse_order}"
            )
        self._hints.clear()
        self._hints = val

    def parse_spec_nums(self, val):
        """Parses a single representation of a catalog number or range"""
        extracted = self.extract(val)
        if len(extracted) == 1:
            for key, vals in extracted.items():
                if key == self.prepare(val):
                    return [parse_spec_num(s) for s in vals]
        raise ValueError(f"Could not parse {repr(val)}")

    def extract_code(self, val):
        """Extracts the museum code from a catalog number"""
        pattern = r"\(?[A-Z]{4}\)?"
        try:
            code = re.search(pattern, val).group()
        except AttributeError:
            return None, val
        else:
            val = re.sub(pattern, "", val).strip()
            return code.strip("()"), val

    def delimit_codes(self, val):

        # Split on trailing museum codes
        parts = re.findall(r".*?\([A-Z]{4}\)", val)
        if len(parts) > 1:
            return "; ".join([p.lstrip(",;| ") for p in parts])

        # Split on parenthicals
        parens = re.split(r"(\(.*?\))", val)
        if len(parens) > 1:
            parts = []
            for paren in parens:
                parts.append(self.delimit_codes(paren.strip("() ")))
            return "; ".join([p for p in parts if p])

        # Split on leading museum codes
        parts = re.findall(r"[A-Z]{4}.+?(?=[A-Z]{4}|$)", val)
        return "; ".join([p.rstrip(",;| ") for p in parts])

    def prepare(self, val):
        if not re.search(r"\d", val):
            raise ValueError(f"No numbers found in {repr(val)}")

        orig = val
        logger.debug(f"Original value is {repr(val)}")
        val = val.lstrip().rstrip("|;,/- ")

        # Guess the primary delimiter
        delim = ";"
        if ";" not in val:
            if "|" in val:
                delim = "|"
            elif "," in val or re.search(r"(\band\b|&)", val):
                delim = ","

        # Standardize format of common elements
        val = re.sub(r"(num\.?|number|#)", "no.", val)
        val = re.sub(r"[,;]? *(and|&) *", " & ", val)
        val = re.sub(r"\( +", "(", val)
        val = re.sub(r" +\)", ")", val)

        # Standardize format of ranged suffixes to 12345/1-3
        val = re.sub(r"(\d+)/ *(\d+|[A-z]) *\- *(\d+|[A-z])$", r"\1/\2-\3", val)
        val = re.sub(
            r"(\d+)\- *(\d+|[A-z]) *(?:to|through|thru) *(\d+|[A-z])$", r"\1/\2-\3", val
        )
        val = re.sub(
            r"(\d+)([A-z]) *(?:to|through|thru|\-) *([A-z])$", r"\1/\2-\3", val
        )
        val = re.sub(r"(\d+)[\- ]*\((\d+|[A-z]) *\- *(\d+|[A-z])\)$", r"\1/\2-\3", val)

        # Perform additional clean up for clean sources
        if self.clean:
            val = re.sub(r" *([-;/\|]+) *", r"\1", val)  # strip spaces around delims

        delimited = self.delimit_codes(val)
        if delimited:
            val = delimited

        # Strip unpaired trailing parenthesis
        if ")" in val and "(" not in val:
            val = val.rstrip(")")

        if val != orig:
            logger.debug(f"Cleaned input {repr(orig)} as {repr(val)}")

        return val

    def extract(self, val):

        orig = val
        val = self.prepare(val)

        # Parse the cleaned value in its entirety as a fallback
        fallback = None
        if self.clean:
            try:
                spec_num = parse_spec_num(val, fallback=True)
            except ValueError:
                pass
            else:
                if spec_num.is_valid(min_num=self.min_num, max_diff=self.max_diff):
                    fallback = [str(spec_num)]

        # Split on hard delimiters and evaluate soft delimiters
        vals = []
        for val in re.split(r" *[;\|] *", val):
            vals.append(val)
        logger.debug(f"Split {repr(val)} into {repr(vals)}")

        extracted = {}
        current_code = ""
        for val in vals:

            # Drop values that don't include numbers
            if not re.search(r"\d", val):
                continue

            # Extract the museum code for the current segment
            code, val = self.extract_code(val)
            if code:
                current_code = code
            elif self.require_code:
                raise ValueError(f"No museum code: {val}")

            # Interpret runs of numbers separated by spaces
            if not self.clean:
                val_ = self.squash(val)
                if val != val_:
                    logger.debug(f"Squashed {repr(val)} as {repr(val_)}")
                    val = val_

            # Split on soft delimiters and group parts
            parts = re.split(r"([,/& ]+)", val)
            parts_ = [(None, parts.pop(0))]
            while parts:
                parts_.append((parts.pop(0), parts.pop(0)))

            try:
                spec_nums = self.group(parts_)
            except ValueError:
                logger.exception("Evaluation failed")
                if fallback:
                    logger.debug(
                        f"Falling back to parse of complete value"
                        f" ({repr(fallback[-1])} from {repr(val)})"
                    )
                    return {orig: fallback}
                else:
                    logger.warning(f"Failed to parse {repr(val)}")
                    extracted[val] = []
            else:
                for spec_num in spec_nums:
                    if spec_num.is_valid(min_num=self.min_num, max_diff=self.max_diff):
                        spec_num = spec_num.modcopy(code=code)
                        extracted.setdefault(val, []).append(str(spec_num))
                        logger.debug(
                            f"Extracted {repr(str(spec_num))} from {repr(val)}"
                        )

        return extracted

    def group(self, parts, join_with="; ", fix_spacing=False):
        """Group list into catalog numbers"""

        # Clean OCR spacing issues
        if fix_spacing:
            parts = self.squash(parts, join_with=join_with)

        vals = []
        base = None
        hint = None
        for delim, part in parts:
            parsed, base, hint = self.evaluate(part, base, delim, hint)
            # Remove previous value if next value uses it as a base number (for
            # example, if 12345 is followed by 12345-1).
            if vals and parsed[0].parent == vals[-1]:
                vals.pop(-1)
            vals.extend(parsed)

        return vals

    def squash(self, val, join_with="; "):
        """Combines list of values with erroneous spaces"""

        if not any(val):
            return ""

        if isinstance(val, list):
            val = join_with.join(val)

        orig = val

        vals = re.split(r"[^A-z0-9\-,]+", orig)

        # Get all possible combinations of values
        combined = []
        for i, val in enumerate(vals):

            # Strip anything before a delimiter
            try:
                val = re.search("[^-,;/]+$", val).group()
            except AttributeError:
                pass

            for val_ in vals[i + 1 :]:
                if val_.isnumeric():
                    val += val_
                    combined.append(val)
                else:
                    # Strip anything after a delimiter
                    if re.search(r"[-,;/]", val_):
                        try:
                            val += re.match("[^-,;/]+", val_).group()
                            combined.append(val)
                        except AttributeError:
                            pass
                        break

        # Limit to parseable candidates
        candidates = []
        for val in combined:
            if is_spec_num(
                re.sub(r"[A-z\-]+$", "", val),
                min_num=self.min_num,
            ):
                candidates.append(val)
        if not candidates:
            return orig

        # Limit to candidates similar to first candidate
        results = [candidates.pop(0)]
        for candidate in candidates:
            common = os.path.commonprefix([results[-1], candidate])
            if len(common) > 2:
                results.append(candidate)

        # Look for combinations of equal length
        num_digits = len(re.findall(r"\d", "".join(vals)))
        for i in range(num_digits, 0, -1):
            matches = [s for s in results if len(s) == i]
            if len("".join(matches)) == num_digits:
                results = matches

        val = orig
        for squashed in results:
            val = re.sub(" *".join(squashed), squashed, val, 1)

        return val

    def evaluate(self, val, base=None, delim=None, hint=None):
        funcs = {
            "range": self.evaluate_range,
            "short": self.evaluate_short,
            "spaced": self.evaluate_spaced,
            "spec_num": self.evaluate_spec_num,
            "spec_num_strict": self.evaluate_spec_num_strict,
            "suffix": self.evaluate_suffix,
        }

        # Tweak parse order by moving specimen number to the end for most delims
        parse_order = self.parse_order[:]

        if hint is not None:
            parse_order.insert(0, parse_order.pop(parse_order.index(hint)))

        if self.clean and delim:
            parse_order = {
                "": [s for s in parse_order if s != "spec_num"] + ["spec_num"],
                "&": parse_order,
                ",": [s for s in parse_order if s != "spec_num"] + ["spec_num"],
                "/": [s for s in parse_order if s != "spec_num"] + ["spec_num"],
            }[delim.strip()]

        try:
            parse_order.insert(0, self.hints[delim.strip()])
        except (AttributeError, KeyError):
            pass

        vals = []
        for key in parse_order:
            try:
                vals.extend(funcs[key](val, base))
            except ValueError:
                pass
            else:
                vals = [s for s in vals if is_spec_num(s, min_num=self.min_num)]
                if vals:
                    logger.debug(
                        f"Evaluated {repr(val)} (base={repr(base)}) as {repr(vals)} (key={repr(key)})"
                    )
                    # Update base
                    spec_num = vals[-1].modcopy(suffix="")
                    new_base = str(spec_num)
                    if base != new_base:
                        logger.debug(
                            f"Updated base from {repr(base)} to {repr(new_base)}"
                        )
                        base = new_base
                    return vals, base, key

            logger.debug(f"Could not evaluate {repr(val)} as {repr(key)}")

        raise ValueError(f"Could not interpret {repr(val)} (base={repr(base)})")

    def evaluate_range(self, val, base=None):
        """Interprets value as a range"""

        # Interprets ranges that look like catalog numbers
        try:
            range_ = parse_spec_num(val).as_range(max_diff=self.max_diff)
        except ValueError:
            try:
                range_ = expand_range(val, max_diff=self.max_diff)
            except ValueError:
                raise ValueError(f"Not a range: {repr(val)} (base={repr(base)})")
        else:
            # Toss non-ranges
            if len(range_) == 1:
                raise ValueError(f"Not a range: {repr(val)} (base={repr(base)})")

            # Is the parsed catalog number likely to be a suffix? For example,
            # 1-2 may evaluate as a specimen number range if min_num is low enough.
            if not range_[0].prefix:
                try:
                    self.evaluate_spec_num_strict(str(range_[0]))
                except ValueError:
                    range_ = [str(s.number) for s in range_]
                else:
                    return range_

        vals = []
        for val in range_:
            if isinstance(val, SpecNum) and val.number and val.suffix:
                vals.append(val)
            else:
                # HACK: Provide delim so that evaluate checks spec_num last
                val, base, _ = self.evaluate(str(val), base, delim="/")
                vals.extend(val)
        return vals

    def evaluate_short(self, val, base=None):
        """Interprets value as a shorthand range"""

        # If range, use the first half for the evaluation, then tack the rest
        # back on at the end
        try:
            val, suffix = val.split("-", 1)
        except ValueError:
            suffix = ""

        if (
            base
            and len(str(base)) > len(str(val))
            and (
                base[-1].isalpha()
                and val.isalpha()
                or base[-1].isnumeric()
                and val.isnumeric()
            )
        ):
            stem = base[: -len(val)]
            last = base[-len(val) :]

            try:
                val_higher = int(last) < int(val)
            except ValueError:
                val_higher = last < val
            if val_higher:
                return parse_spec_num(f"{stem}{val}-{suffix}".rstrip("-")).as_range(
                    max_diff=self.max_diff
                )

        raise ValueError(f"Not shorthand: {repr(val)} (base={repr(base)})")

    def evaluate_spaced(self, val, base=None):
        """Interprets value as a specimen number with incorrect spacing"""
        if base and not self.clean and val.isnumeric():
            try:
                return [parse_spec_num(base + val)]
            except ValueError:
                pass
        raise ValueError(f"Not incorrect spacing: {repr(val)} (base={repr(base)})")

    def evaluate_suffix(self, val, base=None):
        """Interprets value as a suffix"""
        orig = val
        if base:
            # Capture the delimiter if part of the value
            try:
                delim = re.match(r"[-,/ ]+", val).group()
            except AttributeError:
                delim = "-"
            finally:
                val = val.lstrip(delim)
                if val.isalpha():
                    delim = ""

            # NOTE: This intentionally does not try to expand short ranges
            try:
                return [self.evaluate_spec_num(f"{base}{delim}{val}")[0]]
            except ValueError:
                pass

        raise ValueError(f"Not a suffix: {repr(orig)} (base={repr(base)})")

    def evaluate_spec_num(self, val, base=None):
        """Interprets value as a specimen number"""
        try:
            spec_num = parse_spec_num(val)
            if spec_num.is_valid(min_num=self.min_num, max_diff=self.max_diff):
                return [spec_num]
        except ValueError:
            pass

        raise ValueError(f"Not a specimen number: {repr(val)}")

    def evaluate_spec_num_strict(self, val, base=None):
        """Interprets value as a well-formed, non-range specimen number"""
        try:
            spec_num = parse_spec_num(val)
            if spec_num.is_valid(min_num=1000) and not spec_num.is_range(
                max_diff=self.max_diff
            ):
                return [spec_num]
        except ValueError:
            pass

        raise ValueError(f"Not a specimen number (strict): {repr(val)}")
