import json
import os
import re


class Preparation:
    map_path = os.path.expanduser(r"~\data\nmnh_ms_tools\preps\prepmap.json")
    try:
        with open(map_path) as f:
            _map = json.load(f)
    except FileNotFoundError:
        _map = {}
    handle_new = "skip"

    def __init__(self, val):
        if isinstance(val, Preparation):
            val = val.verbatim
        self.verbatim = val
        self.std = self._map_prep()

    def __str__(self):
        return "; ".join(self.std)

    def __repr__(self):
        return f"{self.__class__.__name__}(std={repr(self.std)}, verbatim={repr(self.verbatim)})"

    def __contains__(self, val):
        return val in set(self.std)

    def __and__(self, other):
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        return set(self.std) & set(other.std)

    def reload(self):
        with open(self.__class__.map_path) as f:
            self.__class__._map = json.load(f)

    def append(self, val):
        if val and val not in self.std:
            self.std.append(val)
            self.std.sort()

    def _map_prep(self):
        changed = False
        preps = []
        for prep in self._split(self.verbatim):
            preps.append(self._map.get(prep, "other"))
            # Handle unmapped terms
            if preps[-1] == "other":
                if self.handle_new == "map":
                    self._map[prep] = input(f"{prep}: ")
                    print("--------")
                    preps[-1] = self._map[prep]
                    changed = True
                elif self.handle_new == "raise":
                    raise ValueError(f"Unmapped prep: {prep}")
                elif self.handle_new == "skip":
                    preps[-1] = prep
                else:
                    raise ValueError(
                        "handle_unrecognized must be 'skip', 'raise', 'map', or 'overwrite'"
                    )

        self.std = []
        for prep in preps:
            self.std.extend(prep.split("; "))

        if changed:
            self.save()

        return self.std

    def update_mapping(self):
        self.std = []
        for prep in self._split(self.verbatim):
            self._map[prep] = input(f"{prep}: ")
            print("--------")
            self.std.extend(self._map[prep].split("; "))

        self.save()

        return self.std

    def save(self, sort=False):
        self.std = sorted(set([s for s in self.std if s]))
        if sort:
            self._map = dict(sorted(self._map.items(), key=lambda kv: kv[0]))
        with open(self.map_path, "w") as f:
            json.dump(self._map, f, sort_keys=False, indent=2)

    def sort(self):
        std = sorted()

    @staticmethod
    def _split(val):
        preps = [
            s.strip(".,;: ")
            for s in re.split(r"(?: +and,? +| *& *| *\+ *|[,;] +|\n+)", val.lower())
        ]
        return [p for p in preps if p]
