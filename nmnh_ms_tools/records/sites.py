"""Defines tools for parsing and manipulating locality data"""
import json
import logging
import os
import re

from sqlalchemy.exc import UnboundExecutionError

from .core import Record
from ..bots.geonames import CODES_MARINE, GeoNamesBot
from ..databases.admin import AdminFeatures
from ..databases.cache import CacheDict
from ..databases.geonames import GeoNamesFeatures
from ..databases.georef_data import get_alt_geometry
from ..config import CONFIG
from ..tools.geographic_names.caches import LocalityCache
from ..tools.geographic_names.parsers import (
    clean_locality,
    get_leftover,
    parse_localities
)
from ..tools.geographic_operations import GeoMetry
from ..tools.geographic_operations.kml import write_kml
from ..utils import (
    StaticDict,
    as_list,
    as_str,
    clear_empty,
    clock,
    dedupe,
    dictify,
    get_first,
    get_ocean_name,
    to_attribute
)
from ..utils.standardizers import LocStandardizer





logger = logging.getLogger(__name__)




EMU_LAT_KEYS = [
    'LatLatitude_nesttab',
    'LatLongitude_nesttab',
    'LatLatitudeDecimal_nesttab',
    'LatLongitudeDecimal_nesttab',
    'LatLatitudeVerbatim_nesttab',
    'LatLongitudeVerbatim_nesttab',
    'LatModifier_nesttab',
    'LatComment_nesttab',
    'LatDetSource_tab',
    'LatLatLongDetermination_tab',
    'LatDeterminedByRef_tab',
    'LatDetDate0',
    'LatRadiusVerbatim_tab',
    'LatRadiusNumeric_tab',
    'LatGeometry_tab',
    'LatRadiusProbability_tab',
    'LatRadiusUnit_tab',
    'LatDatum_tab',
    'LatCentroidLatitude0',
    'LatCentroidLatitudeDec_tab',
    'LatCentroidLongitude0',
    'LatCentroidLongitudeDec_tab',
    'LatDeriveCentroid_tab',
    'LatCentroidLongitudeDec_tab',
    'LatGeoreferencingNotes0',
    'LatPreferred_tab'
]
SEAS = {
    'Amundsen Gulf': 'Arctic Ocean',
    'Barents Sea': 'Arctic Ocean',
    'Beaufort Sea': 'Arctic Ocean',
    'Chukchi Sea': 'Arctic Ocean',
    'East Siberian Sea': 'Arctic Ocean',
    #'Greenland Sea': 'Arctic Ocean',
    'Gulf of Boothia': 'Arctic Ocean',
    'Kara Sea': 'Arctic Ocean',
    'Laptev Sea': 'Arctic Ocean',
    'Lincoln Sea': 'Arctic Ocean',
    'Prince Gustav Adolf Sea': 'Arctic Ocean',
    'Pechora Sea': 'Arctic Ocean',
    'Queen Victoria Sea': 'Arctic Ocean',
    'Wandel Sea': 'Arctic Ocean',
    'White Sea': 'Arctic Ocean',
    'Adriatic Sea': 'Atlantic Ocean',
    'Aegean Sea': 'Atlantic Ocean',
    'Alboran Sea': 'Atlantic Ocean',
    'Archipelago Sea': 'Atlantic Ocean',
    'Argentine Sea': 'Atlantic Ocean',
    'Baffin Bay': 'Atlantic Ocean',
    'Balearic Sea': 'Atlantic Ocean',
    'Baltic Sea': 'Atlantic Ocean',
    'Bay of Biscay': 'Atlantic Ocean',
    'Bay of Bothnia': 'Atlantic Ocean',
    'Bay of Campeche': 'Atlantic Ocean',
    'Bay of Fundy': 'Atlantic Ocean',
    'Black Sea': 'Atlantic Ocean',
    'Bothnian Sea': 'Atlantic Ocean',
    'Caribbean Sea': 'Atlantic Ocean',
    'Celtic Sea': 'Atlantic Ocean',
    'English Channel': 'Atlantic Ocean',
    'Foxe Basin': 'Atlantic Ocean',
    'Greenland Sea': 'Atlantic Ocean',
    'Gulf of Bothnia': 'Atlantic Ocean',
    'Gulf of Finland': 'Atlantic Ocean',
    'Gulf of Lion': 'Atlantic Ocean',
    'Gulf of Guinea': 'Atlantic Ocean',
    'Gulf of Maine': 'Atlantic Ocean',
    'Gulf of Mexico': 'Atlantic Ocean',
    'Gulf of Saint Lawrence': 'Atlantic Ocean',
    'Gulf of Sidra': 'Atlantic Ocean',
    'Gulf of Venezuela': 'Atlantic Ocean',
    'Hudson Bay': 'Atlantic Ocean',
    'Ionian Sea': 'Atlantic Ocean',
    'Irish Sea': 'Atlantic Ocean',
    'Irminger Sea': 'Atlantic Ocean',
    'James Bay': 'Atlantic Ocean',
    'Labrador Sea': 'Atlantic Ocean',
    'Levantine Sea': 'Atlantic Ocean',
    'Libyan Sea': 'Atlantic Ocean',
    'Ligurian Sea': 'Atlantic Ocean',
    'Marmara Sea': 'Atlantic Ocean',
    'Mediterranean Sea': 'Atlantic Ocean',
    'Myrtoan Sea': 'Atlantic Ocean',
    'North Sea': 'Atlantic Ocean',
    'Norwegian Sea': 'Atlantic Ocean',
    'Sargasso Sea': 'Atlantic Ocean',
    'Sea of Åland': 'Atlantic Ocean',
    'Sea of Azov': 'Atlantic Ocean',
    'Sea of Crete': 'Atlantic Ocean',
    'Sea of the Hebrides': 'Atlantic Ocean',
    'Thracian Sea': 'Atlantic Ocean',
    'Tyrrhenian Sea': 'Atlantic Ocean',
    'Wadden Sea': 'Atlantic Ocean',
    'Andaman Sea': 'Indian Ocean',
    'Arabian Sea': 'Indian Ocean',
    'Bali Sea': 'Indian Ocean',
    'Bay of Bengal': 'Indian Ocean',
    'Burma Sea': 'Indian Ocean',
    'Flores Sea': 'Indian Ocean',
    'Great Australian Bight': 'Indian Ocean',
    'Gulf of Aden': 'Indian Ocean',
    'Gulf of Aqaba': 'Indian Ocean',
    'Gulf of Khambhat': 'Indian Ocean',
    'Gulf of Kutch': 'Indian Ocean',
    'Gulf of Oman': 'Indian Ocean',
    'Gulf of Suez': 'Indian Ocean',
    'Laccadive Sea': 'Indian Ocean',
    'Mozambique Channel': 'Indian Ocean',
    'Persian Gulf': 'Indian Ocean',
    'Red Sea': 'Indian Ocean',
    'Timor Sea': 'Indian Ocean',
    'Arafura Sea': 'Pacific Ocean',
    'Banda Sea': 'Pacific Ocean',
    'Bering Sea': 'Pacific Ocean',
    'Bismarck Sea': 'Pacific Ocean',
    'Bohai Sea': 'Pacific Ocean',
    'Bohol Sea': 'Pacific Ocean',
    'Camotes Sea': 'Pacific Ocean',
    'Celebes Sea': 'Pacific Ocean',
    'Chilean Sea': 'Pacific Ocean',
    'Coral Sea': 'Pacific Ocean',
    'East China Sea': 'Pacific Ocean',
    'Gulf of Alaska': 'Pacific Ocean',
    'Gulf of Anadyr': 'Pacific Ocean',
    'Gulf of California': 'Pacific Ocean',
    'Gulf of Carpentaria': 'Pacific Ocean',
    'Gulf of Fonseca': 'Pacific Ocean',
    'Gulf of Panama': 'Pacific Ocean',
    'Gulf of Thailand': 'Pacific Ocean',
    'Gulf of Tonkin': 'Pacific Ocean',
    'Halmahera Sea': 'Pacific Ocean',
    'Java Sea': 'Pacific Ocean',
    'Koro Sea': 'Pacific Ocean',
    'Mar de Gra': 'Pacific Ocean',
    'Molucca Sea': 'Pacific Ocean',
    'Moro Gulf': 'Pacific Ocean',
    'Philippine Sea': 'Pacific Ocean',
    'Salish Sea': 'Pacific Ocean',
    'Savu Sea': 'Pacific Ocean',
    'Sea of Japan': 'Pacific Ocean',
    'Sea of Okhotsk': 'Pacific Ocean',
    'Seram Sea': 'Pacific Ocean',
    'Seto Inland Sea': 'Pacific Ocean',
    'Shantar Sea': 'Pacific Ocean',
    'Sibuyan Sea': 'Pacific Ocean',
    'Solomon Sea': 'Pacific Ocean',
    'South China Sea': 'Pacific Ocean',
    'Sulu Sea': 'Pacific Ocean',
    'Tasman Sea': 'Pacific Ocean',
    'Visayan Sea': 'Pacific Ocean',
    'Yellow Sea': 'Pacific Ocean',
    'Amundsen Sea': 'Southern Ocean',
    'Bellingshausen Sea': 'Southern Ocean',
    'Cooperation Sea': 'Southern Ocean',
    'Cosmonauts Sea': 'Southern Ocean',
    'Davis Sea': 'Southern Ocean',
    'D\'Urville Sea': 'Southern Ocean',
    'King Haakon VII Sea': 'Southern Ocean',
    'Lazarev Sea': 'Southern Ocean',
    'Mawson Sea': 'Southern Ocean',
    'Riiser-Larsen Sea': 'Southern Ocean',
    'Ross Sea': 'Southern Ocean',
    'Scotia Sea': 'Southern Ocean',
    'Somov Sea': 'Southern Ocean',
    'Weddell Sea': 'Southern Ocean',
    # Sea names found in the GeoNames ocean webservice
    'Andaman Or Burma Sea': 'Indian Ocean',
    'Canarias Sea': 'Atlantic Ocean',
    'China Sea': 'Pacific Ocean',
    'Coastal Waters Of Southeast Alaska And British Columbia': 'Pacific Ocean',
    'Gulf Cal': 'Pacific Ocean',
    'Gulf of Carpenteria': 'Pacific Ocean',
    'Gulf of Davao': 'Pacific Ocean',
    'Hudson Strait': 'Atlantic Ocean',
    'Joseph Bonaparte Gulf': 'Indian Ocean',
    'Malacca Strait': 'Indian Ocean | Pacific Ocean',
    'Rio De La Plata': 'Atlantic Ocean',
    'Samar Sea': 'Pacific Ocean',
    'Singapore Strait': 'Indian Ocean | Pacific Ocean',
    'South Seas': 'Pacific Ocean',
    'Strait Of Sicilia': 'Atlantic Ocean',
    'Tirreno Sea': 'Atlantic Ocean'
}
for sea in list(SEAS):
    SEAS[sea.lower()] = SEAS[sea]





class Site(Record):
    """Defines methods for parsing and manipulating locality data"""
    config = CONFIG
    adm = AdminFeatures()
    admin_cache = CacheDict()
    bot = GeoNamesBot() if CONFIG.bots.geonames_username else None
    cache = {}
    local = GeoNamesFeatures()
    std = LocStandardizer()
    pipe = None


    @clock
    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ['site_kind']
        # Explicitly define defaults for all reported attributes
        self.location_id = ''
        self.continent = ''
        self.country = ''
        self.state_province = []
        self.county = []
        self.municipality = ''
        self.island = ''
        self.island_group = ''
        self.water_body = []
        self.features = []
        self.maps = []
        self.mine = ''
        self.mining_district = ''
        self.volcano = ''
        self.ocean = ''
        self.sea_gulf = ''
        self.bay_sound = ''
        self.locality = ''
        self.verbatim_locality = ''
        self.geodetic_datum = ''
        self.decimal_latitude = ''
        self.decimal_longitude = ''
        self.verbatim_latitude = ''
        self.verbatim_longitude = ''
        self.footprint_wkt = ''
        self.georeference_protocol = ''
        self.georeference_sources = ''
        self.georeference_remarks = ''
        # GeoNames fields
        self.site_class = ''
        self.site_source = ''
        self.site_num = ''
        self.site_names = []
        self.synonyms = []
        # Define additional attributes
        self.admin_polygons = {}
        self.continent_code = ''
        self.country_code = ''
        self.admin_div_1 = []
        self.admin_code_1 = []
        self.admin_div_2 = []
        self.admin_code_2 = []
        self.related_sites = []
        self.other_ids = {}
        self.interpreted = {}
        # Define additional attributes required for parse
        self._geometry = None
        self._site_kind = ''
        self._features = {}
        self.from_gazetteer = False
        # Generate instance
        super(Site, self).__init__(*args, **kwargs)
        # Match attributes
        self.field = None
        self.filter = {}


    def __getattr__(self, attr):
        """Looks for unrecognized attributes in geometry (fallback)"""
        # Checking attributes needed to populate geometry causes a recursion
        # error, so ignore them
        if attr not in {
            '_geometry',
            'geometry',
            'decimal_latitude',
            'decimal_longitude',
            'verbatim_latitude',
            'verbatim_longitude'
        }:
            try:
                return getattr(self.geometry, attr)
            except AttributeError:
                pass
        mask = "'{}' object has no attribute '{}'"
        raise AttributeError(mask.format(self.__class__.__name__, attr))


    def __getstate__(self):
        state = self.__dict__.copy()
        state['_geometry'] = None
        return state


    def __setattr__(self, attr, val):
        """Ensures that admin codes are updated when names change"""
        if attr == 'radius_km':
            self.geometry.radius_km = val
        elif attr in {'country', 'state_province', 'county'}:
            if hasattr(self, attr) and val != getattr(self, attr):
                self.admin_polygons = {}
            super(Site, self).__setattr__(attr, val)
        else:
            super(Site, self).__setattr__(attr, val)


    @property
    def name(self):
        try:
            return self.site_names[0]
        except IndexError:
            return 'Unnamed site'


    @property
    def geometry(self):
        """Returns the geometry for this site, instantiating it if needed"""
        if self._geometry is None and self.has_coords():
            kwargs = {}
            if self.geodetic_datum:
                kwargs['crs'] = self.geodetic_datum

            if self.footprint_wkt:
                self.geometry = GeoMetry(self.footprint_wkt, **kwargs)
                return self._geometry

            for lat, lng in (
                (self.decimal_latitude, self.decimal_longitude),
                (self.verbatim_latitude, self.verbatim_longitude)
            ):
                if lat and lng:
                    self.geometry = GeoMetry((lat, lng), **kwargs)
                    return self._geometry

            mask = 'Invalid coordinates: {} ({})'
            raise ValueError(mask.format(missed, kwargs))

        return self._geometry


    @geometry.setter
    def geometry(self, geom):
        self._geometry = geom
        # Call radius to test that it exists and is valid
        self.radius_km


    @property
    def radius_km(self):
        """Returns the uncertainty radius for this site"""
        if self.geometry.radius_km is None or self.geometry.radius_km < 1:
            try:
                self.radius_km = CONFIG.get_feature_radius(self.site_kind)
            except (KeyError, TypeError):
                return 1  # force the minimum radius for a site to 1 km
        return self.geometry.radius_km


    @radius_km.setter
    def radius_km(self, val):
        self.geometry.radius_km = val


    @property
    def site_kind(self):
        """Returns the site kind, normally the GeoNames feature code"""
        return self._site_kind


    @site_kind.setter
    def site_kind(self, val):
        self._site_kind = val
        try:
            self.site_class = CONFIG.get_feature_class(val)
        except KeyError:
            pass


    def has_coords(self):
        """Tests if shape has coordinates"""
        return (self.decimal_latitude and self.decimal_longitude
                or self.verbatim_latitude and self.verbatim_longitude
                or self.footprint_wkt)


    def summarize(self, mask=None):
        """Summarizes the content of a record"""
        if mask is None:
            loc_id = self.location_id if self.location_id else 'not provided'
            return '{} ({})'.format(self.name, loc_id)
        if mask == 'admin':
            attrs = ['county', 'state_province', 'country']
            admin = [as_str(getattr(self, a)) for a in attrs]
            return ', '.join([a for a in admin if a])
        return mask.format(**self.to_dict())


    def parse(self, data):
        """Parses site data"""
        if hasattr(data, 'ne_id') or hasattr(data, 'ogc_fid'):
            self._parse_natural_earth(data)
        elif isinstance(data, int):
            self._parse_geoname_id(data)
        elif (
            'irn' in data or any([re.match(r'(Loc|Col)[A-Z]', k) for k in data])
        ):
            self._parse_emu(data)
        elif isinstance(data, list) and 'geonameId' in data[0]:
            self._parse_geonames(data[0])
        elif 'geonameId' in data:
            self._parse_geonames(data)
        elif 'recordNumber' in data or 'record_number' in data:
            self._parse_dwc(data)
        else:
            self._parse(data)

        # Map marine features to proper fields
        self.map_marine_features()

        # Set URL mask based on the identifier
        if not self.url_mask and re.match(r'^Q\d+$', self.location_id):
            self.url_mask = 'https://www.wikidata.org/wiki/{location_id}'

        # Gazetteers should not have the data problems common to collections
        if not self.from_gazetteer:
            self.cleanup()


    def parse_locality(self, val):
        """Parses a locality string"""
        # If attribute given, convert to value
        try:
            val = getattr(self, val)
        except AttributeError:
            pass
        # Skip parse if no value
        if not val:
            return [], None
        # Handle lists, etc.
        if isinstance(val, (list, tuple)):
            features = []
            for part in val:
                features.extend(self.parse_locality(part)[0])
            return features, get_leftover(val, features)
        # Check if value has already been parsed
        for cache in (self._features, self.cache):
            try:
                return cache[val]
            except KeyError:
                pass
        # Parse features and check for leftover information
        split_phrases = re.search(r'(,|;|:|/|\|| - )', clean_locality(val))
        features = parse_localities(val, split_phrases=split_phrases)
        leftover = get_leftover(val, features)
        # Store result
        self._features[val] = features, leftover
        self.cache[val] = features, leftover
        return features, leftover


    def cleanup(self):
        """Cleans up common errors in the site"""
        # Split admin divs joined by a spaced-out hyphen
        delim = r'(?: [/\-] )'
        for attr in ('state_province', 'county'):
            vals = getattr(self, attr)
            if len(vals) == 1 and re.search(delim, vals[0]):
                setattr(self, attr, re.split(delim, vals[0]))
        # Remove unspecifieds so that admin check will pass
        blacklist = [
            r'([a-z]+ )?unknown',
            r'([a-z]+ )?not stated',
            r'([a-z]+ )?(not |un)determined'
            r'locality in multiple [a-z]+'
        ]
        for attr in ('continent', 'country', 'state_province', 'county'):
            vals = as_list(getattr(self, attr))
            for pat in blacklist:
                pat = r'^\[?{}\]?$'.format(pat)
                vals = [s for s in vals if not re.search(pat, s, flags=re.I)]
            setattr(self, attr, vals)
        # Make major ocean names explicit
        pattern = r'\b(atlantic|pacific|indian|(?:ant)?arctic)(?! ocean)'
        for attr in ('water_body', 'ocean'):
            val = getattr(self, attr)
            if isinstance(val, str):
                val = [val]
            vals = []
            for val in val:
                vals.append(re.sub(pattern, r'\1 Ocean', val, flags=re.I))
            setattr(self, attr, vals)


    def validate(self):
        """Verifies that record has required metadata"""
        if self.country and self.country not in ['Unknown']:
            adm = [self.county, self.state_province, self.country]
            try:
                self.map_admin_from_names()
            except (AssertionError, ValueError):
                logger.error('Could not map admin: {}'.format(adm))
                return False
            if not self.country_code:
                logger.error('Invalid country: {}'.format(adm[-1]))
                return False
            if self.state_province and not self.admin_code_1:
                #if 'Colorado' in self.state_province:
                #    self.map_admin_from_names()
                logger.error('Invalid state/province: {}, {}'.format(*adm[-2:]))
                return False
            if self.county and not self.admin_code_2:
                logger.error('Invalid county: {}, {}, {}'.format(*adm))
                return False
        return True


    def map_admin_from_names(self):
        """Gets the GeoNames admin codes for the major admin divisions"""
        func_name = 'map_admin_from_names'
        self.map_continent()
        if clear_empty(self.country) and self.changed(func_name):
            args = []
            for attr in ['country', 'state_province', 'county']:
                args.append(clear_empty(getattr(self, attr)))
            try:
                result = self.adm.get(*args)
            except ValueError:
                mask = 'Could not map admin names: {}'
                raise ValueError(mask.format(json.dumps(args)))
            else:
                if result:
                    for field in self.adm.fields:
                        result.setdefault(field, None)
                    append_to = [a for a in result if a not in self.adm.fields]
                    self.update(result, append_to=append_to)
                    # Clear codes that do not correspond to a name
                    if not self.state_province and self.admin_code_1:
                        self.admin_code_1 = []
                    if not self.county and self.admin_code_2:
                        self.admin_code_2 = []
                    self.changed(func_name)
                    return result


    def map_admin_from_codes(self):
        """Gets the preferred GeoNames names for the major admin divisions"""
        if self.country_code:
            args = (self.country_code, self.admin_code_1, self.admin_code_2)
            try:
                result = self.adm.get(*args)
            except ValueError:
                mask = 'Could not map admin codes: {}'
                raise ValueError(mask.format(json.dumps(args)))
            else:
                if result:
                    for field in self.adm.fields:
                        result.setdefault(field, None)
                    append_to = [a for a in result if a not in self.adm.fields]
                    self.update(result, append_to=append_to)
                    return result


    def map_continent(self):
        """Maps continent names and codes based on GeoNames"""
        self.continent_code = ''
        if self.continent:
            if len(self.continent) == 2:
                self.continent_code = self.continent.upper()
                self.continent = self.adm.get_continent_name(self.continent_code)
            else:
                self.continent_code = self.adm.get_continent_code(self.continent)
        return self


    def compare_names(self, other, std_func=None):
        """Tests and tracks name comparison"""
        return self.compare_attr(None, other, 'names', std_func=std_func)


    def compare_attr(self, val, other, attr, std_func=None):
        """Tests and tracks filters"""
        #print('{}: {} => {}'.format(attr, val, other))
        if attr == 'names':
            score = 1 if self.has_name(other, std_func=std_func) else -1
        elif bool(val) != bool(other) or not val and not other:
            # One or both are blank
            score = 0
        elif val == other:
            score = 1
        elif isinstance(val, str) and isinstance(other, list) and val in other:
            score = 1
        elif isinstance(other, str) and isinstance(val, list) and other in val:
            score = 1
        elif isinstance(val, list) and isinstance(other, list):
            score = 1 if set(val).intersection(set(other)) else -1
        else:
            score = -1
        self.filter[attr] = score
        return score


    def has_name(self, other, std_func=None):
        """Checks if a name or names occurs in the site record"""
        def nrm(val, std_func):
            try:
                return ''.join(sorted(set(std_func(val).split('-'))))
            except ValueError:
                return
        if isinstance(other, self.__class__):
            other = other.site_names + other.synonyms
        elif not isinstance(other, list):
            other = [other]
        names = self.site_names + self.synonyms
        # Standardize names for comparison
        if std_func is None:
            std_func = self.std
        names = {n for n in [nrm(s, std_func) for s in names] if n}
        other = {n for n in [nrm(s, std_func) for s in other] if n}
        return bool(names.intersection(other))


    def subsection(self, direction, name=None):
        """Calcualtes the subsection specified by the direction"""
        subsection = self.geometry.subsection(direction)
        # Return original instance if geometry unchanged
        if subsection == self.geometry:
            return self
        # Add original outline to related sites
        site = self.clone()
        site.geometry = self.geometry
        self.related_sites.append(site)
        self.geometry = subsection
        # Note the subsectioning and update identifiers
        self.location_id += '_' + direction.upper()
        if name is None:
            name = '{} {}'.format(direction, self.name)
        self.site_names = [name]
        self.filter['name'] = name
        return self


    def clone(self, attributes=None):
        """Clones the current site"""
        if attributes:
            attributes = attributes[:]
            # Include admin codes if admin fields
            attrmap = {
                'country': 'country_code',
                'state_province': 'admin_code_1',
                'county': 'admin_code_2',
            }
            for attr in attributes:
                try:
                    attributes.append(attrmap[attr])
                except KeyError:
                    pass
            attributes = set(attributes)
        clone = super(Site, self).clone(attributes=attributes)
        if attributes is None or set(attributes) == set(self.attributes):
            try:
                clone.geometry = self.geometry.clone()
            except AttributeError:
                pass
            clone.filter = self.filter.copy()
            clone.url_mask = self.url_mask
        return clone


    def has_valid_coordinates(self, resize=1.1):
        """Checks coordinates against admin divisions

        Out-of-range latitudes and longitudes are handled by GeoMetry
        """
        if self.is_marine():
            # Verify the ocean name and expand the admin polygons by 50%
            try:
                ocean = get_ocean_name(self.ocean)
                other = get_ocean_name(self.get_ocean())
                if ocean and other:
                    assert ocean == other
            except (AssertionError, AttributeError):
                logger.debug(f'Ocean mismatch: "{ocean}" != "{other}"')
                return False
            resize = 1.5
        # Otherwise verify that the polygons intersect
        polygons = self.get_admin_polygons()
        for key in ['county', 'state_province', 'country']:
            try:
                if not self.intersects(polygons[key].resize(resize)):
                    mask = 'Coordinates fall outside {}: {} '
                    logger.debug(mask.format(key, self.location_id))
                    return False
                return True
            except KeyError:
                pass
        return True


    def restrict(self, other=None):
        """Restricts radius to roughly match intersection with another site

        For example, a mountain range might be restricted to its intersection
        with a county. If no site is provided, restrict to the lowest admin
        polygon instead of the original site instead.
        """
        if other is None:
            # Exclude admin, water and undersea features from the admin check
            try:
                fcl = CONFIG.get_feature_class(self.site_kind)
                if fcl not in {'A', 'H', 'U'}:
                    polygons = self.get_admin_polygons()
                    for key in ('county', 'state_province', 'country'):
                        try:
                            return self.restrict(polygons[key])
                        except KeyError:
                            pass
            except KeyError:
                # Unrecognized classes, including non-GeoNames pipes, end here
                pass
            return self

        contained = self.centroid.within(other)
        if (
            not contained
            or (self.geom_type != 'Point' and other.geom_type != 'Point')
        ):
            try:
                self.geometry = self.intersection(other)
            except ValueError:
                pass

        elif contained:
            # Leave the centroid alone and set the radius to the maximum
            # distance to the other geometry
            max_dist_km = self.max_dist_km(other)
            if max_dist_km < self.radius_km:
                self.radius_km = max_dist_km

        return self


    def get_admin_polygons(self, results=None):
        """Gets polygons for admin divisions"""
        if not self.country:
            return {}
        key = json.dumps([getattr(self, a) for a in self.adm.code_fields])
        try:
            polygons = {k: v.clone() for k, v in self.admin_cache[key].items()}
            if not polygons:
                raise ValueError('Could not map polygons: {}'.format(key))
            return polygons
        except KeyError:
            pass
        self.map_admin_from_names()
        fields = [f for f in self.adm.name_fields if getattr(self, f)]
        admin = self.clone([f for f in fields if getattr(self, f)])
        polygons = {}
        if admin:
            sites = {}
            for result in results if results else self.pipe.process(admin):
                # Limit to fields without trailing numbers
                if result.sites and result.field in admin:
                    sites.setdefault(result.field, []).extend(result.sites)
            # Combine polygons from all matching sites
            last = None
            for field in fields:
                geoms = []
                missed = []
                for site in sites.get(field, []):
                    geom = site.geometry.hull
                    if last is None or last.intersects(geom):
                        #geom.draw(last, title=site.summarize())
                        geoms.append(geom)
                    else:
                        #geom.draw(last, title=site.summarize())
                        missed.append(geom)
                        mask = '{} polygon outside parent: {}'
                        logger.warning(mask.format(field, site.summarize()))
                if not geoms:
                    polygons = list(polygons.values()) + missed
                    polygons.sort(key=lambda p: p.area)
                    #self.draw_admin(polygons, mask='ERROR: {}')
                    # Catch missing or out-of-bounds admin polygons
                    names = to_attribute(admin.summarize('admin'))
                    fn = '{}_{}.kml'.format(names, self.location_id)
                    fp = os.path.join('errors', fn)
                    # Convert site dict to list
                    sitelist = []
                    for fld in fields:
                        sitelist.extend(sites.get(fld, []))
                    write_kml(fp, sitelist)
                    msg = 'Admin disjoint: {}: {}'
                    if not sites.get(field):
                        msg = 'Admin not found: {}: {}'
                    raise ValueError(msg.format(self.location_id, names))
                polygons[field] = GeoMetry(geoms)
                last = polygons[field]
        # Rebuild key since it can be changed from mapped names
        key = json.dumps([getattr(self, a) for a in self.adm.code_fields])
        if not polygons:
            raise ValueError('Could not map polygons: {}'.format(key))
        self.admin_cache[key] = polygons
        #return self.admin_cache[key].copy()
        return {k: v.clone() for k, v in polygons.items()}


    def map_marine_features(self):
        """Maps marine features to specific field"""
        func_name = 'map_marine_features'
        if not self.changed(func_name):
            return
        # Map marine features from general purpose fields
        specific = {
            'bay': 'bay_sound',
            'gulf': 'sea_gulf',
            'ocean': 'ocean',
            'sea': 'sea_gulf',
            'sound': 'bay_sound'
        }
        #vals = {k: as_list(getattr(self, k)) for k in set(specific.values())}
        update = {}
        for attr in ('water_body', 'locality'):
            orig = as_list(getattr(self, attr))
            update[attr] = []  # blank original attribute
            unchanged = []     # holds unchanged values
            for val in orig:
                features, leftover = self.parse_locality(val)
                if leftover:
                    unchanged.append(val)
                else:
                    remaining = []
                    for feature in features:
                        name = feature.feature
                        try:
                            if name.lower() in SEAS:
                                field = 'sea_gulf'
                            else:
                                field = specific[feature.feature_kind]
                            update.setdefault(field, []).append(name)
                        except (AttributeError, KeyError):
                            # Return unmatched features
                            remaining.append(feature.verbatim)
                    # Save changes, if any, otherwise restore original value
                    if remaining == features:
                        unchanged.append(val)
                    else:
                        update[attr].extend(remaining)
            # If no changes made, revert to exact original values
            if unchanged == orig:
                del update[attr]
            else:
                # Map values from unchanged back to original field. Does
                # not maintain order!
                update[attr].extend([s for s in unchanged if s])
        if any(update.values()):
            update = {k: dedupe(v) for k, v in update.items()}
            self.update(update, append_to=list(specific.keys()))
        # Try to map ocean name from sea name
        if self.sea_gulf and not self.ocean:
            try:
                self.ocean = SEAS[self.sea_gulf.lower()]
            except KeyError:
                parsed, _ = self.parse_locality(self.sea_gulf)
                if len(parsed) == 1:
                    for variant in parsed[0].variants():
                        try:
                            self.ocean = SEAS[variant.lower()]
                            break
                        except KeyError:
                            pass
                    else:
                        logger.warning('Unknown sea: {}'.format(self.sea_gulf))
        self.changed(func_name)


    def is_marine(self):
        """Evaulates whether collection site appears to be marine"""
        if not self.ocean:
            self.map_marine_features()
        is_marine = bool(self.ocean or self.sea_gulf) and not self.island
        if is_marine:
            # Exclude sites with terrestrial features
            for feature in self.parse_locality(self.locality)[0]:
                try:
                    feature_kind = feature.feature_kind
                except AttributeError:
                    feature_kind = feature.kind
                if feature.specific and not feature_kind == 'offshore':
                    return False
            return True
        return self.site_kind in CODES_MARINE


    def is_terrestrial(self):
        """Evaulates whether collection site appears to be terrestrial"""
        return not self.is_marine()


    def is_georeferenced(self):
        """Evaluates whether coordinates in site were derived or measured"""
        if not self.geometry:
            raise ValueError('Cannot evaluate georeference if no coordinates')
        pattern = r'\b(collector|gps|unknown)\b'
        if (not self.georeference_protocol
            or re.search(pattern, self.georeference_protocol, flags=re.I)):
                return False
        return True


    def get_ocean(self):
        """Gets the name of the nearest ocean, if any"""
        lng, lat = self.centroid.coords[0]
        response = self.bot.ocean_json(lat, lng, 1, 10)
        name = response.get('ocean', {}).get('name', '').split(',')[0].strip()
        if name:
            try:
                return name if 'ocean' in name.lower() else SEAS[name.lower()]
            except KeyError:
                logger.warning('Unknown sea: {}'.format(name))
        return


    def get_sea(self):
        """Gets the name of the nearest sea"""
        lng, lat = self.centroid.coords[0]
        response = self.bot.ocean_json(lat, lng, 0, 100)
        name = response.get('ocean', {}).get('name').split(',')[0].strip()
        if 'ocean' not in name.lower():
            return name
        return name


    def is_sparse(self):
        """Evaluates sparseness of data in record"""
        # Is very basic locality info provided
        if not (self.continent or self.country or self.ocean or self.sea_gulf):
            return True
        # Do any more specific fields contain any data?
        attrs = [
            'locality',
            'water_body',
            'county',
            'municipality',
            'island',
            'mine',
            'volcano',
            'island_group',
            'bay_sound',
            'mining_district',
            'features',
        ]
        for attr in attrs:
            if getattr(self, attr):
                return False
        # A small-ish country or state is good enough
        is_marine = self.ocean or self.sea_gulf
        polygons = self.get_admin_polygons()
        for field in ['state_province', 'country']:
            try:
                if polygons[field].radius_km <= (1000 if is_marine else 500):
                    return False
            except (AttributeError, KeyError):
                pass
        return True


    def draw_admin(self, polygons=None, mask='{}'):
        """Draws the site along with its administrative divisions"""
        if polygons is None:
            polygons = list(self.get_admin_polygons().values())
        title = mask.format(self.summarize('admin'))
        self.draw(polygons, title=title)


    @staticmethod
    def enable_sqlite_cache(path=None):
        """Enables persistent caching of locality parsing"""
        Site.cache = LocalityCache(path)


    def _parse_dwc(self, data):
        """Parses site from a Simple Darwin Core record"""
        for key, val in data.items():
            attr = to_attribute(key)
            if attr in self.attributes:
                setattr(self, attr, val)


    def _parse_emu(self, data):
        """Constructs a site from an EMu Collections Event record"""
        try:
            self.location_id = data('irn')
        except TypeError:
            # FIXME: Not ideal
            from minsci import xmu
            data = xmu.XMuRecord(data)
            self.location_id = data('irn')
        # Map to DwC field names
        self.continent = data('LocContinent')
        self.country = data('LocCountry')
        self.state_province = data('LocProvinceStateTerritory')
        self.county = data('LocDistrictCountyShire')
        self.municipality = data('LocTownship')
        self.island = data('LocIslandName')
        self.island_group = data('LocIslandGrouping')
        self.water_body = [data('LocBaySound')]
        # Map coordinates
        for latkey, lngkey in [
            ('LatLatitudeVerbatim_nesttab', 'LatLongitudeVerbatim_nesttab'),
            ('LatLatitude_nesttab', 'LatLongitude_nesttab'),
            ('LatLatitudeDecimal_nesttab', 'LatLongitudeDecimal_nesttab'),
            ('LatCentroidLatitude0', 'LatCentroidLongitude0'),
            ('LatCentroidLatitudeDec_tab', 'LatCentroidLongitudeDec_tab'),
        ]:
            try:
                lats = as_list(data(latkey)[0])
                lngs = as_list(data(lngkey)[0])
            except IndexError:
                pass
            else:
                self.verbatim_latitude = lats
                self.verbatim_longitude = lngs
                if lats and len(lats) == len(lngs):
                    self.geometry = GeoMetry(list(zip(lats, lngs)))
                    self.georeference_sources = data('LatDetSource_tab')
                    self.georeference_remarks = data('LatGeoreferencingNotes0')
                    # FIXME: Parse radius
                    break
        # Map custom fields
        self.mine = data('LocMineName')
        self.mining_district = data('LocMiningDistrict')
        self.volcano = data('VolVolcanoName')
        self.sea_gulf = data.get('LocSeaGulf')
        self.ocean = data.get('LocOcean')
        self.maps = [data(k) for k in ['LocQUAD', 'MapName'] if data(k)]
        # Map other locations to locality, beginning with PLSS coordinates
        locality = []
        labels = [s.lower() for s in data('MapOtherKind_tab')]
        if 'section' in labels and 'township range' in labels:
            try:
                labels = [lbl.split(' ')[0] for lbl in labels]
                rows = zip(labels, data('MapOtherCoordA_tab'))
                plss = dict(zip(rows))
                rows = zip(labels, data('MapOtherCoordB_tab'))
                plss['range'] = dict(zip(rows))['township']
                mask = '{quarter} Sec. {section} {township} {range}'
                div = mask.format(**plss)
            except KeyError:
                pass
            else:
                locality.append(div)
        # Map generic location fields to locality
        keys = [
            'LocPreciseLocation',
            'LocGeologicSetting',
            'LocGeomorphologicalLocation'
        ]
        locality.extend([data[k] for k in keys if k in data])
        self.locality = [s for s in locality if s]
        # Map site info
        self.site_kind = data('LocRecordClassification')
        self.site_num = data('LocSiteStationNumber')
        self.site_source = data('LocSiteNumberSource')
        self.site_names = data('LocSiteName_tab')
        self.synonyms = []


    def _parse_geonames(self, data):
        """Constructs a site from a GeoNames record"""
        self.from_gazetteer = True
        self.location_id = data.get('geonameId')
        self.continent = data.get('continentCode')
        self.country = data.get('countryName')
        self.state_province = data.get('adminName1')
        self.county = data.get('adminName2')
        self.features = [data.get('name')]
        # Update admin lookups if codes found in the record
        self.country_code = data.get('countryCode', '')
        self.admin_code_1 = data.get('adminCode1', [])
        self.admin_code_2 = data.get('adminCode2', [])
        # Map site info
        self.site_kind = data.get('fcode', '')
        self.site_num = data.get('geonameId')
        # Set data source. Note that the GeoNames format is used in
        # databases.custom to search and return custom sites, so the
        # source is not always GeoNames.
        source = data.get('source')
        self.site_source = source if source else 'GeoNames (CC-BY-4.0)'
        self.sources.append(self.site_source)
        # Get names and alternate names
        self.synonyms = [data.get('name'), data.get('toponymName')]
        names = data.get('alternateNames', [])
        if names and isinstance(names, str):
            names = json.loads(names)
        self.synonyms.extend([s['name'] for s in names])
        en_names = [s['name'] for s in names if s.get('lang') == 'en']
        if not en_names:
            en_names = [data.get('name')]
        self.site_names = en_names
        # Check for a more specific geometry
        try:
            geom, source = get_alt_geometry(self.location_id)
        except UnboundExecutionError:
            print(self.location_id)
            geom = None
        if geom:
            self.geometry = GeoMetry(geom)
            self.sources.append(source)
        else:
            # Map geometry from lat-lng or bbox
            try:
                self.geometry = GeoMetry(data['bbox'])
            except KeyError:
                self.geometry = GeoMetry((data['lat'], data['lng']))

        # Map explicitly defined URL to url_mask
        if data.get('url'):
            self.url_mask = data['url']

        # Custom locations may use the GeoNames API, so only apply this
        # url mask if the location_id is numeric
        elif self.location_id.isnumeric():
            self.url_mask = 'http://geonames.org/{location_id}'

        # Clear invalid county names (e.g., US.WA.000)
        pattern = re.compile(r'^[A-Z]{2}(\.[A-Z\d]+){1,2}$')
        self.county = [c for c in self.county if not pattern.search(c)]
        return self


    def _parse_geoname_id(self, data):
        return self._parse_geonames(self.local.get_json(data))


    def _parse_natural_earth(self, data):
        """Constructs a site from a Natural Earth record"""
        self.from_gazetteer = True
        def clean_name(name, kind):
            find_repl = {
                'Island': {'i.': 'Island', 'is.': 'Island'},
                'Island Group': {
                    'arch.': 'Archipelago',
                    'i.': 'Islands',
                    'is.': 'Islands'
                },
                'Lake': {'l.': 'Lake'},
                'Pen/Cape': {'pen.': 'Peninsula'},
                'Platea': {'plat.': 'PLateau'},
                'Range/Mtn': {
                    'mts.': 'Mountains',
                    'ra.': 'Range',
                    's.': 'Serra'
                },
                'River': {'r.': 'River'},
            }
            for find, repl in find_repl.get(kind, {}).items():
                name = re.sub(re.escape(find), repl, name, flags=re.I)
            return name
        data = {k.lower(): v for k, v in dictify(data).items()}
        # Convert values to lists where appropriate
        for key, val in data.items():
            if val and not isinstance(val, bytes):
                vals = dedupe([s.strip() for s in str(val).split('|')])
                vals = [s for s in vals if s]
                data[key] = vals if len(vals) > 1 else vals[0]
        # Get site identifiers
        self.location_id = None
        keys = ('ne_id', 'ogc_fid', 'wikidataid')
        for key in keys:
            vals = data.get(key, [])
            if vals and not isinstance(vals, list):
                vals = [vals]
            if vals:
                if not self.location_id:
                    self.location_id = '{}:{}'.format(key, vals[0])
                self.other_ids.setdefault(key, []).extend(vals)
        self.other_ids = {k: sorted(v) for k, v in self.other_ids.items()}
        # Get site kind
        keys = ('unit_type', 'featurecla')
        #keys = ('unit_type', 'type_en', 'type', 'featurecla')
        self.site_kind = get_first(data, keys).title()
        # Get name
        site_names = []
        keys = ('name_full', 'name_en', 'name')
        for key in keys:
            vals = data.get(key)
            if vals:
                if not isinstance(vals, list):
                    vals = [s.strip() for s in vals.split('|') if s.strip()]
                site_names.extend(vals)
        site_names = dedupe(site_names)
        self.site_names = [clean_name(n, self.site_kind) for n in site_names]
        if not self.site_names:
            # Construct a name from the feature and ids
            feature = self.site_kind.lower() if self.site_kind else 'feature'
            other_ids = []
            for key, vals in self.other_ids.items():
                for val in vals:
                    other_ids.append('{}:{}'.format(key, val))
            other_ids = '; '.join(other_ids) if other_ids else 'No ID'
            self.site_names = ['Unnamed {} ({})'.format(feature, other_ids)]
        if 'National' in self.site_kind:
            pattern = r'\bN[A-Z]?([& ]*[A-Z]+)\b'
            self.site_names = [re.sub(pattern, self.site_kind, n)
                               for n in self.site_names]
            if self.site_kind not in self.site_names[0]:
                name = '{} {}'.format(self.site_names[0], self.site_kind)
                self.site_names.insert(0, name)
        self.site_source = 'Natural Earth'
        self.geometry = GeoMetry(data['geometry'])
        self.synonyms = []
        for key, val in data.items():
            if key.startswith('name') and val and isinstance(val, str):
                self.synonyms.append(val)
        self.synonyms = sorted(set(self.synonyms))


    def _parse(self, rec):
        """Parses pre-formatted data into a record object"""
        radius_km = rec.pop('radius_km', None)
        for key, val in rec.items():
            if key not in self.attributes:
                try:
                    getattr(self, key)
                except AttributeError:
                    raise KeyError('Illegal key: {}'.format(key))
            setattr(self, key, val)

        if radius_km:
            self.radius_km = float(radius_km)

        return self
