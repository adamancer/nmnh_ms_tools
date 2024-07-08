"""Defines tables in the GeoNames SQL file"""

import logging

from sqlalchemy import Column, String
from sqlalchemy.orm import declarative_base, sessionmaker

from ..helpers import init_helper


logger = logging.getLogger(__name__)
Base = declarative_base()
Session = sessionmaker()


class Cache(Base):
    """Defines a generic key-value cache"""

    __tablename__ = "cache"
    key = Column(String, primary_key=True)
    val = Column(String)


def init_db(fp, tables=None, **kwargs):
    """Creates the database based on the given path"""
    global Base
    global Session
    init_helper(fp, base=Base, session=Session, tables=tables, **kwargs)
