"""Defines generic bot for making requests with retry"""
import logging
import pprint as pp
import time
from functools import wraps

import requests
import requests_cache
from lxml import etree

from ..config import CONFIG
from ..utils import to_attribute




logger = logging.getLogger(__name__)




class Bot:
    """Methods to handle and retry HTTP requests"""
    user_agent = CONFIG.bots.user_agent

    def __init__(self, wait=3, user_agent=None, wrapper=None,
                 start_param=None, limit_param=None, paged=False):
        self.wait = wait
        if user_agent:
            self.user_agent = user_agent
        self._headers = {}
        self.wrapper = wrapper
        self.start_param = start_param
        self.limit_param = limit_param  # either a key or func(response)
        self.paged = paged


    @property
    def headers(self):
        """Reads request heaers, populating User-Agent if necessary"""
        headers = self._headers.copy()
        if 'User-Agent' not in headers:
            headers['User-Agent'] = self.user_agent
        return headers


    @headers.setter
    def headers(self, headers):
        self._headers = headers


    @staticmethod
    def no_paging(func):
        """Defines a decorator to disable paging"""
        @wraps(func)
        def wrapper(inst, *args, **kwargs):
            start_param = inst.start_param
            inst.start_param = None
            response = func(inst, *args, **kwargs)
            inst.start_param = start_param
            return response
        return wrapper


    @staticmethod
    def no_wrapper(func):
        """Defines a decorator to disable the response wrapper"""
        @wraps(func)
        def wrapper(inst, *args, **kwargs):
            wrapper = inst.wrapper
            inst.wrapper = None
            response = func(inst, *args, **kwargs)
            inst.wrapper = wrapper
            return response
        return wrapper


    def get(self, *args, **kwargs):
        """Makes GET request with retry"""
        return self._retry(requests.get, *args, **kwargs)


    def post(self, *args, **kwargs):
        """Makes POST request with retry"""
        return self._retry(requests.post, *args, **kwargs)


    def validate(self, response):
        """Placeholder function to validate response"""
        return True


    def download(self, url, path, ext=None, chunk_size=8192):
        # FIXME: Get path if not provided
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)


    def handle_error(self, response):
        raise ValueError('Could not parse response: {}'.format(response.text))


    @staticmethod
    def install_cache(path='cache'):
        """Activates cache located at path"""
        try:
            requests_cache.get_cache()
        except AttributeError:
            requests_cache.install_cache(path)


    @staticmethod
    def uninstall_cache():
        """Deactives caches"""
        try:
            requests_cache.get_cache()
        except AttributeError:
            pass
        else:
            requests_cache.uninstall_cache()


    @staticmethod
    def delete_cached_url(url):
        """Deletes the given URL from the cache"""
        try:
            requests_cache.get_cache().delete_url(url)
        except AttributeError:
            pass


    def _retry(self, *args, **kwargs):
        """Routes requests to use single or paged"""
        if self.start_param and self.wrapper:
            response = self._retry_paged(*args, **kwargs)
        else:
            response = self._retry_one(*args, **kwargs)
        if not response:
            self.handle_error(response)
        if self.wrapper:
            return self.wrapper(response)
        return response


    def _retry_one(self, func, *args, **kwargs):
        """Retries failed request using a simple exponential backoff"""
        # Update headers based on defaults
        kwargs.setdefault('headers', {})
        for key, val in self.headers.items():
            try:
                kwargs['headers'][key]
            except KeyError:
                kwargs['headers'][key] = val
        if not kwargs['headers']['User-Agent']:
            raise ValueError('User agent is required')
        # Make the request, repeating the call as necessary
        for i in range(8):
            try:
                response = func(*args, **kwargs)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                wait = 30 * 2 ** i
                req = [func.__name__] + list(args) + [f'{k}={v}' for k, v in kwargs.items()]
                logger.warning(
                    'Retrying in {:,} seconds (request={})...'.format(wait, req)
                )
                time.sleep(wait)
            else:
                # Ensure that the response has the from_cache attribute
                if not hasattr(response, 'from_cache'):
                    response.from_cache = None
                # Enforce the minimum wait if response from server
                local = response.url.startswith(('http://localhost',
                                                 'http://127.0.0.1'))
                if not local and not response.from_cache:
                    logger.info('New request: {}'.format(response.url))
                    # Update wait based on rate limit
                    time.sleep(self.wait_from_rate_limit(response))
                # Validate the response, returning the response oject if OK
                if self.validate(response):
                    return response
        raise Exception('Maximum retries exceeded')


    def _retry_paged(self, *args, **kwargs):
        """Repeats request with retry across paginated content"""
        responses = []
        while True:
            response = self._retry_one(*args, **kwargs)
            if response:
                responses.append(response)
            elif responses:
                return responses
            else:
                return response
            # Update start and limit parameters
            key = 'payload' if args[0].__name__ == 'post' else 'params'
            params = kwargs.get(key, {})
            # Check if available records exhausted
            wrapped = self.wrapper(response)
            if len(responses) == 1:
                if callable(self.limit_param):
                    limit = self.limit_param(response)
                else:
                    limit = params.get(self.limit_param, len(wrapped))
            total = wrapped.total()
            if limit > total:
                limit = total
            if limit and len(responses) >= limit:
                return responses
            # Update start and make new request
            start = params.get(self.start_param, 0)
            start += 1 if self.paged else len(wrapped)
            kwargs[key][self.start_param] = start


    def wait_from_rate_limit(self, response):
        """Updates wait based on rate limit headers in response"""
        headers = response.headers

        # Twitter style
        try:
            remaining = int(headers["x-rate-limit-remaining"])
            reset = int(headers["x-rate-limit-reset"])
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        else:
            # Reset may be seconds or a timestamp
            if reset > 10000:
                reset -= int(time.time())
            if reset < 0:
                reset = 0
            self.wait = reset / remaining
            print(f'Twitter rate limit: {self.wait}')
            return self.wait

        # GitHub style
        try:
            remaining = int(headers["x-ratelimit-remaining"])
            reset = int(headers["x-ratelimit-reset"])
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        else:
            # Reset may be seconds or a timestamp
            if reset > 10000:
                reset -= int(time.time())
            if reset < 0:
                reset = 0
            self.wait = reset / remaining
            print(f'GitHub rate limit: {self.wait}')
            return self.wait

        # CrossRef style
        try:
            limit = int(response.headers.get('x-rate-limit-limit'))
            interval = int(
                response.headers.get('x-rate-limit-interval').rstrip('s')
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        else:
            self.wait = interval / limit
            print(f'CrossRef rate limit: {self.wait}')
            return self.wait

        logger.error(str(response.headers))
        return self.wait




class JSONResponse:
    """Wraps JSON response to add methods for retrieving records"""

    def __init__(self, response, results_path,
                 result_wrapper=None, total_path=None):
        self._response = None
        self._responses = None
        self._json = None
        self._results_path = results_path if results_path else []
        self._result_wrapper = result_wrapper if result_wrapper else []
        self._total_path = total_path if total_path else []
        self._wrap(response)


    def __str__(self):
        return pp.pformat(self._json)


    def __repr__(self):
        return str(self._json)


    def __getattr__(self, attr):
        return getattr(self._response, attr)


    def __getitem__(self, key):
        if isinstance(key, int):
            return self.all(default=[])[0]
        return self._json[key]


    def __iter__(self):
        return iter(self.all(default=[]))


    def __bool__(self):
        return self._response.status_code == 200


    def __len__(self):
        return len(self.all(default=[]))


    @property
    def json(self):
        """Returns the cached JSON representation of the response"""
        return self._json


    def cast_to_json(self):
        """Returns a JSON representation of the response"""
        try:
            return self._response.json()
        except Exception:
            url = self._response.url
            text = self._response.text
            mask = 'Could not cast to JSON: "{} ({})" ({})'
            raise ValueError(mask.format(text, self._response.status_code, url))


    def one(self, default=None):
        """Returns record if exactly one found along results path"""
        try:
            results = self.all(default)
            if len(results) == 1:
                return results[0]
            raise ValueError
        except (KeyError, ValueError):
            return default


    def first(self, default=None):
        """Returns first record found along results path"""
        try:
            return self.all(default)[0]
        except (IndexError, KeyError):
            return default


    def all(self, default=None):
        """Returns all records all results path as a list"""
        obj = self._json
        for key in self._results_path:
            try:
                obj = obj[key]
            except KeyError:
                return default
        for key in self._result_wrapper:
            obj = [row[key] for row in obj]
        return obj


    def get(self, key, default=None):
        """Returns key from JSON"""
        try:
            return self[key]
        except KeyError:
            return default


    def append(self, other):
        """Appends another response object"""
        self.extend([other])


    def extend(self, others):
        """Appends each response object in a list"""
        responses = self._responses
        for other in others:
            responses.extend(other._responses)
        self._wrap(responses)


    def total(self, default=None):
        """Returns the total number of records matching the query"""
        obj = self._json
        for key in self._total_path:
            try:
                obj = obj[key]
            except KeyError:
                return default
        return int(obj) if self._total_path else default


    def _wrap(self, responses):
        """Wraps response(s) in instance of class"""
        if not isinstance(responses, list):
            responses = [responses]
        self._response = responses[0]
        self._responses = responses
        self._json = self.cast_to_json()
        # Update results to include records from all responses if multiple
        if len(responses) > 1:
            obj = self._json
            for key in self._results_path:
                obj = obj[key]
            for response in responses[1:]:
                obj.extend(self.__class__(response,
                                          results_path=self._results_path,
                                          result_wrapper=self._result_wrapper) \
                                          .all())
        mask = 'Wrapped {} records from {} responses with {}'
        logger.debug(mask.format(len(self),
                                 len(responses),
                                 self.__class__.__name__))




class XMLResponse:
    """Wraps XML response"""

    def __init__(self, response):
        self._response = response
        self._xml = etree.fromstring(response.text)
        self.nsmap = self._find_namespaces()


    def __str__(self):
        return etree.tostring(self._xml, encoding='unicode', pretty_print=True)


    def __getattr__(self, attr):
        try:
            return getattr(self._response, attr)
        except AttributeError:
            return getattr(self._xml, attr)


    def __iter__(self):
        return iter(self._xml)


    def xpath(self, xpath):
        return self._xml.xpath(xpath, namespaces=self.nsmap)


    def _find_namespaces(self, root=None, nsmap=None):
        """Finds namespaces by iterating over the full tree"""
        if root is None:
            root = self._xml
            nsmap = {}
        for node in root:
            nsmap.update(node.nsmap.copy())
            self._find_namespaces(node, nsmap)
        return nsmap
