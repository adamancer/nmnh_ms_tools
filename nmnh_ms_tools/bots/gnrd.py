"""Defines bot to interact with the GNRD taxonomic name resolver"""
import logging

from .core import Bot, JSONResponse

from unidecode import unidecode




logger = logging.getLogger(__name__)




class GNRDBot(Bot):
    """Defines methods to interact with GNRD resolvers"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('wrapper', GNRDResponse)
        super().__init__(*args, **kwargs)


    def find_names(self, text, **kwargs):
        """Finds taxonomic names in text"""
        url = 'http://gnrd.globalnames.org/name_finder.json'
        params = {'text': unidecode(text[:5000])}
        params.update(**kwargs)
        return self.get(url, params=params)


    def resolve_names(self, names, **kwargs):
        """Resolves taxonomic names"""
        url = 'http://resolver.globalnames.org/name_resolvers.json'
        params = {'names': unidecode('|'.join(names))}
        params.update(**kwargs)
        return self.get(url, params=params)




class GNRDResponse(JSONResponse):
    """Defines path containing results in a GNRD API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault('results_path', [])
        super().__init__(response, **kwargs)
