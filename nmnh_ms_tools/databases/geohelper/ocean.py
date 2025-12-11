"""Builds and queries tiles representing the global ocean"""

import re
from collections import namedtuple
from functools import cache

import pandas as pd
import geopandas as gpd
from shapely import Geometry, union_all, wkb
from shapely.geometry import Polygon

from .database import Session, OceanTiles
from ..natural_earth import Session as NaturalEarthSession, Ocean
from ...tools.geographic_operations.geometry import GeoMetry


Tile = namedtuple("Tile", ["geom", "name"])


class OceanQuery:
    """Tiles and queries the global ocean"""

    # Deferred but not with LazyAttr
    gdf = None

    @staticmethod
    def std_ocean(name):
        """Extracts the standardized name of an ocean"""
        name = name.lower()
        name = name.replace("ocean", "").strip()
        name = re.sub(r"\bn\b", "north", name)
        name = re.sub(r"\bs\b", "south", name)
        return name.title()

    def query(self, geom=None, ocean=None):
        """Identifies tiles matching a geometry"""

        # Build the reference dataframe the first time it is needed
        if self.gdf is None:
            self._build_gdf()

        gdf = self.gdf.copy()
        if geom is not None:
            if not isinstance(geom, Geometry):
                geom = union_all(GeoMetry(geom).geom.to_crs(4326))
            gdf = gdf[gdf.intersects(geom)]
        if ocean is not None:
            gdf = gdf[gdf["ocean"] == self.std_ocean(ocean)]
        return gdf

    def intersection(self, geom, ocean=None):
        if not isinstance(geom, Geometry):
            geom = union_all(GeoMetry(geom).geom.to_crs(4326))
        gdf = self.query(geom=geom, ocean=ocean)
        return gpd.GeoDataFrame(geometry=[union_all(gdf.intersection(geom))], crs=4326)
        gs = [union_all(gdf.intersection(geom))]

    def _build_gdf(self):
        """Retrieves and indexes ocean tiles"""
        session = Session()
        query = session.query(OceanTiles).order_by(OceanTiles.id)
        if not any(query):
            raise ValueError("ocean database is empty")
        rows = []
        for row in query:
            rows.append({"ocean": row.ocean, "coast": row.coast, "wkb": row.geometry})
        df = pd.DataFrame(rows)
        gs = gpd.GeoSeries.from_wkb(df["wkb"])
        self.__class__.gdf = gpd.GeoDataFrame(df, geometry=gs, crs=4326)
        return self.gdf
