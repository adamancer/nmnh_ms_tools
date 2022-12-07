"""Stores information about a set of georeferences"""
import logging
import os

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ...config import CONFIG
from ..helpers import init_helper




logger = logging.getLogger(__name__)
Base = declarative_base()
Session = sessionmaker()




class Uncertainties(Base):
    """Summarizes distances from sites to reference coordinates"""
    __tablename__ = 'uncertainties'
    id = Column(Integer, primary_key=True)
    occurrence_id = Column(String)
    site_num = Column(String)
    site_name = Column(String(collation='nocase'))
    site_kind = Column(String(collation='nocase'))
    radius = Column(Numeric(1))
    dist_km = Column(Numeric(1))
    __table_args__ = (
        UniqueConstraint('occurrence_id', 'site_num', name='_unique_sites'),
    )


class Localities(Base):
    """Summarizes information about missed localities"""
    __tablename__ = 'localities'
    occurrence_id = Column(String)
    country = Column(String)
    state_province = Column(String)
    county = Column(String)
    field = Column(String)
    parser = Column(String)
    parsed = Column(String)
    verbatim = Column(String, primary_key=True)
    verbatim_full = Column(String, primary_key=True)
    missed = Column(Integer)
    has_poly = Column(Integer)




def init_db(fp=None, tables=None):
    """Creates the database based on the given path"""
    global Base
    global Session
    if fp is None:
        fp = CONFIG["data"]["georef_job"]
    init_helper(fp, base=Base, session=Session, tables=tables)
