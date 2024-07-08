"""Stores information about a set of georeferences"""

import logging

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import Index

from ...config import CONFIG
from ..helpers import init_helper


logger = logging.getLogger(__name__)
Base = declarative_base()
Session = sessionmaker()


class AlternativePolygons(Base):
    """Defines table containing alternative polygons"""

    __tablename__ = "alternative_polygons"
    id = Column(Integer, primary_key=True)
    name = Column(String(collation="nocase"))
    gn_id = Column(String(collation="nocase"))
    geometry = Column(LargeBinary)
    fcode = Column(String(collation="nocase"))
    source = Column(String(collation="nocase"))
    __table_args__ = (Index("ap_ids", "gn_id"), Index("ap_names", "name"))


class NaturalEarthCombined(Base):

    __tablename__ = "natural_earth_combined"
    id = Column(Integer, primary_key=True)
    table = Column(String(collation="nocase"))
    ogc_fid = Column(String(collation="nocase"))
    gn_id = Column(String(collation="nocase"))
    ne_id = Column(String(collation="nocase"))
    wikidataid = Column(String(collation="nocase"))
    name = Column(String(collation="nocase"))
    name_alt = Column(String(collation="nocase"))
    name_en = Column(String(collation="nocase"))
    fcode = Column(String(collation="nocase"))
    GEOMETRY = Column(LargeBinary)
    __table_args__ = (Index("nec_ids", "gn_id"), Index("nec_names", "name"))


class OceanTiles(Base):
    """Defines table of global ocean divided into tiles"""

    __tablename__ = "ocean_tiles"
    id = Column(Integer, primary_key=True)
    geometry = Column(LargeBinary)
    ocean = Column(String(collation="nocase"))
    coast = Column(Boolean)


class PreferredLocalities(Base):
    """Defines table specifying preferred localities"""

    __tablename__ = "preferred_localities"
    id = Column(Integer, primary_key=True)
    country = Column(String(collation="nocase"))
    state_province = Column(String(collation="nocase"))
    county = Column(String(collation="nocase"))
    site_name = Column(String(collation="nocase"))
    geonames_id = Column(Integer)
    __table_args__ = (
        UniqueConstraint(
            "country",
            "state_province",
            "county",
            "site_name",
            name="_unique_localities",
        ),
    )


def init_db(fp=None, tables=None, **kwargs):
    """Creates the database based on the given path"""
    global Base
    global Session
    if fp is None:  # pragma: no cover
        fp = CONFIG["data"]["geohelper"]
    init_helper(fp, base=Base, session=Session, tables=tables, **kwargs)
