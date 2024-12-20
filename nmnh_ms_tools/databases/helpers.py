"""Defines functions to help reading SQLite databases"""

import datetime as dt
import logging
import os

import pandas as pd
import shapely
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import DeferredReflection
from sqlalchemy.pool import NullPool


logger = logging.getLogger(__name__)
_sessions = []


def init_helper(fp, base, session, deferred=False, tables=None, poolclass=None):
    """Creates the database based on the given path"""
    global _sessions
    try:
        if fp == ":memory":
            engine = create_engine("sqlite://", poolclass=NullPool)
        else:
            cwd = os.getcwd()
            dn, fn = os.path.split(os.path.realpath(fp))
            os.chdir(dn)
            engine = create_engine(
                f"sqlite:///{fn}",
                poolclass=poolclass,
            )
            os.chdir(cwd)
        if deferred:
            DeferredReflection.prepare(engine)
        base.metadata.create_all(bind=engine, tables=tables)
        session.configure(bind=engine)
        _sessions.append(session)
    except Exception as e:
        raise RuntimeError(f"Could not load {fp}") from e


def time_query(query):
    compiled = query.statement.compile(compile_kwargs={"literal_binds": True})
    start_time = dt.datetime.now()
    query.all()
    msg = f"{compiled} (t={(dt.datetime.now() - start_time).total_seconds()})"
    print(msg)
    logger.debug(msg)


def from_csv(sessionmaker, table, path, **kwargs):
    rows = [r.to_dict() for _, r in pd.read_csv(path, **kwargs).iterrows()]
    for row in rows:
        try:
            row["geometry"] = shapely.from_wkt(row["geometry"]).wkb
        except KeyError:
            pass

    session = sessionmaker()
    session.bulk_insert_mappings(table, rows)
    session.commit()
    session.close()
