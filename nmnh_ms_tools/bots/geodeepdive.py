"""Defines bot to interact with the GeoDeepDive API"""
import logging

from .core import Bot, JSONResponse
#from ..records.people import Person




logger = logging.getLogger(__name__)




class GeoDeepDiveBot(Bot):
    """Defines methods to interact with https://geodeepdive.org/api"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('wrapper', GeoDeepDiveResponse)
        super().__init__(*args, **kwargs)


    def get_snippets(self, term, **kwargs):
        """Gets snippets matching given criteria from the GeoDeepDive API"""
        url = 'https://geodeepdive.org/api/snippets'
        params = {
            'term': term,
            'clean': '',
            'article_limit': 1000,
            'fragment_limit': 1000,

        }
        params.update(kwargs)
        return self.get(url, params=params)


    def get_article(self, identifier):
        """Gets article matching given docid or doi from the GeoDeepDive API"""
        url = 'https://geodeepdive.org/api/articles'
        key = 'doi' if identifier.startswith('10.') else 'docid'
        params = {key: identifier}
        return self.get(url, params=params)


    def get_articles(self, **kwargs):
        """Gets articles matching given criteria from the GeoDeepDive API"""
        url = 'https://geodeepdive.org/api/articles'
        return self.get(url, params=kwargs)


    def list_coauthors(self, name, **kwargs):
        """Gets a list of coauthors for a person"""
        from ..records.people import Person
        person = Person(name)
        kwargs.update({'lastname': person.last})
        coauthors = []
        for article in self.get_articles(**kwargs):
            authors = [Person(a['name']) for a in article.get('author', [])]
            if any([a.similar_to(person) for a in authors]):
                coauthors.extend(authors)
        return sorted(set([str(n) for n in coauthors]))




class GeoDeepDiveResponse(JSONResponse):
    """Defines path containing results in a GeoDeepDive API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault('results_path', ['success', 'data'])
        super().__init__(response, **kwargs)
