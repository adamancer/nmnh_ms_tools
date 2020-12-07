"""Shapley-based tools to analyze and manipulate geographic shapes"""
from .geometry import GeoMetry, NaiveGeoMetry
from .helpers import (
    am_longitudes,
    azimuth_uncertainty,
    bounding_box,
    continuous,
    crosses_180,
    draw_circle,
    draw_polygon,
    encircle,
    enhull,
    epsg_id,
    fix_shape,
    get_azimuth,
    get_dist_km,
    normalize_shape,
    pm_longitudes,
    similar,
    slope,
    subhorizontal,
    subvertical,
    translate,
    translate_with_uncertainty,
    trim,
)
from .kml import Kml, write_kml
