"""Defines methods to evaluate and summarize georeferencing information"""
import logging
import itertools
import re

from shapely.geometry import GeometryCollection
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .results import MatchResult
from ....bots.geonames import (
    CODES_ADMIN,
    CODES_ISLANDS,
    CODES_MARINE,
    CODES_RIVERS,
    CODES_SHORES,
    CODES_UNDERSEA,
)
from ....config import CONFIG
from ....databases.georef_data import OceanQuery
from ....tools.geographic_operations.geometry import GeoMetry
from ....records import Site
from ....utils import as_set




logger = logging.getLogger(__name__)




STATUSES = {
    'admin',          # an administratic division
    'constrained',    # selection constrained to intersection with this site
    'encompassing',   # selection falls within these sites
    'intersecting',   # selection intersects these sites
    'less specific',  # selection is more specific than these sites
    'more specific',  # selection is less specific but
    'selected',       # selected site(s)
    'very large',     # a continent, ocean, or sea
    # Rejected
    'rejected (duplicate)',               # same geometry repeated elsewhere
    'rejected (interpreted as admin)',    # interpretated name as admin div
    'rejected (interpreted elsewhere)',   # interpretated name already
    'rejected (disjoint on higher geo)',  # disjoint on admin or cont/ocean/sea
    'rejected (disjoint)',                # disjoint from other sites
    'rejected (not reconciled)',          # no coherent georeference possible
    'rejected (outlier)'                  # far away from other sites
}
REJECTED = {
    'rejected (duplicate)',
    'rejected (interpreted as admin)',
    'rejected (interpreted elsewhere)',
    'rejected (disjoint on higher geo)',
    'rejected (disjoint)',
    'rejected (not reconciled)',
    'rejected (outlier)'
}
# Job parameters
MAX_SITES = 150
CONT_SHELF_WIDTH_KM = 200
RESIZE = 1.1




class MatchEvaluator:
    """Georeferences a site by parsing, matching, and evaluating place names"""

    def __init__(self, site, pipes, results=None):
        self.site = site
        self.pipes = pipes
        self.geometry = None
        self.terms_checked = None
        self.terms_matched = None
        self.interpreted = {}
        self.features = {}
        self.leftovers = {}                      # fields with unparseable info
        self.intersecting = False
        self.sources = []
        self.admin_match_type = {}
        self.ocean = OceanQuery()
        self.multiples = {}
        self.smallest_encompassing = None
        # Configure sites property
        self._sites = None
        self.sites = []
        # Configure results property
        self._result = None
        self._results = None
        self.results = results[:] if results is not None else []


    def __getattr__(self, attr):
        """Looks for unrecognized attributes in geometry"""
        try:
            return getattr(self.geometry, attr)
        except AttributeError:
            mask = "'{}' object has no attribute '{}'"
            raise AttributeError(mask.format(self.__class__.__name__, attr))


    def __iter__(self):
        return iter(self.results)


    def __len__(self):
        return len(self.results)


    @property
    def lookup(self):
        """Creates dict to look up sites by location_id"""
        return {site.location_id: site for site in self._sites}


    @property
    def sites(self):
        """Returns list of uninterpreted sites"""
        return self.uninterpreted()


    @sites.setter
    def sites(self, sites):
        # For repeats, keep only the most specific field that matched the site
        grouped = {}
        for site in sites:
            grouped.setdefault(site.location_id, []).append(site)
        self._sites = []
        for group in grouped.values():
            if len(group) > 1:
                generic = {'features', 'locality', 'maps'}
                specific = [s for s in group
                            if s.field[-1].isalpha() and s.field not in generic]
                if specific:
                    group = specific
            self._sites.append(group[0])


    @property
    def result(self):
        """Represents the final georeference as a simple site"""
        if self._result is None:
            result = self.site.clone()
            result.site_names = ['Georeference']
            result.geometry = self.geometry
            if self.interpreted_as('selected'):
                result.georeference_remarks = self.describe()
            result.sources = self.sources
            self._result = result
        return self._result


    @property
    def results(self):
        """Returns the original results list"""
        return self._results


    @results.setter
    def results(self, results):
        self._results = results[:]
        self.update_lists()


    def clone(self):
        """Clones the evaluator object"""
        return self.__class__(self.site, self.pipes, self.results[:])


    def reset(self):
        """Resets te evaluator object"""
        clone = self.clone()
        self.site = clone.site
        self.pipes = clone.pipes
        self.geometry = None
        self.terms_checked = None
        self.terms_matched = None
        self.interpreted = {}
        self.features = {}
        self.leftovers = {}                      # fields with unparseable info
        self.intersecting = False
        self.admin_match_type = {}
        self.smallest_encompassing = None
        # Configure sites property
        self._sites = None
        self.sites = []
        # Configure results property
        self._result = None
        self._results = None
        self.results = clone.results[:] if clone.results is not None else []
        return self


    def key(self, site):
        """Returns field:name for the given site"""
        return '{}:{}'.format(self.field(site.field), site.filter['name'])


    @staticmethod
    def field(field):
        """Returns original field name stripped of iterator"""
        return field.rstrip('0123456789')


    def process(self):
        """Processes place names in the record using the defined pipes"""
        self.leftovers = {}
        base = self.pipes[0].load(self.site).prepare_all()
        for pipe in self.pipes:
            try:
                self.extend(pipe.copy_from(base).process())
                for key, vals in pipe.leftovers.items():
                    self.leftovers.setdefault(self.field(key), []).extend(vals)
            except Exception as e:
                msg = 'Failed to process record: {}'
                logger.error(msg.format(self.site.location_id), exc_info=e)
                raise
        self.leftovers = {k: set(v) for k, v in self.leftovers.items()}
        self.features = self.pipes[0].extract(self.site)


    def encompass(self, sites=None, max_dist_km=100):
        """Calculate coordinates and radius using info from results"""
        if not self.results:
            self.process()
        if sites is None or sites == self.sites:
            sites = self.sites[:]

        # Check if too many sites given
        logger.debug('{:,} sites remain after initial cull'.format(len(sites)))
        if len(sites) > MAX_SITES:
            mask = 'Too many candidates to encompass ({}/{})'
            raise ValueError(mask.format(len(sites), MAX_SITES))
        sites = self.uninterpreted(self.ignore_related(sites))
        sites = self.uninterpreted(self.dedupe(sites))
        logger.debug('Unique geometries: {}'.format(self.names(sites)))

        # Extract large features like admin divisions, oceans, and seas
        terr = self.uninterpreted(self.validate_against_higher_geo(sites))
        logger.debug('Matches terrestrial: {}'.format(self.names(terr)))
        marine = self.uninterpreted(self.validate_against_marine(sites))
        logger.debug('Matches marine: {}'.format(self.names(marine)))
        sites = terr + marine

        # Check againt very large features
        sites = self.uninterpreted(self.validate_against_large(sites))
        logger.debug('Intersects continent/ocean: {}'.format(self.names(sites)))

        # Make some eductaed guesses about how to interpret names if multiple
        sites = self.uninterpreted(self.disentangle_names(sites))
        logger.debug('Names disentangled: {}'.format(self.names(sites)))

        # Look for encompassed/encompassing relationships between sites. For
        # this round, a site must encompass/be encompassed by instances of
        # all other names to count.
        if len(sites) > 1:
            encompassed, encompassing = self.encompassed(sites)
            if not encompassing or not encompassed or encompassed == sites:
                encompassing, encompassed = self.encompassing(sites)
            if encompassing and encompassed and encompassed != sites:
                logger.debug('Found encompassing sites')
                self.interpret(encompassing, 'encompassing', True)
                others = [s for s in self.uninterpreted() if s not in encompassed]
                self.interpret(others, 'rejected (interpreted elsewhere)')
                return self.encompass(encompassed, max_dist_km=max_dist_km)

        # Return encompassing sites to the pool if no sites remain
        if not sites:
            sites = self.uninterpret(status='encompassing')

        # Ignore oceans and continents
        for site in self.active():
            if site.site_kind in {'CONT', 'OCN'}:
                self.interpret(site, 'very large', True)
        sites = self.uninterpreted(sites)
        logger.debug('Not continent or ocean: {}'.format(self.names(sites)))

        # Limit to mutually intersecting sites if possible. If a large
        # number of distinct names are found, the intersection is still
        # considered valid if one name cannot be reconciled. Repeat on
        # the high-graded list to catch sites that are only connected by
        # some huge feature like an ocean.
        candidates = sites + self.interpreted_as('very large')
        sites = self.uninterpreted(self.find_intersecting(candidates))
        sites = self.uninterpreted(self.find_intersecting(sites, None))
        logger.debug('Intersecting: {}'.format(self.names(sites)))
        sites = self.uninterpreted(self.discard_outliers(sites))

        # Examine parsed locality strings
        logger.debug('Examining parsed strings')
        parsers = (
            'BetweenParser',
            'DirectionParser',
            'ModifiedParser',
            'PLSSParser'
        )
        parsed = [s for s in sites if s.site_source in parsers]
        points = [s for s in sites if s.radius_km <= 10 and s not in parsed]
        for site in parsed:
            # Look for very specific localities (like PLSS)
            if site.site_source == 'PLSSParser':
                logger.debug('Matched PLSS coordinates')
                return self.select([site])
            # Look for directions corresponding to named localities
            for point in points:
                if site.distance_from(point) <= 20:
                    self.interpret(site, 'intersecting')
                    logger.debug('Matched vicinity')
                    return self.select([point])

        # Restrict large candidates to intersection with lowest admin polygon
        logger.debug('Restricting sites to lowest admin')
        restricted_to_admin = []
        for site in sites:
            try:
                restricted = site.restrict()
                restricted_to_admin.append(restricted)
            except ValueError as e:
                # Failure to map admin is a serious error--does anything
                # else trigger this?
                if str(e).startswith('Could not map admin names'):
                    raise
                logger.debug('Could not restrict: {}'.format(site))
                restricted_to_admin.append(site)
        sites = restricted_to_admin
        logger.debug('Restricted to admin: {}'.format(self.names(sites)))


        # Look for most specific names
        names = self.most_specific_names(sites)
        groups = self.group_by_name(sites)
        status = 'intersecting' if self.intersecting else 'less specific'
        specific = []
        for name, group in groups.items():
            if len(group) > 5:
                admin_in = self.centroid_inside_admin(group)
                admin_out = [s for s in sites if s not in admin_in]
                if admin_out:
                    logger.debug('Centroids outside admin')
                    status = 'rejected (disjoint on higher geo)'
                    self.interpret(admin_out, status)
                group = admin_in
            if name in names:
                specific.extend(group)
            else:
                self.interpret(group, status)

        # Empty specific if all features there are larger than an admin div
        try:
            enc = self.interpreted_as({'admin', 'encompassing'})
            min_encompassing = min([s.radius_km for s in enc])
            min_radius = min([s.radius_km for s in specific])
            #enc[0].draw(enc[1:])
            if min_encompassing < min_radius:
                self.interpret(specific, status)
                # Reset groups
                names = []
                groups = {}
                specific = []
        except ValueError:
            pass

        # Log basic info before trying to select the best match
        mask = 'Matched {} sites across {} names'
        logger.debug(mask.format(len(specific), len(names)))

        # Exactly one small, specific site found
        if len(specific) == 1 and specific[0].radius_km < max_dist_km:
            logger.debug('Matched most specific site')
            return self.select(specific)

        # One specific name found, but multiple sites match that name
        if len(names) == 1 and len(specific) > 1:
            geom, valid = self.encompass_name(specific)
            if valid:
                logger.debug('Matched multiple instances of one name')
                # The encompass_name method can toss sites from the list, so
                # limit sites being selected to those that are uninterpreted
                return self.select(self.uninterpreted(specific), geom)

            # Limit results to populated places
            cities = self.find_major_cities(specific)
            if cities:
                geom, valid = self.encompass_name(cities)
                if valid:
                    logger.debug('Matched cities matching one name')
                    others = [s for s in specific if s not in cities]
                    if all([re.match(r'^PPL[AC]', s.site_kind) for s in cities]):
                        msg = 'excluded all features except capital cities'
                    else:
                        msg = 'excluded all features except populated places'
                    self.explain(others, msg)
                    self.interpret(others, 'rejected (interpreted elsewhere)')
                    return self.select(self.uninterpreted(cities), geom)
                mask = 'Could not encompass name {} (radius={:.2f} km)'
                logger.debug(mask.format(names[0], geom.radius_km))

        # Multiple names of similar specificity found
        if len(names) > 1:
            geom, selected = self.most_specific_combination(specific)
            if geom.radius_km <= max_dist_km:
                logger.debug('Matched most specific combination')
                # Mark sites that were not selected as ignored
                ignored = [s for s in specific if s not in selected]
                self.interpret(ignored, 'rejected (interpreted elsewhere)')
                return self.select(selected, geom)
            mask = 'Could not encompass names {} (radius={:.2f} km)'
            logger.debug(mask.format(names, geom.radius_km))

        # Check for marine sites. Combinations of terrestrial and marine
        # features are excluded from certain checks.
        admin = self.interpreted_as({'admin', 'encompassing'})
        active = [s for s in self.active() if s not in admin and s.site_kind != 'CONT']
        terr, marine = self.split_land_sea(active)
        if bool(admin or terr) != bool(marine):

            # Disregard stream-like features with point geometries. Streams
            # vary widely in size and because they are linear fare poorly
            # with the radius estimates used here.
            streams = []
            for site in specific:
                if site.site_kind in CODES_RIVERS and site.geom_type == 'Point':
                    streams.append(site)
            if streams:
                self.interpret(streams, 'less specific')
                specific = self.uninterpreted(specific)

            # Relax max distance if a site meets certain criteria. To start
            # with, try falling back to the smallest specific feature.
            if len(specific) == 1:
                logger.debug('Matched most specific feature (fallback)')
                return self.select(specific)

            # Fall back to simple combinations (one site per name)
            if len(self.find_combinations(specific)) == 1:
                geom, _ = self.most_specific_combination(specific)
                logger.debug('Matched most specific combination (fallback)')
                return self.select(specific, geom)

        # If zero or multple terrestrial sites, use the smallest admin instead
        if admin and len(terr) != 1:
            admin.sort(key=lambda s: s.radius_km)
            self.interpret(self.uninterpreted(terr), 'rejected (not reconciled)')
            terr = [admin[0]]

        # Fall back to combination of terrestrial and marine sites
        if terr:
            extended = self.extend_into_ocean(terr[0].geometry)
            if (
                marine
                and extended.area < terr[0].area
                and extended.radius_km <= max_dist_km
            ):
                logger.debug('Matched combination of marine and'
                             ' terrestial features')
                self.interpret(marine, 'less specific')
                return self.select(terr, extend_into_ocean=True)

            # Fall back to intersection of large features with admin
            if terr and self.smallest_encompassing:
                field, polygon = self.smallest_encompassing
                for site in sorted(terr, key=lambda s: -s.radius_km):
                    geom = self.constrain(site.geometry, polygon, field)
                    if (geom.radius_km <= max_dist_km * 5
                        and geom.radius_km < polygon.radius_km):
                            logger.debug('Matched combination of'
                                         ' terrestial features')
                            self.interpret(self.sites, 'more specific')
                            return self.select([site], geom)

        # Fall back to smallest encompassing feature
        try:
            enc = self.most_specific_sites(self.interpreted_as({'admin', 'encompassing'}))
            geom = self.encompass_sites(enc)
            if geom.radius_km <= max_dist_km * 5:
                self.interpret(self.sites, 'more specific')
                logger.debug('Matched encompassing feature (fallback)')
                return self.select(enc, geom)
        except (IndexError, ValueError):
            pass

        # Fall back to admin divisions as a last resort. This fallback is
        # subject to max_dist_km unless there is no info in the record
        # besides admin divisions.
        if not marine:
            self.interpret(self.uninterpreted(), 'rejected (not reconciled)')
            fields = ('county', 'state_province', 'country')
            # First check for minor admin divisions
            admin = [s for s in admin if s.field not in fields]
            if admin:
                admin.sort(key=lambda s: s.radius_km)
                geom = admin[0].geometry
                if geom.radius_km < max_dist_km:
                    logger.debug('Matched minor admin division (fallback)')
                    return self.select([admin[0]], geom)
            # Failing that, fall back to major admin divisions
            polygons = self.site.get_admin_polygons()
            for field in fields:
                try:
                    admin = [k for k, v in self.interpreted.items() if v == 'admin']
                    sites = [s for s in self.expand(admin) if s.field == field]
                    # The calculated admin polygons are padded, so use the site
                    # polygon if there is only one site for the given field
                    geom = sites[0].geometry if len(sites) == 1 else polygons[field]
                    if (geom.radius_km <= max_dist_km
                        or geom.radius_km < 1000 and self.site.is_marine()):
                            logger.debug('Matched major admin division (fallback)')
                            return self.select(sites, geom)
                except KeyError:
                    pass
        # Estimate best possible uncertainty and re-run
        estimated = self.estimate_minimum_uncertainty()
        if estimated > max_dist_km:
            self.reset()
            logger.debug('Retrying with radius={} km'.format(estimated))
            return self.encompass(max_dist_km=estimated)
        mask = 'Could not encompass sites within {} km'
        logger.debug(mask.format(max_dist_km))
        raise ValueError(mask.format(max_dist_km))


    def select(self, sites, geom=None, extend_into_ocean=False):
        """Select sites and compute geometry"""
        assert isinstance(sites, (list, tuple)), 'sites must be list-like'
        self.interpret(sites, 'selected')
        for site in sites:
            self.sources.extend(site.sources)
        self.sources = sorted(set(self.sources))
        if geom is None:
            geom = sites[0].geometry

        # Constrain selection based on administrative info. This can help
        # reduce the uncertainty associated with large areas (like gulfs
        # or regions) but can move the centroid of a point significantly,
        # especially if only limited admin info is provided. Note that this
        # block will not fire for very large features that are discarded
        # earlier on.
        polygons = self.site.get_admin_polygons()
        admin = ('county', 'state_province', 'country')
        for field in admin:
            admin = getattr(self.site, field)
            if admin and field not in {s.field for s in sites}:
                geom = self.constrain(geom, polygons[field], field)

        # Extend polygon into ocean
        if extend_into_ocean or self.site.is_marine():
            try:
                geom = self.extend_into_ocean(geom)
            except ValueError:
                pass

        # Flag anything that hasn't been handled as unreconciled
        self.interpret(self.uninterpreted(), 'rejected (not reconciled)')
        self.geometry = geom

        # Summarize selection
        if False:
            import pprint as pp
            pp.pprint(sorted([self.key(s) for s in self._sites]))
            pp.pprint(self.interpreted)
            self.geometry.draw([self.geometry.centroid] + self._sites)
        return geom


    def constrain(self, geom, other, field, name=None):
        """Constrains geometry to intersection with another geometry"""
        if other.radius_km > 4 * geom.radius_km:
            return geom
        try:
            xtn = geom.intersection(other)
            if name:
                logging.debug('Checking intersection with {}'.format(name))
            # Do not constrain small features on the edges of large polygons
            if xtn.area / geom.area > 0.1:
                # Constrain to all sites matched on field
                sites_ = [s for s in self._sites if s.field == field]
                self.interpret(sites_, 'constrained')
                return xtn
        except KeyError:
            pass
        except (TypeError, ValueError):
            # Capture failed intersections. Not necessarily an error
            # because directions, etc. might fall outside of the
            # specified political geography
            logger.warning('Could not constrain to {}'.format(name))
        return geom


    def disentangle_names(self, sites=None, aggressive=True):
        """Evaluates likely matches for names that match more than one site

        This function is one source of the "best match" for names corresponding to
        multiple sites in MatchAnnotator. The best match will be a town/city, if present.
        Failing that, the best match is anything that isn't classified by GeoNames as
        a spot.
        """
        if sites is None:
            sites = self.sites[:]
        for name, group in self.group_by_name(sites).items():
            # Check for mutually intersecting groups
            if len(group) > 1 and group[0].intersects_all(group[1:]):
                # Prefer encompassing
                codes = set(CODES_ADMIN + CODES_ISLANDS)
                enc = [s for s in group if s.site_kind in codes]
                if enc:
                    others = [s for s in group if s.site_kind not in codes]
                    self.explain(others, ('excluded all features except'
                                          ' admin divisions and islands'))
                    self.interpret(others, 'rejected (interpreted elsewhere)')
                    continue
                # Prefer populated places
                places = [s for s in group if s.site_class == 'P']
                if places:
                    others = [s for s in group if s.site_class != 'P']
                    self.explain(others, ('excluded all features except'
                                          ' populated places'))
                    self.interpret(others, 'rejected (interpreted elsewhere)')
                    continue
                # Discard building and spot names
                places = [s for s in group if s.site_class != 'S']
                if places and places != sites:
                    others = [s for s in group if s.site_class == 'S']
                    self.explain(others, 'excluded buildings and spots')
                    self.interpret(others, 'rejected (interpreted elsewhere)')
                    continue
            elif len(group) > 1:
                mask = 'Sites matching "{}" are not mutually intersecting'
                logger.debug(mask.format(group[0].filter['name']))
        return self.uninterpreted(sites)


    def find_major_cities(self, sites=None):
        """Finds cities in a list of sites, preferring capitals if they exist"""
        if sites is None:
            sites = self.sites[:]
        capitals = [s for s in sites if re.match(r'^PPL[AC]', s.site_kind)]
        if capitals:
            return capitals
        return [s for s in sites if s.site_class == 'P']


    def extend_into_ocean(self, geom):
        """Extends polygon into ocean"""
        # Verify that there is at least one active terrestrial feature
        terr, marine = self.split_land_sea(self.active())
        marine = [m for m in marine if m not in self.interpreted_as('selected')]
        if terr and marine:
            logger.debug('Extending polygon into ocean')
            marine.sort(key=lambda s: s.radius_km)
            # Separate oceans from other marine localities
            oceans = [s for s in marine if s.site_kind == 'OCN']
            ocean = oceans[0].name if oceans else None
            # Resize the base geometry. If the resize fails, return the
            # original geometry immediately so the function doesn't incorrectly
            # report that the result is constrained to the ocean/sea
            resized = geom.resize(RESIZE, min_diff_km=CONT_SHELF_WIDTH_KM)
            if geom == resized:
                logger.debug('Resize failed: {:.1f} km'.format(geom.radius_km))
                return geom
            # Map intersection of geometry with ocean
            tiles = self.ocean.query(resized, ocean=ocean)
            if tiles:
                # Get intersection of proposed geometry with the world ocean
                shape = self.adjacent(tiles)
                geom = resized.intersection(shape)

                # Limit to smaller named water body possible
                for wtr_body in [s for s in marine if s.site_kind != 'OCN']:
                    try:
                        xtn = geom.intersection(wtr_body.resize(RESIZE))
                        diff_km = abs(round(xtn.radius_km, 1) - round(geom.radius_km, 1))
                        if diff_km / geom.radius_km > 0.1:
                            geom = xtn
                            self.interpret(wtr_body, 'constrained')
                        else:
                            self.interpret(wtr_body, 'intersecting')
                        break
                    except ValueError:
                        pass
                else:
                    # If no smaller water bodies exist or if none intersect
                    # the proposed geometry, fallback to the ocean
                    diff_km = abs(round(geom.radius_km, 1) - round(resized.radius_km, 1))
                    if diff_km / geom.radius_km > 0.1:
                        self.interpret(oceans, 'constrained')
                    else:
                        self.interpret(oceans, 'intersecting')
                # FIXME: Fails with combinations of marine features
                #geom = geom.difference(orig)
        return geom


    def dedupe(self, sites=None):
        """Removes duplicate sites and geometries"""
        logger.debug('Deduping site list')
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        sites.sort(key=lambda s: s.location_id)
        # FIXME: Added to fix a bug where sites repeat at end of list,
        #        but not clear where the repeats are coming from.
        sites = [s for i, s in enumerate(sites) if s not in sites[:i]]
        # Removes sites with duplicate geometries
        distinct = []
        for site in sites:
            for other in distinct:
                if site.geometry.almost_equals(other, 2):
                    #site.geometry.draw([other], site.name)
                    self.interpret(site, 'rejected (duplicate)')
                    break
            else:
                distinct.append(site)
        return distinct


    def ignore_related(self, sites=None):
        """Removes sites appearing in related_sites in of other sites

        For example, if the direction "1 km N of Ellensburg" is found, sites
        matching Ellensburg itself will be discarded.
        """
        logger.debug('Ignoring related sites')
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        related = []
        for site in sites:
            related.extend([s.location_id for s in site.related_sites])
        distinct = []
        for site in sites:
            if site.location_id in related:
                self.interpret(site, 'rejected (interpreted elsewhere)')
            else:
                distinct.append(site)
        return distinct


    def matches_admin(self, site):
        """Tests whether site matches all admin in original record"""
        for name_field, code_field in [
            ('country', 'country_code'),
            ('state_province', 'admin_code_1'),
            ('county', 'admin_code_2')
        ]:
            if getattr(self.site, name_field) and site.filter[code_field] != 1:
                return False
        return True


    def validate_against_higher_geo(self, sites=None):
        """Looks for admin divisions and checks other terrestrial sites against them"""
        logger.debug('Finding and validating administrative divisions')
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        terr, marine = self.split_land_sea(sites)

        # Verify that sites overlap with the most specific administrative
        # division specified in the original record. This ensures that matches
        # from GeoNames aren't in the wrong hemisphere or something.
        polygons = self.site.get_admin_polygons()
        for field in ('county', 'state_province', 'country'):
            try:
                polygon = polygons[field].resize(RESIZE)
                break
            except KeyError:
                pass
        else:
            polygon = None
            in_bounds = sites

        if polygon is not None:
            # Look for more specific admin divisions in the site list
            admin = {}
            for site in terr:
                if self.field(site.field) not in polygons:
                    site_kind = site.site_kind.rstrip('H')
                    if re.match(r'ADM\d', site_kind) and site.intersects(polygon):
                        admin.setdefault(site_kind, []).append(site)

            # Set the admin level based on the most specific available polygon
            if field == 'county':
                start_index = 3
            elif field == 'state_province':
                start_index = 2
            else:
                start_index = 1

            for key in ['ADM{}'.format(i) for i in range(start_index, 7)]:
                try:
                    divs = admin[key]
                except KeyError:
                    # Chain must be continuous to reduce chance of bad matches
                    break
                poly = None
                if len(divs) == 1:
                    poly = divs[0].geometry
                elif divs and divs[0].intersects_all(divs[1:]):
                    poly = divs[0].geometry.combine([d.geometry for d in divs[1:]])
                # Use the more specific division
                if poly and polygon.intersects(poly):
                    polygon = poly
                    fields = {'ADM1': 'state_province', 'ADM2': 'county'}
                    try:
                        setattr(self.site, fields[key], admin[-1].name)
                    except KeyError:
                        pass
                    self.interpret(divs, 'admin', True)
                    terr = self.uninterpreted(terr)
                    field = key

            # Use encompassing polygons if well-formed and smaller than admins
            enc = []
            for site in self.interpreted_as('encompassing'):
                if (site.geom_type != 'Point'
                    and site.radius_km < polygon.radius_km):
                        enc.append(site)
            if enc:
                enc.sort(key=lambda s: s.radius_km)
                polygon = enc[0].geometry.resize(RESIZE)
                field = enc[0].field

            # If single island found, use it to refine the reference polygon
            islands = []
            for site in terr:
                if ((site.field == 'island' or site.site_kind.startswith('ISL'))
                    and site.intersects(polygon)
                    and site.radius_km < polygon.radius_km):
                        islands.append(site)
            if len(islands) == 1 and islands[0].geom_type != 'Point':
                field = 'island'
                polygon = polygon.intersection(islands[0]).resize(RESIZE)
                #self.interpret(islands[0], 'encompassing', True)
                #terr = [s for s in terr if s != islands[0]]

            self.smallest_encompassing = (field, polygon)

            # Check which sites occur within the given divisions
            logger.debug('Testing intersection with {}'.format(field))
            in_bounds = []
            for site in terr + marine:
                # Test political geography against both primary and related
                # sites to account for directions, etc. where the base site is
                # within bound but the direction is not.
                for site_ in [site] + site.related_sites:
                    if site_.centroid.intersects(polygon):
                        in_bounds.append(site_)
                        self.admin_match_type[site_.location_id] = 'centroid'
                        break
                    if site_.hull.resize(RESIZE).intersects(polygon):
                        in_bounds.append(site_)
                        self.admin_match_type[site_.location_id] = 'polygon'
                        break
                    if (site_.location_id.isnumeric()
                        and field in {'country', 'state_province', 'county'}
                        and self.matches_admin(site_)):
                            in_bounds.append(site_)
                            self.admin_match_type[site_.location_id] = 'centroid'
                            break
                else:
                    # Marine sites are also checked further elsewhere, so
                    # they aren't rejected here. The conditional checks both
                    # the marine container and the is_marine() method becuase
                    # the methods diverge if the reference site does not
                    # contain a sea or ocean.
                    if not marine or not site.is_marine():
                        #site.draw(polygon, title=site.summarize())
                        mask = '"{}" does not intersect the specified {}'
                        logger.debug(mask.format(site.summarize(), field))
                        self.interpret(site, 'rejected (disjoint on higher geo)')

        # Extract and interpret admin divisions
        for site in in_bounds:
            if site.field is None:
                mask = 'Field attribute missing (from_cache={}): {}'
                try:
                    from_cache = site.from_cache
                except AttributeError:
                    from_cache = False
                logger.warning(mask.format(from_cache, site))
                site.field = 'locality'

        plain = [s for s in in_bounds if s.field[-1].isalpha()]
        numbered = [s for s in in_bounds if s.field[-1].isnumeric()]
        for group in [plain, numbered]:
            for site in self.uninterpreted(group):
                field = self.field(site.field)
                if field in {'country', 'state_province', 'county'}:
                    self.interpret(site, 'admin', True)

        return in_bounds


    def validate_against_marine(self, sites=None):
        """Validate marine sites against each other"""
        terr, marine = self.split_land_sea()
        if not marine:
            return []
        # Check that marine sites fall within or near larger marine sites
        marine.sort(key=lambda s: -s.radius_km)
        last_parent = None
        in_bounds = []
        for site in marine:
            # The largest body of water is in-bounds by default
            if not in_bounds:
                in_bounds.append(site)
                last_parent = site
                continue

            if site.intersects(in_bounds[-1]):
                in_bounds.append(site)
                last_parent = site.resize(RESIZE)
            elif site.intersects(last_parent):
                in_bounds.append(site)
                last_parent = site.resize(RESIZE)
            else:
                mask = '"{}" does not intersect {}'
                logger.debug(mask.format(site.summarize(), in_bounds[-1].name))
                self.interpret(site, 'rejected (disjoint on higher geo)')
        # Check that terrestrial localities are in the ballpark of at
        # least one valid marine feature if original site is marine
        marine = sorted(self.uninterpreted(marine), key=lambda s: -s.radius_km)
        try_hull = marine[0].site_kind != 'OCN'
        for site in terr:
            if not site.intersects(marine[0], try_hull=try_hull):
                mask = '"{}" does not intersect {}'
                logger.debug(mask.format(site.summarize(), marine[0].name))
                self.interpret(site, 'rejected (disjoint on higher geo)')
        # Interpret large bodies, like oceans, if more specific features found
        if len(in_bounds) > 1:
            ref_km = in_bounds[-1].radius_km * 2
            specific = [s for s in in_bounds if s.radius_km <= ref_km]
            marine = [s for s in in_bounds if s not in specific]
            self.interpret(marine, 'very large')
            return specific
        return in_bounds


    def validate_against_large(self, sites=None):
        """Verifies that site or admin intersects mentioned continent/ocean"""
        sites = self.active(sites)
        # Skip continent if country is known
        codes = {'CONT', 'OCN'} if not self.site.country_code else {'OCN'}
        valid = self.validate_against_code(codes, sites=sites)
        # Test disjoint features against seas, which are sometimes more
        # useful than oceans near shore.
        disjoint = [s for s in sites if s not in valid]
        if disjoint:
            valid = self.validate_against_code({'SEA', 'GULF'}, sites=disjoint)
            self.uninterpret(sites=valid)
        return self.active()


    def validate_against_code(self, codes, sites=None, fallback=None):
        """Validates sites against active"""
        if sites is None:
            sites = self.sites[:]
        disjoint = []
        for ref_site in [s for s in self.active() if s.site_kind in codes]:
            geom = ref_site.geometry.hull
            for site in sites:
                if not site.intersects(geom):
                    try:
                        admin = site.get_admin_polygons().get(fallback)
                        if not admin or not admin.intersects(geom):
                            disjoint.append(site)
                    except ValueError as e:
                        # Error nesting site admin polygons
                        logger.error(str(e), exc_info=e)
        if disjoint:
            logger.debug('Disjoint on {}'.format(codes))
            self.interpret(disjoint, 'rejected (disjoint)')
        return [s for s in sites if s not in disjoint]


    def split_land_sea(self, sites=None):
        """Splits list into marine and terrestrial sites"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        # Marine features recognized only if ocean/sea given
        marine = []
        if self.site.ocean or self.site.sea_gulf:
            codes = set(CODES_MARINE + CODES_SHORES + CODES_UNDERSEA)
            marine = [s for s in sites if s.site_kind in codes]
        terrestrial = [s for s in sites if s not in marine]
        return terrestrial, marine


    def split_area_linear(self, sites=None):
        """Splits list into area/point and linear sites"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        # Marine features recognized only if ocean/sea given
        areas = [s for s in sites if s.site_kind not in CODES_RIVERS]
        linear = [s for s in sites if s.site_kind in CODES_RIVERS]
        return areas, linear


    def most_specific_names(self, sites=None):
        """Finds names with the smallest sites attached to them"""
        logger.debug('Finding most specific names')
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        groups = self.group_by_name(sites)
        names = []
        sizes = []
        for name, group in groups.items():
            size_range = [s.radius_km for s in group]
            sizes.append([name, min(size_range), max(size_range)])
            # Include directions even if they're large
            if group[0].site_source == 'DirectionParser':
                names.append(name)
        # Use a multiplier and a minimum size so we're not too stingy
        min_size = min([s[1] for s in sizes]) * 1.5 if sizes else 0
        if min_size < 10:
            min_size = 10
        names.extend([s[0] for s in sizes if s[1] <= min_size])
        return sorted(set(names))


    def most_specific_sites(self, sites=None):
        """Finds sites associated with the most specific names"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        names = self.most_specific_names(sites)
        return [s for s in sites if self.key(s) in names]


    def most_specific_combination(self, sites=None):
        """Selects combination including each name with smallest radius"""
        logger.debug('Finding the most specific combination of sites')
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        combinations = []
        for group in self.find_combinations(sites):
            geom = self.encompass_sites(group)
            combinations.append((geom, group))
        combinations.sort(key=lambda c: c[0].radius_km)
        geom, selected = combinations[0]
        return geom, selected


    def missed(self):
        """Identifies terms that were not matched"""
        missed = {}
        for result in self.results:
            for term in result.terms_checked - result.terms_matched:
                missed.setdefault(term, []).append(result.field)
        countries = {s.country for s in self._sites}
        # Add related sites to matched
        matched = list(self.terms_matched)
        for site in self.active():
            matched.extend([s.name for s in site.related_sites])
        missed = {k: v[0] for k, v in missed.items()
                  if k not in countries | set(matched)}
        terms = ['{}="{}"'.format(v, k.strip('"')) for k, v in missed.items()]
        return sorted(set(terms))


    def encompass_sites(self, sites=None):
        """Encompassses a list of sites"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        if len(sites) == 1:
            return sites[0].geometry
        # Flatten group dict to a list of sites
        if isinstance(sites, dict):
            sitelist = []
            for group in sites.values():
                sitelist.extend(group)
            sites = sitelist
        geoms = [s.geometry for s in self.expand(sites)]
        if len(geoms) == 1:
            return geoms[0]
        geoms = geoms[0].normalize(geoms[1:])
        return GeoMetry(GeometryCollection(geoms).convex_hull)


    def encompass_name(self, sites, max_dist_km=100):
        """Encompasses one name matching multiple sites"""
        logger.debug('Encompassing multiple sites matching one name')
        geom = self.encompass_sites(sites)
        if geom.radius_km < max_dist_km:
            return geom, True
        # Radius is larger than max, but might still be the best possible.
        # Keep best polygon if the calculated geometry is within 20% of the
        # estimate of the best possible radius for this group of sites.
        max_radius = max([s.radius_km for s in sites])
        if geom.radius_km / max_radius <= 1.2:
            # Return the largest polygon if it has similar radius to max
            polygons = [s for s in sites if s.geom_type != 'Point']
            polygons = [s for s in polygons if s.radius_km > max_radius * 0.9]
            if polygons:
                polygons.sort(key=lambda s: s.radius_km)
                return polygons[-1].geometry, True
            return geom, True
        return geom, False


    def encompass_combinations(self, sites=None):
        """Selects combination including each name with smallest radius"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        combinations = []
        for group in self.find_combinations(sites):
            encompassed, encompassing = self.encompassed(group)
            if encompassed:
                combinations.append((encompassed, encompassing))
        if len(combinations) == 1:
            return combinations[0]


    def map_relationships(self, sites=None):
        """Maps encompassing/encompassed relationships between sites"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        rel = {s.location_id: {'parents': [], 'children': []} for s in sites}
        for i, site in enumerate(sites):
            for other in sites[(i + 1):]:
                overlaps = site.overlap(other, percent=True) > 0.8
                if overlaps and site.radius_km > other.radius_km:
                    rel[other.location_id]['parents'].append(site.location_id)
                    rel[site.location_id]['children'].append(other.location_id)
                # Check if other contains site
                elif overlaps and other.radius_km > site.radius_km:
                    rel[site.location_id]['parents'].append(other.location_id)
                    rel[other.location_id]['children'].append(site.location_id)
        return rel


    def find_intersecting(self, sites=None, allow_miss=4):
        """Limits to mutually intersecting sites"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        groups = self.group_by_name(sites)
        misses = 0 if allow_miss is None or len(groups) < allow_miss else 1
        if len(groups) > 1:
            intersections = {}
            for i, site in enumerate(sites):
                sid = site.location_id
                intersections.setdefault(sid, []).append(sid)
                for other in sites[i + 1:]:
                    if site.resize(RESIZE).intersects(other.resize(RESIZE)):
                        oid = other.location_id
                        intersections.setdefault(sid, []).append(oid)
                        intersections.setdefault(oid, []).append(sid)
            # Group each result by how many names it matches
            matched = {}
            for group in intersections.values():
                names = self.names(group)
                matched.setdefault(len(set(names)), []).extend(group)
            matched = {k: set(v) for k, v in matched.items()}
            # Look for strong matches
            if matched and max(matched) >= (len(groups) - misses):
                self.intersecting = True
                strong = self.expand(list(matched[max(matched)]))
                # Reinterpret intersecting sites
                xing = [s for s in strong if s.location_id in self.interpreted]
                self.interpret(xing, 'intersecting')
                # Note disjoint sites
                rejected = [s for s in sites if s not in strong]
                if rejected:
                    logger.debug('Disjoint on mutual intersection')
                    self.interpret(rejected, 'rejected (disjoint)')
                # Interpret any site in strong that matches all intersecting
                # sites as intersecting and redo the intersection calculation
                loc_ids = {s.location_id for s in strong}
                if len(loc_ids) > 2:
                    for site in sorted(strong, key=lambda s: -s.radius_km):
                        key = site.location_id
                        vals = intersections[key]
                        if set([key] + vals) == loc_ids:
                            loc = '{} ({})'.format(site.name, site.location_id)
                            logger.debug('{} intersects all sites'.format(loc))
                            self.interpret(site, 'intersecting')
                            uninterpreted = self.uninterpreted(strong)
                            return self.find_intersecting(uninterpreted)
                return strong
        return sites


    def discard_outliers(self, sites=None):
        """Discards outlying sites"""
        if sites is None:
            sites = self.sites
        if len(sites) > 1 and len({self.key(s) for s in sites}) > 1:
            radii = {}
            dists = {}
            for i, site in enumerate(sites):
                radii[site.location_id] = site.radius_km
                others = [s for s in sites[i + 1:]
                          if self.key(s) != self.key(site)]
                for other in others:
                    dist_km = site.dist_km(other)
                    dists.setdefault(site.location_id, []).append(dist_km)
                    dists.setdefault(other.location_id, []).append(dist_km)
            outliers = []
            for loc_id, radius in radii.items():
                dist = 5 * radius
                if min(dists[loc_id]) > (dist if dist >= 25 else 25):
                    outliers.append(loc_id)
            inliers = [loc for loc in radii if loc not in outliers]
            # If no inliers remain (i.e., there are no nearby sites), return
            # the original site list
            if not inliers:
                return sites
            # Otherwise reject the outliers and return the rest
            self.interpret(self.expand(outliers), 'rejected (outlier)')
            return self.expand(inliers)
        return sites


    def find_related(self, key, sites=None):
        """Finds sites encompased by instances of all other names"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        rel = self.map_relationships(sites)
        all_names = sorted({self.key(s) for s in sites})
        target = []
        related = []
        for site, others in rel.items():
            site = self.expand(site)
            others = self.expand(others[key])
            # Get list of all possible names
            names = {n for n in all_names if n != self.key(site)}
            # Get list of related names from others
            other_names = {self.key(s) for s in others}
            # Test if all names are accounted for in other_names
            if names and not names - other_names:
                target.append(site)
                related.extend(others)
        return target, related


    def encompassed(self, sites=None):
        """Finds sites encompassing instances of all other names"""
        logger.debug('Checking for encompassed')
        encompassed, encompassing = self.find_related('parents', sites)
        # Exclude linear features from encompassing
        encompassing, linear = self.split_area_linear(encompassing)
        if encompassing and linear:
            encompassed.extend(linear)
        return encompassed, encompassing


    def encompassing(self, sites=None):
        """Finds sites encompassing instances of all other names"""
        logger.debug('Checking for encompassing')
        encompassing, encompassed = self.find_related('children', sites)
        # Exclude linear features from encompassing
        encompassing, linear = self.split_area_linear(encompassing)
        if encompassing and linear:
            encompassed.extend(linear)
        return encompassing, encompassed


    def group_by_name(self, sites=None):
        """Groups sites by the term they matched on"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        groups = {}
        for site in sites:
            groups.setdefault(self.key(site), []).append(site)
        # Log names with many matches
        for name, group in groups.items():
            if len(group) >= 10:
                logger.debug('{} matches {} records'.format(name, len(group)))
        return groups


    def find_combinations(self, sites=None):
        """Creates combinations of sites grouped by name"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        groups = list(self.group_by_name(sites).values())
        if len(groups) > 1:
            groups = list(itertools.product(*groups))
            # Remove combinations that include duplicates
            nums = [[s.location_id for s in grp] for grp in groups]
            indexes = []
            for i, grp in enumerate(nums):
                if len(grp) != len(set(grp)) or grp in nums[:i]:
                    indexes.append(i)
            for i in sorted(indexes)[::-1]:
                del groups[i]
            return groups
        return []


    def interpret(self, sites, status, reject_similar=False):
        """Assigns an interpretation to a list of sites"""
        if status not in STATUSES:
            raise KeyError('Invalid status: {}'.format(status))
        if not isinstance(sites, (list, tuple)):
            sites = [sites]
        for site in sites:
            mask = 'Interpreted {} ({}) as {}'
            logger.debug(mask.format(site.name, site.location_id, status))
            self.interpreted[site.location_id] = status
        # Reject sites with same field:name as those interpreted here
        if reject_similar:
            self.reject_interpreted(self.uninterpreted(),
                                    sites,
                                    interpretation=status)


    def interpreted_as(self, statuses):
        """Returns list of sites interpreted with the given status"""
        statuses = as_set(statuses)
        for status in statuses:
            if status not in STATUSES:
                raise KeyError('Invalid status: {}'.format(status))
        sites = [n for n, s in self.interpreted.items() if s in statuses]
        return self.expand(sites)


    def uninterpret(self, sites=None, status=None):
        """Deletes interpretations and returns that list of sites"""
        assert sites is not None or status is not None
        if status:
            sites = self.interpreted_as(status)
        sites = self.expand(sites)
        for site in sites:
            del self.interpreted[site.location_id]
        return sites


    def explain(self, sites, explanation):
        """Assigns a keyword explanation"""
        for site in self.expand(sites):
            logger.debug('{}: {}'.format(explanation, site.summarize()))
            self.multiples.setdefault(site.filter['name'], []).append(explanation)
            for rel in site.related_sites:
                self.multiples.setdefault(rel.filter['name'], []).append(explanation)


    def active(self, sites=None, include_selected=True):
        """Returns list of unrejected sites

        In contrast to the list returned by self.uninterpreted(), this list
        includes sites that have been interpreted but not rejected (for
        example, admin divisions).
        """
        active = [s.location_id for s in self.uninterpreted()]
        ignore = REJECTED
        if not include_selected:
            ignore = list(ignore) + ['selected']
        interpreted = self.interpreted.items()
        active.extend([s for s, st in interpreted if st not in ignore])
        # Limit to intersection with sites list if given
        if sites is not None:
            active = [s for s in sites if s.location_id in active]
        return self.expand(active)


    def uninterpreted(self, sites=None):
        """Returns list of uninterpreted sites"""
        if sites is None:
            sites = self._sites[:]
        return [s for s in sites if s.location_id not in self.interpreted]


    def inactive(self, sites=None):
        """Returns list of rejected sites"""
        if sites is None:
            sites = self._sites[:]  # uses all sites, not just the active ones
        return [s for s in sites if s not in self.active()]


    def ignored(self):
        """Returns a list of names that have been rejected"""
        statuses = {}
        for key, status in self.interpreted.items():
            site = self.expand(key)
            statuses.setdefault(self.key(site), []).append(status)
        ignored = []
        for key, statuses in statuses.items():
            statuses = set(statuses)
            if (not statuses - REJECTED
                and statuses != {'rejected (interpreted elsewhere)'}):
                    ignored.append(key)
        return [s.split(':', 1)[1] for s in ignored]


    def reject_interpreted(self, sites=None, interpreted=None,
                           status='rejected (interpreted elsewhere)',
                           interpretation=None):
        """Finds and rejects sites similar to those in the given site list"""
        if sites is None:
            sites = self.uninterpreted()
        if interpreted is None:
            interpreted = self.interpreted

        # Use a special status for names that overlap with admin. This
        # prevents rejected sites from showing up in the description.
        if interpretation == 'admin':
            status = 'rejected (interpreted as admin)'

        # Ignore matches from locality if name occurs specifically elsewhere
        keys = [self.key(s) for s in interpreted]
        keys.extend(['locality:{}'.format(k.split(':')[-1]) for k in keys])
        rejectees = [s for s in sites if self.key(s) in set(keys)]
        self.interpret(rejectees, status)

        # Explain interpretation if given
        if interpretation in {'admin', 'encompassing'}:
            self.explain(rejectees, 'used the largest encompassing feature')



    def append(self, result):
        """Appends a result to the results list"""
        self.results.append(result)
        self.update_lists()


    def extend(self, results):
        """Appends multiple results to the results list"""
        self.results.extend(results)
        self.update_lists()


    def expand(self, sites):
        """Expands a site or list of sites"""
        expanded = []
        for site in sites if isinstance(sites, (dict, list, set)) else [sites]:
            if isinstance(site, str):
                site = self.lookup[site]
            expanded.append(site)
        return expanded if isinstance(sites, (dict, list)) else expanded[0]


    def names(self, sites):
        """Gets keys for list of sites"""
        return [self.key(s) for s in self.expand(sites)]


    def update_lists(self):
        """Compiles lists of terms checked and matched"""
        sites = []
        terms_checked = []
        terms_matched = []
        if self.results:
            for i, result in enumerate(self.results):
                # Convert a list of sites to a simple MatchResult
                if not isinstance(result, MatchResult):
                    result = MatchResult(result, None, [], [])
                    self.results[i] = result
                # Check for sites attribute used by Georeference class
                if result.sites is not None:
                    for site in result.sites:
                        site.field = result.field
                        sites.append(site)
                terms_checked.extend(result.terms_checked)
                terms_matched.extend(result.terms_matched)
        self.sites = sites
        self.terms_checked = set(terms_checked)
        self.terms_matched = set(terms_matched)


    def estimate_minimum_uncertainty(self):
        """Estimates the minimum uncertainty expected for a given site"""
        sites = self.active()
        terr, marine = self.split_land_sea(sites)
        # Estimate the minimum radius for each group of active matches
        radii = []
        for name, group in self.group_by_name(self.expand(sites)).items():
            # If marine sites are found, increase terrestrial radii to
            # account for changes made by extend_into_ocean
            if marine:
                dist_km = CONFIG.routines.georeferencing.params.dist_km_to_extend_sites_offshore
                radii = [s.radius_km for s in group if s in marine]
                radii.extend([s.radius_km + dist_km for s in group if s in terr])
                radius = min(radii)
            else:
                radius = min([s.radius_km for s in group])
            # FIXME: Offshore localities are not fully calculated until late
            if name.startswith('Off '):
                radius += 100
            radii.append(radius)
        # Estimate the minimum radius for each field with unmatched data
        rejected = [k.split(':')[0] for k in self.names(self.inactive())]
        missed = [k.split('=')[0] for k in self.missed()]
        for field in set(missed + rejected + list(self.leftovers)):
            radii.append(CONFIG.min_size(field))
        # No radii means the encompass failed, but must return int anyway
        if not radii:
            logger.warning('Unable to estimate a minimum uncertainty')
            return 1000
        return min(radii)


    def centroid_inside_admin(self, sites=None):
        """Finds sites whose centroid falls into the lowest admin division"""
        if sites is None or sites == self.sites:
            sites = self.sites[:]
        return [s for s in sites if self.admin_match_type.get(s.location_id) == 'centroid']


    @staticmethod
    def adjacent(shapes):
        """Calculates the union the largest set of intersecting shapes"""
        tree = STRtree(shapes)
        neighbors = []
        for shape in shapes:
            neighbors.append(tree.query(shape))
        # Use the largest cluster as the base geometry
        adjacent = sorted(neighbors, key=len)[-1]
        shapes = [s for s in shapes if s not in adjacent]
        geom = unary_union(adjacent)
        # Append any shapes adjacent to the cluster
        while True:
            adjacent = []
            for shape in shapes:
                if shape.intersects(geom):
                    adjacent.append(shape)
            if not adjacent:
                break
            shapes = [s for s in shapes if s not in adjacent]
            geom = unary_union([geom] + adjacent)
        return geom
