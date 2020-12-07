"""Stores information about a set of georeferences"""
import logging
import os

from sqlalchemy import (
    Column,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import Index

from ...config import CONFIG
from ..helpers import init_helper




logger = logging.getLogger(__name__)
Base = declarative_base()
Session = sessionmaker()




class AlternativePolygons(Base):
    """Defines table containing alternative polygons"""
    __tablename__ = 'alternative_polygons'
    id = Column(Integer, primary_key=True)
    name = Column(String(collation='nocase'))
    geoname_id = Column(String(collation='nocase'))
    geometry = Column(LargeBinary)
    fcode = Column(String(collation='nocase'))
    source = Column(String(collation='nocase'))
    source_id = Column(String(collation='nocase'))
    source_class = Column(String(collation='nocase'))
    ogc_fid = Column(String(collation='nocase'))
    wikidata_id = Column(String(collation='nocase'))
    __table_args__ = (
        Index('poly_ids', 'geoname_id'),
        Index('poly_names', 'name')
    )


class OceanTiles(Base):
    """Defines table of global ocean divided into tiles"""
    __tablename__ = 'ocean_tiles'
    id = Column(Integer, primary_key=True)
    geometry = Column(LargeBinary)
    ocean = Column(String(collation='nocase'))


class PreferredLocalities(Base):
    """Defines table specifying preferred localities"""
    __tablename__ = 'preferred_localities'
    id = Column(Integer, primary_key=True)
    country = Column(String(collation='nocase'))
    state_province = Column(String(collation='nocase'))
    county = Column(String(collation='nocase'))
    site_name = Column(String(collation='nocase'))
    geonames_id = Column(Integer)
    __table_args__ = (
        UniqueConstraint('country', 'state_province', 'county', 'site_name',
                         name='_unique_localities'),
    )




def init_db(fp=None, tables=None):
    """Creates the database based on the given path"""
    global Base
    global Session
    if fp is None:  # pragma: no cover
        fp = CONFIG.data.georef_data
    init_helper(fp, base=Base, session=Session, tables=tables)
