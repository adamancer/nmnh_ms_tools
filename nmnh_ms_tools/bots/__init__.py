"""Defines bots using a consistent interface to work with various APIs"""

from .. import _ImportClock

with _ImportClock("bots"):
    from .core import Bot, JSONResponse
    from .adamancer import AdamancerBot
    from .geodeepdive import GeoDeepDiveBot
    from .geogallery import GeoGalleryBot
    from .geonames import GeoNamesBot, FEATURE_TO_CODES
    from .gnrd import GNRDBot
    from .itis import ITISBot
    from .macrostrat import MacrostratBot
    from .metbullbot import MetBullBot
    from .plss import PLSSBot
