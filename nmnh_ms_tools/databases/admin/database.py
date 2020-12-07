"""Defines tables in the admin division SQL file"""
import logging
import os

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
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




class AdminNames(Base):
    __tablename__ = 'admin_names'
    id = Column(Integer, primary_key=True)
    geoname_id = Column(Integer)
    name = Column(String(collation='nocase'))
    fcode = Column(String(length=8, collation='nocase'))
    st_name = Column(String(collation='nocase'))
    country_code = Column(String(length=2, collation='nocase'))
    admin_code_1 = Column(String(collation='nocase'))
    admin_code_2 = Column(String(collation='nocase'))
    admin_code_3 = Column(String(collation='nocase'))
    admin_code_4 = Column(String(collation='nocase'))


class AdminThesaurus(Base):
    __tablename__ = 'admin_thesaurus'
    id = Column(Integer, primary_key=True)
    country = Column(String(collation='nocase'))
    state_province = Column(String(collation='nocase'))
    county = Column(String(collation='nocase'))
    mapping = Column(String(collation='nocase'))
    __table_args__ = (
        UniqueConstraint('country', 'state_province', 'county',
                         name='_unique_localities'),
    )




def init_db(fp=None, tables=None):
    """Creates the database based on the given path"""
    global Base
    global Session
    if fp is None:
        fp = CONFIG.data.admin
    init_helper(fp, base=Base, session=Session, tables=tables)
