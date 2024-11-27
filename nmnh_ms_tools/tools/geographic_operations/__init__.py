"""Shapley-based tools to analyze and manipulate geographic shapes"""

from ... import _ImportClock

with _ImportClock("geometry"):
    from .geometry import GeoMetry, geoms_to_geodataframe, geoms_to_geoseries
    from .kml import Kml, write_kml
