"""Defines constants and helper functions for common geographic operations"""

import logging
import math
import re

import numpy as np
from geographiclib.geodesic import Geodesic
from pyproj import Geod
from shapely.geometry import (
    GeometryCollection,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from .lists import as_list
from .standardizers import Standardizer


logger = logging.getLogger(__name__)


GEODESIC_GEOLIB = Geodesic.WGS84
GEODESIC_PYPROJ = Geod(ellps="WGS84")
SHAPE_TO_MULTISHAPE = {
    "LineString": MultiLineString,
    "Point": MultiPoint,
    "Polygon": MultiPolygon,
}
STD = Standardizer(minlen=1, delim="")


def bounding_box(lat1, lon1, lat2, lon2, close=False):
    """Calculates a bounding box from two sets of coordinates"""
    if lat1 == lat2 or lon1 == lon2:
        args = lat1, lon1, lat2, lon2
        raise ValueError("Not a box: {}".format(args))
    lat1, lat2 = sorted([lat1, lat2])
    lon1, lon2 = sorted([lon1, lon2])
    return box(lon1, lat1, lon2, lat2)


def epsg_id(val):
    """Maps name to EPSG identifier"""
    systems = {
        # Full names
        "Clarke 1858": "EPSG:4007",  # datum based on EPSG:7007 ellipsoid
        "Fundamental de Ocotepeque": "EPSG:5451",
        "Japanese Geodetic Datum 2000 ": "EPSG:6612",
        "Ocotepeque 1935": "EPSG:5451",
        # Common shorthand
        "NAD27": "EPSG:4267",
        "NAD83": "EPSG:4269",
        "PRP-M": "EPSG:4248",  # not sure about this one
        "WGS84": "EPSG:4326",
        # Strings designating no info
        "not recorded": "EPSG:4326",
        "unknown": "EPSG:4326",
    }
    # Return EPSG codes as uppercase
    if val.lower().startswith("epsg:"):
        return val.upper()
    # Return WKT definitions as is
    if val.startswith("PROJCRS"):
        return val
    # Extract parentheticals
    pattern = r"\((.*?)\)"
    if re.search(pattern, val):
        val = re.search(pattern, val).group(1)
    # Remove 19 from 19xx years
    val = re.sub(r"19(\d\d)", r"\1", val)
    epsg_id = {STD(k): v for k, v in systems.items()}.get(STD(val), val.upper())
    return epsg_id


def get_azimuth(bearing):
    """Converts a compass bearing to an azimuth

    Currently this function handles bearings like N, NE, NNE, or N40E.
    """
    if isinstance(bearing, (float, int)):
        return bearing
    # Set base values for each compass direction
    vals = {"N": 0 if "E" in bearing else 360, "S": 180, "E": 90, "W": 270}
    # Find the components of the bearing
    pattern = r"([NSEW])(\d*)([NSEW]?)([NSEW]?)"
    match = re.search(pattern, bearing)
    d1, deg, d2, d3 = [match.group(i) for i in range(1, 5)]
    v1, v2, v3 = [float(vals.get(d, 0)) for d in [d1, d2, d3]]
    # Swap the second and third coordinates if both are populated
    if d2 and d3:
        v2, v3 = v3, v2
        d2, d3 = d3, d2
    deg = float(deg) if deg.isnumeric() else 0
    # Determine the quadrant in which the azimuth falls
    quad = ("N" if "N" in bearing else "S") + ("E" if "E" in bearing else "W")
    # The sign of the major direction is postive when the azimuth is NE or SW
    s2 = 1 if quad in ["NE", "SW"] else -1
    # The sign of the minor direction is postive when the azimuth is NW or SE
    s3 = 1 if quad in ["NW", "SE"] else -1
    # Zero the second major direction if same as first (e.g., ENE) or if
    # a precise bearing is given (e.g., N40E)
    if (d1 == d2 and d3) or deg:
        d2 = 0
    # Calculate the azimuth
    azimuth = v1 + (45 if d2 else 0) * s2 + (22.5 if d3 else 0) * s3 + deg * s2
    if azimuth < 0 or azimuth == 360:
        return 360 - azimuth
    # mask = 'Calculated azimuth={} from bearing={}'
    # logger.debug(mask.format(azimuth, bearing))
    return azimuth


def draw_circle(lat, lon, dist_km):
    """Calculates a circle using the shapely buffer trick"""
    lon = pm_longitudes([lon])[0]
    translated = translate(lat, lon, 45, dist_km)
    slon, slat = translated.coords[0]
    dist = ((slon - lon) ** 2 + (slat - lat) ** 2) ** 0.5
    return Point(lon, lat).buffer(dist)


def draw_polygon(lat, lon, dist_km, sides=4):
    """Calculates a polygon of a given number of sides around a point"""
    azimuths = [45 + (i * 360 / sides) for i in range(sides)]
    lats = [lat] * len(azimuths)
    lons = [lon] * len(azimuths)
    dists_km = [dist_km] * len(azimuths)
    return translate(lats, lons, azimuths, dists_km)


def get_spoke_km(dist_km):
    """Calculates length of spoke in km

    This method originally split the difference between two possible
    interpretations of a radius (diagonal or along axis). The MaNIS guidelines
    use the diagonal, and that approach is adopted here.
    """
    s1 = (2 * dist_km**2) ** 0.5  # circle contains square (x along diagonal)
    # s2 = (dist_km ** 2 / 2) ** 0.5  # square contains circle (x along axes)
    # return (s1 + s2) / 2            # split the difference
    return s1


def fix_shape(shape, multipolygon="largest"):
    """Fixes invalid shape using shapely buffer trick, then convex hull"""
    shape = normalize_shape(shape)
    if not shape.is_valid:
        # Buffer then crop to ensure the shape is valid in lat-long space. Note that this
        # fix assumes the original shape is basically okay and only goes out-of-bounds
        # because of the buffer.
        shape = shape.buffer(0.1)
        cropped = shape.intersection(box(-180, -90, 180, 90))
        if shape != cropped and cropped.area / shape.area > 0.5:
            shape = cropped
        if not shape.is_valid:
            shape = shape.convex_hull
    # For MultiPolygons, simplify to either the largest multipolygon or the
    # hull encompassing the set of polygons. The former option is preferred
    # for most locality parsing operations, the latter is needed for
    # associating farflung provinces with the correct country.
    if isinstance(shape, MultiPolygon):
        geoms = sorted(shape.geoms, key=lambda g: g.area)
        # Keep largest polygon only if it is much bigger than the rest (so
        # keep the continental US but not like half of Malaysia) and quite
        # large itself, since this exists to catch places on the order of
        # countries or states.
        #
        # Thresholds are rough and based on the following:
        # + Area of Alaska / continental US = 4.7
        # + Area of Rhode Island: ~3,000 km²
        # + Area of the big island of Hawaii: ~11,000 km²
        if (
            multipolygon == "largest"
            and geoms[-1].area > 2
            and geoms[-1].area / geoms[-2].area > 3
        ):
            shape = geoms[-1]
        else:
            shape = shape.convex_hull
    elif isinstance(shape, (GeometryCollection, MultiLineString)):
        shape = shape.convex_hull
    return shape


def get_dist_km(lat1, lon1, lat2, lon2):
    """Calculates the distance in kilometers between two points"""
    try:
        return get_dist_km_pyproj(lat1, lon1, lat2, lon2)
    except ValueError:
        if lat1 == lat2 and lon1 == lon2:
            return 0
        raise ValueError(f"Could not calculate distance: {(lat1, lon1, lat2, lon2)}")


def get_dist_km_geolib(lat1, lon1, lat2, lon2):
    """Calculates distance in km between two points w/ geographiclib.Geodesic"""
    lon1, lon2 = pm_longitudes([lon1, lon2])
    result = GEODESIC_GEOLIB.Inverse(lat1, lon1, lat2, lon2)
    dist_km = result["s12"] / 1000
    if np.isnan(dist_km):
        mask = "Invalid distance: {:.2f}, {:.2f}, {:.2f}, {:.2f}"
        raise ValueError(mask.format(lat1, lon1, lat2, lon2))
    return dist_km


def get_dist_km_haversine(lat1, lon1, lat2, lon2):
    """Calculates distance in km between two points using Haversine formula

    From https://nathanrooy.github.io/posts/2016-09-07/haversine-with-python/
    """
    lon1, lon2 = pm_longitudes([lon1, lon2])
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    dist_km = 6371000 * c / 1000
    if np.isnan(dist_km):
        mask = "Invalid distance: {:.2f}, {:.2f}, {:.2f}, {:.2f}"
        raise ValueError(mask.format(lat1, lon1, lat2, lon2))
    return dist_km


def get_dist_km_pyproj(lat1, lon1, lat2, lon2):
    """Calculates distance in km between two points using pyproj.Geod"""
    lon1, lon2 = pm_longitudes([lon1, lon2])
    result = GEODESIC_PYPROJ.inv(lon1, lat1, lon2, lat2)
    dist_km = result[2] / 1000
    if np.isnan(dist_km):
        mask = "Invalid distance: {:.2f}, {:.2f}, {:.2f}, {:.2f}"
        raise ValueError(mask.format(lat1, lon1, lat2, lon2))
    return dist_km


def translate(lats, lons, bearings, dists_km):
    """Calculates point at a distance along a bearing"""
    return translate_pyproj(lats, lons, bearings, dists_km)


def translate_geolib(lats, lons, bearings, dists_km):
    """Calculates point at a distance along a bearing w/ geographiclib"""
    args = _prep_translate(lats, lons, bearings, dists_km)
    points = []
    for lat, lon, azimuth, dist_m in zip(*args):
        result = GEODESIC_GEOLIB.Direct(lat, lon, azimuth, dist_m)
        points.append((result["lon2"], result["lat2"]))
    if len(points) == 1:
        return Point(points[0])
    return Polygon([(x, y) for x, y in points])


def translate_pyproj(lats, lons, bearings, dists_km):
    """Calculates points at a distance along a bearing with pyproj.Geod"""
    lats, lons, azm, dists_km = _prep_translate(lats, lons, bearings, dists_km)
    # pyprog.Geod uses lon, lat order
    lons, lats, _ = GEODESIC_PYPROJ.fwd(lons, lats, azm, dists_km)
    if len(lats) == 1:
        return Point(lons[0], lats[0])
    return Polygon([(x, y) for x, y in zip(lons, lats)])


def translate_with_uncertainty(
    lat, lon, bearing, dist_km, abs_err_degrees=None, rel_err_distance=0.25
):
    """Calculates point with uncertainty for a distance along a bearing"""
    # Calculate uncertainty on azimuth
    azimuth = bearing
    if not isinstance(azimuth, float):
        azimuth = get_azimuth(bearing)
    if abs_err_degrees is None:
        abs_err_degrees = azimuth_uncertainty(azimuth, dist_km)
    azm1, azm2 = azimuth + abs_err_degrees, azimuth - abs_err_degrees
    # The shape is translated along the uncertainty-adjusted bearings, so
    # the distance along the original bearing is short. Scale that distance
    # based on the error angle to fix that.
    dist_km /= math.cos(abs_err_degrees * math.pi / 180)
    # Calculate uncertainty on distance. MaNIS-based estimates are currently
    # by the precision attribute in DirectionParser.
    rel_err_distance = dist_km * rel_err_distance
    min_dist = dist_km - rel_err_distance
    max_dist = dist_km + rel_err_distance
    # Calculate an envelope
    lats = [lat] * 4
    lons = [lon] * 4
    bearings = [azm1, azm1, azm2, azm2]
    dists_km = [min_dist, max_dist] * 2
    return translate(lats, lons, bearings, dists_km)


def azimuth_uncertainty(azimuth, min_uncertainty=5.75):
    """Calculates uncertainty associated with a given azimuth

    Based on MaNIS georeferencing guidelines.
    """
    if not azimuth % 90:
        return 45
    elif not azimuth % 45:
        return 22.5
    elif not azimuth % 22.5:
        return 11.25
    return min_uncertainty


def forward_azimuth(lat1, lon1, lat2, lon2):
    """Calculates the inverse geodesic using pyproj"""
    return GEODESIC_PYPROJ.inv(lon1, lat1, lon2, lat2)[0]


def similar(num, other, threshold=0.01):
    """Tests if two numbers are similar"""
    return abs(num - other) <= threshold


def slope(point, other):
    """Calculates the slope of a line"""
    return (point[1] - other[1]) / (point[0] - other[0])


def subhorizontal(point, other):
    """Tests if two points can be linked by a subhorizontal line"""
    try:
        return np.rad2deg(np.arctan(abs(slope(point, other)))) < 10
    except ZeroDivisionError:
        return False


def subvertical(point, other):
    """Tests if two points can be linked by a subvertical line"""
    try:
        return np.rad2deg(np.arctan(abs(slope(point, other)))) > 80
    except ZeroDivisionError:
        return True


def continuous(lst):
    """Tests if a list is continuous"""
    return all([val[i] == val[i - 1] + 1 for i, val in enumerate(lst) if i])


def trim(coords, i, trim_func, both_ends=True):
    """Trims segments from the edge of polygon using given function"""
    coords = coords[:]
    last = coords[0]
    for pt in coords[1:]:
        if not trim_func(pt, last):
            break
        coords.pop(0)
        last = pt
    if both_ends:
        coords = trim(coords[::-1], i, trim_func, False)[::-1]
    return coords


def sort_geoms(geoms, direction):
    """Sorts a list geometries by compass direction"""
    if direction in "NS":
        return sorted(geoms, key=lambda s: as_list(s.centroid.lat)[0])
    elif direction in "EW":
        return sorted(geoms, key=lambda s: as_list(s.centroid.lon)[0])
    raise ValueError("Bad direction: {}".format(direction))


def encircle(lat_s):
    """Calculates centroid and radius for a circle around a set of lat-lons"""
    lat_lons = normalize_coords(lat_lons)
    mpt = MultiPoint([(lon, lat) for lat, lon in lat_lons])
    centroid = mpt.centroid
    clat, clon = centroid.y, centroid.x
    hull = mpt.convex_hull.exterior.coords
    # Calculate distance between centroid and each point
    radius = max([get_dist_km(clat, clon, lat, lon) for lon, lat in hull])
    return draw_circle(clat, clon, radius)


def enhull(lat_lons):
    """Calculates hull around a set of lat-lons"""
    lat_lons = normalize_coords(lat_lons)
    return MultiPoint([(lon, lat) for lat, lon in lat_lons]).convex_hull


def get_coordinates(shape):
    """Extracts a list of coordinates from a shapely object"""
    if not shape:
        return []
    if shape.geom_type == "Point":
        return [(shape.y, shape.x)]
    try:
        return [(y, x) for x, y in shape.exterior.coords]
    except AttributeError:
        pass
    try:
        return [(y, x) for x, y in shape.coords]
    except NotImplementedError:
        pass
    raise ValueError("Could not parse '{}'".format(shape))


def normalize_shape(shape, to_antimeridian=None):
    """Calculates shape to ensure it is not split by the antimeridian"""
    orig = shape
    multishape = None
    if hasattr(shape, "geoms"):
        multishape = shape.__class__
        shape = list(shape.geoms)
    if isinstance(shape, list):
        if multishape:
            minlon, _, maxlon, _ = orig.bounds
            to_antimeridian = crosses_180([minlon, maxlon])
        else:
            # For lists, normalize to antimeridian if any shape crosses it
            lons = []
            if to_antimeridian is None:
                to_antimeridian = False
                for geom in shape:
                    minlon, _, maxlon, _ = geom.bounds
                    if crosses_180([minlon, maxlon]):
                        to_antimeridian = True
                        break
                    else:
                        lons.extend([minlon, maxlon])
            # Final check to catch shapes where no individual feature crosses
            # the antimeridian but the group itself does
            if not to_antimeridian:
                to_antimeridian = crosses_180(lons)
        shapes = [normalize_shape(g, to_antimeridian) for g in shape]
        return multishape(shapes) if multishape is not None else shapes
    # Map transformed coordinates back to original shape
    lat_lons = get_coordinates(shape)
    xy = [(x, y) for y, x in normalize_coords(lat_lons, to_antimeridian)]
    return shape.__class__(xy)


def normalize_coords(lat_lons, to_antimeridian=None):
    """Calculates longitudes to ensure they are not split by the antimeridian"""
    lats, lons = zip(*lat_lons)
    if to_antimeridian is None:
        to_antimeridian = crosses_180(lons)
    lons = am_longitudes(lons) if to_antimeridian else pm_longitudes(lons)
    return list(zip(lats, lons))


def crosses_180(lons):
    """Tests if longitudes cross the antimeridian"""
    min_lon = min(lons)
    max_lon = max(lons)
    return abs(max_lon) > 180 or abs(min_lon) > 180 or max_lon - min_lon > 180


def am_longitudes(lons):
    """Normalizes longitudes to between 0 and 360"""
    # return [(lon + 360 if lon < 0 else lon) for lon in lons]
    am_lons = []
    for lon in lons:
        orig = lon
        # Convert very negative longitudes to equivalent positive values
        if lon < -180:
            lon += 360
        # Normalize negative longitudes (-180 to 0)
        if lon < 0:
            lon += 360
        am_lons.append(lon)
    return am_lons


def pm_longitudes(lons):
    """Normalizes longitudes to between -180 and 180"""
    # return [(lon - 360 if lon > 180 else lon) for lon in lons]
    pm_lons = []
    for lon in lons:
        if lon > 180:
            lon -= 360
        elif lon < -180:
            lon += 360
        pm_lons.append(lon)
    return pm_lons


def _prep_translate(lats, lons, bearings, dists_km):
    """Prepares arguments for a batch of translations"""
    lats = as_list(lats)
    lons = pm_longitudes(as_list(lons))
    azimuths = [get_azimuth(b) for b in as_list(bearings)]
    azimuths *= len(lats) - len(azimuths) + 1
    dists_m = [dist_km * 1000 for dist_km in as_list(dists_km)]
    dists_m *= len(lats) - len(dists_m) + 1
    return lats, lons, azimuths, dists_m
