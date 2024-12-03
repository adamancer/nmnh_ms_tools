"""Defines constants and helper functions for common geographic operations"""

import logging
import math
import re

import numpy as np
from geographiclib.geodesic import Geodesic
from pyproj import Geod
from shapely.geometry import Point, Polygon

from .lists import as_list


logger = logging.getLogger(__name__)


GEODESIC_GEOLIB = Geodesic.WGS84
GEODESIC_PYPROJ = Geod(ellps="WGS84")


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


def get_dist_km(lat1, lon1, lat2, lon2):
    """Calculates the distance in kilometers between two points"""
    return get_dist_km_pyproj(lat1, lon1, lat2, lon2)


def get_dist_km_geolib(lat1, lon1, lat2, lon2):
    """Calculates distance in km between two points w/ geographiclib.Geodesic"""
    lon1, lon2 = pm_longitudes([lon1, lon2])
    result = GEODESIC_GEOLIB.Inverse(lat1, lon1, lat2, lon2)
    dist_km = result["s12"] / 1000
    if np.isnan(dist_km):
        raise ValueError(
            f"Invalid distance: {lat1:.2f}, {lon1:.2f}, {lat2:.2f}, {lon2:.2f}"
        )
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
        raise ValueError(
            f"Invalid distance: {lat1:.2f}, {lon1:.2f}, {lat2:.2f}, {lon2:.2f}"
        )
    return dist_km


def get_dist_km_pyproj(lat1, lon1, lat2, lon2):
    """Calculates distance in km between two points using pyproj.Geod"""
    lon1, lon2 = pm_longitudes([lon1, lon2])
    result = GEODESIC_PYPROJ.inv(lon1, lat1, lon2, lat2)
    dist_km = result[2] / 1000
    if np.isnan(dist_km):
        raise ValueError(
            f"Invalid distance: {lat1:.2f}, {lon1:.2f}, {lat2:.2f}, {lon2:.2f}"
        )
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
    lats, lons, azm, dists_m = _prep_translate(lats, lons, bearings, dists_km)
    # pyprog.Geod uses lon, lat order
    lons, lats, _ = GEODESIC_PYPROJ.fwd(lons, lats, azm, dists_m)
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
    raise ValueError(f"Bad direction: {direction}")


def crosses_180(lons):
    """Tests if longitudes cross the antimeridian"""
    min_lon = min(lons)
    max_lon = max(lons)
    return abs(max_lon) > 180 or abs(min_lon) > 180 or max_lon - min_lon > 180


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
