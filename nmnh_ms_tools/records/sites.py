"""Defines tools for parsing and manipulating locality data"""

import json
import logging
import re
from itertools import product
from warnings import warn

import geopandas as gpd
import pandas as pd
from sqlalchemy.exc import OperationalError, UnboundExecutionError
from xmu import EMuRecord

from .core import Record
from ..bots.geonames import CODES_MARINE, GeoNamesBot
from ..databases.admin import AdminFeatures
from ..databases.cache import CacheDict
from ..databases.geonames import GeoNamesFeatures
from ..databases.geohelper import get_alt_geometry
from ..config import CONFIG, GEOCONFIG
from ..tools.geographic_names.caches import LocalityCache
from ..tools.geographic_names.parsers import (
    clean_locality,
    get_leftover,
    parse_localities,
)
from ..tools.geographic_operations import GeoMetry, geoms_to_geodataframe
from ..tools.geographic_operations.kml import write_kml
from ..utils import (
    as_list,
    as_str,
    combine,
    dedupe,
    dictify,
    get_first,
    get_ocean_name,
    mutable,
    set_immutable,
    to_attribute,
)
from ..utils.standardizers import LocStandardizer


logger = logging.getLogger(__name__)


EMU_LAT_KEYS = [
    "LatLatitude_nesttab",
    "LatLongitude_nesttab",
    "LatLatitudeDecimal_nesttab",
    "LatLongitudeDecimal_nesttab",
    "LatLatitudeVerbatim_nesttab",
    "LatLongitudeVerbatim_nesttab",
    "LatModifier_nesttab",
    "LatComment_nesttab",
    "LatDetSource_tab",
    "LatLatLongDetermination_tab",
    "LatDeterminedByRef_tab",
    "LatDetDate0",
    "LatRadiusVerbatim_tab",
    "LatRadiusNumeric_tab",
    "LatGeometry_tab",
    "LatRadiusProbability_tab",
    "LatRadiusUnit_tab",
    "LatDatum_tab",
    "LatCentroidLatitude0",
    "LatCentroidLatitudeDec_tab",
    "LatCentroidLongitude0",
    "LatCentroidLongitudeDec_tab",
    "LatDeriveCentroid_tab",
    "LatCentroidLongitudeDec_tab",
    "LatGeoreferencingNotes0",
    "LatPreferred_tab",
]
SEAS = {
    "Amundsen Gulf": "Arctic Ocean",
    "Barents Sea": "Arctic Ocean",
    "Beaufort Sea": "Arctic Ocean",
    "Chukchi Sea": "Arctic Ocean",
    "East Siberian Sea": "Arctic Ocean",
    #'Greenland Sea': 'Arctic Ocean',
    "Gulf of Boothia": "Arctic Ocean",
    "Kara Sea": "Arctic Ocean",
    "Laptev Sea": "Arctic Ocean",
    "Lincoln Sea": "Arctic Ocean",
    "Prince Gustav Adolf Sea": "Arctic Ocean",
    "Pechora Sea": "Arctic Ocean",
    "Queen Victoria Sea": "Arctic Ocean",
    "Wandel Sea": "Arctic Ocean",
    "White Sea": "Arctic Ocean",
    "Adriatic Sea": "Atlantic Ocean",
    "Aegean Sea": "Atlantic Ocean",
    "Alboran Sea": "Atlantic Ocean",
    "Archipelago Sea": "Atlantic Ocean",
    "Argentine Sea": "Atlantic Ocean",
    "Baffin Bay": "Atlantic Ocean",
    "Balearic Sea": "Atlantic Ocean",
    "Baltic Sea": "Atlantic Ocean",
    "Bay of Biscay": "Atlantic Ocean",
    "Bay of Bothnia": "Atlantic Ocean",
    "Bay of Campeche": "Atlantic Ocean",
    "Bay of Fundy": "Atlantic Ocean",
    "Black Sea": "Atlantic Ocean",
    "Bothnian Sea": "Atlantic Ocean",
    "Caribbean Sea": "Atlantic Ocean",
    "Celtic Sea": "Atlantic Ocean",
    "English Channel": "Atlantic Ocean",
    "Foxe Basin": "Atlantic Ocean",
    "Greenland Sea": "Atlantic Ocean",
    "Gulf of Bothnia": "Atlantic Ocean",
    "Gulf of Finland": "Atlantic Ocean",
    "Gulf of Lion": "Atlantic Ocean",
    "Gulf of Guinea": "Atlantic Ocean",
    "Gulf of Maine": "Atlantic Ocean",
    "Gulf of Mexico": "Atlantic Ocean",
    "Gulf of Saint Lawrence": "Atlantic Ocean",
    "Gulf of Sidra": "Atlantic Ocean",
    "Gulf of Venezuela": "Atlantic Ocean",
    "Hudson Bay": "Atlantic Ocean",
    "Ionian Sea": "Atlantic Ocean",
    "Irish Sea": "Atlantic Ocean",
    "Irminger Sea": "Atlantic Ocean",
    "James Bay": "Atlantic Ocean",
    "Labrador Sea": "Atlantic Ocean",
    "Levantine Sea": "Atlantic Ocean",
    "Libyan Sea": "Atlantic Ocean",
    "Ligurian Sea": "Atlantic Ocean",
    "Marmara Sea": "Atlantic Ocean",
    "Mediterranean Sea": "Atlantic Ocean",
    "Myrtoan Sea": "Atlantic Ocean",
    "North Sea": "Atlantic Ocean",
    "Norwegian Sea": "Atlantic Ocean",
    "Sargasso Sea": "Atlantic Ocean",
    "Sea of Åland": "Atlantic Ocean",
    "Sea of Azov": "Atlantic Ocean",
    "Sea of Crete": "Atlantic Ocean",
    "Sea of the Hebrides": "Atlantic Ocean",
    "Thracian Sea": "Atlantic Ocean",
    "Tyrrhenian Sea": "Atlantic Ocean",
    "Wadden Sea": "Atlantic Ocean",
    "Andaman Sea": "Indian Ocean",
    "Arabian Sea": "Indian Ocean",
    "Bali Sea": "Indian Ocean",
    "Bay of Bengal": "Indian Ocean",
    "Burma Sea": "Indian Ocean",
    "Flores Sea": "Indian Ocean",
    "Great Australian Bight": "Indian Ocean",
    "Gulf of Aden": "Indian Ocean",
    "Gulf of Aqaba": "Indian Ocean",
    "Gulf of Khambhat": "Indian Ocean",
    "Gulf of Kutch": "Indian Ocean",
    "Gulf of Oman": "Indian Ocean",
    "Gulf of Suez": "Indian Ocean",
    "Laccadive Sea": "Indian Ocean",
    "Mozambique Channel": "Indian Ocean",
    "Persian Gulf": "Indian Ocean",
    "Red Sea": "Indian Ocean",
    "Timor Sea": "Indian Ocean",
    "Arafura Sea": "Pacific Ocean",
    "Banda Sea": "Pacific Ocean",
    "Bering Sea": "Pacific Ocean",
    "Bismarck Sea": "Pacific Ocean",
    "Bohai Sea": "Pacific Ocean",
    "Bohol Sea": "Pacific Ocean",
    "Camotes Sea": "Pacific Ocean",
    "Celebes Sea": "Pacific Ocean",
    "Chilean Sea": "Pacific Ocean",
    "Coral Sea": "Pacific Ocean",
    "East China Sea": "Pacific Ocean",
    "Gulf of Alaska": "Pacific Ocean",
    "Gulf of Anadyr": "Pacific Ocean",
    "Gulf of California": "Pacific Ocean",
    "Gulf of Carpentaria": "Pacific Ocean",
    "Gulf of Fonseca": "Pacific Ocean",
    "Gulf of Panama": "Pacific Ocean",
    "Gulf of Thailand": "Pacific Ocean",
    "Gulf of Tonkin": "Pacific Ocean",
    "Halmahera Sea": "Pacific Ocean",
    "Java Sea": "Pacific Ocean",
    "Koro Sea": "Pacific Ocean",
    "Mar de Gra": "Pacific Ocean",
    "Molucca Sea": "Pacific Ocean",
    "Moro Gulf": "Pacific Ocean",
    "Philippine Sea": "Pacific Ocean",
    "Salish Sea": "Pacific Ocean",
    "Savu Sea": "Pacific Ocean",
    "Sea of Japan": "Pacific Ocean",
    "Sea of Okhotsk": "Pacific Ocean",
    "Seram Sea": "Pacific Ocean",
    "Seto Inland Sea": "Pacific Ocean",
    "Shantar Sea": "Pacific Ocean",
    "Sibuyan Sea": "Pacific Ocean",
    "Solomon Sea": "Pacific Ocean",
    "South China Sea": "Pacific Ocean",
    "Sulu Sea": "Pacific Ocean",
    "Tasman Sea": "Pacific Ocean",
    "Visayan Sea": "Pacific Ocean",
    "Yellow Sea": "Pacific Ocean",
    "Amundsen Sea": "Southern Ocean",
    "Bellingshausen Sea": "Southern Ocean",
    "Cooperation Sea": "Southern Ocean",
    "Cosmonauts Sea": "Southern Ocean",
    "Davis Sea": "Southern Ocean",
    "D'Urville Sea": "Southern Ocean",
    "King Haakon VII Sea": "Southern Ocean",
    "Lazarev Sea": "Southern Ocean",
    "Mawson Sea": "Southern Ocean",
    "Riiser-Larsen Sea": "Southern Ocean",
    "Ross Sea": "Southern Ocean",
    "Scotia Sea": "Southern Ocean",
    "Somov Sea": "Southern Ocean",
    "Weddell Sea": "Southern Ocean",
    # Sea names found in the GeoNames ocean webservice
    "Andaman Or Burma Sea": "Indian Ocean",
    "Canarias Sea": "Atlantic Ocean",
    "China Sea": "Pacific Ocean",
    "Coastal Waters Of Southeast Alaska And British Columbia": "Pacific Ocean",
    "Gulf Of Aden": "Indian Ocean",
    "Gulf Cal": "Pacific Ocean",
    "Gulf of Carpenteria": "Pacific Ocean",
    "Gulf of Davao": "Pacific Ocean",
    "Hudson Strait": "Atlantic Ocean",
    "Iceland Sea": "Atlantic Ocean",
    "Joseph Bonaparte Gulf": "Indian Ocean",
    "Malacca Strait": "Indian Ocean | Pacific Ocean",
    "Maluku Sea": "Pacific Ocean",
    "North Greenland Sea": "Atlantic Ocean",
    "Rio De La Plata": "Atlantic Ocean",
    "Samar Sea": "Pacific Ocean",
    "Singapore Strait": "Indian Ocean | Pacific Ocean",
    "South Seas": "Pacific Ocean",
    "Strait Of Sicilia": "Atlantic Ocean",
    "Tirreno Sea": "Atlantic Ocean",
}
for sea in list(SEAS):
    SEAS[sea.lower()] = SEAS[sea]


class Site(Record):
    """Defines methods for parsing and manipulating locality data"""

    config = CONFIG
    adm = AdminFeatures()
    admin_cache = CacheDict()
    bot = GeoNamesBot() if CONFIG["bots"]["geonames_username"] else None
    cache = {}
    local = GeoNamesFeatures()
    std = LocStandardizer()
    pipe = None

    terms = [
        "location_id",
        "continent",
        "country",
        "state_province",
        "county",
        "municipality",
        "island",
        "island_group",
        "water_body",
        "features",
        "settings",
        "maps",
        "mine",
        "mining_district",
        "volcano",
        "ocean",
        "sea_gulf",
        "bay_sound",
        "locality",
        "verbatim_locality",
        "georeference_protocol",
        "georeference_sources",
        "georeference_remarks",
        "plss",
        "site_class",
        "site_source",
        "site_num",
        "site_names",
        "synonyms",
        "continent_code",
        "country_code",
        "admin_div_1",
        "admin_code_1",
        "admin_div_2",
        "admin_code_2",
    ]

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ["site_kind", "geometry"]
        self._writable = ["field", "filter", "from_cache", "interpreted"]
        # Explicitly define defaults for all reported attributes
        self.location_id = ""
        self.continent = ""
        self.country = ""
        self.state_province = []
        self.county = []
        self.municipality = ""
        self.island = ""
        self.island_group = ""
        self.water_body = []
        self.features = []
        self.settings = []
        self.maps = []
        self.mine = ""
        self.mining_district = ""
        self.volcano = ""
        self.ocean = ""
        self.sea_gulf = ""
        self.bay_sound = ""
        self.locality = ""
        self.verbatim_locality = ""
        self.georeference_protocol = ""
        self.georeference_sources = ""
        self.georeference_remarks = ""
        self.plss = ""
        # GeoNames fields
        self.site_class = ""
        self.site_source = ""
        self.site_num = ""
        self.site_names = []
        self.synonyms = []
        # Define additional attributes
        self.admin_polygons = {}
        self.continent_code = ""
        self.country_code = ""
        self.admin_div_1 = []
        self.admin_code_1 = []
        self.admin_div_2 = []
        self.admin_code_2 = []
        self.other_ids = {}
        # Define hidden attributes derived from geometry
        # self._verbatim_latitude = ""
        # self._verbatim_longitude = ""
        # Define additional attributes required for parse
        self._geometry = None
        self._site_kind = ""
        self._features = {}
        self.from_gazetteer = False
        # Generate instance
        try:
            super().__init__(*args, **kwargs)
        except Exception as exc:
            raise ValueError(
                f"Could not create a site from {args}, {kwargs}: {exc}"
            ) from exc
        # Mutable attributes
        self.field = None
        self.filter = {}
        self.interpreted = {}
        self.related_sites = []

    def __getattr__(self, attr):
        """Looks for unrecognized attributes in geometry (fallback)"""
        try:
            if attr not in {"_geometry", "geometry"}:
                return getattr(self.geometry, attr)
        except AttributeError as exc:
            if "has no attribute" not in str(exc):
                raise
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{attr}'"
        )

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_geometry"] = None
        return state

    @property
    def name(self):
        try:
            return self.site_names[0]
        except IndexError:
            return "Unnamed site"

    @property
    def geometry(self):
        """Returns the geometry for this site, instantiating it if needed"""
        return self._geometry

    @geometry.setter
    def geometry(self, geom):
        if geom is not None:
            self._geometry = geom
            self.radius_km

    @property
    def radius_km(self):
        """Returns the uncertainty radius for this site"""
        try:
            return self.geometry.radius_km
        except AttributeError:
            return 0

    @radius_km.setter
    def radius_km(self, val):
        if val is None or val < 1:
            try:
                val = GEOCONFIG.get_feature_radius(self.site_kind)
            except (KeyError, TypeError):
                return 1  # force the minimum radius for a site to 1 km
        with mutable(self.geometry):
            self.geometry.radius_km = val

    @property
    def site_kind(self):
        """Returns the site kind, normally the GeoNames feature code"""
        return self._site_kind

    @site_kind.setter
    def site_kind(self, val):
        # Must be a string for some comparisons when georeferencing
        self._site_kind = val if val else ""
        try:
            self.site_class = GEOCONFIG.get_feature_class(val)
        except KeyError:
            pass

    @property
    def decimal_latitude(self):
        return self.geometry.lat

    @property
    def decimal_longitude(self):
        return self.geometry.lon

    @property
    def footprint_wkt(self):
        return self.geometry.wkt()

    @property
    def geodetic_datum(self):
        return self.geometry.crs

    def summarize(self, mask=None):
        """Summarizes the content of a record"""
        if mask is None:
            loc_id = self.location_id if self.location_id else "not provided"
            return "{} ({})".format(self.name, loc_id)
        if mask == "admin":
            attrs = ["county", "state_province", "country"]
            admin = [as_str(getattr(self, a)) for a in attrs]
            return ", ".join([a for a in admin if a])
        return mask.format(**self.to_dict())

    def parse(self, data):
        """Parses site data"""
        if hasattr(data, "ne_id") or hasattr(data, "ogc_fid"):
            self._parse_natural_earth(data)
        elif isinstance(data, int):
            self._parse_geoname_id(data)
        elif isinstance(data, str) and data.isnumeric():
            self._parse_geoname_id(int(data))
        elif "irn" in data or any([re.match(r"(Loc|Col)[A-Z]", k) for k in data]):
            self._parse_emu(data)
        elif isinstance(data, list) and "geonameId" in data[0]:
            self._parse_geonames(data[0])
        elif "geonameId" in data:
            self._parse_geonames(data)
        elif "recordNumber" in data or "record_number" in data:
            self._parse_dwc(data)
        elif data:
            self._parse(data)

        # Map marine features to proper fields
        self.map_marine_features()

        # Set URL mask based on the identifier
        if not self.url_mask and re.match(r"^Q\d+$", self.location_id):
            self.url_mask = "https://www.wikidata.org/wiki/{location_id}"

        # Gazetteers should not have the data problems common to collections
        if not self.from_gazetteer:
            self.cleanup()

        # Check the geometry
        if self.geometry and not self.geometry.is_valid:
            raise ValueError(f"GeoMetry invalid: {self.geometry}")

    def parse_locality(self, val):
        """Parses a locality string"""
        # If attribute given, convert to value
        try:
            val = getattr(self, val)
        except AttributeError:
            pass
        except TypeError:
            if val:
                raise
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
        split_phrases = re.search(r"(,|;|:|/|\|| - )", clean_locality(val))
        features = parse_localities(val, split_phrases=split_phrases)
        leftover = get_leftover(val, features)
        # Store result
        self._features[val] = features, leftover
        self.cache[val] = features, leftover
        return features, leftover

    def cleanup(self):
        """Cleans up common errors in the site"""
        # Split admin divs joined by a spaced-out hyphen
        delim = r"(?: [/\-] )"
        for attr in ("state_province", "county"):
            vals = getattr(self, attr)
            if len(vals) == 1 and re.search(delim, vals[0]):
                setattr(self, attr, re.split(delim, vals[0]))
        # Remove unspecifieds so that admin check will pass
        blacklist = [
            r"([a-z]+ )?unknown",
            r"([a-z]+ )?not stated",
            r"([a-z]+ )?(not |un)determined" r"locality in multiple [a-z]+",
        ]
        for attr in ("continent", "country", "state_province", "county"):
            vals = as_list(getattr(self, attr))
            for pat in blacklist:
                pat = r"^\[?{}\]?$".format(pat)
                vals = [s for s in vals if not re.search(pat, s, flags=re.I)]
            setattr(self, attr, vals)
        # Make major ocean names explicit
        pattern = r"\b(atlantic|pacific|indian|(?:ant)?arctic)(?! ocean)"
        for attr in ("water_body", "ocean"):
            val = getattr(self, attr)
            if isinstance(val, str):
                val = [val]
            vals = []
            for val in val:
                vals.append(re.sub(pattern, r"\1 Ocean", val, flags=re.I))
            setattr(self, attr, vals)

    def validate(self):
        """Verifies that record has required metadata"""
        if self.country and self.country not in ["Unknown"]:
            adm = [self.county, self.state_province, self.country]
            try:
                self.map_admin()
            except (AssertionError, ValueError):
                logger.error("Could not map admin: {}".format(adm))
                return False
            if not self.country_code:
                logger.error("Invalid country: {}".format(adm[-1]))
                return False
            if self.state_province and not self.admin_code_1:
                logger.error("Invalid state/province: {}, {}".format(*adm[-2:]))
                return False
            if self.county and not self.admin_code_2:
                logger.error("Invalid county: {}, {}, {}".format(*adm))
                return False
        return True

    def map_continent(self):
        """Maps continent names and codes based on GeoNames"""
        self.continent_code = ""
        if not self.continent and self.country:
            self.continent = self.local.get_continent(self.country)
        if self.continent:
            if len(self.continent) == 2:
                self.continent_code = self.continent.upper()
                self.continent = self.adm.get_continent_name(self.continent_code)
            else:
                self.continent_code = self.adm.get_continent_code(self.continent)
        return self

    def map_admin(self):
        # Check cache for polygons
        adm_fields = ["continent", "country", "state_province", "county"]
        vals = [getattr(self, a) for a in adm_fields]
        vals = [s for s in vals if s and "?" not in "".join(s)]
        if not vals:
            return gpd.GeoDataFrame()

        vkey = json.dumps(vals)
        try:
            gdf, result, interpreted = self.admin_cache[vkey]
        except KeyError:
            pass
        else:
            with mutable(self):
                for key, val in result.items():
                    setattr(self, key, val if isinstance(val, str) else val.copy())
                self.interpreted = interpreted.copy()
            return gdf

        attrs = {
            "country": "country_code",
            "state_province": "admin_code_1",
            "county": "admin_code_2",
        }

        # Determine whether to map from codes or names
        names = 0
        codes = 0
        for name, code in attrs.items():
            if getattr(self, name):
                names += 1
            if getattr(self, code):
                codes += 1
        attrs = list(attrs) if names > codes else list(attrs.values())
        is_name = names > codes

        result = {}
        val_to_id = {}
        id_to_field = {}

        # Map admin
        if names + codes:
            # Get all combinations of country/state_province/county
            admin = []
            for attr in attrs:
                vals = as_list(getattr(self, attr))
                if not vals:
                    break
                admin.append(vals)

            # Get matching administrative divisions
            matches = {}
            results = []
            for adm in product(*admin):
                result = self.adm.get(*adm, is_name=is_name)
                for key in attrs:
                    try:
                        val = result[key]
                    except KeyError:
                        pass
                    else:
                        if val:
                            matches.setdefault((key, val[0]), []).extend(
                                self.adm.query(val, key, **result)
                            )
                results.append(result)

            # Update record with preferred names, admin codes, and georeference matches
            result = combine(*results)
            result["admin_div_1"] = result.get("state_province", [])
            result["admin_div_2"] = result.get("county", [])
            with mutable(self):
                for key, val in result.items():
                    setattr(self, key, val)

            # Map each geonames_id to the corresponding admin field (country, state_province, etc.)
            for (field, val), rows in matches.items():
                for row in rows:
                    gn_id = str(row.geoname_id)
                    id_to_field[gn_id] = field
                    val_to_id[(field, val)] = gn_id

        # Map continent and add to ID lookups
        with mutable(self):
            self.map_continent()
        if self.continent:
            continent_id = str(
                GeoNamesFeatures().search_json(self.continent, fcode="CONT")[0][
                    "geonameId"
                ]
            )
            id_to_field[continent_id] = "continent"
            val_to_id[("continent", self.continent)] = continent_id
            result["continent_code"] = self.continent_code
            result["continent"] = self.continent

        # Map feature metadata from each site to a GeoDataFrame
        sites = {}
        for rec in GeoNamesFeatures().get_many(list(id_to_field)):
            site = Site(rec)
            sites[site.location_id] = site
        gdf = sites_to_geodataframe(sites.values())

        # Update site with georeference info
        interpreted = {k: sites[v] for k, v in val_to_id.items()}
        self.interpreted.update(interpreted)

        # Create the admin geodataframe for testing feature intersections
        fields = pd.DataFrame(id_to_field.items(), columns=["location_id", "field"])
        gdf = gdf.merge(fields)
        gdf = (
            gdf[["field", "geometry", "area"]]
            .dissolve("field")
            .sort_values("area", ascending=False)
            .reset_index()
        )

        # Check for admin units that have not been assigned polygons
        has_area = gdf[gdf["area"] != 0]
        no_area = set(gdf["field"]) - set(has_area["field"])
        if no_area:
            print(
                f"No polygon for {no_area} {(self.country, self.state_province, self.county)})"
            )

        # Add dataframe to cache
        key = json.dumps([getattr(self, a) for a in adm_fields])
        self.admin_cache[key] = (gdf, result, interpreted)
        self.admin_cache[vkey] = self.admin_cache[key]

        return gdf.copy()

    def compare_names(self, other, std_func=None):
        """Tests and tracks name comparison"""
        return self.compare_attr(None, other, "names", std_func=std_func)

    def compare_attr(self, val, other, attr, std_func=None):
        """Tests and tracks filters"""
        # print('{}: {} => {}'.format(attr, val, other))
        if attr == "names":
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
                return "".join(sorted(set(std_func(val).split("-"))))
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

    def subsection(self, direction, name=None, inplace=False):
        """Calcualtes the subsection specified by the direction"""
        subsection = self.geometry.subsection(direction)
        # Return exact copy if geometry unchanged
        site = self.copy() if not inplace else self
        if subsection == self.geometry:
            return site
        # Add original outline to related sites
        with mutable(site):
            site.related_sites.append(self)
            site.geometry = subsection
            # Note the subsectioning and update identifiers
            site.location_id += "_" + direction.upper()
            if name is None:
                name = "{} {}".format(direction, self.name)
            site.site_names = [name]
            site.filter["name"] = name
        return site

    def has_valid_coordinates(self):
        """Checks coordinates against admin divisions

        Out-of-range latitudes and longitudes are handled by GeoMetry
        """
        buffer_km = 10
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
            else:
                buffer_km = 200
        # Otherwise verify that the polygons intersect the given coordinates
        gdf = self.map_admin()
        if not self.geometry:
            logger.debug(f"Coordinates not specified: {self}")
            return False
        if not gdf.empty:
            row = gdf.iloc[-1]
            geom = GeoMetry(gdf.geometry.iloc[-1:].reset_index(drop=True), gdf.crs)
            if not self.intersects(geom.buffer(buffer_km)):
                mask = "Coordinates fall outside {}: {}"
                logger.debug(mask.format(row["field"], self.location_id))
                return False
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
                fcl = GEOCONFIG.get_feature_class(self.site_kind)
                if fcl not in {"A", "H", "U"}:
                    gdf = self.map_admin()
                    if not gdf.empty:
                        row = gdf.geometry.iloc[-1:].reset_index(drop=True)
                        geom = GeoMetry(row.geometry, gdf.crs)
                        return self.restrict(geom)
            except KeyError:
                # Unrecognized classes, including non-GeoNames pipes, end here
                pass
            return self

        contained = self.centroid.within(other)
        if not contained or (self.geom_type != "Point" and other.geom_type != "Point"):
            xtn = self.intersection(other)
            if xtn.geom[0].is_empty:
                raise ValueError(f"Could not restrict {self} to {other}")
            self.geometry = GeoMetry(xtn, crs=self.crs)

        elif contained:
            # Leave the centroid alone and set the radius to the maximum
            # distance to the other geometry
            max_dist_km = self.max_dist_km(other)
            if max_dist_km < self.radius_km:
                self.radius_km = max_dist_km

        return self

    def map_marine_features(self):
        """Maps marine features to specific field"""
        func_name = "map_marine_features"
        if not self.changed(func_name):
            return

        # Look for known ocean and sea names anywhere in the record
        if not self.ocean and not self.sea_gulf:
            rec_str = str(self)
            for pat in [
                r"\b(?:(?:north|south) )?(?:atlantic|pacific)(?: ocean)?\b",
                r"\b(?:antarctic|arctic|indian|southern)(?: ocean)\b",
            ] + [r"\b" + s + r"\b" for s in SEAS]:
                matches = re.findall(pat, rec_str, flags=re.I)
                oceans = [m for m in matches if "ocean" in m.lower()]
                if oceans:
                    self.ocean = " | ".join(oceans)
                seas = [m for m in matches if "sea" in m.lower()]
                if seas:
                    self.sea_gulf = " | ".join(seas)

        # Parse locality is very expensive, so only run it if an ocean/sea is found
        if not self.ocean and not self.sea_gulf:
            self.changed(func_name)
            return

        # Map marine features from general purpose fields
        specific = {
            "bay": "bay_sound",
            "gulf": "sea_gulf",
            "ocean": "ocean",
            "sea": "sea_gulf",
            "sound": "bay_sound",
        }

        update = {}
        for attr in ("water_body", "locality"):
            orig = as_list(getattr(self, attr))
            update[attr] = []  # blank original attribute
            unchanged = []  # holds unchanged values
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
                                field = "sea_gulf"
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
                    logger.warning("Unknown sea: {}".format(self.sea_gulf))
        self.changed(func_name)

    def is_marine(self):
        """Evaulates whether collection site appears to be marine"""
        pat = r"\b(atlantic|pacific|indian|arctic|southern|ocean|sea|bay|gulf|off|offshore)\b"
        likely_marine = (
            (
                re.search(pat, str(self), flags=re.I)
                or self.ocean
                or self.sea_gulf
                or self.bay_sound
            )
        ) and not self.island
        if likely_marine:
            if not self.ocean:
                self.map_marine_features()
            # Exclude sites with terrestrial features
            for feature in self.parse_locality(self.locality)[0]:
                try:
                    feature_kind = feature.feature_kind
                except AttributeError:
                    feature_kind = feature.kind
                if feature.specific and not feature_kind == "offshore":
                    return False
            return True
        return self.site_kind in CODES_MARINE

    def is_terrestrial(self):
        """Evaulates whether collection site appears to be terrestrial"""
        return not self.is_marine()

    def is_georeferenced(self):
        """Evaluates whether coordinates in site were derived or measured"""
        if not self.geometry:
            raise ValueError("Cannot evaluate georeference if no coordinates")
        pattern = r"\b(collector|gps|unknown)\b"
        if not self.georeference_protocol or re.search(
            pattern, self.georeference_protocol, flags=re.I
        ):
            return False
        return True

    def get_ocean(self):
        """Gets the name of the nearest ocean, if any"""
        centroid = self.centroid
        response = self.bot.ocean_json(centroid.y, centroid.x, 1, 10)
        name = response.get("ocean", {}).get("name", "").split(",")[0].strip()
        if name:
            try:
                return name if "ocean" in name.lower() else SEAS[name.lower()]
            except KeyError:
                logger.warning("Unknown sea: {}".format(name))
        return

    def get_sea(self):
        """Gets the name of the nearest sea"""
        centroid = self.centroid
        response = self.bot.ocean_json(centroid.y, centroid.x, 0, 100)
        name = response.get("ocean", {}).get("name").split(",")[0].strip()
        if "ocean" not in name.lower():
            return name
        return name

    def is_sparse(self):
        """Evaluates sparseness of data in record"""
        # Is very basic locality info provided
        if not (self.continent or self.country or self.ocean or self.sea_gulf):
            return True
        # Do any more specific fields contain any data?
        attrs = [
            "locality",
            "water_body",
            "county",
            "municipality",
            "island",
            "mine",
            "volcano",
            "island_group",
            "bay_sound",
            "mining_district",
            "features",
        ]
        for attr in attrs:
            if getattr(self, attr):
                return False
        # A small-ish country or state is good enough
        is_marine = self.ocean or self.sea_gulf
        gdf = self.map_admin()
        if not gdf.empty:
            geom = GeoMetry(gdf.geometry.iloc[-1:].reset_index(drop=True), gdf.crs)
            if geom.radius_km <= (1000 if is_marine else 500):
                return False
        return True

    @staticmethod
    def enable_sqlite_cache(path=None):
        """Enables persistent caching of locality parsing"""
        Site.cache = LocalityCache(path)

    def _build_geometry(self, geom, **kwargs):
        # if not hasattr(geom, "crs") or not geom.crs:
        #    kwargs.setdefault(
        #        "crs", self.geodetic_datum if self.geodetic_datum else "epsg:4326"
        #    )
        if not hasattr(geom, "radius_km") or not geom.radius_km:
            try:
                kwargs.setdefault(
                    "radius_km", GEOCONFIG.get_feature_radius(self.site_kind)
                )
            except KeyError:
                kwargs.setdefault("radius_km", 10)
        return GeoMetry(geom, **kwargs)

    def _parse_dwc(self, data):
        """Parses site from a Simple Darwin Core record"""
        for key, val in data.items():
            attr = to_attribute(key)
            if attr in self.attributes:
                setattr(self, attr, val)

    def _parse_emu(self, data):
        """Constructs a site from an EMu Collections Event record"""
        if not isinstance(data, EMuRecord):
            data = EMuRecord(data, module="ecollectionevents")
        self.location_id = data.get("irn")
        # Map to DwC field names
        self.continent = data.get("LocContinent")
        self.country = data.get("LocCountry")
        self.state_province = data.get("LocProvinceStateTerritory")
        self.county = data.get("LocDistrictCountyShire")
        self.municipality = data.get("LocTownship")
        self.island = data.get("LocIslandName")
        self.island_group = data.get("LocIslandGrouping")
        self.locality = data.get("LocPreciseLocation")
        # Map coordinates
        grid = data.grid("LatLatitudeDecimal_nesttab").pad()
        if grid:
            row = grid.filter(where={"LatPreferred_tab": "Yes"})
            if not row:
                row = grid[0]
            self.geometry = self._build_geometry(row)
        # Map PLSS
        labels = [s.lower() for s in data.get("MapOtherKind_tab", [])]
        if "section" in labels and "township range" in labels:
            try:
                labels = [lbl.split(" ")[0] for lbl in labels]
                rows = zip(labels, data.get("MapOtherCoordA_tab"))
                plss = dict(zip(rows))
                rows = zip(labels, data.get("MapOtherCoordB_tab"))
                plss["range"] = dict(zip(rows))["township"]
                mask = "{quarter} Sec. {section} {township} {range}"
                plss = mask.format(**plss)
            except KeyError:
                pass
            else:
                self.plss = plss
        # Map custom fields
        self.mine = data.get("LocMineName")
        self.mining_district = data.get("LocMiningDistrict")
        self.volcano = data.get("VolVolcanoName")
        self.bay_sound = data.get("LocBaySound")
        self.sea_gulf = data.get("LocSeaGulf")
        self.ocean = data.get("LocOcean")
        self.maps = [data.get(k) for k in ["LocQUAD", "MapName"] if data.get(k)]
        # Map generic location fields
        self.features = [
            str(f)
            for f in self.parse_locality(data.get("LocGeomorphologicalLocation", ""))[0]
        ]
        self.settings = [
            str(f) for f in self.parse_locality(data.get("LocGeologicSetting", ""))[0]
        ]
        # Map site info
        self.site_kind = data.get("LocRecordClassification")
        self.site_num = data.get("LocSiteStationNumber")
        self.site_source = data.get("LocSiteNumberSource")
        self.site_names = data.get("LocSiteName_tab")
        self.synonyms = []

    def _parse_geonames(self, data):
        """Constructs a site from a GeoNames record"""
        sources = []
        self.from_gazetteer = True
        self.location_id = data.get("geonameId")
        self.continent = data.get("continentCode")
        self.country = data.get("countryName")
        self.state_province = data.get("adminName1")
        self.county = data.get("adminName2")
        self.features = [data.get("name")]
        # Update admin lookups if codes found in the record
        self.country_code = data.get("countryCode", "")
        self.admin_code_1 = data.get("adminCode1", [])
        self.admin_code_2 = data.get("adminCode2", [])
        # Map site info
        self.site_kind = data.get("fcode", "")
        self.site_num = data.get("geonameId")
        # Set data source. Note that the GeoNames format is used in
        # databases.custom to search and return custom sites, so the
        # source is not always GeoNames.
        source = data.get("source")
        self.site_source = source if source else "GeoNames (CC-BY-4.0)"
        self.sources.append(self.site_source)
        # Get names and alternate names
        self.synonyms = [data.get("name"), data.get("toponymName")]
        names = data.get("alternateNames", [])
        if names and isinstance(names, str):
            names = json.loads(names)
        self.synonyms.extend([s["name"] for s in names])
        en_names = [s["name"] for s in names if s.get("lang") == "en"]
        if not en_names:
            en_names = [data.get("name")]
        self.site_names = en_names
        # Check for a more specific geometry
        geom = None
        source_ = None
        try:
            geom, source_ = get_alt_geometry(self.location_id)
        except UnboundExecutionError:
            warn("geohelper database not initiated")
        except OperationalError:
            warn("alternative_polygons table does not exist")
        finally:
            # Store the geometry in bbox so it is available if converted to dict
            if geom:
                source = source_
            # Custom geometries may provide only a bounding box
            else:
                geom = data.get("bbox")
                source = self.site_source
        if geom and (isinstance(geom, (str, dict)) or geom.geom_type != "Point"):
            self.geometry = self._build_geometry(geom, crs=4326)
            self.sources.append(source)
        else:
            # Geometries from GeoNames use lat/lng to define the center, than the
            # bounding box to determine the error radius. This is intended to
            # align the geometry with human georeferences, which commonly use the
            # center, not the bounding box, while capturing an accurate error radius.
            point = self._build_geometry((data["lat"], data["lng"]), crs=4326)
            try:
                bbox = self._build_geometry(data["bbox"], crs=4326)
            except KeyError:
                self.geometry = point
            else:
                self.geometry = point.encompass(bbox)

        # Map explicitly defined URL to url_mask
        if data.get("url"):
            self.url_mask = data["url"]

        # Custom locations may use the GeoNames API, so only apply this
        # url mask if the location_id is numeric
        elif self.location_id.isnumeric():
            self.url_mask = "http://geonames.org/{location_id}"

        # Sort sources
        self.sources = sorted(set(self.sources))

        # Clear invalid county names (e.g., US.WA.000)
        pattern = re.compile(r"^[A-Z]{2}(\.[A-Z\d]+){1,2}$")
        self.county = [c for c in self.county if not pattern.search(c)]
        return self

    def _parse_geoname_id(self, data):
        self.verbatim = self.local.get_json(data)
        return self._parse_geonames(self.verbatim)

    def _parse_natural_earth(self, data):
        """Constructs a site from a Natural Earth record"""
        self.from_gazetteer = True

        def clean_name(name, kind):
            find_repl = {
                "Island": {"i.": "Island", "is.": "Island"},
                "Island Group": {
                    "arch.": "Archipelago",
                    "i.": "Islands",
                    "is.": "Islands",
                },
                "Lake": {"l.": "Lake"},
                "Pen/Cape": {"pen.": "Peninsula"},
                "Platea": {"plat.": "PLateau"},
                "Range/Mtn": {"mts.": "Mountains", "ra.": "Range", "s.": "Serra"},
                "River": {"r.": "River"},
            }
            for find, repl in find_repl.get(kind, {}).items():
                name = re.sub(re.escape(find), repl, name, flags=re.I)
            return name

        data = {k.lower(): v for k, v in dictify(data).items()}
        # Convert values to lists where appropriate
        for key, val in data.items():
            if val and not isinstance(val, bytes):
                vals = dedupe([s.strip() for s in str(val).split("|")])
                vals = [s for s in vals if s]
                data[key] = vals if len(vals) > 1 else vals[0]
        # Get site identifiers
        self.location_id = None
        keys = ("ne_id", "ogc_fid", "wikidataid")
        for key in keys:
            vals = data.get(key, [])
            if vals and not isinstance(vals, list):
                vals = [vals]
            if vals:
                if not self.location_id:
                    self.location_id = "{}:{}".format(key, vals[0])
                self.other_ids.setdefault(key, []).extend(vals)
        self.other_ids = {k: sorted(v) for k, v in self.other_ids.items()}
        # Get site kind
        keys = ("unit_type", "featurecla")
        # keys = ('unit_type', 'type_en', 'type', 'featurecla')
        self.site_kind = get_first(data, keys).title()
        # Get name
        site_names = []
        keys = ("name_full", "name_en", "name")
        for key in keys:
            vals = data.get(key)
            if vals:
                if not isinstance(vals, list):
                    vals = [s.strip() for s in vals.split("|") if s.strip()]
                site_names.extend(vals)
        site_names = dedupe(site_names)
        self.site_names = [clean_name(n, self.site_kind) for n in site_names]
        if not self.site_names:
            # Construct a name from the feature and ids
            feature = self.site_kind.lower() if self.site_kind else "feature"
            other_ids = []
            for key, vals in self.other_ids.items():
                for val in vals:
                    other_ids.append("{}:{}".format(key, val))
            other_ids = "; ".join(other_ids) if other_ids else "No ID"
            self.site_names = ["Unnamed {} ({})".format(feature, other_ids)]
        if "National" in self.site_kind:
            pattern = r"\bN[A-Z]?([& ]*[A-Z]+)\b"
            self.site_names = [
                re.sub(pattern, self.site_kind, n) for n in self.site_names
            ]
            if self.site_kind not in self.site_names[0]:
                name = "{} {}".format(self.site_names[0], self.site_kind)
                self.site_names.insert(0, name)
        self.site_source = "Natural Earth"
        self.geometry = self._build_geometry(data["geometry"], crs=4326)
        self.synonyms = []
        for key, val in data.items():
            if key.startswith("name") and val and isinstance(val, str):
                self.synonyms.append(val)
        self.synonyms = sorted(set(self.synonyms))

    def _parse(self, rec):
        """Parses pre-formatted data into a record object"""

        # Extract geometry
        geom = rec.pop("geometry", None)
        lat = rec.pop("latitude", None)
        lon = rec.pop("longitude", None)
        crs = rec.pop("crs", None)
        radius_km = rec.pop("radius_km", 0)

        for key, val in rec.items():
            if key not in self.attributes:
                try:
                    getattr(self, key)
                except AttributeError:
                    raise KeyError("Illegal key: {}".format(key))
            setattr(self, key, val)

        if geom:
            self.geometry = GeoMetry(geom, crs=crs)
        elif lat and lon:
            self.geometry = GeoMetry((lat, lon), crs=crs, radius_km=radius_km)
        elif lat or lon or crs or radius_km:
            raise ValueError("Only partial geometry info provided")

        return self


def sites_to_geodataframe(sites, **kwargs):
    """Creates a geodataframe of all sites using a coherent equal-area CRS"""
    import numpy as np

    geoms = []
    metadata = {}
    for site in as_list(sites):
        geoms.append(site.geometry)
        for key, val in site.to_dict().items():
            if isinstance(val, list):
                val = " | ".join(val)
            metadata.setdefault(key, []).append(val if val else np.nan)
    return geoms_to_geodataframe(geoms, **metadata)
