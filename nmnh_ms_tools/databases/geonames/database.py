"""Stores feature data and lookups for GeoNames"""

import logging

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from ...config import CONFIG
from ..helpers import init_helper


logger = logging.getLogger(__name__)
Base = declarative_base()
Session = sessionmaker()


class AllCountries(Base):
    """Defines table for data from GeoNames allCountries.zip file"""

    __tablename__ = "all_countries"
    geoname_id = Column(Integer, primary_key=True)
    name = Column(String(collation="nocase"))
    ascii_name = Column(String(collation="nocase"))
    toponym_name = Column(String(collation="nocase"))
    alternate_names = Column(String(collation="nocase"))
    lat = Column(String)
    lng = Column(String)
    bbox = Column(String)
    fcl = Column(String(length=1, collation="nocase"))
    fcode = Column(String(length=8, collation="nocase"))
    country_name = Column(String(collation="nocase"))
    admin_name_1 = Column(String(collation="nocase"))
    admin_name_2 = Column(String(collation="nocase"))
    ocean = Column(String(collation="nocase"))
    continent_code = Column(String(length=2, collation="nocase"))
    country_code = Column(String(length=2, collation="nocase"))
    admin_code_1 = Column(String(collation="nocase"))
    admin_code_2 = Column(String(collation="nocase"))


class AlternateNames(Base):
    """Defines table indexing alternate names"""

    __tablename__ = "alternate_names"
    id = Column(Integer, primary_key=True)
    st_name = Column(String(collation="nocase"))
    st_name_rev = Column(String(collation="nocase"))
    geoname_id = Column(ForeignKey("all_countries.geoname_id"))
    fcl = Column(String(length=1, collation="nocase"))
    fcode = Column(String(length=8, collation="nocase"))
    continent_code = Column(String(length=2, collation="nocase"))
    country_code = Column(String(length=2, collation="nocase"))
    admin_code_1 = Column(String(collation="nocase"))
    admin_code_2 = Column(String(collation="nocase"))
    ocean = Column(String(collation="nocase"))


def init_db(fp=None, tables=None, **kwargs):
    """Creates the database based on the given path"""
    global Base
    global Session
    if fp is None:
        fp = CONFIG["data"]["geonames"]
    init_helper(fp, base=Base, session=Session, tables=tables, **kwargs)
