"""Defines class to handle projection of lat/long data"""

import logging
import re
import warnings
from functools import cached_property
from math import isclose

import geopandas as gpd
import numpy as np
from shapely import union_all, wkb, wkt, to_wkt, to_wkb
from shapely.affinity import translate
from shapely.geometry.base import BaseGeometry
from shapely.geometry import (
    GeometryCollection,
    Point,
    Polygon,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    box,
)
from shapely.ops import nearest_points, split

from xmu import EMuLatitude, EMuLongitude, EMuRecord, EMuRow

from ....databases.cache import CacheDict
from ....utils import (
    LazyAttr,
    as_list,
    custom_copy,
    custom_eq,
    del_immutable,
    draw_polygon,
    get_dist_km,
    mutable,
    parse_measurement,
    set_immutable,
    similar,
    sort_geoms,
    subhorizontal,
    subvertical,
    translate_with_uncertainty,
    trim,
    truncate,
)


logger = logging.getLogger(__name__)


class GeoMetry:
    """Subclasses NaiveGeometry to handle common projection operations"""

    # Deferred class attributes are defined at the end of the file
    geom_cache = None
    op_cache = None

    # Normal class attributes
    lat_lon_mask = "+proj=longlat +lat_0={lat:.1f} +lon_0={lon:.1f} +ellps=WGS84 +datum=WGS84 +no_defs"
    lat_lon_bounds = (-180, -90, 180, 90)

    equal_area_mask = "+proj=eck4 +lat_0={lat:.1f} +lon_0={lon:.1f} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    equal_area_bounds = (-16921202.92, -8460500, 16921202.92, 8460500)

    cached = (
        "x",
        "y",
        "meridians",
        "lat",
        "lon",
        "coords",
        "lat_lons",
        "centroid",
        "convex_hull",
        "center",
        "area",
        "bounds",
        "radius_km",
        "height_km",
        "width_km",
        "as_equal_area",
        "as_lat_lon",
        "as_wgs84",
        "envelope",
        "ellipse",
        "main",
        "polygon",
        "drawable",
        "wkb",
        "wkt",
    )

    def __init__(self, geom=None, crs=None, radius_km=0, validate=True):

        with mutable(self):

            # Metadata
            self.name = None
            self.parents = []
            self.modifer = None

            self._geom = None
            self._radius_km = radius_km
            self._resized = {}

            self.validate = validate

            if geom is not None:

                # Infer CRS from geometry if possible. If the geometry is present in the
                # associated metadata, that should be checked in parse.
                if crs is None:
                    try:
                        crs = (
                            geom.iloc[0].crs
                            if isinstance(geom, (list, tuple))
                            else geom.crs
                        )
                    except AttributeError:
                        pass

                # Parse the provided shape data
                self.verbatim = geom
                parsed, crs = self.parse(geom, crs=crs)
                logger.debug(
                    f"Parsed input as {repr(parsed)} (input_type={type(geom)},"
                    f" output_type={type(parsed)}, crs={crs})"
                )

                # Extract EPSG code from the CRS if present
                if isinstance(crs, str) and not crs.isnumeric():
                    try:
                        crs = re.search(r"epsg:\d+", crs, flags=re.I).group()
                    except:
                        raise

                if crs is None:
                    raise ValueError("Could not infer CRS")

                # Parsed geometries are always saved as GeoSeries
                self.verbatim_geom = gpd.GeoSeries(parsed, crs=crs)
                self.geom = gpd.GeoSeries(parsed, crs=crs)

    def __setattr__(self, attr, val):
        set_immutable(self, attr, val)

    def __delattr__(self, attr):
        del_immutable(self, attr)

    def __str__(self):
        return (
            f"<GeoMetry name={repr(self.name)}"
            f" crs={repr(str(self.crs))}"
            f" radius_km={self.radius_km:.1f}"
            f" geom={_truncate(self.wkt)}>"
        )

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return custom_eq(self, other)

    @property
    def geom(self):
        return self._geom

    @geom.setter
    def geom(self, geom):

        if not isinstance(geom, gpd.GeoSeries):
            raise TypeError(f"geom must be a GeoSeries ({repr(type(geom))} given)")

        if not geom.any():
            raise ValueError(f"Passed geometry is empty: {geom}")

        self._geom = geom

        # Clear cached properties when geom changes
        for attr in self.cached:
            try:
                delattr(self, attr)
            except AttributeError:
                pass

        # Validate the geoemtry once set
        if self.validate:
            self.validate_shape()

    @property
    def crs(self):
        return self.geom.crs

    @property
    def geom_type(self):
        return self.geom.geom_type[0]

    @cached_property
    def x(self):
        if self.geom_type == "Point":
            return self.coords[0][0]
        return [c[0] for c in self.coords]

    @cached_property
    def y(self):
        if self.geom_type == "Point":
            return self.coords[0][1]
        return [c[1] for c in self.coords]

    @cached_property
    def meridians(self):
        logger.debug("Calculating meridians")
        try:
            logger.debug("Getting meridians from x")
            # Previously this approach used the full set of x coordinates for each
            # shape. This failed sporadically with shapes that cross the antimeridian,
            # so switched to using representative point instead.
            # meridians = self.as_wgs84.x
            meridians = [self.representative_point(4326).x]
        except NotImplementedError:
            logger.debug("Getting meridians from subgeoms")
            meridians = []
            for geom in self.as_wgs84.geom.iloc[0].geoms:
                for x, _ in geom.exterior.coords:
                    meridians.append(int(x))
        return get_meridians(meridians)

    @cached_property
    def lat(self):
        return self.y

    @cached_property
    def lon(self):
        return self.x

    @cached_property
    def coords(self):
        if self.geom_type == "Polygon":
            logger.debug("Getting coords for Polygon")
            return list(self.geom.iloc[0].exterior.coords)
        elif self.geom_type == "LineString":
            logger.debug("Getting coords for LineString")
            return list(self.geom.iloc[0].coords)
        elif self.geom_type == "Point":
            return [(self.geom.iloc[0].x, self.geom.iloc[0].y)]
        logger.debug(f"Getting coords for {self.geom_type} (crs={self.crs})")
        return list(self.convex_hull.coords)

    @cached_property
    def lat_lons(self):
        return [(y, x) for x, y in self.coords]

    @cached_property
    def centroid(self):
        if self.geom_type == "Point":
            geom = self.copy()
            with mutable(geom):
                geom._radius_km = 0
            return geom
        return self.match(self.as_equal_area.geom.centroid)

    @cached_property
    def convex_hull(self):
        return self.match(self.as_equal_area.geom.convex_hull)

    @cached_property
    def center(self):
        logger.debug(f"Calculating the center of {_truncate(self.geom.iloc[0])}")
        if self.geom.iloc[0].is_empty:
            raise ValueError(
                f"Cannot calculate center of empty shape: {self.geom.iloc[0]}"
            )
        # Return point
        if self.geom_type == "Point":
            return self.match(self.geom.iloc[0])
        # Return centroid if polygon does not cross the dateline
        geom = self.geom.to_crs(4326)
        x1, y1, x2, y2 = geom.total_bounds
        lat = 0  # (y1 + y2) / 2
        lon = get_meridian([(x1 + x2) / 2])
        # Return centroid if polygon does not cross the dateline
        if abs(x1 - x2) < 180:
            proj_string = self.equal_area_mask.format(lat=lat, lon=lon)
            centroid = geom.to_crs(proj_string).centroid
            return self.match(centroid)
        # Reproject until polygon is in one piece
        for lon in range(-180, 180, 60):
            reproj = geom.to_crs(self.lat_lon_mask.format(lat=lat, lon=lon))
            x1_, _, x2_, _ = reproj.total_bounds
            if abs(x1_ - x2_) < 180:
                proj_string = self.equal_area_mask.format(lat=lat, lon=lon)
                centroid = reproj.to_crs(proj_string).centroid
                return self.match(centroid)
        # Assign center=0 for features that span the full range of longitude
        # that can't otherwise be mapped to a coherent polygon
        maxx = max((x1, x2))
        minx = min((x1, x2))
        if (
            isclose(maxx, 180, abs_tol=1e-3)
            or maxx > 180
            and isclose(minx, -180, abs_tol=1e-3)
            or minx < 180
        ):
            return self.match(Point(0, lat), other_crs=4326)
        raise ValueError("Could not calculate center")

    @cached_property
    def area(self):
        logger.debug(f"Calculating the area of {_truncate(self.geom)}")
        return self.as_equal_area.polygon.geom.iloc[0].area

    @cached_property
    def bounds(self):
        logger.debug(f"Calculating the bounds of {_truncate(self.geom)}")
        if self.geom_type == "Point":
            return self.polygon.geom.total_bounds
        return self.geom.total_bounds

    @cached_property
    def radius_km(self):
        logger.debug(f"Calculating the radius in km of {_truncate(self.geom)}")
        if self.geom_type == "Point":
            return float(self._radius_km)
        lon1, lat1, lon2, lat2 = self.as_wgs84.bounds
        return get_dist_km(lat1, lon1, lat2, lon2) / 2

    @cached_property
    def height_km(self):
        logger.debug(f"Calculating the height in km of {_truncate(self.geom)}")
        if self.geom_type == "Point":
            return self._radius_km * 2
        lon1, lat1, lon2, _ = self.as_wgs84.bounds
        return get_dist_km(lat1, lon1, lat1, lon2)

    @cached_property
    def width_km(self):
        logger.debug(f"Calculating the width in km of {_truncate(self.geom)}")
        if self.geom_type == "Point":
            return self._radius_km * 2
        lon1, lat1, _, lat2 = self.as_wgs84.bounds
        return get_dist_km(lat1, lon1, lat2, lon1)

    @cached_property
    def as_equal_area(self):
        mask = self.equal_area_mask
        name = mask.split(" ")[0]
        if str(self.crs).startswith(name):
            return self.copy()
        proj_string = self.customize_proj_string(mask)
        # Use standard 53012 if meridian is 0
        if "lat0=0 " in proj_string:
            proj_string = 53012
        return self.to_crs(proj_string)

    @cached_property
    def as_lat_lon(self):
        mask = self.lat_lon_mask
        name = mask.split(" ")[0]
        if str(self.crs).startswith(name):
            return self.copy()
        proj_string = self.customize_proj_string(mask)
        # Use standard 4326 if meridian is 0
        if "lat0=0 " in proj_string:
            proj_string = 4326
        return self.to_crs(proj_string)

    @cached_property
    def as_wgs84(self):
        return self.to_crs(4326)

    @cached_property
    def envelope(self):
        logger.debug(f"Calculating the envelope of {_truncate(self)}")
        if self.geom_type == "Point" and self.radius_km:
            geom = self.as_wgs84
            poly = draw_polygon(geom.center.y, geom.center.x, self.radius_km, 4)
            return self.match(poly, geom.crs)
        geom = self.as_lat_lon
        poly = box(*self.as_lat_lon.bounds)
        return self.match(poly, other_crs=geom.crs)

    @cached_property
    def ellipse(self):
        """Returns the ellipse around the centroid of the geometry"""
        logger.debug(f"Calculating the ellipse of {_truncate(self)}")
        geom = self.as_lat_lon
        poly = draw_polygon(geom.center.y, geom.center.x, self.radius_km, 50)
        return self.match(poly, other_crs=geom.crs)

    @cached_property
    def main(self):
        if self.geom_type == "MultiPolygon":
            logger.debug(f"Finding the main polygon in {_truncate(self)}")
            geoms = {g.area: g for g in self.geom.iloc[0].geoms}
            return self.match(geoms[max(geoms)])
        return self.copy()

    @cached_property
    def polygon(self):
        """A representation of the geometry as a polygon"""
        return self.ellipse if self.geom_type == "Point" else self

    @cached_property
    def drawable(self):
        x1, _, x2, _ = self.bounds
        if (
            self.crs == 4326
            and self.crosses_dateline()
            and not isclose(max(x1, x2), 180)
            and not isclose(min(x1, x2), -180)
        ):
            return self.split_at_dateline().geom.iloc[0]
        return self.polygon.geom.iloc[0]

    @cached_property
    def wkb(self):
        return self.geom.iloc[0].wkb

    @cached_property
    def wkt(self):
        return to_wkt(self.geom.iloc[0], rounding_precision=6)

    @property
    def is_empty(self):
        return self.geom.iloc[0].is_empty

    @property
    def is_valid(self):
        return self.geom.iloc[0].is_valid

    def to_crs(self, crs, validate=True):
        """Reprojects geometry to another crs"""

        geom = self.verbatim_geom.copy(True)

        if not geom.crs.equals(crs):
            logger.debug(
                f"Reprojecting from {repr(str(self.verbatim_geom.crs))}"
                f" to {repr(str(crs))}"
            )
            geom = geom.to_crs(crs)

        # Defer validation of the reprojected shape until the verbatim_geom from
        # the parent can be copied over to the new object. This allows the original
        # geometry to be used when reassessing an invalid shape.
        geom = self.__class__(geom, validate=False)
        with mutable(geom):
            geom.verbatim_geom = self.verbatim_geom.copy()
            if validate:
                geom.validate_shape()
            geom.validate = validate

            # Copy metadata
            geom.name = self.name
            geom.parents = self.parents.copy()
            geom._radius_km = self._radius_km

        return geom

    def representative_point(self, crs=None):
        point = self.match(self.geom.representative_point()[0])
        if crs is not None:
            point = point.to_crs(crs)
        return point

    def to_gdf(self):
        data = self.to_json()
        data["geometry"] = wkt.loads(data["geometry"])
        return gpd.GeoDataFrame([data], crs=self.crs, geometry="geometry")

    def to_json(self):
        return {
            "name": self.name,
            "geometry": self.verbatim_geom.iloc[0].wkt,
            "crs": self.verbatim_geom.crs,
            "radius_km": self._radius_km,
            "validate": self.validate,
        }

    def match(self, other, other_crs=None):
        """Matches another geometry to this class and CRS"""
        logger.debug(f"Reprojecting {_truncate(other)} to match {_truncate(self.crs)}")
        if not isinstance(other, self.__class__):
            try:
                other = self.__class__(other, crs=other_crs)
            except ValueError as e:
                if str(e) != "Could not infer CRS":
                    raise
                other = self.__class__(other, crs=self.crs)
        if not self.crs.equals(other.crs):
            other = other.to_crs(self.crs)
        return other

    def copy(self):
        logger.debug(f"Creating a copy of {_truncate(self)}")
        return custom_copy(self)

    def simplify(self, tolerance=0.05, num_points=25):
        if self.geom_type != "Point":
            logger.debug(
                f"Simplifying {_truncate(self)} (tolerance={tolerance}, num_points={num_points})"
            )
            # geom = (
            #    self.geom.iloc[0]
            #    if self.geom_type == "Polygon"
            #    else self.convex_hull.geom.iloc[0]
            # )
            geom = self.geom.iloc[0]
            simplified = None
            coords = None
            while simplified is None or len(coords) > num_points:
                simplified = geom.simplify(tolerance)
                tolerance += 0.01
                try:
                    coords = simplified.exterior.coords
                except AttributeError:
                    try:
                        coords = simplified.coords
                    except NotImplementedError:
                        break
            return self.match(geom if simplified is None else simplified)
        return self.copy()

    def customize_proj_string(self, proj_string):
        point = self.representative_point(4326)
        return proj_string.format(lat=0, lon=get_meridian([point.x]))

    def equals_exact(self, other, tolerance=0.1):
        geom, other = self.reproject(other)
        return geom.geom.iloc[0].equals_exact(other.geom.iloc[0], tolerance=tolerance)

    def contains(self, other):
        logger.debug(f"Checking if {_truncate(self)} contains {_truncate(other)}")
        geom, other = self.reproject(other)
        return geom.polygon.geom.iloc[0].contains(other.polygon.geom.iloc[0])

    def crosses(self, other):
        logger.debug(f"Checking if {_truncate(self)} crosses {_truncate(other)}")
        geom, other = self.reproject(other)
        return geom.polygon.geom.iloc[0].crosses(other.polygon.geom.iloc[0])

    def disjoint(self, other):
        logger.debug(
            f"Checking if {_truncate(self)} is disjoint from {_truncate(other)}"
        )
        geom, other = self.reproject(other)
        return geom.polygon.geom.iloc[0].disjoint(other.polygon.geom.iloc[0])

    def intersects(self, other):
        logger.debug(f"Checking if {_truncate(self)} intersects {_truncate(other)}")
        geom, other = self.reproject(other)
        return geom.polygon.geom.iloc[0].intersects(other.polygon.geom.iloc[0])

    def touches(self, other):
        logger.debug(f"Checking if {_truncate(self)} touches {_truncate(other)}")
        geom, other = self.reproject(other)
        return geom.polygon.geom.iloc[0].touches(other.polygon.geom.iloc[0])

    def within(self, other):
        logger.debug(f"Checking if {_truncate(self)} is within {_truncate(other)}")
        geom, other = self.reproject(other)
        return other.contains(self)
        # NOTE: within throws a Topology Error sometimes
        return geom.polygon.geom.iloc[0].within(other.polygon.geom.iloc[0])

    def difference(self, other):
        logger.debug(
            f"Calculating the difference between {_truncate(self)} and {_truncate(other)}"
        )
        geom, other = self.reproject(other)
        crs = geom.crs
        geom = geom.polygon.geom.iloc[0].difference(other.polygon.geom.iloc[0])
        return self.match(geom, other_crs=crs)

    def intersection(self, other):
        logger.debug(
            f"Calculating the intersection between {_truncate(self)} and {_truncate(other)}"
        )
        geom, other = self.reproject(other)
        crs = geom.crs
        geom = geom.polygon.geom.iloc[0].intersection(other.polygon.geom.iloc[0])
        return self.match(geom, other_crs=crs)

    def intersects_all(self, others, transitive=True):
        """Tests if list of shapes all intersect"""
        others = self.reproject(others)
        geom = others.pop(0)
        # If transitive is False, shape must itself intersect all others
        if not transitive:
            for other in others:
                if not geom.intersects(other):
                    return False
            return True
        # If transitive is True, look for chains of intersection
        intersecting = [geom]
        last = None
        while intersecting != last:
            disjoint = []
            for geom in intersecting[:]:
                for other in others:
                    if geom.intersects(other):
                        intersecting.append(other)
                    else:
                        disjoint.append(other)
            last = intersecting
            others = disjoint
        return not disjoint

    def overlap(self, other, percent=False):
        """Calculates the overlap between two objects"""
        geom, other = self.reproject(other)
        try:
            site, other = [s.envelope for s in [geom, other]]
            if site.disjoint(other):
                return 0.0
            if site.contains(other):
                return 1.0 if percent else other.area
            if site.within(other):
                return 1.0 if percent else site.area
            # Calculate overlap as the ratio of the area of the intersection
            # to the smaller of the two shapes
            if all([s.area for s in [site, other]]):
                larger = sorted([site, other], key=lambda s: s.area)[-1]
                overlap = site.intersection(other).area
                return overlap / larger.area if percent else overlap
        except ValueError:
            pass
        return 0.0

    def nearest_points(self, other):
        """Calculates nearest points between this and another geometry"""
        geom, other = self.reproject(other)
        crs = geom.crs
        # Use centroids where radius is estimated
        geom = (geom.centroid if geom.geom_type == "Point" else geom).geom.union_all()
        other = (
            other.centroid if other.geom_type == "Point" else other
        ).geom.union_all()

        return [self.match(g, other_crs=crs) for g in nearest_points(geom, other)]

    def similar_to(self, other, *args, dist_km=0.1, **kwargs):
        """Tests if centroid and radius of two shapes are within 100 m"""
        geom, other = self.reproject(other)
        if args or kwargs:
            return geom._similar_to(other, *args, **kwargs)
        if geom.centroid_dist_km(other) <= dist_km:
            return abs(geom.radius_km - other.radius_km) <= dist_km
        return False

    def combine(self, others, allow_hull=True):
        """Combines list of shapes using their union or convex hull"""
        geoms = [s.geom.iloc[0] for s in self.reproject(others)]
        # geom = geoms[0]
        # others = geoms[1:]
        return self.match(union_all(geoms))
        if allow_hull:
            return self.match(GeometryCollection(geoms).convex_hull)
        raise ValueError("Could not combine shapes")

    def translate(self, bearing, dist_km, abs_err_degrees=None, rel_err_distance=0.25):
        """Translates the shape based on a distance and bearing"""
        kwargs = {
            "abs_err_degrees": abs_err_degrees,
            "rel_err_distance": rel_err_distance,
        }
        if self.radius_km >= 100:
            kwargs["abs_err_degrees"] = 5.75
        points = []
        for lon, lat in self.coords:
            polygon = translate_with_uncertainty(lat, lon, bearing, dist_km, **kwargs)
            points.extend(polygon.exterior.coords)
        return self.match(MultiPoint(points).convex_hull)

    def smart_translate(
        self, bearing, dist_km=None, abs_err_degrees=None, rel_err_distance=0.25
    ):
        """Interprets directions based on type of shape"""
        kwargs = {
            "abs_err_degrees": abs_err_degrees,
            "rel_err_distance": rel_err_distance,
        }

        # Use the edge when translating a complex polygon N, S, E, or W.
        # Primarily for calculating directions for country or state borders.
        use_edge = (
            len(bearing) == 1
            and self.geom_type != "Point"
            and not self.geom.equals(self.envelope)
        )

        geom = self.main.copy()
        if use_edge:
            geom = geom.edge(bearing)
        elif self.radius_km <= 10:
            geom = geom.subsection(bearing)

        # If no distance is given, guess distance based on the size of
        # the polygon in the axis corresponding to the bearing.
        extend_from_edge = False
        if dist_km is None:
            # Decrease scalar as size of original geom increases
            scalar = 2 if self.radius_km <= 100 else 4
            if bearing in "NS":
                dist_km = self.height_km / 4
            elif bearing in "EW":
                dist_km = self.width_km / 4
            else:
                dist_km = self.radius_km / 4
            extend_from_edge = True
            kwargs["rel_err_distance"] = 0

        # Translate geom according to the bearing and distance
        translated = geom.translate(bearing, dist_km, **kwargs)

        if use_edge and not extend_from_edge:
            # Buffer edges according to precision if disance specified. Must
            # be buffer, not resize or scale, because edge returns a line.
            buffer_dist_km = dist_km * kwargs["rel_err_distance"]
            buffered = translated.edge(bearing).buffer(buffer_dist_km, how="km")
            translated = self.match(buffered)

        elif use_edge and extend_from_edge:
            # This branch is intended for translations of countries where
            # the distance was estimated based on the size of the original
            # polygon. It produces a polygon that is continuous from the
            # original to the translated edge.
            #
            # Run the original geom through the translate method so it has the
            # same geom as the translated geom
            smoothed = geom.translate(bearing, 0, **kwargs)

            # Create a new geom from the two parallel edges. Reorder the
            # translated edge so that the points are in the right order when
            # the lists are combined.
            # orig_edge = smoothed.lat_lons
            # tran_edge = translated.lat_lons[::-1]
            # translated = self.match(orig_edge + tran_edge)

            translated = self.match(translated.difference(smoothed))

        # If geometry is a polygon (i.e., if the extent of the geometry is
        # well-constrained), limit the translated object to the portion that
        # does not intersect the original polygon.
        # if self.geom_type != 'Point':
        #    translated = translated.difference(self)

        # For simple bearings, crop height or width of the translated geom
        # based on the original. For example, if the bearing is E, the
        # north-south extent of the translated polygon will not exceed the
        # north-south extent of the original polygon.
        if self.radius_km > 500 and not extend_from_edge:
            crop_to = self.subsection(bearing)
            kwargs = {
                "N": {"top": False},
                "S": {"bottom": False},
                "E": {"right": False},
                "W": {"left": False},
                "NE": {"top": False, "right": False},
                "NW": {"left": False, "top": False},
                "SE": {"bottom": False, "right": False},
                "SW": {"left": False, "bottom": False},
            }
            try:
                return translated.crop(crop_to, **kwargs[bearing])
            except KeyError:
                pass

        return translated

    def crop(self, other, left=True, bottom=True, right=True, top=True):
        """Crops shape to bounding box for all directions given as True"""
        geom, other = self.reproject(other)
        bounds = list(self.bounds)
        for i, val in enumerate([left, bottom, right, top]):
            if val:
                bounds[i] = other.bounds[i]
        bbox = box(*bounds)
        return self.intersection(bbox)

    def centroid_dist_km(self, other, *args, **kwargs):
        """Calculates distance in km between centroids of two geometries"""
        geom, other = self.reproject(other)
        return geom.centroid.min_dist_km(other.centroid, *args, **kwargs)

    def max_dist_km(self, other):
        """Estimates the maximum distance in km between two geometries"""
        geom = self.as_wgs84
        other = other.as_wgs84
        # Simplify the geometries to hulls to partially mitigate the awfulness
        # of this appraoch
        geom = geom.convex_hull if geom.geom_type != "Point" else geom
        other = other.convex_hull if other.geom_type != "Point" else other
        dists_km = []
        for lon, lat in geom.coords:
            for olon, olat in other.coords:
                dists_km.append(get_dist_km(lat, lon, olat, olon))
        return max(dists_km)

    def min_dist_km(self, other, threshold_km=None):
        """Calculates minimum distance in km between two geometries"""
        # FIXME: Should this be a reproject?
        geom = self.as_wgs84
        other = other.as_wgs84
        # Use centroids where radius is estimated
        geom = geom.centroid if geom.geom_type == "Point" else geom
        other = other.centroid if other.geom_type == "Point" else other
        if geom.intersects(other):
            return 0.0
        pts = [p.centroid.geom.iloc[0] for p in geom.nearest_points(other)]
        dist_km = get_dist_km(pts[0].y, pts[0].x, pts[1].y, pts[1].x)
        # If threshold specified and exceeded, check variants
        # if threshold_km is not None and dist_km > threshold_km:
        #    dists_km = []
        #    for geom in geom.variants():
        #        geom = geom.centroid if geom.geom_type == "Point" else geom
        #        pts = geom.nearest_points(other)
        #        vdist_km = get_dist_km(pts[0].y, pts[0].x, pts[1].y, pts[1].x)
        #        if vdist_km < threshold_km:
        #            return vdist_km
        #        dists_km.append(vdist_km)
        #    return min(dists_km)
        return dist_km

    def encompass(self, other, how="ellipse"):
        """Creates a polygon centered on a point that encompasses another geometry"""
        if self.geom_type != "Point":
            raise ValueError("Geometry must be a Point")
        geom = self.copy()
        other = self.__class__(other)
        with mutable(geom):
            geom._radius_km = geom.max_dist_km(other)
        return getattr(geom, how)

    def get_common_projection(self, others):
        if others is None:
            return self.crs
        if not isinstance(others, (list, tuple)):
            others = [others]
        others = [self.__class__(o) for o in others]
        # Order geometrics with largest first
        geoms = sorted([self] + others, key=lambda g: -g.area)
        meridians = [g.meridians for g in geoms]
        for lon in meridians[0].intersection(*meridians[1:]):
            return self.equal_area_mask.format(lat=0, lon=lon)
        # Find meridian where convex hulls for all shapes are single polygons
        counts = {}
        for merids in meridians:
            for merid in merids:
                counts.setdefault(merid, 0)
                counts[merid] += 1
        hulls = [g.convex_hull for g in [self] + others]
        for merid in [kv[0] for kv in sorted(counts.items(), key=lambda kv: -kv[1])]:
            proj = self.equal_area_mask.format(lat=0, lon=merid)
            for hull in hulls:
                if "Multi" in hull.to_crs(proj).geom_type:
                    break
            else:
                return proj
        raise ValueError("No common meridian found")

    def reproject(self, others, other_crs=None):
        """Reprojects geometries to a common projection"""
        geoms = [self] + [self.__class__(o) for o in as_list(others)]
        if len(geoms) == 1:
            return [self.as_equal_area]
        crs = geoms[0].get_common_projection(geoms[1:])
        return [g.to_crs(crs) for g in geoms]

    def crosses_dateline(self):
        x1, _, x2, _ = self.bounds
        return abs(x1 - x2) > 180

    def split_at_dateline(self):
        if self.crosses_dateline():
            logger.debug("Splitting geometry at dateline")
            translated = translate(self.geom.iloc[0], xoff=180)
            geom = split(translated, LineString([(180, 90), (180, -90)]))
            geoms = []
            for geom in translate(geom, xoff=-180).geoms:
                x1, _, x2, _ = geom.bounds
                dateline = 180 if min(x1, x2) >= 0 else -180
                coords = [(x if x else dateline, y) for x, y in geom.exterior.coords]
                geoms.append(Polygon(coords))
            return self.match(MultiPolygon(geoms))
        return self

    def validate_shape(self):
        if not self.is_valid:
            geom = self.geom.simplify(0.001)
            if geom.is_valid.all():
                logger.debug("Simplified to fix invalid shape")
                self.geom = geom
        if not self.is_valid:
            try:
                geom = self.buffer(0.1)
            except ValueError:
                pass
            else:
                if geom.is_valid:
                    logger.debug("Buffered to fix invalid shape")
                    self.geom = geom.geom
        if not self.is_valid:
            geom = geom.convex_hull
            if geom.is_valid.all():
                logger.debug("Took convex hull to fix invalid shape")
                self.geom = geom
        if not self.is_valid:
            warnings.warn(f"GeoMetry invalid: {self.geom.iloc[0]}")
        return
        if not self.is_valid:
            geom = self.clip(validate=False)
            if geom.is_valid:
                return geom.geom
        if not self.is_valid:
            # Special handling for circumpolar features
            wgs84 = self.__class__(self.verbatim_geom, validate=False).to_crs(
                4326, validate=False
            )
            try:
                bounds = {round(c) for c in wgs84.bounds}
            except OverflowError:
                return geom.geom
            common = {-180, -90, 90, 180} & bounds
            if len(common) == 5:  # Change to 3 to enable, but I wouldn't

                # Get the bounds of the shape in the current CRS
                x1, y1, x2, y2 = self.bounds

                # Get the edge facing away from the pole based on
                # WGS84 latitudes
                lat = max((y1, y2)) if 90 in common else min((y1, y2))

                # Create the edge in WGS84. Using another CRS may clip the edge.
                edge = wgs84.edge("S" if 90 in common else "N").geom.iloc[0]

                # Fill in the edge with additional points. Use the interpolated
                # line to
                coords = []
                dist = 0
                while True:
                    coord = edge.interpolate(dist)
                    if coords and coord == coords[-1]:
                        break
                    coords.append(coord)
                    dist += 1
                geom = self.__class__(LineString(coords), crs=4326, validate=False)
                x1, _, x2, _ = geom.bounds

                # Project the edge to the provided CRS and reorder the points
                # so that they are continuous across the given range in x
                reproj = geom.to_crs(self.crs)
                coords = reproj.coords
                for i, (x, _) in enumerate(reproj.coords):
                    if i:
                        diff = abs(x - reproj.coords[i - 1][0])
                        if diff > max((x1, x2)):
                            coords = reproj.coords[i:] + reproj.coords[:i]

                # Add the pole
                xmin, xmax = sorted((x1, x2))
                x1 = coords[0].x if hasattr(coords[0], "x") else coords[0][0]
                x2 = coords[-1].x if hasattr(coords[-1], "x") else coords[-1][0]
                if x1 > x2:
                    coords.insert(0, (xmax, lat))
                    coords.append((xmin, lat))
                else:
                    coords.insert(0, (xmin, lat))
                    coords.append((xmax, lat))

                logger.debug(f"Fixed invalid polar geometry")
                return gpd.GeoSeries(Polygon(coords), crs=self.crs)

        # Otherwise tweak the polygon to correct minor errors
        geom = self.geom.iloc[0]
        if not geom.is_valid:
            geom = geom.buffer(0.1)
        if not geom.is_valid:
            geom = geom.convex_hull
        if geom.is_valid:
            return gpd.GeoSeries(geom, crs=self.crs)

        raise ValueError(f"Invalid geometry: {self.geom}")

    def plot(self, others=None, **kwargs):
        """Draws a set of geometries"""
        logger.debug(f"Plotting {_truncate(self)} and others")
        crs = kwargs.pop("crs", self.get_common_projection(others))
        geoms = [g.to_crs(crs) for g in [self] + as_list(others)]
        geoms = [g if g.geom_type == "Point" else g for g in geoms]
        geoms.sort(key=lambda g: -g.area)
        return geoms_to_geoseries(geoms, crs=crs).plot(**kwargs)

    def buffer(self, dist, how="km"):
        """Buffers an object by distance in km"""
        # FIXME: Buffering shapes that cross dateline produces strange results
        logger.debug(f"Buffering shape to {repr(dist)} (how={repr(how)})")
        if how not in ("km", "rel"):
            raise ValueError("how must be 'km' or 'rel'")
        if not isinstance(dist, (float, int)):
            raise TypeError(f"dist must be a numeric data type ({repr(dist)} given)")
        if how == "rel":
            dist = self.radius_km * (dist - 1)
        if dist:
            # Convert distance to meters
            dist *= 1000
            # Buffer and crop the geometry
            proj_string = self.equal_area_mask.format(
                lat=0, lon=get_meridian([self.representative_point(4326).x])
            )
            geom = self.envelope.geom if self.geom_type == "Point" else self.geom
            geom = geom.to_crs(proj_string)
            buffered = geom.buffer(dist).clip(self.equal_area_bounds)
            # Revert to original CRS
            return self.__class__(buffered, crs=self.crs)
        return self.copy()

    def resize(self, dist=0, how="km"):
        return self.buffer(dist, how)

    def clip(self, other=None, validate=True):
        if other is None:
            crs = str(self.crs)
            if "longlat" in crs or "4326" in crs:
                other = self.lat_lon_bounds
            elif "eck4" in crs:
                other = self.equal_area_bounds
            else:
                raise ValueError(f"Could not guess extent: {_truncate(self.crs)}")
        return self.__class__(self.geom.clip(other), validate=validate)

    def subsection(self, modifier):
        """Splits polygon along a line based on a modifier"""
        geom = self.polygon
        # Get subsection based on area within a shape
        if not re.match(r"[NEWS23]{1,2}", modifier):
            try:
                multiplier = {
                    "center": 0.5,
                    "inner": 1.0,
                    "lower": 1.0,
                    "near": 1.5,
                    "outer": 1.0,
                    "upper": 1.0,
                }[modifier]
            except KeyError:
                raise ValueError(f"Unrecognized modifier: {modifier}")

            if multiplier == 1:
                geom.modifier = modifier
                geom.parents.append(self)
                return geom
            elif multiplier > 1:
                geom = geom.resize(multiplier, how="rel")
                geom.modifier = modifier
                geom.parents.append(self)
                return geom
            else:
                return geom
                # Calculate shape representing the middle 50% of the geometry
                # FIXME: Does not work well with high aspect ratios
                geom = self.match(
                    draw_polygon(geom.center.y, geom.center.x, self.radius_km / 2, 50)
                )
                geom.modifier = modifier
                geom.parents.append(self)
                return geom

        fraction = 3 if "3" in modifier else 2
        # Split along longitude
        if modifier[-1] in "EW":
            w = (max(geom.lon) - min(geom.lon)) / fraction
            x = max(geom.lon) - w if modifier[-1] == "E" else min(geom.lon) + w
            line = LineString([(x, min(geom.lat)), (x, max(geom.lat))])
            geom = geom.split(line, modifier[-1])
        # Split along latitude
        if modifier[0] in "NS":
            h = (max(geom.lat) - min(geom.lat)) / fraction
            y = max(geom.lat) - h if modifier[-1] == "N" else min(geom.lat) + h
            line = LineString([(min(geom.lon), y), (max(geom.lon), y)])
            geom = geom.split(line, modifier[0])
        geom = self.match(geom)
        geom.modifier = modifier
        geom.parents.append(self)
        return geom

    def supersection(self):
        """Returns the parent of the current section"""
        return self.parents[-1]

    def split(self, line, direction):
        """Splits geom along line, returning the half in the given direction"""
        assert direction in {"N", "S", "E", "W"}
        geoms = self.split_and_group(line)
        geoms = sort_geoms(geoms, direction)
        return geoms[-1] if direction in "NE" else geoms[0]

    def edge(self, direction):
        """Approximates the edge of a geometry based on its bounds"""
        # Define params for vertical
        if direction in "NS":
            index = 0
            trim_func = subvertical
            bounds = self.lon
        elif direction in "EW":
            index = 1
            trim_func = subhorizontal
            bounds = self.lat
        else:
            raise ValueError(f"Bad direction: {direction}")

        # Split polygon into halves based on bounding coordinates
        coords = self.coords
        if coords[0] == coords[-1]:
            coords.pop(-1)
        indexes = [i for i, pt in enumerate(coords) if similar(pt[index], min(bounds))]
        coords = coords[indexes[-1] :] + coords[: indexes[-1]]

        # Second half
        indexes = [i for i, pt in enumerate(coords) if similar(pt[index], max(bounds))]
        coords = coords[indexes[-1] :], coords[: indexes[-1]]

        # Trim features at edge of polygon that are parallel to the axis
        # given by the direction. For example, if looking for the north
        # coast, subvertical (e.g., N-S) segments on the edge of the coast
        # are trimmed because they are not really part of the coast we're
        # interested in.
        coords = [trim(c, index, trim_func) for c in coords]
        geoms = [self.match(LineString(c)) for c in coords if len(c) > 1]
        geoms = sort_geoms(geoms, direction)
        geom = geoms[-1] if direction in "NE" else geoms[0]
        geom.parents.append(self)

        return geom

    def split_and_group(self, line):
        """Groups geometries based on which edge intersects a given line

        Needed when the split line cuts through a gap in a polygon.
        """
        line = self.match(line).geom.iloc[0]
        geoms = list(split(self.geom.iloc[0], line).geoms)
        if len(geoms) > 2:
            bounds = line.bounds
            val = bounds[0] if bounds[0] == bounds[2] else bounds[1]
            grouped = {}
            for geom in geoms:
                try:
                    index = [i for i, v in enumerate(geom.bounds) if v == val][0]
                except IndexError:
                    # FIXME: Does this need a warning?
                    pass
                else:
                    grouped.setdefault(index, []).append(geom)
            geoms = [union_all(g) for g in grouped.values()]
        return [self.match(g) for g in geoms]

    def parse(self, obj, crs=None):
        """Parses coordinates or shapely object"""

        logger.debug(f"Parsing {_truncate(obj)} (type={type(obj)}, crs={crs})")

        geom_type_hint = None

        if isinstance(obj, (list, tuple)) and len(obj) == 1:
            logger.debug("Limited to first entry in sequence")
            obj = obj[0]

        if hasattr(obj, "name"):
            self.name = obj.name

        if isinstance(obj, GeoMetry):
            logger.debug("Parsed geometry from GeoMetry")
            geom = obj.geom.copy()
            if crs and not obj.crs.equals(crs):
                geom = geom.to_crs(crs)
            return geom, crs

        # Object is a GeoDataFrame
        if isinstance(obj, gpd.GeoDataFrame):
            logger.debug("Parsed geometry from GeoDataFrame")
            if crs and not obj.crs.equals(crs):
                obj = obj.to_crs(crs)
            return obj.geometry.iloc[-1:].reset_index(drop=True), crs

        # Object is a GeoSeries
        if isinstance(obj, gpd.GeoSeries):
            logger.debug("Parsed geometry from GeoSeries")
            if crs and not obj.crs.equals(crs):
                obj = obj.to_crs(crs)
            return obj.geometry.iloc[-1:].reset_index(drop=True), crs

        # Shape is a shapely geometry object
        if isinstance(obj, BaseGeometry):
            logger.debug("Parsed geometry from BaseGeometry")
            return obj, crs

        # Interpet bytes as WKB
        if isinstance(obj, bytes):
            logger.debug("Parsed geometry from WKB")
            return wkb.loads(obj), crs

        # Interpet str as WKT
        if isinstance(obj, str):
            if obj.startswith("<"):
                logger.debug("Parsed GeoMetry string")
                obj = obj.strip("<>").split(" ", 1)[1]
                params = re.findall(r"(\w+=(?:'.*?'|\d+(?:.\d+)|None))", obj)
                params = dict((p.split("=", 1) for p in params))
                params = {k: v.strip("'") for k, v in params.items()}
                geom, crs = self.parse(params["geom"], crs=params["crs"])
                if params["name"] not in {None, "None"}:
                    self.name = params["name"]
                self.radius_km = float(params["radius_km"])
                return geom, crs
            else:
                logger.debug("Parsed geometry from WKT")
                return wkt.loads(obj), crs

        # Extract row of coordinate data from EMuRecord
        if isinstance(obj, EMuRecord):
            # Get collection event data if from catalog
            obj = obj.get("BioEventSiteRef", obj)

            # Select row from lat/long grid
            grid = obj.grid("LatLatitude_nesttab").add_columns().pad()
            if not grid:
                raise ValueError("EMuRecord does not contain lat/long data: {rec}")
            for row in obj.grid("LatLatitude_nesttab").add_columns().pad():
                if row.get("LatPreferred_tab") == "Yes":
                    obj = row
                    break
            else:
                obj = grid[0]

        # Interpret row from EMu
        if isinstance(obj, EMuRow):
            try:
                lats = obj["LatLatitudeVerbatim_nesttab"]
                lons = obj["LatLongitudeVerbatim_nesttab"]
                if not (lats and lons):
                    raise KeyError
            except KeyError:
                try:
                    if obj["LatLatitudeOrig_nesttab"] == 0:
                        lats = obj["LatLatitude_nesttab"]
                        lons = obj["LatLongitude_nesttab"]
                    else:
                        lats = obj["LatLatitudeDecimal_nesttab"]
                        lons = obj["LatLongitudeDecimal_nesttab"]
                except KeyError:
                    raise ValueError(
                        "EMu exports must include either the original or verbatim coordinate fields"
                    )

            # Get CRS from geodetic datumm forcing 4326 if none provided. CRS
            # errors are typically small and the geometry cannot be created
            # without specifying one, which interferes with certain validation
            # routines for EMu imports.
            crs = obj.get("LatDatum_tab")
            if not crs or crs.lower() == "unknown":
                crs = 4326

            # Set radius based on data in table
            try:
                radius = f"{obj["LatRadiusNumeric_tab"]} {obj["LatRadiusUnit_tab"]}"
            except KeyError:
                radius = obj.get("LatRadiusVerbatim_tab")
            if radius and radius not in ("None None"):
                self._radius_km = parse_measurement(radius).convert_to("km").numeric

            # Route the lat-lons through the list parsing logic below
            geom_type_hint = obj.get("LatGeometry_tab")
            obj = list(zip(lats, lons))

        # Interpret dict as a Geonames-style bounding box
        elif isinstance(obj, dict):
            logger.debug("Parsed geometry from GeoNames bounding box")
            lats = [obj["south"], obj["north"]]
            lons = [obj["west"], obj["east"]]
            return box(lons[0], lats[0], lons[1], lats[1]), crs

        if isinstance(obj, (list, tuple)):
            obj = obj[:]

            # Convert numpy arrays to lists
            try:
                obj = [c.tolist() for c in obj]
            except AttributeError:
                pass

            # Extract underlying shapely shapes from a list of geometries
            if isinstance(obj[0], GeoMetry):
                logger.debug("Parsed as a series of GeoMetry objects")
                geoms = []
                for geom in obj:
                    geom = self.__class__(geom.verbatim_geom, crs=geom.verbatim.crs)
                    if not geom.crs.equals(crs):
                        geom = geom.to_crs(crs)
                    geoms.append(geom.geom.iloc[0])
                obj = geoms

            # Interpret lists of shapely objects
            if isinstance(obj[0], BaseGeometry):
                logger.debug("Parsed as a series of BaseGeometry objects")

                # Convert list mixing multiple shapely objects to GeometryCollection
                if len({s.geom_type for s in obj}) > 1:
                    return GeometryCollection(obj), crs

                # Convert list of Point to a LineString or Polygon
                if geom_type_hint:
                    shape_class = geom_type_hint
                else:
                    shape_class = LineString if len(obj) == 2 else Polygon
                try:
                    return shape_class([(p.x, p.y) for p in obj]), crs
                except AttributeError:
                    pass

                # Convert list of Polygon to a MultiPolygon, then take the convex hull
                if isinstance(obj[0], Polygon):
                    try:
                        return union_all(MultiPolygon(obj)), crs
                    except ValueError:
                        pass

                # Convert list of LineString to a MultiLineString
                if isinstance(obj[0], LineString):
                    try:
                        return MultiLineString(obj), crs
                    except ValueError:
                        pass

            # Interpret lists of coordinates
            list_of_lists = isinstance(obj[0], (list, tuple))
            try:
                list_of_pairs = all([len(c) == 2 for c in obj[:10]])
            except TypeError:
                list_of_pairs = False

            lat_lons = None

            # Interpet list of pairs as [(lat, lon),...]
            if list_of_lists and list_of_pairs:
                logger.debug("Parsed as a series of lat-lons")
                lat_lons = list(obj)

            # Interpret a pair of lists as [lats, lons]
            elif list_of_lists:
                logger.debug("Parsed as latitude and longitude lists")
                # Shape is [lats, lons]
                lat_lons = list(zip(*obj))

            # Interpret a single pair as a point
            elif len(obj) == 2:
                logger.debug("Parsed as a point")
                lat_lons = [obj]

            if lat_lons:

                lats = []
                lons = []
                for lat, lon in lat_lons:

                    # Coordinates are concatenated strings
                    if isinstance(lat, str) and "|" in lat:
                        lats.extend(
                            [
                                self.parse_coordinate(s.strip(), "lat")
                                for s in lat.split("|")
                            ]
                        )
                        lons.extend(
                            [
                                self.parse_coordinate(s.strip(), "lon")
                                for s in lon.split("|")
                            ]
                        )

                    # Coordinates are parseable
                    else:
                        lats.append(self.parse_coordinate(lat, "lat"))
                        lons.append(self.parse_coordinate(lon, "lon"))

                # Convert coordinates to shapely geometry
                xy = list(zip(lons, lats))
                if len(xy) == 1 or geom_type_hint == "Point":
                    return Point(xy[0]), crs
                if len(xy) == 2 or geom_type_hint == "LineString":
                    return LineString(xy), crs
                return Polygon(xy), crs

        # Check for a geometry attribute
        if hasattr(obj, "geometry"):
            logger.debug("Parsed geometry from geometry attribute")
            return self.parse(obj.geometry, crs=crs)

        # Give up
        msg = f"Parse failed: {obj} (unknown format)"
        logger.error(msg)
        raise ValueError(msg)

    def parse_coordinate(self, val, kind):
        """Placeholder function used to parse coordinates"""
        try:
            return float(val)
        except ValueError:
            return float({"lat": EMuLatitude, "lon": EMuLongitude}[kind](val))

    def _similar_to(self, other, min_overlap=0.9, min_area_ratio=0.5):
        """Tests if two geometries have similar positions and sizes"""
        other = self.match(other)
        try:
            if self.intersects(other):
                areas = [s.envelope.area for s in [self, other]]
                area_ratio = min(areas) / max(areas)
                return (
                    self.overlap(other, True) >= min_overlap
                    and area_ratio >= min_area_ratio
                )
        except ValueError:
            pass
        return False

    @staticmethod
    def _is_valid(obj):
        if isinstance(obj, gpd.GeoSeries):
            return all(obj.is_valid)
        return obj.is_valid


def geoms_to_geoseries(geoms, crs=None):
    """Converts list of geoms to a GeoSeries with a coherent equal-area CRS"""
    if crs is None:
        geoms = reproject(geoms)
    return gpd.GeoSeries([g.geom.iloc[0] for g in geoms], crs=geoms[0].crs)


def geoms_to_geodataframe(geoms, **kwargs):
    geoms = reproject(geoms)
    kwargs["geometry"] = gpd.GeoSeries(
        [g.geom.iloc[0] for g in geoms], crs=geoms[0].crs
    )
    gdf = gpd.GeoDataFrame(kwargs)
    gdf["area"] = gdf["geometry"].area
    return gdf.sort_values("area", ascending=False)


def get_meridians(lons):
    vals, bins = np.histogram(lons, bins=3, range=(-180, 180))
    midpoints = [np.mean((val, bins[i])) for i, val in enumerate(bins[1:])]
    vals = [int(m) for m, v in zip(midpoints, vals) if v]
    if 0 in vals:
        vals.insert(0, vals.pop(vals.index(0)))
    return set(vals)


def get_meridian(lons):
    for lon in get_meridians(lons):
        return lon


def reproject(geoms):
    return geoms[0].reproject(geoms[1:])


def _truncate(val):
    """Truncates string for log"""
    if isinstance(val, (gpd.GeoDataFrame, gpd.GeoSeries)):
        try:
            val = val.iloc[0]
        except IndexError:
            val = ""
    return repr(truncate(str(val), 128))


# Define deferred class attributes
LazyAttr(GeoMetry, "geom_cache", CacheDict)
LazyAttr(GeoMetry, "op_cache", CacheDict)
