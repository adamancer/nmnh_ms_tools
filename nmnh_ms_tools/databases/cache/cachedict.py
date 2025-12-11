"""Defines dict linked to a SQLite file"""

import logging
import os

from sqlalchemy.exc import IntegrityError

from .database import Session, Cache, init_db


logger = logging.getLogger(__name__)


class CacheDict:
    """Defines dict linked to a SQLite file"""

    def __init__(self, *args, **kwargs):
        self.session = None
        self.recent = {}
        self.max_recent = 5000
        for key, val in dict(*args, **kwargs).items():
            self[key] = val

    def __str__(self):
        return str(self.recent)

    def __setitem__(self, key, val):
        key = self.keyer(key)
        try:
            self.recent[key]
        except KeyError:
            # Add key-val to persistent cache if configured
            if self.session is not None:
                try:
                    self.session.add(Cache(key=key, val=self.writer(val)))
                    self.session.commit()
                except ValueError:
                    # Writer method threw an error, so don't save this pair
                    return
                except IntegrityError:
                    # Record already exists
                    self.session.rollback()
            # Limit recent to max length by deleting oldest key
            self.recent[key] = val
            while len(self.recent) > self.max_recent:
                self.recent.popitem(last=False)

    def __getitem__(self, key):
        key = self.keyer(key)
        try:
            return self.recent[key]
        except KeyError:
            if self.session is not None:
                query = self.session.query(Cache.val).filter_by(key=key)
                try:
                    val = self.reader(query.first())
                    self.recent[key] = val
                    return val
                except AttributeError:
                    pass
            raise KeyError(f"{repr(key)} not found")

    def __delitem__(self, key):
        raise NotImplementedError

    def init_db(self, path):
        """Initializes the cache database"""
        try:
            os.makedirs(os.path.dirname(path))
        except OSError:
            pass
        init_db(path)
        self.session = Session()

    def fill_recent(self):
        """Fills the recent dictionary with previously cached entries"""
        if self.session:
            query = self.session.query(Cache).limit(self.max_recent)
            self.recent = {r.key: self.reader(r) for r in query}

    @staticmethod
    def keyer(key):
        """Defines function to apply when key-val pair is cached"""
        return key

    @staticmethod
    def writer(val):
        """Defines function to apply when key-val pair is cached"""
        return val

    @staticmethod
    def reader(row):
        """Defines function to apply when key is retrieved"""
        return row.val
