"""Match volcanoes and volcanic features to GVP database"""

import re
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from ...config import CONFIG, DATA_DIR
from ...utils import LazyAttr, as_list


class GVPVolcanoes:
    """Search for GVP volcano information"""

    # Deferred class attributes are defined at the end of the file
    df = None

    @cached_property
    def localities(self):
        localities = []
        for key in ["country", "ocean"]:
            for val in self.df[key].unique():
                if val:
                    localities.extend(re.split(r"\s*\|\s+", val))
        return set(localities)

    def find(
        self, term: str = None, kind: str = None, locality: str | list[str] = None
    ) -> pd.DataFrame:
        """Finds the volcano, feature, or province matching the given criteria

        Parameters
        ----------
        term : str, optional
            the name or GVP number for a volcano or volcanic feature
        kind : str, optional
            the type of feature. One of 'volcano', 'feature', or 'province'.
        locality : str | list[str], optional
            the name of a country or ocean

        returns
        -------
        pd.DataFrame
            Dataframe with matching records
        """
        matches = self.df

        if term:
            term = _index_term(term)
            # Restrict searchs on volcano numbers to volcanoes
            if kind is None and term.isnumeric():
                kind = "volcano"
            matches = matches[matches["index"] == term]

        if locality is not None:
            cond = None
            for loc in as_list(locality):
                if loc not in self.localities:
                    raise ValueError(f"Unrecognzied locality: {repr(loc)}")
                for key in ("country", "ocean"):
                    if cond is None:
                        cond = matches[key].str.contains(rf"\b{loc}\b")
                    else:
                        cond |= matches[key].str.contains(rf"\b{loc}\b")
            matches = matches[cond]
        if kind is not None:
            kind = {
                "feature": "GVPSUB",
                "province": "GVPPROV",
                "volcano": "GVPVLC",
            }[kind]
            matches = matches[matches["site_kind"] == kind]
        del matches["index"]
        return matches.drop_duplicates()

    def find_volcano(
        self, term: str = None, locality: str | list[str] = None
    ) -> pd.Series:
        """Finds the volcano matching for the given criteria

        Parameters
        ----------
        term : str, optional
            the name or GVP number for a volcano or volcanic feature
        locality : str | list[str], optional
            the name of a country or ocean

        returns
        -------
        pd.Series
            series with volcano data in GeoNames format
        """
        matches = self.find(term, locality=locality)
        if len(matches) == 1:
            match = matches.iloc[0]
            # If the match isn't a volcano, use the volcano number to get it
            if match.site_kind != "GVPVLC":
                match = self.find(match.site_num, kind="volcano").iloc[0]
            return match
        raise ValueError(
            f"Could not find exactly one volcano matching {repr(term)} (locality={repr(locality)})"
        )


def _index_term(name: str) -> str:
    """Standardizes term for serarch"""
    if not name:
        return ""
    name = str(name)
    if name.count(",") == 1:
        name = " ".join((s.strip() for s in name.split(",")[::-1]))
    name = name.lower()
    name = re.sub(r"\b(saint|santa|ste)\b", "st", name)
    name = re.sub(r"\b(mount(ain)?|mt)\b", "", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    return name


def _read_dataframe():
    """Reads the dataframe with GVP volcano data"""
    path = Path(DATA_DIR) / "gazetteers" / "global_volcanism_program_volcanoes.csv"
    df = pd.read_csv(path, dtype=str, comment="#")
    rows = []
    for _, row in df.iterrows():
        vals = [row["site_names"]]
        if row["site_kind"] == "GVPVLC":
            vals.append(row["site_num"])
        if not pd.isna(row["synonyms"]):
            vals.extend(re.split(r"\s+\|\s+,", row["synonyms"]))
            row["synonyms"] = np.nan
        for val in vals:
            if val and not pd.isna(val):
                row_ = row.to_dict()
                row_["index"] = val
                rows.append(row_)
    df = pd.DataFrame(rows)
    df["index"] = df["index"].apply(_index_term)
    df = df.fillna("")
    return df


# Define deferred class attributes
LazyAttr(GVPVolcanoes, "df", _read_dataframe)
