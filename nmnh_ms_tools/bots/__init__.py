"""Defines bots using a conssitent interface to work with various APIs"""
from .core import Bot, JSONResponse

from .adamancer import AdamancerBot
from .elsevier import ElsevierBot
from .gnrd import GNRDBot
from .geodeepdive import GeoDeepDiveBot
from .geogallery import GeoGalleryBot
from .geonames import GeoNamesBot, FEATURE_TO_CODES
from .gnrd import GNRDBot
from .itis import ITISBot
from .macrostrat import MacrostratBot
from .metbullbot import MetBullBot
from .plss import PLSSBot
