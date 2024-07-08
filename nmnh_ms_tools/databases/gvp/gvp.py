import glob
import os
import re
import warnings
from collections import namedtuple

import pandas as pd
from unidecode import unidecode

from ...config import CONFIG


Volcano = namedtuple(
    "Volcano", ["name", "kind", "country", "gvp_volcano", "gvp_number"]
)


class GVPVolcanoes:
    def __init__(self):
        self._df = None

    @property
    def df(self):
        if self._df is None:
            self._init_db()
        return self._df

    def __getitem__(self, key):
        rows = self.df[
            (self.df["Kind"] == "volcano") & (self.df["Volcano Number"] == str(key))
        ]
        if len(rows) == 1:
            return self._row_to_volc(rows.iloc[0])
        raise KeyError(f"'{key}'")

    def find(self, val, country=None):
        matches = []

        val = str(val)
        if val.isnumeric():
            query = (self.df["Kind"] == "volcano") & (self.df["Volcano Number"] == val)
        else:
            query = self.df["_Indexed"] == self.index_name(val)

        if country is not None:
            query = query & (self.df["Country"] == country)

        for _, row in self.df[query].iterrows():
            matches.append(self._row_to_volc(row))

        # Try a country-less search if no matches found
        if not matches and country is not None:
            try:
                matches = self.find(val)
            except ValueError:
                pass
            else:
                if len(matches) != 1:
                    matches = []

        if not matches or (val.isnumeric() and len(matches) > 1):
            raise ValueError(f"'{val}' (country={country})")

        return matches

    @staticmethod
    def format_name(name):
        if name.count(",") == 1:
            name = " ".join((s.strip() for s in name.split(",")[::-1]))
        return name

    def index_name(self, name):
        name = self.format_name(name).lower()
        name = re.sub(r"^(mount|mt)\b", "", name)
        name = re.sub(r"\b(mount(ain)?)", "", name)
        name = re.sub(r"[^a-z0-9]", "", name)
        return name

    def _init_db(self):
        dfs = []
        for path in glob.iglob(CONFIG["data"]["gvp"]):
            df = pd.read_excel(path, header=1, dtype=str)
            df["Source"] = os.path.basename(path)
            dfs.append(df)
        df = pd.concat(dfs)
        df["Volcano Name"] = [self.format_name(s) for s in df["Volcano Name"]]

        kinds = []
        for _, row in df.iterrows():
            if not pd.isna(row["Country"]):
                kinds.append("volcano")
            elif row["Primary Volcano Type"].startswith("Synonym"):
                kinds.append("synonym")
            else:
                kinds.append("feature")
        df["Kind"] = kinds

        # Map countries for features and synonyms
        volc = df[~pd.isna(df["Country"])]
        for vnum, country in dict(zip(volc["Volcano Number"], volc["Country"])).items():
            df.loc[df["Volcano Number"] == vnum, "Country"] = country

        df["_Indexed"] = [self.index_name(s) for s in df["Volcano Name"]]
        self._df = df

    def _row_to_volc(self, row):
        volc_name = self.df[
            (self.df["Kind"] == "volcano")
            & (self.df["Volcano Number"] == row["Volcano Number"])
        ]["Volcano Name"].iloc[0]
        return Volcano(
            row["Volcano Name"],
            row["Kind"],
            row["Country"],
            volc_name,
            row["Volcano Number"],
        )
