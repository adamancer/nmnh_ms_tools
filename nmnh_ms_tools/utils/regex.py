import re


class RegexHelper:

    def __init__(self):
        self.units = {
            "and": r"( and | ?[&+] ?)",
            "cap_word": r"([A-Z][a-z]+(-[A-z]+)?)",
            "conj": r"(de|del|des|do|du|el|la|los|of( the)?|van|von)",
            "initials": r"([A-Z]\.?( ?[A-Z]\.?){0,3})",
            "name": r"((O'|Ma?c)?[A-Z][a-z]+(-[A-z]+)*('s)?)",
            "num_signs": r"(#|no\.?|number)"
        }
        patterns = self.units.copy()
        phrases = [
            ("unit", r"({name}(( {num_signs})? \d+)?)"),
            ("feature", r"(({initials} )?{unit}(( {conj}){0,3} {unit}){0,3})"),
            ("highway", (
                r"((({initials}[- ])({name} )?\d+|{name}[- ]\d+)[A-Z]?)")
            ),
            ("road", r"({highway}|{feature})"),
        ]
        for key, pattern in phrases:
            patterns[key] = self._prep_pattern(pattern, **patterns)
        # Unexpected capture groups are a big headache when processing regexes,
        # so convert all groups to non-capture groups.
        self.patterns = {k: v.replace('(', '(?:') for k, v in patterns.items()}


    def _prep_pattern(self, pattern, **kwargs):
        """Builds a regex pattern by substituting in defined patterns"""
        if not kwargs:
            kwargs = self.patterns
        pattern = pattern.replace(' {and} ', '{and}')
        pattern = re.sub(r"{(\d+(,\d+)?)}", "{{" + r"\1" + "}}", pattern)
        return pattern.format(**kwargs)


    def compile(self, pattern, *args, **kwargs):
        return re.compile(self._prep_pattern(pattern), *args, **kwargs)


    def match(self, pattern, *args, **kwargs):
        return re.match(self._prep_pattern(pattern), *args, **kwargs)


    def search(self, pattern, *args, **kwargs):
        return re.search(self._prep_pattern(pattern), *args, **kwargs)


    def sub(self, pattern, *args, **kwargs):
        return re.sub(self._prep_pattern(pattern), *args, **kwargs)




RE = RegexHelper()
