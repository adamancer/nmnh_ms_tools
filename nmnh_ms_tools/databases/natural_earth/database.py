"""Defines tables in the Natural Earth SQL file"""

import logging

from sqlalchemy.ext.declarative import DeferredReflection
from sqlalchemy.orm import declarative_base, sessionmaker

from ...config import CONFIG
from ..helpers import init_helper


logger = logging.getLogger(__name__)
Base = declarative_base()
Session = sessionmaker()


class Counties(DeferredReflection, Base):
    __tablename__ = "ne_10m_admin_2_counties"


class Countries(DeferredReflection, Base):
    __tablename__ = "ne_10m_admin_0_countries"


class GeographicRegions(DeferredReflection, Base):
    __tablename__ = "ne_10m_geography_regions_polys"


class Lakes(DeferredReflection, Base):
    __tablename__ = "ne_10m_lakes"


class LakesAustralia(DeferredReflection, Base):
    __tablename__ = "ne_10m_lakes_australia"


class LakesEurope(DeferredReflection, Base):
    __tablename__ = "ne_10m_lakes_europe"


class LakesNorthAmerica(DeferredReflection, Base):
    __tablename__ = "ne_10m_lakes_north_america"


class ParksAndProtectedLands(DeferredReflection, Base):
    __tablename__ = "ne_10m_parks_and_protected_lands_area"


class PopulatedPlaces(DeferredReflection, Base):
    __tablename__ = "ne_10m_populated_places"


class Playas(DeferredReflection, Base):
    __tablename__ = "ne_10m_playas"


class Reefs(DeferredReflection, Base):
    __tablename__ = "ne_10m_reefs"


class RiversAustralia(DeferredReflection, Base):
    __tablename__ = "ne_10m_rivers_australia"


class RiversEurope(DeferredReflection, Base):
    __tablename__ = "ne_10m_rivers_europe"


class RiversNorthAmerica(DeferredReflection, Base):
    __tablename__ = "ne_10m_rivers_north_america"


class MarineRegions(DeferredReflection, Base):
    __tablename__ = "ne_10m_geography_marine_polys"


class MinorIslands(DeferredReflection, Base):
    __tablename__ = "ne_10m_minor_islands"


class Ocean(DeferredReflection, Base):
    __tablename__ = "ne_10m_ocean"


class StatesProvinces(DeferredReflection, Base):
    __tablename__ = "ne_10m_admin_1_states_provinces"


def init_db(fp=None, tables=None, **kwargs):
    """Creates the database based on the given path"""
    global Base
    global Session
    if fp is None:
        fp = CONFIG["data"]["natural_earth"]
    init_helper(fp, base=Base, session=Session, deferred=True, tables=tables, **kwargs)
