"""Defines class for manipulating geographic data"""
import json
import re
import logging
from functools import wraps

import matplotlib.pyplot as plt
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely import wkb, wkt
from shapely.geometry.base import BaseGeometry
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon
)
from shapely.ops import nearest_points, split, unary_union

from ....databases.cache import CacheDict
from ..helpers import (
    am_longitudes,
    bounding_box,
    crosses_180,
    draw_circle,
    draw_polygon,
    fix_shape,
    get_dist_km,
    epsg_id,
    normalize_shape,
    pm_longitudes,
    similar,
    sort_geoms,
    subhorizontal,
    subvertical,
    translate_with_uncertainty,
    trim
)




logger = logging.getLogger(__name__)




class NaiveGeoMetry:
    """Manipulate and calculate properties of geographic shapes"""
    resized = CacheDict()
    resized.max_recent = 1000
    transformers = {}
    wkts = {}


    def __init__(self, shape, crs='EPSG:4326', radius_km=None):
        self._crs = None
        self._coords = None
        self._centroid = None
        self._hull = None
        self._radius_km = self.validate_radius(radius_km)
        # Attributes below defined as properties to support deferred parsing
        self._shape = None
        self._geom_type = None
        self._parsed_shape = None
        self._valid_shape = None
        self._verbatim_shape = None
        # Set exposed attributes
        self.subshapes = None
        self.crs = crs
        # Keep a record of the original CRS, etc.
        self.verbatim = shape       # original data
        self.verbatim_shape = None  # original shapely object
        self.verbatim_crs = crs
        # Additional attributes
        self.cache = ['_coords', '_centroid', '_hull']
        self.parents = []
        self.modifier = None
        self.transformed = {}
        self.name = None
        if not self.crs:
            raise ValueError('No CRS defined: {}'.format(shape))


    def __bool__(self):
        return not self.shape.is_empty if self.shape else False


    def __eq__(self, other):
        try:
            return (self.shape.equals(other.shape)
                    and self.parsed_shape.equals(other.parsed_shape))
        except AttributeError:
            return False


    def __getattr__(self, attr):
        try:
            result = getattr(self.shape, attr)
            # Wrap shapely objects in the current class
            if isinstance(result, BaseGeometry):
                return self.derive(result)
            return result
        except AttributeError:
            mask = "'{}' object (geom_type={}) has no attribute '{}'"
            msg = mask.format(self.__class__.__name__, self.geom_type, attr)
            raise AttributeError(msg)


    def __iter__(self):
        return iter(self.lat_lngs)


    def __len__(self):
        return len(self.coords)


    def __str__(self):
        return str(self.shape)


    @property
    def center(self):
        """Simplistically calculates the center of the bounding box"""
        return self.shape.centroid


    @property
    def centroid(self):
        """Calculates the centroid of the geometry"""
        if self._centroid is None:
            self._centroid = self.derive(self.shape.centroid, radius_km=0)
        return self._centroid


    @property
    def coords(self):
        """Returns coordinates as a list of x-y pairs"""
        if not self:
            return []
        if self._coords is None:
            try:
                self._coords = list(self.shape.exterior.coords)
            except AttributeError:
                self._coords = list(self.shape.coords)
        return self._coords[:]


    @property
    def crs(self):
        """Returns the identifier for the current coordinate reference system"""
        return self._crs


    @crs.setter
    def crs(self, crs):
        if not self._crs:
            self._crs = crs
        else:
            raise AttributeError('Cannot change crs. Use transform to create'
                                 ' a geometry with the new crs.')


    @property
    def ellipse(self):
        """Calculates an uncertainty ellipse based on the radius"""
        radius_km = self.radius_km if self.radius_km is not None else 1
        return self.draw_circle(radius_km)


    @property
    def height_km(self):
        """Calculates height of the bounding box"""
        _, miny, _, maxy = self.bounds
        x = self.centroid.coords[0][0]
        return get_dist_km(miny, x, maxy, x)


    @property
    def lat_lngs(self):
        """Returns coordinates as a list of lat-lng pairs"""
        return [(y, x) for x, y in self.coords]


    @property
    def latitudes(self):
        """Returns list of latitudes"""
        return list(self.y)


    @property
    def longitudes(self):
        """Returns list of longitudes"""
        return list(self.x)


    @property
    def width_km(self):
        """Calculates width of the bounding box"""
        minx, _, maxx, _ = self.bounds
        y = self.centroid.coords[0][1]
        return get_dist_km(y, minx, y, maxx)


    @property
    def xy(self):
        """Returns coordinates as lists of x and y"""
        return list(zip(*self.coords))


    @property
    def x(self):
        """Returns list of ys a la shapely"""
        return [x for x, _ in self.coords]


    @property
    def y(self):
        """Returns list of x coordinates a la shapely"""
        return [y for _, y in self.coords]


    @property
    def radius_km(self):
        """Returns the radius in km, calculating it if appropriate"""
        if (self._radius_km is None
            and self.geom_type not in {None, 'Point'}
            and max([abs(c) for c in self.longitudes]) <= 360):
                minx, miny, maxx, maxy = self.bounds
                radius_km = get_dist_km(miny, minx, maxy, maxx) / 2
                self._radius_km = self.validate_radius(radius_km)
        return self._radius_km


    @radius_km.setter
    def radius_km(self, radius_km):
        radius_km = self.validate_radius(radius_km)
        if radius_km != self._radius_km:
            self._radius_km = radius_km
            # If radius_km is given for a point, set the shape attribute to
            # the envelope calculated for that radius
            if self.geom_type == 'Point' and radius_km:
                #lng, lat = self.centroid.coords[0]  # fails with GeoMetry
                lng, lat = self.shape.centroid.coords[0]
                for attr in self.cache:
                    setattr(self, attr, None)
                self._shape = draw_polygon(lat, lng, radius_km, sides=4)


    @property
    def shape(self):
        """Returns the underlying shapely shape"""
        if self.verbatim and self._shape is None:
            parsed = self.parse(self.verbatim)
            # NaiveGeoMetry handled by parse and returns None
            if parsed:
                self.geom_type = parsed.geom_type
                self.shape = parsed
        return self._shape


    @shape.setter
    def shape(self, shape):
        # Set verbatim shape only when shape is first set
        if self._verbatim_shape is None:
            self.verbatim_shape = normalize_shape(shape)
        # Set shape attriutes, repairing the given shape if needed
        self.parsed_shape = shape
        self.valid_shape = fix_shape(shape)
        if shape.geom_type == 'Point' and self.radius_km:
            x, y = self.valid_shape.x, self.valid_shape.y
            self._shape = draw_polygon(y, x, self.radius_km, sides=4)
        else:
            self._shape = self.valid_shape
        # Clear any cached parameters
        for attr in self.cache:
            setattr(self, attr, None)
        # Verify that both shapes are shapely objects
        try:
            assert isinstance(self.parsed_shape, BaseGeometry)
            assert not self.parsed_shape.is_empty
            assert isinstance(self.valid_shape, BaseGeometry)
            assert not self.valid_shape.is_empty
            assert self.valid_shape.intersects(self._shape)
        except AssertionError:
            raise ValueError('Unfixable shape: {}'.format(self.verbatim))
        self.finalize_shape()
        #logging.debug('Successfully parsed shape from {}'.format(type(shape)))


    def finalize_shape(self):
        pass


    @property
    def geom_type(self):
        if self.verbatim and self._geom_type is None:
            self.shape
        return self._geom_type


    @geom_type.setter
    def geom_type(self, val):
        self._geom_type = val


    @property
    def parsed_shape(self):
        if self.verbatim and self._parsed_shape is None:
            self.shape
        return self._parsed_shape


    @parsed_shape.setter
    def parsed_shape(self, val):
        self._parsed_shape = val


    @property
    def valid_shape(self):
        if self.verbatim and self._valid_shape is None:
            self.shape
        return self._valid_shape


    @valid_shape.setter
    def valid_shape(self, val):
        self._valid_shape = val


    @property
    def verbatim_shape(self):
        if self.verbatim and self._verbatim_shape is None:
            self.shape
        return self._verbatim_shape


    @verbatim_shape.setter
    def verbatim_shape(self, val):
        self._verbatim_shape = val


    @property
    def hull(self):
        """Returns the convex hull of the underlying shape

        The usage for MultiPolygons is more complex. MultiPolygons for
        geographic features have two main uses in this module: to check if
        one feature intersects another and to calculate distances along
        bearings. These aims can be at cross purposes for something like the
        United States, where the convex hull is needed to test admin divisions
        (like for Alaska) but directions are usually understood as relative to
        the continental United States. MultiPolygons are therefore stored with
        distinct hulls and shapes, which is janky but serviceable for now.

        For all other shapes, the hull and convex hull should be identical.
        """
        if self._hull is None:
            if self.verbatim_shape.geom_type == 'MultiPolygon':
                # Returns the original convex hull of a MultiPolygon transformed
                # to the current CRS. Does not use derive because CRS may have
                # changed since GeoMetry object was created.
                shape = self.verbatim_shape
                hull = self.__class__(shape.convex_hull, crs=self.verbatim_crs)
                if hull.crs != self.crs:
                    hull = hull.transform(self.crs)
                self._hull = hull
            else:
                self._hull = self.convex_hull
        return self._hull


    def difference(self, other):
        """Calculates the part of this geometry that does not intersect other"""
        other = self.attune(other)
        return self.derive(self.shape.difference(other))


    def intersection(self, other, try_hull=True):
        """Calculates the intersection between this and another geometry"""
        other = self.attune(other)
        if self.shape.intersects(other.shape):
            return self.derive(self.shape.intersection(other.shape))
        # If shapes do not intersect, try hull
        if try_hull and self.shape != self.verbatim_shape.convex_hull:
            return self.derive(self.hull.intersection(other.hull))
        raise ValueError('Geometries do not intersect')


    def intersects(self, other, try_hull=True):
        """Tests whether this geometry intersects the others"""
        other = self.attune(other)
        if try_hull:
            return self.hull.shape.intersects(other.hull.shape)
        return self.shape.intersects(other.shape)


    def attune(self, other, strict=False):
        """Converts the given object to this class"""
        geom = other
        if (not isinstance(other, self.__class__)
            or (strict and type(self) != type(other))):
                geom = self.__class__(other)
        if geom.crs != self.crs:
            try:
                geom = geom.transform(self.crs)
            except ValueError:
                geom = self.derive(other)
        return geom


    def derive(self, other, **kwargs):
        """Derives a new geometry from this one"""
        kwargs['crs'] = self.crs
        return self.__class__(other, **kwargs)


    def clone(self):
        """Creates a copy of the current object"""
        return self.__class__(self)


    def variants(self):
        """Calculates negated and transposed geometries"""
        lats = self.latitudes[:]
        lngs = self.longitudes[:]
        neg_lats = [-1 * lat for lat in lats]
        neg_lngs = [-1 * lng for lng in lngs]
        for i, coords in enumerate((
            (lats, lngs),          # lats, lngs
            (lngs, lats),          # lngs, lats
            (lats, neg_lngs),      # lats, -lngs
            (neg_lats, lngs),      # -lats, lngs
            (neg_lats, neg_lngs),  # -lats, -lngs
            (lngs, neg_lats),      # lngs, -lats
            (neg_lngs, lats),      # -lngs, lats
            (neg_lngs, neg_lats)   # -lngs, -lats
        )):
            try:
                geom = self.derive(coords) if i else self
                geom.shape
                yield geom
            except ValueError:
                pass


    def validate(self):
        """Validates the shape"""
        return self.shape


    def transform(self, to_crs, trn=None, **kwargs):
        """Transforms shape to another coordinate system"""
        if trn is None:
            from_crs = epsg_id(self.crs)
            to_crs = epsg_id(to_crs)
            trn = get_transformer(from_crs, to_crs, always_xy=True)[0]
        x, y = self.xy
        coords = trn.transform(x, y, **kwargs)
        xy = list(zip(*coords))
        if len(xy) == 1:
            shape = Point(xy[0])
        elif len(xy) == 2:
            shape = LineString(xy)
        else:
            shape = Polygon(xy)
        transformed = self.__class__(shape, crs=to_crs)
        # Transfer the radius if original is in lat-lng space
        if max([abs(c) for c in self.longitudes]) <= 360:
            transformed.radius_km = self.radius_km
        return transformed


    def distance_from(self, other, *args, **kwargs):
        """Alias for dist_km"""
        return self.dist_km(other, *args, **kwargs)


    def dist_km(self, other, threshold_km=None):
        """Calculates minimum distance in km between two geometries"""
        other = self.attune(other)
        # Use centroids where radius is estimated
        geom = self.centroid if self.geom_type == 'Point' else self
        other = other.centroid if other.geom_type == 'Point' else other
        if geom.intersects(other):
            return 0
        pts = [pt.centroid.shape for pt in geom.nearest_points(other)]
        dist_km = get_dist_km(pts[0].y, pts[0].x, pts[1].y, pts[1].x)
        # If threshold specified and exceeded, check variants
        if threshold_km is not None and dist_km > threshold_km:
            dists_km = []
            for geom in self.variants():
                geom = geom.centroid if geom.geom_type == 'Point' else geom
                pts = nearest_points(geom, other)
                vdist_km = get_dist_km(pts[0].y, pts[0].x, pts[1].y, pts[1].x)
                if vdist_km < threshold_km:
                    return vdist_km
                dists_km.append(vdist_km)
            return min(dists_km)
        return dist_km


    def nearest_points(self, other):
        """Calculates nearest points between this and another geometry"""
        other = self.attune(other)
        # Use centroids where radius is estimated
        geom = self.centroid if self.geom_type == 'Point' else self
        other = other.centroid if other.geom_type == 'Point' else other
        return [self.attune(g) for g in nearest_points(geom, other)]


    def max_dist_km(self, other):
        """Estimates the maximum distance in km between two geometries"""
        other = self.attune(other)
        # Simplify the geometries to hulls to partially mitigate the awfulness
        # of this appraoch
        geom = self.convex_hull if self.geom_type != 'Point' else self
        other = other.convex_hull if other.geom_type != 'Point' else other
        dists_km = []
        for lat, lng in geom.lat_lngs:
            for olat, olng in other.lat_lngs:
                dists_km.append(get_dist_km(lat, lng, olat, olng))
        return max(dists_km)


    def centroid_dist_km(self, other, *args, **kwargs):
        """Calculates distance in km between centroids of two geometries"""
        other = self.attune(other)
        return self.centroid.dist_km(other.centroid, *args, **kwargs)


    def translate(self, bearing, dist_km, **kwargs):
        """Translates the shape based on a distance and bearing"""
        if self.radius_km >= 100:
            kwargs['abs_err_degrees'] = 5.75
        points = []
        for lat, lng in self.lat_lngs:
            polygon = translate_with_uncertainty(lat, lng, bearing, dist_km,
                                                 **kwargs)
            points.extend(polygon.exterior.coords)
        return self.derive(MultiPoint(points).convex_hull)


    def interpret_directions(self, bearing, dist_km=None, **kwargs):
        """Interprets directions based on type of shape"""
        # Use the edge when translating a complex polygon N, S, E, or W.
        # Primarily for calculating directions for country or state borders.
        use_edge = (len(bearing) == 1
                    and self.geom_type != 'Point'
                    and not self.shape.equals(self.envelope))
        if use_edge:
            shape = self.edge(bearing)
        elif self.radius_km <= 10:
            shape = self.subsection(bearing)
        else:
            shape = self

        # If no distance is given, guess distance based on the size of
        # the polygon in the axis corresponding to the bearing.
        extend_from_edge = False
        if dist_km is None:
            # Decrease scalar as size of original shape increases
            scalar = 2 if self.radius_km <= 100 else 4
            if bearing in 'NS':
                dist_km = self.height_km / 4
            elif bearing in 'EW':
                dist_km = self.width_km / 4
            else:
                dist_km = self.radius_km / 4
            extend_from_edge = True
            kwargs['rel_err_distance'] = 0

        # Translate shape according to the bearing and distance
        translated = shape.translate(bearing, dist_km, **kwargs)

        if use_edge and not extend_from_edge:
            # Buffer edges according to precision if disance specified. Must
            # be buffer, not resize or scale, because edge returns a line.
            buffer_dist_km = dist_km * kwargs['rel_err_distance']
            buffered = translated.edge(bearing).buffer_km(buffer_dist_km)
            translated = self.derive(buffered)

        elif use_edge and extend_from_edge:
            # This branch is intended for translations of countries where
            # the distance was estimated based on the size of the original
            # polygon. It produces a polygon that is continuous from the
            # original to the translated edge.

            # Run the original shape through the translate method so it has the
            # same shape as the translated shape
            smoothed = shape.translate(bearing, 0, **kwargs)

            # Create a new shape from the two parallel edges. Reorder the
            # translated edge so that the points are in the right order when
            # the lists are combined.
            orig_edge = smoothed.lat_lngs
            tran_edge = translated.lat_lngs[::-1]
            translated = self.derive(orig_edge + tran_edge)

        # If geometry is a polygon (i.e., if the extent of the geometry is
        # well-constrained), limit the translated object to the portion that
        # does not intersect the original polygon.
        #if self.geom_type != 'Point':
        #    translated = translated.difference(self)
        # For simple bearings, crop height or width of the translated shape
        # based on the original. For example, if the bearing is E, the
        # north-south extent of the translated polygon will not exceed the
        # north-south extent of the original polygon.
        if self.radius_km > 500 and not extend_from_edge:
            crop_to = self.subsection(bearing)
            kwargs = {
                'N': {'top': False},
                'S': {'bottom': False},
                'E': {'right': False},
                'W': {'left': False},
                'NE': {'top': False, 'right': False},
                'NW': {'left': False, 'top': False},
                'SE': {'bottom': False, 'right': False},
                'SW': {'left': False, 'bottom': False}
            }
            try:
                return translated.crop(crop_to, **kwargs[bearing])
            except KeyError:
                pass
        return translated


    def crop(self, other, left=True, bottom=True, right=True, top=True):
        """Crops shape to bounding box for all directions given as True"""
        other = self.attune(other)
        bounds = list(self.bounds)  # minx=left,miny=bottom,maxx=right,maxy=top
        for i, val in enumerate([left, bottom, right, top]):
            if val:
                bounds[i] = other.bounds[i]
        lng1, lat1, lng2, lat2 = bounds
        bbox = bounding_box(lat1, lng1, lat2, lng2)
        return self.intersection(bbox)


    def overlap(self, other, percent=False):
        """Calculates amount of overlap between two objects"""
        other = self.attune(other)
        try:
            site, other = [s.envelope for s in [self, other]]
            if site.disjoint(other):
                return 0.
            if site.contains(other):
                return 1. if percent else other.area
            if site.within(other):
                return 1. if percent else site.area
            # Calculate overlap as the ratio of the area of the intersection
            # to the smaller of the two shapes
            if all([s.area for s in [site, other]]):
                larger = sorted([site, other], key=lambda s: s.area)[-1]
                overlap = site.intersection(other).area
                return overlap / larger.area if percent else overlap
        except ValueError:
            pass
        return 0.


    def similar_to(self, other, *args, **kwargs):
        """Tests if centroid and radius of two shapes are within 100 m"""
        other = self.attune(other)
        if args or kwargs:
            return self._similar_to(other, *args, **kwargs)
        if self.centroid_dist_km(other) <= 0.1:
            return abs(self.radius_km - other.radius_km) <= 0.1
        return False


    def draw_circle(self, *args, **kwargs):
        """Draws a circle around the centroid of the geometry"""
        lng, lat = self.centroid.coords[0]
        return self.derive(draw_circle(lat, lng, *args, **kwargs))


    def draw_polygon(self, *args, **kwargs):
        """Draws a polygon around the centroid of the geometry"""
        lng, lat = self.centroid.coords[0]
        return self.derive(draw_polygon(lat, lng, *args, **kwargs))


    def parse(self, shape):
        """Parses coordinates or shapely object"""
        if shape:
            if hasattr(shape, 'name'):
                self.name = shape.name
            # Check for class with a geometry attribute
            try:
                shape = shape.geometry
            except AttributeError:
                pass
            if isinstance(shape, NaiveGeoMetry):
                # Transform the shape to the given CRS if necessary
                if epsg_id(self.crs) != epsg_id(shape.crs):
                    shape = shape.transform(self.crs)
                # Shape is an instance of this class
                self.verbatim = shape.verbatim
                self.verbatim_shape = shape.verbatim_shape
                self.verbatim_crs = shape.verbatim_crs
                self.geom_type = shape.geom_type
                self.shape = shape.parsed_shape
                # Attributes that only exist in a subclass will not be carried over
                for attr in self.cache:
                    try:
                        setattr(self, attr, getattr(shape, attr))
                    except AttributeError:
                        pass
                if self._radius_km is None:
                    # Setting the private attribute sidesteps the radius
                    # setter, which produces a different shape for points
                    self.radius_km = shape.radius_km
                self.subshapes = shape.subshapes
                return None
            if isinstance(shape, BaseGeometry):
                # Shape is a shapely geometry object
                return shape
            if isinstance(shape, bytes):
                return wkb.loads(shape)
            if isinstance(shape, str):
                return wkt.loads(shape)
            if isinstance(shape, dict):
                # Shape is a GeoNames-style bounding box
                lats = [shape['south'], shape['north']]
                lngs = [shape['west'], shape['east']]
                return Polygon(bounding_box(lats[0], lngs[0], lats[1], lngs[1]))
            if isinstance(shape, (list, tuple)):
                shape = shape[:]
                # Convert numpy arrays to lists
                try:
                    shape = [c.tolist() for c in shape]
                except AttributeError:
                    pass
                # Extract underlying shapely shapes from a list of geometries
                if isinstance(shape[0], NaiveGeoMetry):
                    geoms = []
                    for geom in shape:
                        shape = geom.verbatim_shape
                        geom = self.__class__(shape, crs=geom.verbatim_crs)
                        if geom.crs != self.crs:
                            geom = geom.transform(self.crs)
                        geoms.append(geom)
                    shape = [g.shape for g in geoms]
                # Lists of shapely objects
                if isinstance(shape[0], BaseGeometry):
                    if len(shape) == 1:
                        return shape[0]
                    # Shape is a list mixing multiple shapely objects
                    if len({s.geom_type for s in shape}) > 1:
                        return GeometryCollection(shape)
                    # Shape is a list of Points
                    shape_class = LineString if len(shape) == 2 else Polygon
                    try:
                        return shape_class([(p.x, p.y) for p in shape])
                    except AttributeError:
                        pass
                    # Shape is a list of Polygons
                    if isinstance(shape[0], Polygon):
                        try:
                            return MultiPolygon(shape)
                        except ValueError:
                            pass
                    # Shape is a list of LineStrings
                    if isinstance(shape[0], LineString):
                        try:
                            return MultiLineString(shape)
                        except ValueError:
                            pass
                # Shape is a list of coordinates
                list_of_lists = isinstance(shape[0], (list, tuple))
                try:
                    list_of_pairs = all([len(c) == 2 for c in shape[:10]])
                except TypeError:
                    list_of_pairs = False
                if list_of_lists and list_of_pairs:
                    # Shape is [(lat, lng)] or [(lat1, lng1),...]
                    lat_lngs = list(shape)
                elif list_of_lists:
                    # Shape is [lats, lngs]
                    lat_lngs = list(zip(*shape))
                elif len(shape) == 2:
                    # Shape is (lat, lng)
                    lat_lngs = [shape]
                else:
                    msg = 'Parse failed: {} (unknown format)'.format(shape)
                    logger.error(msg)
                    raise ValueError(msg)
                # Ensure that coordinates are floats
                lats = []
                lngs = []
                for lat, lng in lat_lngs:
                    lats.append(self.parse_coordinate(lat, 'latitude'))
                    lngs.append(self.parse_coordinate(lng, 'longitude'))
                # Convert coordinates to shapely geometry
                xy = list(zip(lngs, lats))
                if len(xy) == 1:
                    return Point(xy[0])
                if len(xy) == 2:
                    return LineString(xy)
                return Polygon(xy)
        msg = 'Parse failed: {} (empty)'.format(shape)
        raise ValueError(msg)


    def parse_coordinate(self, val, *args, **kwargs):
        """Placeholder function used to parse coordinates"""
        return val


    def simple_combine(self, *others):
        """Combines shapes based on min and max coordinates"""
        others = [self.attune(o) for o in others]
        if not all([epsg_id(o.crs) == epsg_id(self.crs) for o in others]):
            raise AssertionError('Shapes use different CRS')
        minlng, minlat, maxlng, maxlat = self.bounds
        lats = [minlat, maxlat]
        lngs = [minlng, maxlng]
        for other in others:
            minlng, minlat, maxlng, maxlat = other.bounds
            lats.extend([minlat, maxlat])
            lngs.extend([minlng, maxlng])
        # Normalize longitudes if coordinates are lat/lng
        if abs(max(lngs)) <= 360 and abs(max(lats)) <= 90:
            if crosses_180(lngs):
                lngs = am_longitudes(lngs)
            else:
                lngs = pm_longitudes(lngs)
        # Construct a bounding box combining all given geometries
        try:
            bbox = bounding_box(min(lats), min(lngs), max(lats), max(lngs))
            return self.derive(Polygon(bbox))
        except ValueError:
            return self.derive(Point(minlng, minlat))


    def draw(self, others=None, title=None, labels=None):
        """Draws a set of geometries"""
        geoms = [self]
        if others:
            if not isinstance(others, list):
                others = [others]
            geoms.extend([self.attune(o) for o in others])
        for i, geom in enumerate(geoms):
            color = 'gainsboro' if i else 'b'
            if geom.geom_type == 'Point':
                x, y = geom.centroid.coords[0]
                plt.plot(x, y, 'o', color=color)
                plt.plot(geom.x, geom.y, color=color)
            elif geom.subshapes:
                for geom_ in geom.subshapes.geoms:
                    try:
                        plt.plot(*geom_.exterior.xy, color=color)
                    except AttributeError:
                        plt.plot(*geom_.xy, color=color)
            else:
                try:
                    plt.plot(geom.x, geom.y, color=color)
                    #plt.fill(geom.x, geom.y)
                    if labels:
                        minx, miny, maxx, maxy = geom.bounds
                        x = (maxx + minx) / 2
                        y = (maxy + miny) / 2
                        kwargs = {
                            'fontsize': 8,
                            'horizontalalignment': 'center',
                            'verticalalignment': 'center'
                        }
                        if isinstance(labels, (list, tuple)):
                            plt.text(x, y, labels[i], **kwargs)
                        elif isinstance(labels, str):
                            plt.text(x, y, getattr(geom, labels), **kwargs)
                except Exception as e:
                    logger.warning(e)
                    for geom_ in geom.geoms:
                        plt.plot(*geom_.exterior.xy, color=color)
        plt.title(title)
        plt.show()


    def combine(self, others, allow_hull=True):
        """Combines list of shapes using their union or convex hull"""
        others = [self.attune(o) for o in others]
        geoms = [s.shape for s in [self] + others]
        if self.intersects_all(others):
            return self.derive(unary_union(geoms))
        if allow_hull:
            return self.derive(GeometryCollection(geoms).convex_hull)
        raise ValueError('Could not combine shapes')


    def intersects_all(self, others, transitive=True):
        """Tests if list of shapes all intersect"""
        others = [self.attune(o) for o in others]
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
            for shape in intersecting[:]:
                for other in others:
                    if shape.intersects(other):
                        intersecting.append(other)
                    else:
                        disjoint.append(other)
            last = intersecting
            others = disjoint
        return not disjoint


    def buffer_km(self, dist_km):
        """Buffers an object by distance in km"""
        lng, lat = self.centroid.coords[0]
        # Get distances per degree
        km_per_deg_lng = get_dist_km(lat, lng, lat, lng + 1)
        km_per_deg_lat = get_dist_km(lat, lng, lat + 1, lng)
        # Calculate x and y scaling factors
        xfact = dist_km / km_per_deg_lng
        yfact = dist_km / km_per_deg_lat
        return self.derive(self.shape.buffer(max([xfact, yfact])))


    def resize(self, multiplier, min_diff_km=0):
        """Resizes the site by multuplier or desired difference in km"""
        if multiplier == 1 and not min_diff_km:
            return self.clone()
        key = json.dumps([str(self.shape), multiplier, min_diff_km])
        try:
            return self.resized[key].clone()
        except KeyError:
            # Update multiplier based on min_dist_km
            if min_diff_km:
                km_multiplier = (self.radius_km + min_diff_km) / self.radius_km
                multiplier = max([multiplier, km_multiplier])
            # Calculate dist parameter required by the shapely buffer function
            min_x, min_y, max_x, max_y = self.shape.bounds
            mult = (multiplier - 1) if multiplier > 1 else -(1 - multiplier)
            dist = (max_x - min_x + max_y - min_y) * mult / 4
            return self.derive(self.shape.buffer(dist))


    def split(self, line, direction):
        """Splits shape along line, returning the half in the given direction"""
        assert direction in {'N', 'S', 'E', 'W'}
        geoms = self.split_and_group(line)
        geoms = sort_geoms(geoms, direction)
        return geoms[-1] if direction in 'NE' else geoms[0]


    def edge(self, direction):
        """Approximates the edge of a geometry based on its bounds"""
        # Define params for vertical
        if direction in 'NS':
            index = 0
            trim_func = subvertical
            bounds = self.longitudes
        elif direction in 'EW':
            index = 1
            trim_func = subhorizontal
            bounds = self.latitudes
        else:
            raise ValueError('Bad direction: {}'.format(direction))

        # Split polygon into halves based on bounding coordinates
        coords = self.coords
        if coords[0] == coords[-1]:
            coords.pop(-1)
        indexes = [i for i, pt in enumerate(coords)
                   if similar(pt[index], min(bounds))]
        coords = coords[indexes[-1]:] + coords[:indexes[-1]]

        # Second half
        indexes = [i for i, pt in enumerate(coords)
                   if similar(pt[index], max(bounds))]
        coords = coords[indexes[-1]:], coords[:indexes[-1]]

        # Trim features at edge of polygon that are parallel to the axis
        # given by the direction. For example, if looking for the north
        # coast, subvertical (e.g., N-S) segments on the edge of the coast
        # are trimmed because they are not really part of the coast we're
        # interested in.
        coords = [trim(c, index, trim_func) for c in coords]
        geoms = [self.derive(LineString(c)) for c in coords if len(c) > 1]
        geoms = sort_geoms(geoms, direction)
        geom = geoms[-1] if direction in 'NE' else geoms[0]
        geom.parents.append(self)

        return geom


    def subsection(self, modifier):
        """Splits polygon along a line based on a modifier"""
        if not re.match(r'[NEWS23]{1,2}', modifier):
            multipliers = {
                'center': 0.5,
                'inner': 1.0,
                'lower': 1.0,
                'near': 1.5,
                'outer': 1.0,
                'upper': 1.0
            }
            try:
                resized = self.envelope.resize(multipliers[modifier])
                geom = self.derive(resized)
                assert self.intersects(geom)
                geom.modifier = modifier
                geom.parents.append(self)
                return geom
            except AssertionError:
                raise ValueError('Subsection does not intersect original')
            except KeyError:
                raise ValueError('Illegal modifier: {}'.format(modifier))
            except ValueError:
                logger.error("Resize to '{}' failed".format(modifier))
                return self
        fraction = 3 if '3' in modifier else 2
        geom = self.clone()
        # Split along longitude
        if modifier[-1] in 'EW':
            lats = geom.latitudes
            lngs = geom.longitudes
            w = (max(lngs) - min(lngs)) / fraction
            x = max(lngs) - w if modifier[-1] == 'E' else min(lngs) + w
            line = LineString([(x, min(lats)), (x, max(lats))])
            geom = geom.split(line, modifier[-1])
        # Split along latitude
        if modifier[0] in 'NS':
            lats = geom.latitudes
            lngs = geom.longitudes
            h = (max(lats) - min(lats)) / fraction
            y = max(lats) - h if modifier[-1] == 'N' else min(lats) + h
            line = LineString([(min(lngs), y), (max(lngs), y)])
            geom = geom.split(line, modifier[0])
        geom = self.derive(geom)
        geom.modifier = modifier
        geom.parents.append(self)
        return geom


    def supersection(self):
        """Returns the parent of the current section"""
        return self.parents[-1]


    def split_and_group(self, line):
        """Groups geometries based on which edge intersects a given line

        Needed when the split line cuts through a gap in a polygon.
        """
        line = self.attune(line).shape
        geoms = list(split(self.shape, line))
        if len(geoms) > 2:
            bounds = line.bounds
            val = bounds[0] if bounds[0] == bounds[2] else bounds[1]
            grouped = {}
            for geom in geoms:
                index = [i for i, v in enumerate(geom.bounds) if v == val][0]
                grouped.setdefault(index, []).append(geom)
            geoms = [unary_union(g) for g in grouped.values()]
        return [self.derive(g) for g in geoms]


    def validate_radius(self, radius_km):
        """Verifies that radius is a positive number"""
        if not (radius_km is None
                or isinstance(radius_km, (float, int)) and radius_km >= 0):
            msg = 'Invalid radius_km: {} (bounds={})'
            raise ValueError(msg.format(radius_km, self.bounds))
        return radius_km


    def _similar_to(self, other, min_overlap=0.9, min_area_ratio=0.5):
        """Tests if two shapes are similar in position and size"""
        other = self.attune(other)
        try:
            if self.intersects(other):
                areas = [s.envelope.area for s in [self, other]]
                area_ratio = min(areas) / max(areas)
                return (self.overlap(other, True) >= min_overlap
                        and area_ratio >= min_area_ratio)
        except ValueError:
            pass
        return False




def same_meridian(func):
    """Projects shapes so that they are not split by the antimeridian"""
    @wraps(func)
    def wrapper(inst, other, *args, **kwargs):
        geoms = [NaiveGeoMetry(s) for s in inst.normalize(other)]
        result = getattr(geoms[0], func.__name__)(geoms[1], *args, **kwargs)
        #geoms[0].draw(geoms[1:], title='{}={}'.format(func.__name__, result))
        return inverse(inst, result)
    return wrapper


def equal_area(func):
    """Projects shapes to and from equal area projection"""
    @wraps(func)
    def wrapper(inst, *args, **kwargs):
        # Project shape to equal area CRS
        shapes, trn, args = forward(inst, *args)
        # Run function on transformed coordinates from parent
        if len(shapes) == 1 and not (args or kwargs):
            result = getattr(shapes[0], func.__name__)
        elif len(shapes) == 1:
            result = getattr(shapes[0], func.__name__)(*args, **kwargs)
        else:
            others = shapes[1:]
            result = getattr(shapes[0], func.__name__)(*others, *args, **kwargs)
        # Project result back to original CRS
        return inverse(inst, result, trn=trn)
    return wrapper


def forward(inst, *args):
    """Transfroms shape or shapes to EPSG:6933"""
    try:
        others = []
        for other in list(args):
            others.append(NaiveGeoMetry(other))
    except ValueError:
        pass
    args = list(args)[len(others):]
    # Construct projection specific to the list of sites
    shape = inst if not others else inst.simple_combine(*others)
    try:
        to_crs = customize_wkt('EPSG:6933', shape.center)
        trn = get_transformer(inst.crs, to_crs, always_xy=True)[0]
    except CRSError:
        raise ValueError('Invalid projection: {}'.format(inst.crs))
    # Project all shapes to same coordinate system
    shapes = [NaiveGeoMetry(inst)] + others
    transformed = [s.transform(str(to_crs), trn) for s in shapes]
    return transformed, trn, args


def inverse(inst, result, trn=None):
    """Converts result to back to original class, if appropriate"""
    try:
        if isinstance(result[0], (BaseGeometry, NaiveGeoMetry)):
            return [inverse(inst, r, trn=trn) for r in result]
    except (IndexError, TypeError):
        pass
    if isinstance(result, BaseGeometry):
        result = NaiveGeoMetry(result)
    if isinstance(result, NaiveGeoMetry):
        if trn:
            result = result.transform(inst.crs, trn, direction='INVERSE')
        return inst.__class__(result)
    return result


def get_transformer(from_crs, to_crs, **kwargs):
    """Retrieves a stored transformer, creating it if needed"""
    from_crs = epsg_id(from_crs)
    to_crs = epsg_id(to_crs)
    key = json.dumps([from_crs, to_crs, kwargs])
    try:
        return NaiveGeoMetry.transformers[key]
    except KeyError:
        trn = Transformer.from_crs(from_crs, to_crs, **kwargs)
        NaiveGeoMetry.transformers[key] = trn, to_crs
        return trn, to_crs


def customize_wkt(name, center, base=15):
    """Retrieves a stored WKT, creating it if doesn't already exist"""
    meridian = base * round(center.longitudes[0] / base)
    key = json.dumps([name, meridian])
    try:
        return NaiveGeoMetry.wkts[key]
    except KeyError:
        crs = CRS.from_user_input(name).to_wkt()
        crs = crs.replace('tude of natural origin",0,',
                          'tude of natural origin",{},'.format(meridian))
        NaiveGeoMetry.wkts[key] = crs
        return crs
