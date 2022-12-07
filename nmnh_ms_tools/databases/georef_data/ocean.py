"""Builds and queries tiles representing the global ocean"""
import re
from collections import namedtuple

from shapely import wkb
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .database import Session, OceanTiles
from ..natural_earth import Ocean
from ...tools.geographic_operations.geometry import GeoMetry


Tile = namedtuple("Tile", ["geom", "name"])


class OceanQuery:
    """Tiles and queries the global ocean"""

    _tree = None

    def __init__(self):
        self.oceans = {}
        if self._tree is None:
            self.__class__._tree = self.build_tree()

    @staticmethod
    def std_ocean(name):
        """Extracts the standardized name of an ocean"""
        name = name.lower()
        name = name.replace("ocean", "").strip()
        name = re.sub(r"\bn\b", "north", name)
        name = re.sub(r"\bs\b", "south", name)
        return name.title()

    def query(self, geom, ocean=None):
        """Identifies tiles matching a geometry"""
        if geom.crosses_180():
            tiles = []
            for geom_ in geom.subshapes.geoms:
                tiles.extend(self._tree.query(geom_))
            return tiles
        # Filiter results by ocean if given
        tiles = self._tree.query(geom)
        if ocean:
            ocean = self.std_ocean(ocean)
            filtered = [t for t in tiles if ocean in self.oceans.get(t.name, "")]
            if filtered:
                return filtered
        return tiles

    def intersection(self, geom):
        """Calculates the union of the tiles returned by query"""
        return unary_union(self.query(geom))

    def build_tree(self):
        """Retrieves and indexes ocean tiles"""
        session = Session()
        query = session.query(OceanTiles)
        if not any(query):
            self.generate_tiles()
            session.query(OceanTiles)
        tiles = []
        for row in query:
            geom = wkb.loads(row.geometry)
            geom.name = row.id
            tiles.append(geom)
            if row.ocean:
                self.oceans[row.id] = row.ocean
        session.close()
        return STRtree(tiles)

    @staticmethod
    def generate_tiles(interval=15):
        """Calculates a set of tiles spaced by a given interval"""
        session = Session()
        shape = wkb.loads(session.query(Ocean).first().GEOMETRY)
        for x1 in range(-180, 180, interval):
            x2 = x1 + interval
            for y1 in range(-90, 90, interval):
                y2 = y1 + interval
                polygon = Polygon([(x1, y1), (x1, y2), (x2, y2), (x2, y1)])
                print([(x1, y1), (x1, y2), (x2, y2), (x2, y1)])
                geom = polygon.intersection(shape)
                try:
                    for geom in geom.geoms:
                        # geom = geom.simplify(0.1)
                        tile = OceanTiles(geometry=wkb.dumps(geom), coast=True)
                        session.add(tile)
                except AttributeError:
                    # geom = geom.simplify(0.1)
                    tile = OceanTiles(geometry=wkb.dumps(geom), coast=True)
                    session.add(tile)
        session.commit()
        session.close()

    @staticmethod
    def map_tiles():
        """Allows user to map tiles to an ocean"""
        session = Session()
        rows = session.query(OceanTiles).order_by(OceanTiles.id)
        tiles = [wkb.loads(row.geometry) for row in rows]
        last = None
        for i, row in enumerate(rows):
            if row.ocean is None:
                minx, miny, maxx, maxy = tiles[i].bounds
                if (maxy - miny) < 1 and (maxx - minx) < 1:
                    continue
                if maxy <= -60:
                    ocean = "Southern"
                elif miny >= 75:
                    ocean = "Arctic"
                else:
                    start = 0 if i < 100 else i - 100
                    end = i + 100
                    print("lats:", miny, maxy)
                    print("lngs:", minx, maxx)
                    GeoMetry(tiles[i]).draw(tiles[start:end])
                    ocean = input("ocean (last={}): ".format(last))
                    if not ocean:
                        ocean = last
                    last = ocean
                session.merge(OceanTiles(id=row.id, ocean=ocean))
                session.commit()
            else:
                last = row.ocean
        # Map North and South halves of the Atlantic and Pacific
        for name in ("Atlantic", "Pacific"):
            term = "%{}%".format(name)
            pattern = r"^.*{}$".format(name)
            for row in session.query(OceanTiles).filter(OceanTiles.ocean.like(term)):
                geom = wkb.loads(row.geometry)
                minx, miny, maxx, maxy = geom.bounds
                mask = "North {}" if miny >= 0 else "South {}"
                oceans = [s.strip() for s in row.ocean.split("|")]
                oceans = [re.sub(pattern, mask.format(name), o) for o in oceans]
                session.merge(OceanTiles(id=row.id, ocean=" | ".join(oceans)))
            session.commit()
