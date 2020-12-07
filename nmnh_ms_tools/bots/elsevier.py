"""Defines bot to interact with Elsevier web services"""
import logging
import re

from lxml import etree

from .core import Bot, JSONResponse
from ..config import CONFIG




logger = logging.getLogger(__name__)




class ElsevierBot(Bot):
    """Defines methods to interact with https://api.elsevier.com"""

    def __init__(self, *args, **kwargs):
        api_key = kwargs.pop('api_key', CONFIG.bots.elsevier_api_key)
        if not api_key:
            raise ValueError('Elsevier API key required')
        kwargs.setdefault('wrapper', ElsevierReponse)
        kwargs.setdefault('start_param', 'start')
        kwargs.setdefault('limit_param', 'count')
        super().__init__(*args, **kwargs)
        self._headers['X-ELS-APIKey'] = api_key


    def search(self, **kwargs):
        """Finds articles matching the given parameters"""
        url = 'https://api.elsevier.com/content/search/sciencedirect'
        if isinstance(kwargs.get('query'), dict):
            kwargs['query'] = self.build_query(**kwargs['query'])
        return self.get(url, params=kwargs)


    @Bot.no_wrapper
    @Bot.no_paging
    def article(self, doi, **kwargs):
        """Retrieves aritcles mathing the given DOI"""
        url = 'https://api.elsevier.com/content/article/doi/{}'.format(doi)
        params = {
            'httpAccept': 'text/xml'
        }
        params.update(kwargs)
        return self.get(url, params=params)


    @staticmethod
    def build_query(**kwargs):
        """Builds a simple query string for the Elsevier search API"""
        query = []
        for key, vals in kwargs.items():
            if not isinstance(vals, list):
                vals = [vals]
            vals = ['"{}"'.format(s) if ' ' in str(s) else str(s) for s in vals]
            val = ' OR '.join(vals)
            query.append('{}({})'.format(key.upper(), val))
        return ' AND '.join(query)




class ElsevierReponse(JSONResponse):
    """Defines path containing results in an Elsevier API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault('results_path', ['search-results', 'entry'])
        kwargs.setdefault(
            'total_path',
            ['search-results', 'opensearch:totalResults']
        )
        super().__init__(response, **kwargs)




def xml_to_text(root, output=None):
    """Converts article XML to text"""
    if isinstance(root, str):
        root = etree.fromstring(root)
    if output is None:
        output = []
    for child in root:
        _, local = child.tag.lstrip('{').split('}', 1)
        if local == 'title' and not output:
            text = '# {}.\n'.format(child.xpath('normalize-space()'))
            output.append(text)
        elif local == 'section-title':
            text = '## {}.\n'.format(child.xpath('normalize-space()'))
            output.append(text)
        elif local == 'label':
            text = child.xpath('normalize-space()')
            if len(text) > 1:
                text = '### {}.\n'.format(text)
            output.append(text)
        elif local in ['para', 'simple-para']:
            text = '{}\n'.format(child.xpath('normalize-space()'))
            if '•' in text:
                text = [s.strip() for s in text.split('•') if s.strip()]
                text = '\n'.join(['• {}.'.format(s) for s in text])
            output.append(text)
        output = xml_to_text(child, output)
    return output
