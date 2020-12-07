"""Defines functions to help reading SQLite databases"""
import datetime as dt
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import DeferredReflection




logger = logging.getLogger(__name__)




def init_helper(fp, base, session, deferred=False, tables=None):
    """Creates the database based on the given path"""
    if fp == ':memory':
        fp = ''
    if fp:
        fp = '/' + os.path.realpath(fp).replace(os.sep, os.sep * 2)
    engine = create_engine('sqlite://{}'.format(fp))
    if deferred:
        DeferredReflection.prepare(engine)
    base.metadata.bind = engine
    base.metadata.create_all(tables=tables)
    session.configure(bind=engine)



def time_query(query):
    compiled = query.statement.compile(compile_kwargs={'literal_binds': True})
    start_time = dt.datetime.now()
    query.all()
    msg = '{} (t={})'.format(compiled, dt.datetime.now() - start_time)
    logger.debug(msg)
    print(msg)
