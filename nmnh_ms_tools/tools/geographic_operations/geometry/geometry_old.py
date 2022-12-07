"""Defines class to handle projection of lat/long data"""
import json
import logging

from shapely.affinity import scale
from shapely.geometry import LineString, MultiLineString, MultiPolygon

from .naivegeometry import NaiveGeoMetry, equal_area, forward, inverse, same_meridian
from ....databases.cache import CacheDict
from ....utils.coords import parse_coordinate
from ....utils.geo import am_longitudes, crosses_180, epsg_id, pm_longitudes


logger = logging.getLogger(__name__)


class GeoMetry(NaiveGeoMetry):
    """Subclasses NaiveGeometry to handle common projection operations"""

    _c180 = {}

    def __init__(self, *args, **kwargs):
        super(GeoMetry, self).__init__(*args, **kwargs)
        self._crosses_180 = None
        self._am_shape = None
        self._pm_shape = None
        self._subshapes = None
        self.cache.extend(["_crosses_180", "_am_shape", "_pm_shape"])
        for attr in self.cache[-3:]:
            try:
                setattr(self, attr, getattr(self.verbatim, attr))
            except AttributeError:
                pass
        # self.finalize_shape()

    @property
    def subshapes(self):
        if self.verbatim and self._subshapes is None:
            self.shape
        return self._subshapes

    @subshapes.setter
    def subshapes(self, val):
        self._subshapes = val

    @property
    def centroid(self):
        """Calculates centroid of a geographic area"""
        # Bypass equal area transformation for small localities
        if self.radius_km is None or self.radius_km <= 100:
            if self.crosses_180():
                # NaiveGeoMetry will give a longitude ~0 for shapes crossing
                # the antimeridian if left to its own devices
                geom = NaiveGeoMetry([self.latitudes, self.pm_longitudes])
            else:
                geom = NaiveGeoMetry(self)
            return inverse(self, geom.centroid)
        shapes, trn, _ = forward(self)
        centroid = inverse(self, shapes[0].centroid, trn=trn)
        # If centroid doesn't fall inside the polygon, return the nearest
        # point inside the polygon instead.
        if not self.intersects(centroid, try_hull=False):
            centroid = self.nearest_points(centroid)[0]
        return centroid

    @property
    @equal_area
    def area(self):
        pass

    @same_meridian
    def contains(self, other):
        pass

    @same_meridian
    def crosses(self, other):
        pass

    @same_meridian
    def intersection(self, other):
        pass

    @same_meridian
    def intersects(self, other):
        pass

    @same_meridian
    def touches(self, other):
        pass

    @same_meridian
    def within(self, other):
        pass

    @same_meridian
    def nearest_points(self, other):
        pass

    @same_meridian
    def overlap(self, other):
        pass

    @same_meridian
    def split_and_group(self, line):
        pass

    def finalize_shape(self):
        # Coerce to WGS84
        if epsg_id(self.crs) != "EPSG:4326":
            transformed = self.transform("epsg:4326")
            self._crs = transformed.crs
            self.shape = transformed.shape

    def resize(self, multiplier, min_diff_km=0):
        """Resizes the site by multuplier or desired difference in km"""
        if self.radius_km is None or self.radius_km <= 100:
            shapes = [NaiveGeoMetry(self)]
            trn = None
        else:
            shapes, trn, _ = forward(self)
        # Check cache for key
        key = json.dumps([str(shapes[0]), multiplier, min_diff_km])
        try:
            return self.resized[key].clone()
        except KeyError:
            pass
        # Resize each axis using scale if multiplier < 1. This should never
        # fail, so no try-except used here.
        if multiplier < 1:
            shape = shapes[0].shape
            resized = self.derive(scale(shape, multiplier, multiplier))
            geom = inverse(self, resized, trn=trn)
            if self.validate_resize(geom, multiplier, min_diff_km):
                self.resized[key] = geom.clone()
                return geom
        # Calculate whether resize is likely to force shape beyond poles
        if min_diff_km:
            km_multiplier = (self.radius_km + min_diff_km) / self.radius_km
            multiplier = max([multiplier, km_multiplier])
        _, min_lat, _, max_lat = self.bounds
        diff_deg = (multiplier - 1) * (max_lat - min_lat)
        if (max_lat + diff_deg) < 85 and (min_lat - diff_deg) > -85:
            try:
                resized = shapes[0].resize(multiplier, min_diff_km)
                geom = inverse(self, resized, trn=trn)
                # shapes[0].draw(resized, title='resized both axes')
                if self.validate_resize(geom, multiplier, min_diff_km):
                    self.resized[key] = geom.clone()
                    return geom
            except Exception as e:
                pass
        # Scale longitude only if shape plots beyond the poles
        try:
            geom = inverse(self, self.derive(scale(shape, multiplier)), trn=trn)
            # shapes[0].draw(resized, title='resized longitude only')
            if self.validate_resize(geom, multiplier, min_diff_km):
                self.resized[key] = geom.clone()
                return geom
        except Exception as e:
            pass
        # Log warning and return original geometry
        mask = "Resize failed (multiplier={}, min_diff_km={})"
        logger.debug(mask.format(multiplier, min_diff_km))
        self.resized[key] = self.clone()
        return self.clone()

    def validate_resize(self, other, multiplier, min_diff_km=None):
        """Tests if resize looks reasonable by comparing the areas"""
        if min_diff_km:
            width = self.width_km + min_diff_km
            height = self.height_km + min_diff_km
            km_multiplier = (width * height) / (self.width_km * self.height_km)
            multiplier = max([multiplier, km_multiplier])
        min_diff = 0.5 * multiplier**2
        max_diff = 2.0 * multiplier**2
        return min_diff < other.area / self.area < max_diff

    @property
    def bounds(self):
        """Calculates bounds ensuring PM-normalized longitudes"""
        lats = self.latitudes
        lngs = self.pm_longitudes
        return min(lngs), min(lats), max(lngs), max(lats)

    @property
    def center(self):
        """Simplistically calculates the center of the bounding box

        Used to calculate a reasonable meridian when reprojecting.
        """
        # Latitude calculation is straightforward
        lat = (min(self.latitudes) + max(self.latitudes)) / 2
        # Longitude pairs may cross the antimeridian, so start by normalizing
        # the coordinates so they don't break across the relavant meridian.
        if self.crosses_180():
            minlng = min(self.am_longitudes)
            maxlng = max(self.am_longitudes)
        else:
            minlng = min(self.pm_longitudes)
            maxlng = max(self.pm_longitudes)
        # Next calculate the distance between the min and max long in degrees.
        # If the difference exceeds 180 degrees, go the other way instead.
        diff = (maxlng - minlng) / 2
        if diff > 90:
            diff = 180 - diff
        # Add the difference to the min longitude to get the midpoint. If
        # the coordinates cross the antimeridian, may also need to knock the
        # longitude down to a valid number by subtracting 360.
        lng = minlng + diff
        if lng > 180:
            lng -= 360
        return self.derive((lat, lng))

    def normalize(self, *others):
        """Normalizes shapes to either the prime meridian or antimeridian"""
        geoms = [self]
        if others:
            geoms.extend([self.attune(o) for o in others])
        for geom in geoms:
            if geom.crosses_180():
                return [g.am_shape for g in geoms]
        return [g.pm_shape for g in geoms]

    @property
    def am_shape(self):
        """Returns shape with longitudes normalized to between 0 and 360"""
        if self._am_shape is None:
            xy = list(zip(self.am_longitudes, self.latitudes))
            self._am_shape = self.shape.__class__(xy)
        return self._am_shape

    @property
    def pm_shape(self):
        """Returns shape with longitudes normalized to between -180 and 180"""
        if self._pm_shape is None:
            xy = list(zip(self.pm_longitudes, self.latitudes))
            self._pm_shape = self.shape.__class__(xy)
        return self._pm_shape

    @property
    def am_longitudes(self):
        """Normalizes longitudes to between 0 and 360"""
        return am_longitudes(self.longitudes)

    @property
    def pm_longitudes(self):
        """Normalizes longitudes to between -180 to 180"""
        return pm_longitudes(self.longitudes)

    def parse_coordinate(self, val, *args, **kwargs):
        """Converts a coordinate to a decimal"""
        return parse_coordinate(val, *args, **kwargs)[0].decimal

    def crosses_180(self):
        """Tests if longitudes cross the antimeridian"""
        if self._crosses_180 is None:
            self._crosses_180 = crosses_180(self.longitudes)
        if self._crosses_180 and not self._subshapes:
            self.split_at_180()
        return self._crosses_180

    def split_at_180(self):
        """Splits features that cross the 180th meridian"""
        if not self._crosses_180 or self._subshapes:
            return
        # Construct a shape from the normalized coordinates
        coords = zip(self.am_longitudes, self.latitudes)
        shape = self.shape.__class__(coords)
        # Split the polygon at meridian 180
        line = LineString([(180, -90), (180, 90)])
        geom = NaiveGeoMetry(shape)
        try:
            geoms = geom.split_and_group(line)
        except ValueError:
            geoms = [geom]
        # Correct longitudes in leftmost shape
        for i, geom in enumerate(geoms):
            try:
                x, y = list(geom.exterior.xy)
            except AttributeError:
                x, y = list(geom.xy)
            x = [c - 360 if c > 180 else c for c in x]
            if any([c < 0 for c in x]):
                x = [c if c < 0 else -c for c in x]
            geoms[i] = self.shape.__class__(zip(x, y))
        if len(geoms) > 1:
            if self.geom_type == "LineString":
                self.subshapes = MultiLineString(geoms)
            else:
                self.subshapes = MultiPolygon(geoms)
        else:
            # If entire shape is over 180, replace the original with corrected shape
            self._crosses_180 = False
            self.shape = geoms[0]
