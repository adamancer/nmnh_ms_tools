"""Defines bot to interact with http://adamancer.pythonanywhere.com"""
import logging

from .core import Bot, JSONResponse




logger = logging.getLogger(__name__)




class AdamancerBot(Bot):
    """Defines methods to interact with http://adamancer.pythonanywhere.com"""
    domain = 'http://adamancer.pythonanywhere.com'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('wrapper', AdamancerResponse)
        super().__init__(*args, **kwargs)


    def chronostrat(self, earliest, **kwargs):
        """Gets info about a given named or numeric geologic age"""
        url = '{}/chronostrat'.format(self.domain.rstrip('/'))
        params = {
            'earliest': earliest
        }
        params.update(kwargs)
        return self.get(url, params=params)


    def metbull(self, name):
        """Gets info about a given named or numeric geologic age"""
        return self.get('{}/metbull/{}'.format(self.domain.rstrip('/'), name))




class AdamancerResponse(JSONResponse):
    """Defines path containing results in a Macrostrat API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault('results_path', ['data'])
        super().__init__(response, **kwargs)
