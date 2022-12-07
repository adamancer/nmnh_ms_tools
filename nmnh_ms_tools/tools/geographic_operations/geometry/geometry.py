"""Defines class to handle projection of lat/long data"""
import json
import logging
import re
from functools import cached_property

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely import wkb, wkt
from shapely.affinity import scale, translate
from shapely.geometry.base import BaseGeometry
from shapely.geometry import (
    Point,
    Polygon,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    box,
)
from shapely.ops import nearest_points, split, unary_union

from ....databases.cache import CacheDict
from ....utils.coords import parse_coordinate
from ....utils.geo import (
    crosses_180,
    draw_circle,
    draw_polygon,
    epsg_id,
    fix_shape,
    get_dist_km,
    similar,
    sort_geoms,
    subhorizontal,
    subvertical,
    translate_with_uncertainty,
    trim,
)


logger = logging.getLogger(__name__)


class GeoMetry:
    """Subclasses NaiveGeometry to handle common projection operations"""

    lat_lon_mask = (
        "+proj=longlat +lat_0={lat} +lon_0={lon} +ellps=WGS84 +datum=WGS84 +no_defs"
    )
    equal_area_mask = (
        "+proj=eck4 +lon_0={lon} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    polar_equal_area_mask = "proj=laea +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m no_defs"

    geom_cache = CacheDict()
    op_cache = CacheDict()

    def __init__(self, geom, crs=None, radius_km=0):
        self._crs = None
        if crs is None:
            try:
                crs = geom[0].crs if isinstance(geom, (list, tuple)) else geom.crs
            except AttributeError:
                raise ValueError("Could not infer CRS")

        parsed = self.parse(geom, crs=crs)

        self.geom = gpd.GeoSeries(parsed)
        self.crs = crs

        self.verbatim = geom
        self.verbatim_geom = parsed
        self.verbatim_crs = crs

        self.name = None
        self.parents = []

        self._radius_km = radius_km
        self._resized = {}

        # self.geom = self.validate_shape()

    def validate_shape(self):
        geom = self.geom.to_crs(self.customize_proj_string(self.equal_area_mask))
        if not self._is_valid(geom):
            geom = geom.buffer(0.1)
            if not self._is_valid(geom):
                geom = geom.convex_hull
            if not self._is_valid(geom):
                raise ValueError(f"Invalid geometry: {self.geom}")
            return geom.to_crs(self.crs)
        return self.geom

    def __str__(self):
        return (
            f"<GeoMetry geom={self.geom[0]} crs={self.crs} radius_km={self.radius_km}>"
        )

    def __repr__(self):
        return str(self)

    @property
    def crs(self):
        return self._crs

    @crs.setter
    def crs(self, crs):
        if self._crs is not None:
            raise ValueError("Cannot change CRS once set")
        self._crs = crs
        self.verbatim_crs = crs
        if crs is not None:
            self.geom.set_crs(crs, inplace=True)

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
    def lat(self):
        return self.y

    @cached_property
    def lon(self):
        return self.x

    @cached_property
    def coords(self):
        try:
            return list(self.geom[0].exterior.coords)
        except AttributeError:
            try:
                return list(self.geom[0].coords)
            except NotImplementedError:
                return list(self.convex_hull.coords)

    @cached_property
    def lat_lons(self):
        return [(y, x) for x, y in self.coords]

    @cached_property
    def centroid(self):
        if self.geom_type == "Point":
            geom = self.copy()
            geom.radius_km = 0
            return geom
        return self.match(self.as_equal_area.geom.centroid)

    @cached_property
    def convex_hull(self):
        return self.match(self.as_equal_area.geom.convex_hull)

    @cached_property
    def center(self):
        # Return point
        if self.geom_type == "Point":
            return self.match(self.geom[0])
        # Return centroid if polygon does not cross the dateline
        geom = self.geom.to_crs(4326)
        x1, y1, x2, y2 = geom.total_bounds
        lat = (y1 + y2) / 2
        lon = (x1 + x2) / 2
        if abs(x1 - x2) < 180:
            proj_string = self.equal_area_mask.format(lat=lat, lon=lon)
            centroid = geom.to_crs(proj_string).centroid
            return self.match(centroid)
        # Reproject until polygon is in one piece
        for x in range(0, 180, 15):
            for lon in (x, -x):
                reproj = geom.to_crs(self.lat_lon_mask.format(lat=lat, lon=lon))
                x1, _, x2, _ = reproj.total_bounds
                if abs(x1 - x2) < 180:
                    proj_string = self.equal_area_mask.format(lat=lat, lon=lon)
                    centroid = reproj.to_crs(proj_string).centroid
                    return self.match(centroid)
        raise ValueError("Could not compute center")

    @cached_property
    def area(self):
        return self.as_equal_area.polygon.geom[0].area

    @cached_property
    def bounds(self):
        return self.geom.total_bounds

    @cached_property
    def radius_km(self):
        if self.geom_type == "Point":
            return self._radius_km
        lon1, lat1, lon2, lat2 = self.as_wgs84.bounds
        return get_dist_km(lat1, lon1, lat2, lon2) / 2

    @cached_property
    def height_km(self):
        if self.geom_type == "Point":
            return self._radius_km
        lon1, lat1, lon2, lat2 = self.as_wgs84.bounds
        return get_dist_km(lat1, lon1, lat1, lon2) / 2

    @cached_property
    def width_km(self):
        if self.geom_type == "Point":
            return self._radius_km
        lon1, lat1, lon2, lat2 = self.as_wgs84.bounds
        return get_dist_km(lat1, lon1, lat2, lon1) / 2

    @cached_property
    def as_equal_area(self):
        return self.to_crs(self.customize_proj_string(self.equal_area_mask))

    @cached_property
    def as_lat_lon(self):
        return self.to_crs(self.customize_proj_string(self.lat_lon_mask))

    @cached_property
    def as_wgs84(self):
        geom = self.to_crs(4326)
        geom._radius_km = self._radius_km
        return geom

    @cached_property
    def envelope(self):
        if self.geom_type == "Point" and self.radius_km:
            geom = self.as_wgs84
            poly = draw_polygon(geom.center.y, geom.center.x, self.radius_km, 4)
            return self.match(poly, geom.crs)
        geom = self.as_lat_lon
        poly = box(*self.as_lat_lon.bounds)
        return self.match(poly, geom.crs)

    @cached_property
    def ellipse(self):
        """Returns the ellipse around the centroid of the geometry"""
        geom = self.as_lat_lon
        poly = draw_polygon(geom.center.y, geom.center.x, self.radius_km, 50)
        return self.match(poly, geom.crs)

    @cached_property
    def main(self):
        if self.geom_type == "MultiPolygon":
            geoms = {g.area: g for g in self.geom[0].geoms}
            return self.match(geoms[max(geoms)])
        return self.copy()

    @cached_property
    def polygon(self):
        """A representation of the geometry as a polygon"""
        return self.envelope if self.geom_type == "Point" else self

    @cached_property
    def drawable(self):
        geom = self.polygon
        if geom.crs == 4326 and geom.crosses_dateline():
            geom = geom.split_at_dateline()
        return geom.geom[0]

    def to_crs(self, crs):
        obj = self.copy()
        if crs != self.crs:
            obj.geom = obj.geom.to_crs(crs)
            obj._crs = crs
        return obj

    def match(self, other, other_crs=None):
        """Matches another geometry to this class and CRS"""
        if not isinstance(other, self.__class__):
            try:
                other = self.__class__(other, crs=other_crs)
            except ValueError as e:
                if str(e) != "Could not infer CRS":
                    raise
                other = self.__class__(other, crs=self.crs)
        if self.crs != other.crs:
            other = other.to_crs(self.crs)
        return other

    def copy(self):
        copy = self.__class__(self.verbatim, crs=self.verbatim_crs)
        if self.crs != self.verbatim_crs:
            copy = copy.to_crs(self.crs)
        return copy

    def clone(self):
        return self.copy()

    def simplify(self, tolerance=0.05, num_points=25):
        if self.geom_type != "Point":
            geom = (
                self.geom[0]
                if self.geom_type == "Polygon"
                else self.convex_hull.geom[0]
            )
            simplified = None
            coords = None
            while simplified is None or len(coords) > num_points:
                simplified = geom.simplify(tolerance)
                tolerance += 0.01
                try:
                    coords = simplified.exterior.coords
                except AttributeError:
                    coords = simplified.coords
            return self.match(geom if simplified is None else simplified)
        return self.copy()

    def customize_proj_string(self, proj_string):
        center = self.center.as_wgs84
        return proj_string.format(lat=center.y, lon=center.x)

    def equals_exact(self, other, tolerance=0.1):
        other = self.match(other)
        return self.geom[0].equals_exact(other.geom[0], tolerance=tolerance)

    def contains(self, other):
        other = self.as_equal_area.match(other)
        return self.as_equal_area.polygon.geom[0].contains(other.polygon.geom[0])

    def crosses(self, other):
        other = self.as_equal_area.match(other)
        return self.as_equal_area.polygon.geom[0].crosses(other.polygon.geom[0])

    def disjoint(self, other):
        other = self.as_equal_area.match(other)
        return self.as_equal_area.polygon.geom[0].disjoint(other.polygon.geom[0])

    def intersects(self, other):
        other = self.as_equal_area.match(other)
        return self.as_equal_area.polygon.geom[0].intersects(other.polygon.geom[0])

    def touches(self, other):
        other = self.as_equal_area.match(other)
        return self.as_equal_area.polygon.geom[0].touches(other.polygon.geom[0])

    def within(self, other):
        other = self.as_equal_area.match(other)
        return self.as_equal_area.polygon.geom[0].within(other.polygon.geom[0])

    def difference(self, other):
        other = self.as_equal_area.match(other)
        geom = self.as_equal_area.polygon.geom.difference(other.polygon.geom)
        return self.match(geom, self.as_equal_area.crs)

    def intersection(self, other):
        other = self.as_equal_area.match(other)
        geom = self.as_equal_area.polygon.geom.intersection(other.polygon.geom)
        return self.match(geom, self.as_equal_area.crs)

    def intersects_all(self, others, transitive=True):
        """Tests if list of shapes all intersect"""
        others = [self.match(o) for o in others]
        # If transitive is False, shape must itself intersect all others
        if not transitive:
            for other in others:
                if not self.intersects(other):
                    return False
            return True
        # If transitive is True, look for chains of intersection
        intersecting = [self]
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
        geom = self.as_equal_area
        other = geom.match(other)
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
        other = self.match(other)
        # Use centroids where radius is estimated
        geom = (self.centroid if self.geom_type == "Point" else self).geom.unary_union
        other = (
            other.centroid if other.geom_type == "Point" else other
        ).geom.unary_union
        return [self.match(g) for g in nearest_points(geom, other)]

    def similar_to(self, other, *args, dist_km=0.1, **kwargs):
        """Tests if centroid and radius of two shapes are within 100 m"""
        other = self.match(other)
        if args or kwargs:
            return self._similar_to(other, *args, **kwargs)
        if self.centroid_dist_km(other) <= dist_km:
            return abs(self.radius_km - other.radius_km) <= dist_km
        return False

    def combine(self, others, allow_hull=True):
        """Combines list of shapes using their union or convex hull"""
        others = [self.match(o) for o in others]
        geoms = [s.geom[0] for s in [self] + others]
        if self.intersects_all(others):
            return self.match(unary_union(geoms))
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
            buffered = translated.edge(bearing).buffer_km(buffer_dist_km)
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
        other = self.match(other)
        bounds = list(self.bounds)
        for i, val in enumerate([left, bottom, right, top]):
            if val:
                bounds[i] = other.bounds[i]
        bbox = box(*bounds)
        return self.intersection(bbox)

    def centroid_dist_km(self, other, *args, **kwargs):
        """Calculates distance in km between centroids of two geometries"""
        other = self.match(other)
        return self.centroid.dist_km(other.centroid, *args, **kwargs)

    def max_dist_km(self, other):
        """Estimates the maximum distance in km between two geometries"""
        other = self.match(other)
        # Simplify the geometries to hulls to partially mitigate the awfulness
        # of this appraoch
        geom = self.convex_hull if self.geom_type != "Point" else self
        other = other.convex_hull if other.geom_type != "Point" else other
        dists_km = []
        for lon, lat in geom.coords:
            for olon, olat in other.coords:
                dists_km.append(get_dist_km(lat, lon, olat, olon))
        return max(dists_km)

    def min_dist_km(self, other, threshold_km=None):
        """Calculates minimum distance in km between two geometries"""
        other = self.match(other)
        # Use centroids where radius is estimated
        geom = self.centroid if self.geom_type == "Point" else self
        other = other.centroid if other.geom_type == "Point" else other
        if geom.intersects(other):
            return 0.0
        pts = [p.centroid.geom[0] for p in geom.nearest_points(other)]
        dist_km = get_dist_km(pts[0].y, pts[0].x, pts[1].y, pts[1].x)
        # If threshold specified and exceeded, check variants
        if threshold_km is not None and dist_km > threshold_km:
            dists_km = []
            for geom in self.variants():
                geom = geom.centroid if geom.geom_type == "Point" else geom
                pts = geom.nearest_points(other)
                vdist_km = get_dist_km(pts[0].y, pts[0].x, pts[1].y, pts[1].x)
                if vdist_km < threshold_km:
                    return vdist_km
                dists_km.append(vdist_km)
            return min(dists_km)
        return dist_km

    def crosses_dateline(self):
        x1, _, x2, _ = self.bounds
        return abs(x1 - x2) > 180

    def split_at_dateline(self):
        if self.crosses_dateline():
            translated = translate(self.geom[0], xoff=180)
            geom = split(translated, LineString([(180, 90), (180, -90)]))
            geoms = []
            for geom in translate(geom, xoff=-180).geoms:
                x1, _, x2, _ = geom.bounds
                dateline = 180 if min(x1, x2) >= 0 else -180
                coords = [(x if x else dateline, y) for x, y in geom.exterior.coords]
                geoms.append(Polygon(coords))
            return self.match(MultiPolygon(geoms))
        return self

    def draw(self, others=None, title=None, labels=None):
        """Draws a set of geometries"""
        geoms = [self]
        if others:
            if not isinstance(others, list):
                others = [others]
            geoms.extend([self.match(o) for o in others])

        for i, geom in enumerate(geoms):

            drawable = geom.drawable
            try:
                drawable = drawable.geoms
            except AttributeError:
                drawable = [drawable]

            color = "gainsboro" if i else "b"

            for geom in drawable:
                geom = self.match(geom)
                if geom.geom_type == "Point":
                    plt.plot(geom.centroid.x, geom.centroid.y, "o", color=color)
                    plt.plot(geom.x, geom.y, color=color)
                else:
                    plt.plot(geom.x, geom.y, color=color)
                    # plt.fill(geom.x, geom.y)
                    if labels:
                        minx, miny, maxx, maxy = geom.bounds
                        x = (maxx + minx) / 2
                        y = (maxy + miny) / 2
                        kwargs = {
                            "fontsize": 8,
                            "horizontalalignment": "center",
                            "verticalalignment": "center",
                        }
                        if isinstance(labels, (list, tuple)):
                            plt.text(x, y, labels[i], **kwargs)
                        elif isinstance(labels, str):
                            plt.text(x, y, getattr(geom, labels), **kwargs)
        plt.title(title)
        plt.show()

    def buffer_km(self, dist_km):
        """Buffers an object by distance in km"""
        centroid = self.centroid
        lon = centroid.x
        lat = centroid.y
        # Get distances per degree
        km_per_deg_lon = get_dist_km(lat, lon, lat, lon + 1)
        km_per_deg_lat = get_dist_km(lat, lon, lat + 1, lon)
        # Calculate x and y scaling factors
        xfact = dist_km / km_per_deg_lon
        yfact = dist_km / km_per_deg_lat
        return self.match(self.geom.buffer(max([xfact, yfact])))

    def resize(self, multiplier, min_diff_km=0):
        """Resizes the site by multiplier or desired difference in km"""

        # Update the multiplier if a minimum distance is specified
        if min_diff_km:
            km_multiplier = (self.radius_km + min_diff_km) / self.radius_km
            multiplier = max([multiplier, km_multiplier])

        try:
            return self._resized[multiplier].copy()
        except KeyError:
            pass

        geom = self.as_equal_area.convex_hull
        resized = self.match(geom.geom.scale(multiplier, multiplier))
        if not all(resized.geom.is_valid):
            resized = self.match(geom.geom.scale(multiplier))
        if all(resized.geom.is_valid):
            self._resized[multiplier] = resized.copy()
            return resized

        # Log warning and return original geometry
        mask = "Resize failed (multiplier={}, min_diff_km={})"
        logger.debug(mask.format(multiplier, min_diff_km))
        self._resized[multiplier] = self.copy()
        return self.copy()

    def subsection(self, modifier):
        """Splits polygon along a line based on a modifier"""
        if not re.match(r"[NEWS23]{1,2}", modifier):
            multipliers = {
                "center": 0.5,
                "inner": 1.0,
                "lower": 1.0,
                "near": 1.5,
                "outer": 1.0,
                "upper": 1.0,
            }
            try:
                geom = self.envelope.resize(multipliers[modifier])
                assert self.intersects(geom)
                geom.modifier = modifier
                geom.parents.append(self)
                return geom
            except AssertionError:
                raise ValueError("Subsection does not intersect original")
            except KeyError:
                raise ValueError("Illegal modifier: {}".format(modifier))
            except ValueError:
                logger.error("Resize to '{}' failed".format(modifier))
                return self
        fraction = 3 if "3" in modifier else 2
        geom = self.polygon
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
            raise ValueError("Bad direction: {}".format(direction))

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
        line = self.match(line).geom[0]
        geoms = list(split(self.geom[0], line).geoms)
        if len(geoms) > 2:
            bounds = line.bounds
            val = bounds[0] if bounds[0] == bounds[2] else bounds[1]
            grouped = {}
            for geom in geoms:
                index = [i for i, v in enumerate(geom.bounds) if v == val][0]
                grouped.setdefault(index, []).append(geom)
            geoms = [unary_union(g) for g in grouped.values()]
        return [self.match(g) for g in geoms]

    def parse(self, obj, crs=None):
        """Parses coordinates or shapely object"""
        if isinstance(obj, (list, tuple)) and len(obj) == 1:
            obj = obj[0]

        if hasattr(obj, "name"):
            self.name = obj.name

        if isinstance(obj, GeoMetry):
            return obj.geom.copy()

        # Object is a GeoSeries
        if isinstance(obj, gpd.GeoSeries):
            return obj[0]

        # Shape is a shapely geometry object
        if isinstance(obj, BaseGeometry):
            return obj

        # Interpet bytes as WKB
        if isinstance(obj, bytes):
            return wkb.loads(obj)

        # Interpet str as WKT
        if isinstance(obj, str):
            return wkt.loads(obj)

        # Interpret dict as a Geonames-style bounding box
        if isinstance(obj, dict):
            lats = [obj["south"], obj["north"]]
            lons = [obj["west"], obj["east"]]
            return box(lons[0], lats[0], lons[1], lats[1])

        if isinstance(obj, (list, tuple)):
            obj = obj[:]

            # Convert numpy arrays to lists
            try:
                obj = [c.tolist() for c in obj]
            except AttributeError:
                pass

            # Extract underlying shapely shapes from a list of geometries
            if isinstance(obj[0], GeoMetry):
                geoms = []
                for geom in obj:
                    geom = self.__class__(geom.verbatim_geom, crs=geom.verbatim_crs)
                    if geom.crs != crs:
                        geom = geom.to_crs(crs)
                    geoms.append(geom.geom[0])
                obj = geoms

            # Interpret lists of shapely objects
            if isinstance(obj[0], BaseGeometry):

                # Convert list mixing multiple shapely objects to GeometryCollection
                if len({s.geom_type for s in obj}) > 1:
                    return GeometryCollection(obj)

                # Convert list of Point to a LineString or Polygon
                shape_class = LineString if len(obj) == 2 else Polygon
                try:
                    return shape_class([(p.x, p.y) for p in obj])
                except AttributeError:
                    pass

                # Convert list of Polygon to a MultiPolygon, then take the convex hull
                if isinstance(obj[0], Polygon):
                    try:
                        return unary_union(MultiPolygon(obj))
                    except ValueError:
                        pass

                # Convert list of LineString to a MultiLineString
                if isinstance(obj[0], LineString):
                    try:
                        return MultiLineString(obj)
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
                lat_lons = list(obj)

            # Interpret a pair of lists as [lats, lons]
            elif list_of_lists:
                # Shape is [lats, lons]
                lat_lons = list(zip(*obj))

            # Interpret a single pair as a point
            elif len(obj) == 2:
                lat_lons = [obj]

            if lat_lons:
                # Ensure that coordinates are floats
                lats = []
                lons = []
                for lat, lon in lat_lons:
                    lats.append(self.parse_coordinate(lat, "latitude"))
                    lons.append(self.parse_coordinate(lon, "longitude"))

                # Convert coordinates to shapely geometry
                xy = list(zip(lons, lats))
                if len(xy) == 1:
                    return Point(xy[0])
                if len(xy) == 2:
                    return LineString(xy)
                return Polygon(xy)

        # Check for a geometry attribute
        if hasattr(obj, "geometry"):
            return self.parse(obj.geometry)

        # Give up
        msg = "Parse failed: {} (unknown format)".format(obj)
        logger.error(msg)
        raise ValueError(msg)

    def parse_coordinate(self, val, *args, **kwargs):
        """Placeholder function used to parse coordinates"""
        return float(val)

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


def geom_to_geoseries(geoms):
    """Converts list of geoms to a GeoSeries with a coherenent equal-area CRS"""
    series = gpd.GeoSeries([g.geom[0] for g in geoms], crs=geoms[0].crs)
    ctr = geoms[0].__class__(box(*series.total_bounds), crs=series.crs).center
    return series.to_crs(
        geoms[0].__class__.equal_area_mask.format(lat=ctr.y, lon=ctr.x)
    )
