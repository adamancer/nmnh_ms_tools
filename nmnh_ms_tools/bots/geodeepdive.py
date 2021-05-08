"""Defines bot to interact with the GeoDeepDive API"""
import logging

from .core import Bot, JSONResponse
#from ..records.people import Person
from ..utils import as_list




logger = logging.getLogger(__name__)




class GeoDeepDiveBot(Bot):
    """Defines methods to interact with https://geodeepdive.org/api"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('wrapper', GeoDeepDiveResponse)
        super().__init__(*args, **kwargs)
        self._docid_clusters = {}


    def get_snippets(self, term=None, **kwargs):
        """Gets snippets matching given criteria from the GeoDeepDive API"""
        url = 'https://geodeepdive.org/api/snippets'

        # Use the scrollID if given
        if kwargs.get("scroll_id"):
            return self._get_clustered(url, {"scroll_id": kwargs["scroll_id"]})

        if not term:
            raise ValueError("Must provide either term or scrollID")

        # If term is a non-string iterable, join into a string
        if not isinstance(term, str):
            term = ','.join(term)

        params = {
            'term': term,
            'clean': '',
            'fragment_limit': 1000,
        }
        params.update(kwargs)
        return self._get_clustered(url, params=params)


    def get_article(self, identifier):
        """Gets article matching given docid or doi from the GeoDeepDive API"""
        url = 'https://geodeepdive.org/api/articles'
        key = 'doi' if identifier.startswith('10.') else 'docid'
        params = {key: identifier}
        return self.get(url, params=params)


    def get_articles(self, **kwargs):
        """Gets articles matching given criteria from the GeoDeepDive API"""
        url = 'https://geodeepdive.org/api/articles'
        return self._get_clustered(url, params=kwargs)


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


    def _get_clustered(self, url, params):
        """Clusters queries that use the docid parameter"""
        params = params.copy()

        doc_ids = as_list(params.get('docid'))
        if doc_ids:
            qid = str({k: v for k, v in params.items() if k != 'docid'})
            self._docid_clusters.setdefault(url, {}).setdefault(qid, [])

            # Find document IDs that have already been clustered
            clustered = []
            for cluster in self._docid_clusters[url][qid]:
                clustered.extend(cluster)

            # If document IDs exactly match clustered, use existing clusters.
            # Otherwise start from scratch.
            if clustered == doc_ids[:len(clustered)]:
                doc_ids = [d for d in doc_ids if d not in set(clustered)]
            else:
                self._docid_clusters[url][qid] = []

            while doc_ids:
                self._docid_clusters[url][qid].append(doc_ids[:75])
                doc_ids = doc_ids[75:]

            # Make requests for each group of doc ids
            responses = []
            for doc_ids in self._docid_clusters[url][qid]:
                params['docid'] = ','.join(doc_ids)
                responses.append(self.get(url, params=params))

            # Combine responses
            response = responses[0]
            response.extend(responses[1:])
            return response

        return self.get(url, params=params)




class GeoDeepDiveResponse(JSONResponse):
    """Defines path containing results in a GeoDeepDive API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault('results_path', ['success', 'data'])
        super().__init__(response, **kwargs)
