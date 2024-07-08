"""Defines bot to interact with the ITIS API"""

import logging

from .core import Bot, XMLResponse


logger = logging.getLogger(__name__)


class ITISBot(Bot):
    """Defines methods to interact with ITIS webservices"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrapper", XMLResponse)
        super().__init__(*args, **kwargs)

    def get_taxon(self, name, **kwargs):
        url = "http://www.itis.gov/ITISWebService/services/ITISService/searchByScientificName"
        params = {"srchKey": name}
        params.update(**kwargs)
        return self.get(url, params=params)

    def get_hierarchy(self, tsn, **kwargs):
        url = "http://www.itis.gov/ITISWebService/services/ITISService/getFullHierarchyFromTSN"
        params = {"tsn": tsn}
        params.update(**kwargs)
        return self.get(url, params=params)


class ITISResponse(XMLResponse):
    """Defines path containing results in a ITIS API call"""

    def __init__(self, response, **kwargs):
        super().__init__(response, **kwargs)
