"""Defines generic bot for making requests with retry"""

from functools import wraps
import logging
import pprint as pp
import random
import time
import warnings
from contextlib import contextmanager

import requests
import requests_cache
from lxml import etree

from ..config import CONFIG


logger = logging.getLogger(__name__)


class Bot:
    """Methods to handle and retry HTTP requests"""

    try:
        email = CONFIG["bots"]["email"]
    except KeyError:
        email = input("Email: ")

    def __init__(
        self,
        wait=3,
        email=None,
        wrapper=None,
        start_param=None,
        limit_param=None,
        paged=False,
        num_retries=7,
        **kwargs,
    ):
        self.wait = wait
        if email:
            self.email = email
        self._headers = {}
        self.wrapper = wrapper
        self.start_param = start_param
        self.limit_param = limit_param  # either a key or func(resp)
        self.paged = paged
        self.num_retries = num_retries
        self.kwargs = kwargs
        self.session = requests.Session()
        self._cached_session = None

    @property
    def headers(self):
        """Reads request heaers, populating User-Agent if necessary"""
        headers = self._headers.copy()
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.user_agent
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
            resp = func(inst, *args, **kwargs)
            inst.start_param = start_param
            return resp

        return wrapper

    @staticmethod
    def no_wrapper(func):
        """Defines a decorator to disable the response wrapper"""

        @wraps(func)
        def wrapper(inst, *args, **kwargs):
            wrapper = inst.wrapper
            inst.wrapper = None
            resp = func(inst, *args, **kwargs)
            inst.wrapper = wrapper
            return resp

        return wrapper

    @property
    def user_agent(self):
        return f"python-requests/{requests.__version__}/{self.email}"

    def get(self, *args, **kwargs):
        """Makes GET request with retry"""
        return self._retry("get", *args, **kwargs)

    def post(self, *args, **kwargs):
        """Makes POST request with retry"""
        return self._retry("post", *args, **kwargs)

    def head(self, *args, **kwargs):
        """Makes HEAD request with retry"""
        # HEAD requests are not resource intensive but don't seem to be cacheable,
        # so reduce wait to a fraction of a second if
        wait = self.wait
        if wait > 0.1:
            self.wait = 0.1
        resp = self._retry("head", *args, **kwargs)
        self.wait = wait
        return resp

    def validate(self, resp):
        """Placeholder function to validate resp"""
        return True

    def download(self, url, path, chunk_size=8192):
        """Downloads content at url to path"""
        with self.get(url, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)

    def handle_error(self, resp):
        msg = f"Could not resolve {resp.url} (status_code={resp.status_code})"
        if isinstance(self.session, requests_cache.CachedSession):
            msg = msg.rstrip(")") + f", from_cache={resp.from_cache})"
        warnings.warn(msg)

    def install_cache(self, cache_name="http_cache"):
        """Activates cache located at path"""
        if (
            not isinstance(self.session, requests_cache.CachedSession)
            or self.session.cache.cache_name != cache_name
        ):
            self.session = requests_cache.CachedSession(cache_name, **self.kwargs)

    def uninstall_cache(self):
        """Deactives cache"""
        self.session = requests.Session()

    @contextmanager
    def disable_cache(self):
        """Temporarily disables cache

        Has no effect if cache is not enabled
        """
        try:
            cache_name = self.get_cache().cache_name
        except AttributeError:
            cache_name = None
        else:
            self.uninstall_cache()

        try:
            yield self
        finally:
            if cache_name is not None:
                self.install_cache(cache_name)

    def get_cache(self):
        return self.session.cache

    def is_cached(self):
        return isinstance(self.session, requests_cache.CachedSession)

    def delete_cached_url(url):
        """Deletes the given URL from the cache"""
        try:
            requests_cache.get_cache().delete_url(url)
        except AttributeError:
            pass

    def _retry(self, method, *args, **kwargs):
        """Routes requests to use single or paged"""
        kwargs.setdefault("allow_redirects", True)
        if CONFIG["bots"]["cache_name"] and not self.is_cached():
            self.install_cache(CONFIG["bots"]["cache_name"])
        func = getattr(self.session, method)
        if self.start_param and self.wrapper:
            resp = self._retry_paged(func, *args, **kwargs)
        else:
            resp = self._retry_one(func, *args, **kwargs)
        if not resp:
            self.handle_error(resp)
        if self.wrapper:
            return self.wrapper(resp)
        return resp

    def _retry_one(self, func, *args, **kwargs):
        """Retries failed request using a simple exponential backoff"""
        # Update headers based on defaults
        kwargs.setdefault("headers", {})
        for key, val in self.headers.items():
            try:
                kwargs["headers"][key]
            except KeyError:
                kwargs["headers"][key] = val
        if not kwargs["headers"]["User-Agent"]:
            raise ValueError("User agent is required")
        # Make the request, repeating it if a resolvable error is encountered
        for i in range(self.num_retries):
            logger.debug(f"Making request: {args}, {kwargs}")
            try:
                resp = func(*args, **kwargs)
                # Retry if status code indicates a temporary problem
                if resp.status_code in (429, 503):
                    raise requests.exceptions.ConnectionError(
                        f"Request failed: {resp.url} (status_code={resp.status_code})"
                    )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                # Add a random number of milliseconds to the wait time to prevent
                # multiple retries from synchronizing
                wait = 2**i + random.randint(1, 1000) / 1000
                req = (
                    [func.__name__]
                    + list(args)
                    + [f"{k}={v}" for k, v in kwargs.items()]
                )
                logger.warning(f"Retrying in {wait:,} seconds (request={req})...")
                time.sleep(wait)
            else:
                # Ensure that the response has the from_cache attribute
                if not hasattr(resp, "from_cache"):
                    resp.from_cache = None
                # Enforce the minimum wait only if response is from an external server
                local = resp.url.startswith(("http://localhost", "http://127.0.0.1"))
                if not local and not resp.from_cache:
                    logger.info(f"Made new request: {resp.url}")
                    # Update wait based on rate limit
                    time.sleep(self.wait_from_rate_limit(resp))
                # Validate the response, returning the response object if OK
                if self.validate(resp):
                    return resp
        raise Exception("Maximum retries exceeded")

    def _retry_paged(self, *args, **kwargs):
        """Repeats request with retry across paginated content"""
        responses = []
        while True:
            resp = self._retry_one(*args, **kwargs)
            if resp:
                responses.append(resp)
            elif responses:
                return responses
            else:
                return resp

            # Update start and limit parameters
            key = "payload" if args[0].__name__ == "post" else "params"
            params = kwargs.get(key, {})

            # Check if available records exhausted
            wrapped = self.wrapper(resp)
            if len(responses) == 1:
                if callable(self.limit_param):
                    limit = self.limit_param(resp)
                else:
                    limit = params.get(self.limit_param, len(wrapped))

            total = wrapped.total()
            if total is not None and limit > total:
                limit = total
            if limit and len(responses) >= limit:
                return responses

            # Update start and make new request
            start = params.get(self.start_param, 0)
            start += 1 if self.paged else len(wrapped)
            kwargs[key][self.start_param] = start

    def wait_from_rate_limit(self, resp):
        """Updates wait based on rate limit headers in resp"""
        headers = resp.headers

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
            return self.wait

        # CrossRef style
        try:
            limit = int(resp.headers.get("x-rate-limit-limit"))
            interval = int(resp.headers.get("x-rate-limit-interval").rstrip("s"))
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        else:
            self.wait = interval / limit
            return self.wait

        logger.info(f"No rate limit found: {resp.headers}")
        return self.wait


class JSONResponse:
    """Wraps JSON response to add methods for retrieving records"""

    def __init__(self, resp, results_path, result_wrapper=None, total_path=None):
        self._response = None
        self._responses = None
        self._json = None
        self._results_path = results_path if results_path else []
        self._result_wrapper = result_wrapper if result_wrapper else []
        self._total_path = total_path if total_path else []
        self._wrap(resp)

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
            raise ValueError(
                f"Could not cast to JSON: {repr(text)} ({self._response.status_code}) ({url})"
            )

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
        """Returns all records from the results path as a list"""
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
            for resp in responses[1:]:
                if isinstance(obj, list):
                    obj.extend(
                        self.__class__(
                            resp,
                            results_path=self._results_path,
                            result_wrapper=self._result_wrapper,
                        ).all()
                    )
                elif isinstance(obj, dict):
                    new = resp.json()
                    for key in self._results_path:
                        new = new[key]
                    obj.update(new)
        logger.debug(
            f"Wrapped {len(self):,} records from {len(responses):,} responses with {self.__class__.__name__}"
        )


class XMLResponse:
    """Wraps XML response"""

    def __init__(self, resp):
        self._response = resp
        self._xml = etree.fromstring(resp.text)
        self.nsmap = self._find_namespaces()

    def __str__(self):
        return etree.tostring(self._xml, encoding="unicode", pretty_print=True)

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
