"""Defines bot to interact with GeoNames webservices"""
import logging
import sys

from .core import Bot, JSONResponse
from ..config import CONFIG
from ..databases.geonames import GeoNamesFeatures




logger = logging.getLogger(__name__)




CODES_ADMIN = [
    'ADM1',
    'ADM2',
    'ADM3',
    'ADM4',
    'ADM5',
    'ADM1H',
    'ADM2H',
    'ADM3H',
    'ADM4H',
    'ADM5H',
    'ADMD',
    'ZONE',
]
CODES_CANALS = [
    'CNL',
    'CNLA',
    'CNLB',
    'CNLD',
    'CNLI',
    'CNLN',
    'CNLQ',
    'CNLX',
    'DTCH',
    'DTCHD',
    'DTCHI',
    'DTCHM',
    'TNLC'
]
CODES_COUNTRIES = [
    'PCL',
    'PCLD',
    'PCLF',
    'PCLH',
    'PCLI',
    'PCLIX',
    'PCLS',
    'TERR',
]
CODES_DESERTS = [
    'DSRT',
    'DUNE',
    'ERG',
    'HMDA',
    'REG',
    'SAND'
]
CODES_ISLANDS = [
    'ATOL',
    'ISL',
    'ISLET',
    'ISLF',
    'ISLM',
    'ISLS',
    'ISLT',
    'RK',
    'RKS',
    'SMU',
    'SMSU',
    'TMSU',
    'TMTU'
]
CODES_LAKES = [
    'LBED',
    'LGN',
    'LGNS',
    'LGNX',
    'LK',
    'LKC',
    'LKI',
    'LKN',
    'LKNI',
    'LKO',
    'LKOI',
    'LKS',
    'LKSB',
    'LKSC',
    'LKSI',
    'LKSN',
    'LKSNI',
    'LKX',
    'MFGN',
    'OAS',
    'PND',
    'PNDI',
    'PNDN',
    'PNDNI',
    'PNDS',
    'PNDSF',
    'PNDSI',
    'PNDSN',
    'POOL',
    'POOLI',
    'RSV',
    'RSVI',
    'RSVT'
]
CODES_MARINE = [
    'CHN',
    'CHNL',
    'CHNM',
    'CHNN',
    'GULF',
    'OCN',
    'SEA',
    'STRT'
]
CODES_MOUNTAINS = [
    'MT',
    'NTK',
    'PK',
    'RDGE',
    'SPUR',
    'VLC'
]
CODES_MOUNTAIN_RANGES = [
    'MTS',
    'NTKS',
    'PKS',
    'UPLD',
    'VLC'
]
CODES_MUNICIPALITIES = [
    'PPL',
    'PPLA',
    'PPLA2',
    'PPLA3',
    'PPLA4',
    'PPLA5',
    'PPLC',
    'PPLCH',
    'PPLF',
    'PPLG',
    'PPLH',
    'PPLL',
    'PPLQ',
    'PPLR',
    'PPLS',
    'PPLW',
    'PPLX',
    'STLMT',
]
CODES_PARKS = [
    'PRK',
    'RES',
    'RESA',
    'RESF',
    'RESH',
    'RESN',
    'RESP',
    'RESV',
    'RESW',
    'RES',
    'RES'
]
CODES_REEFS = [
    'ATOL',
    'RF',
    'RFC',
    'RFX',
    'RFSU',
    'RFU'
]
CODES_RIVERS = [
    'CNFL',
    'CRKT',
    'RCH',
    'RPDS',
    'SBED',
    'STM',
    'STMA',
    'STMB',
    'STMC',
    'STMD',
    'STMH',
    'STMI',
    'STMIX',
    'STMM',
    'STMQ',
    'STMS',
    'STMSB',
    'STMX',
    'WTRC'
]
CODES_SHORES = [
    'BAY',
    'BAYS',
    'BGHT',
    'COVE',
    'FJD',
    'FJDS',
    'LGN',
    'LGNS',
    'GULF',
    'INLT',
    'INLTQ',
    'SD',
    'SHOR'
]
CODES_STATES_PROVINCES = [
    'ADM1',
    'ADM1H'
]
CODES_VALLEYS = [
    'GRGE',
    'RVN',
    'VAL',
    'VALG',
    'VALS',
    'VALX',
    'WAD',
    'WADB',
    'WADJ',
    'WADM',
    'WADS',
    'WADX'
]
CODES_VOLCANOES = [
    'CLDA',
    'CONE',
    'FSR',
    'VLC',
    'VLF',
    'VLS'
]
CODES_WETLANDS = [
    'CRKT',
    'MRSH',
    'MRSHN',
    'SWMP',
    'WTLD',
    'WTLDI'
]
CODES_UNDERSEA = [
    'APNU',
    'ARCU',
    'ARRU',
    'BDLU',
    'BKSU',
    'BNKU',
    'BSNU',
    'CDAU',
    'CNSU',
    'CNYU',
    'CRSU',
    'DEPU',
    'EDGU',
    'ESCU',
    'FANU',
    'FLTU',
    'FRZU',
    'FURU',
    'GAPU',
    'GLYU',
    'HLLU',
    'HLSU',
    'HOLU',
    'KNLU',
    'KNSU',
    'LDGU',
    'LEVU',
    'MESU',
    'MNDU',
    'MOTU',
    'MTU',
    'PKSU',
    'PKU',
    'PLNU',
    'PLTU',
    'PNLU',
    'PRVU',
    'RDGU',
    'RDSU',
    'RFSU',
    'RFU',
    'RISU',
    'SCNU',
    'SCSU',
    'SDLU',
    'SHFU',
    'SHLU',
    'SHSU',
    'SHVU',
    'SILU',
    'SLPU',
    'SMSU',
    'SMU',
    'SPRU',
    'TERU',
    'TMSU',
    'TMTU',
    'TNGU',
    'TRGU',
    'TRNU',
    'VALU',
    'VLSU'
]
FEATURE_TO_CODES = {
    'admin': CODES_ADMIN,
    'bay': CODES_SHORES,
    'canal': CODES_CANALS,
    'country': CODES_COUNTRIES,
    'crater': ['CRTR'],
    'island': CODES_ISLANDS,
    'island_group': CODES_ISLANDS,
    'lake': CODES_LAKES,
    'marine': CODES_MARINE,
    'mountain': CODES_MOUNTAINS,
    'mountain_range': CODES_MOUNTAIN_RANGES,
    'municipality': CODES_MUNICIPALITIES,
    'park': CODES_PARKS,
    'reef': CODES_REEFS,
    'river': CODES_RIVERS,
    'shore': CODES_SHORES,
    'state_province': CODES_STATES_PROVINCES,
    'valley': CODES_VALLEYS,
    'volcano': CODES_VOLCANOES,
    'wetland': CODES_WETLANDS
}




class GeoNamesBot(Bot):
    """Defines methods to interact with http://api.geonames.org"""
    geonames_db = GeoNamesFeatures()
    username = CONFIG.bots.geonames_username

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('wait', 3600 / 2000)
        kwargs.setdefault('wrapper', GeoNamesResponse)
        if not self.username:
            raise ValueError('GeoNamesBot.username is empty')
        super().__init__(*args, **kwargs)


    def validate(self, response):
        """Validates response from the GeoNames API"""
        url = response.url
        status = response.json().get('status', {}).get('value')
        # Request completed successfully
        if status is None:
            return True
        # Retry errors (delete result, retry)
        codes = [13, 22]
        if status in codes:
            self.delete_cached_url(url)
            mask = 'Retrying request: {} (code={}, http_code={})'
            msg = mask.format(url, status, response.status_code)
            logger.warning(msg)
            return False
        # Data errors (keep result, no retry)
        codes = [11, 12, 14, 15, 16, 17, 21, 23, 24, 25]
        if status in codes:
            mask = 'No results: {} (code={}, http_code={})'
            msg = mask.format(url, status, response.status_code)
            logger.warning(msg)
            return True
        # Fatal error (delete result, stop script)
        codes = [10, 18, 19, 20]
        if status in codes:
            self.delete_cached_url(url)
            mask = 'Fatal error: {} (code={}, http_code={})'
            msg = mask.format(url, status, response.status_code)
            logger.error(msg)
            sys.exit()
        return False


    def handle_error(self, response):
        """Handles failed requests

        At least a subset of failed responses now give a non-200 status code,
        so this method routes failed requests through validate.
        """
        self.validate(response)


    def get_json(self, geoname_id, style='full'):
        """Returns feature data for a given GeoNames ID

        Args:
            geoname_id (str): the ID of a feature in GeoNames

        Returns:
            JSON representation of the matching feature
        """
        try:
            int(geoname_id)
        except TypeError:
            raise TypeError('Invalid geoname_id: {}'.format(geoname_id))
        url = 'http://api.geonames.org/getJSON'
        return self._query_geonames(url, geonameId=geoname_id, style=style)


    def search_json(self, name=None, **params):
        """Searches all GeoNames fields for a query string

        Args:
            query (str): query string
            countries (mixed): a list or pipe-delimited string of countries
            features (list): a list of GeoNames feature classes and codes

        Returns:
            JSON representation of matching locations
        """
        url = 'http://api.geonames.org/searchJSON'
        valid = {
            'adminCode1',
            'adminCode2',
            'continentCode',
            'country',
            'countryName',
            'featureClass',
            'featureCode',
            'inclBbox',
            'isNameRequired',
            'maxRows',
            'name',
            'name_equals',
            'q',
            'state',
            'style'
        }
        invalid = sorted(set(params) - valid)
        if invalid:
            raise ValueError('Illegal params: {}'.format(invalid))
        if name is not None:
            params['name'] = name
        if len(set(params) & {'name', 'name_equals', 'q'}) != 1:
            raise ValueError('Illegal params: Exactly one of name,'
                             ' name_equals, or q required')
        return self._query_geonames(url, **params)


    def find_nearby_json(self, lat, lng, dec_places=None, **kwargs):
        """Returns geographical information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/findNearbyJSON'
        return self._find_latlong(url, lat, lng, dec_places, **kwargs)


    def country_subdivision_json(self, lat, lng, dec_places=None):
        """Returns basic geographical information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/countrySubdivisionJSON'
        return self._find_latlong(url, lat, lng, dec_places)


    def ocean_json(self, lat, lng, dec_places=None, radius=100):
        """Returns basic ocean information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/oceanJSON'
        if not dec_places:
            lat, lng = int(lat), int(lng)
        return self._find_latlong(url, lat, lng, dec_places, radius=radius)


    def get_state(self, name, country_code):
        """Gets the state matching the given name and country code"""
        results = self.search_json(name,
                                   country=country_code,
                                   featureCode=['ADM1'])
        return results.first()


    def get_country(self, name):
        """Gets the country matching the given name and country code"""
        features = ['PCL', 'PCLD', 'PCLH', 'PCLI', 'PCLIX', 'PCLS']
        results = self.search_json(name, featureCode=features)
        return results.first()


    def _query_geonames(self, url, **kwargs):
        """Generalized method for querying the GeoNames webservices

        Args:
            url (str): the url to query
            params (dict): query parameters

        Returns:
            Result set as JSON
        """
        if not self.username:
            raise AttributeError('username is required')
        params = {
            'style': 'full',
            'username': self.username,
        }
        params.update(kwargs)
        return self.get(url, params=params)


    def _find_latlong(self, url, lat, lng, dec_places=None, **kwargs):
        """Returns information for a lat-long pair from the given url

        Args:
            url (str): url of webservice. Must accept lat/lng as params.
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        if dec_places is not None:
            if not isinstance(lat, float):
                lat = float(lat)
            if not isinstance(lng, float):
                lng = float(lng)
            mask = '{0:.' + str(dec_places) + 'f}'
            lat = mask.format(lat)
            lng = mask.format(lng)
        params = {'lat': lat, 'lng': lng}
        params.update(kwargs)
        return self._query_geonames(url, **params)


    def _map_country(self, countries):
        """Maps country name to code"""
        if not isinstance(countries, list):
            countries = [s.strip() for s in countries.split('|')]
        try:
            return [self.geonames_db.get_country_code(c) for c in countries if c]
        except KeyError:
            raise ValueError('Unknown country: {}'.format(countries))




class GeoNamesResponse(JSONResponse):
    """Defines path containing results in a GeoNames API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault('results_path', ['geonames'])
        super().__init__(response, **kwargs)
