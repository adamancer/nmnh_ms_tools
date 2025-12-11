from pathlib import Path

import pandas as pd


class PersistentLookup:

    dfs = {}

    def __init__(self, cache_name="lookup.csv"):
        self.cache_name = cache_name
        self._save_on_change = True

    @property
    def path(self):
        return Path(self.cache_name).resolve()

    @property
    def df(self):
        df = self.__class__.dfs.get(self.path)
        if df is None:
            try:
                df = pd.read_csv(self.cache_name).set_index("key")
                self.__class__.dfs[self.path] = df
            except FileNotFoundError:
                pass
        return df

    @df.setter
    def df(self, df):
        self.__class__.dfs[self.path] = df

    def __str__(self):
        return str(dict(zip(self.df.index, self.df["value"])))

    def __repr__(self):
        return repr(dict(zip(self.df.index, self.df["value"])))

    def __setitem__(self, key, val):
        df = pd.DataFrame([{"key": key, "value": val}]).set_index("key")
        if self.df is None:
            self.df = df
        else:
            try:
                self.df = pd.concat([self.df, df], verify_integrity=True)
            except ValueError:
                self.df.loc[self.df.index == key, "value"] = val
        self.save()

    def __getitem__(self, key):
        if self.df is None:
            raise KeyError(repr(key))
        try:
            return self.df[self.df.index == key].iloc[0]["value"]
        except IndexError:
            raise KeyError(repr(key))

    def __delitem__(self, key):
        if self.df is None:
            raise KeyError(repr(key))
        self.df = self.df.drop(index=key)
        self.save()

    def update(self, *args, **kwargs):
        self._save_on_change = False
        for key, val in dict(*args, **kwargs).items():
            self[key] = val
        self._save_on_change = True
        self.save()

    def save(self):
        if self._save_on_change:
            self.df.to_csv(self.cache_name, encoding="utf-8-sig")
