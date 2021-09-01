"""Defines class to describe how a georeference was determined"""
import logging
import os
import re

from .evaluator import MatchEvaluator
from ....bots.geonames import CODES_COUNTRIES
from ....config import CONFIG
from ....databases.georef_job import Session, Localities, Uncertainties
from ....tools.geographic_operations.kml import Kml
from ....utils.standardizers import LocStandardizer
from ....utils import oxford_comma




logger = logging.getLogger(__name__)




class MatchAnnotator(MatchEvaluator):
    """Describes how georeference was determined"""
    std = LocStandardizer()


    def __init__(self, *args, **kwargs):
        super(MatchAnnotator, self).__init__(*args, **kwargs)
        self.description = None


    @property
    def selected(self):
        """Returns list of sites used to determine the georeference"""
        return self.interpreted_as('selected')


    def describe(self):
        """Describes the geoerefence"""
        if self.description:
            return self.description
        self.save_parsed()
        if self.interpreted_as('selected'):
            # Calculate distance from original coordinates to active features
            if self.site.geometry:
                self.get_uncertainty()
            desc = []
            for method in [
                self._describe_selection,
                self._describe_filter,
                self._describe_uncertainty,
                self._describe_multiples,
                self._describe_encompassing,
                self._describe_intersecting,
                self._describe_less_specific,
                self._describe_more_specific,
                self._describe_ignored,
                self._describe_missed,
                self._describe_sources
            ]:
                try:
                    desc.append(method())
                except AttributeError as e:
                    logger.error(str(e), exc_info=e)
                    desc = '\n'.join([s for s in self._describe_miss() if s])
                    break
            else:
                desc = '. '.join([s for s in desc if s]) + '.'
                selected = self.interpreted_as('selected')
                desc = desc.replace('(s)', '' if len(selected) == 1 else 's')
        else:
            desc = '\n'.join([s for s in self._describe_miss() if s])
        # Add interpretations to debug
        for loc_id, status in self.interpreted.items():
            site = self.expand(loc_id)
            logger.debug('{} ({}): {}'.format(site.name, loc_id, status))
        logger.debug('Description:\n{}'.format(desc))
        self.description = desc
        return desc


    def strong_match(self):
        """Tests if georeference appears strong"""
        return (len(self.selected) == 1
                and not self.missed()
                and not self.leftovers)


    def kml(self, fn, refsite=None):
        """Saves results as KML"""
        kml = Kml()
        try:
            kml.add_site(self.result, 'final')
        except AttributeError:
            pass
        if refsite is not None and refsite.geometry:
            kml.add_site(refsite, 'measured')
        # Get all selected and candidate sites
        candidates = self.sites[:]

        statuses = {'rejected (encompassed)'}
        candidates.extend(self.interpreted_as(statuses))

        for site in self.active():
            if site.site_kind not in {'CONT', 'OCN'}:
                candidates.append(site)
        for site in self.interpreted_as('selected'):
            candidates.extend(site.related_sites)
        for site in self.expand(candidates):
            if site.radius_km <= 2000:
                kml.add_site(site, 'candidate')
        if not fn.endswith('.kml'):
            fn = '{}.kml'.format(fn)
        kml.save(os.path.join('kml', fn))


    def _describe_selection(self):
        """Lists the selected names and gives gist of determination"""
        groups = self.group_by_name(self.interpreted_as('selected'))
        selected = []
        for name, group in groups.items():
            combined = group[0].combine(*group[1:])
            combined.verbatim_latitude = None
            combined.verbatim_longitude = None
            for attr, code in (
                ('county', 'admin_code_2'),
                ('state_province', 'admin_code_1'),
                ('country', 'country_code')):
                    if not group[0].filter.get(code):
                        setattr(combined, attr, None)
            combined.site_names = [name.split(':', 1)[1]]
            # Inherit certain attributes from selected site
            combined.related_sites = group[0].related_sites
            combined.url_mask = group[0].url_mask
            combined.geometry = self.geometry
            #if (combined.geometry
            #    and not re.search(r'^\d+$', combined.location_id)):
            #        combined.radius_km = group[0].radius_km
            if len(group) > 1:
                combined.url_mask = 'multiple matching localities'
            selected.append(self.name(combined))
        constrained_to = self.interpreted_as('constrained')
        if constrained_to:
            constrained_to.sort(key=lambda s: s.radius_km)
            selected += [self.name(s) for s in constrained_to]
            mask = 'the intersection between {}'
            result = mask.format(oxford_comma(selected, delim='; '))
        else:
            mask = '{}' if len(selected) == 1 else 'a circle encompassing {}'
            result = mask.format(oxford_comma(selected, delim='; '))
        return 'Coordinates and uncertainty based on {}'.format(result)


    def _describe_miss(self):
        """Lists names considered for a missed georeference"""
        desc = []
        desc.append('Terms checked: {}'.format(self.terms_checked))
        desc.append('Terms missed: {}'.format(self.missed()))
        mask = '{} (id={}, code={}, lat={:.1f}, lng={:.1f}, radius={:.1f} km)'
        for name, group in self.group_by_name(self._sites).items():
            # Limit to active sites
            group = [s for s in group if s in self.active()]
            if group:
                desc.append(name)
                for site in group:
                    lng, lat = site.centroid.coords[0]
                    summary = mask.format(site.name,
                                          site.location_id,
                                          site.site_kind,
                                          lat,
                                          lng,
                                          site.radius_km)
                    desc.append('+ {}'.format(summary))
            else:
                desc.append('{} (no active sites)'.format(name))
        return desc


    def _describe_uncertainty(self):
        """Describes how uncertainty compares to estimate of best possible"""
        estimated = self.estimate_minimum_uncertainty()
        if 0.9 * self.radius_km <= estimated <= 1.1 * self.radius_km:
            rel = 'is similar to'
        elif self.radius_km < estimated:
            rel = 'is smaller than'
        else:
            rel = 'exceeds'
        # Round the uncertainty radius
        if estimated < 1:
            estimated = 1
        if self.radius_km < 10:
            radius_km = '{:.1f}'.format(self.radius_km)
            if radius_km.endswith('.0'):
                radius_km = radius_km.split('.')[0]
        else:
            radius_km = int(round(self.radius_km))
        return ('The uncertainty radius ({} km) {} an estimate'
                ' of the minimum likely uncertainty radius calculated'
                ' based on the provided locality information'
                ' (~{} km)').format(radius_km, rel, int(round(estimated)))


    def _describe_filter(self):
        """Describes common elements of filters for selected sites"""
        master = None
        for site in self.interpreted_as('selected'):
            if master is None:
                master = site.filter
            else:
                master = {k: v for k, v in master.items()
                          if v and v == site.filter.get(k)}
        # Map admin codes back to names
        codes = {
            'country_code': 'country',
            'admin_code_1': 'state_province',
            'admin_code_2': 'county'
        }
        master = {codes.get(k, k): v for k, v in master.items() if v}
        logger.debug('Final filter: {}'.format(master))
        ordered = CONFIG.routines.georeferencing.ordered_field_list
        fltr = [f['field'] for f in ordered if f['field'] in master]
        fltr = [self.field(f).replace('_', '/') for f in fltr]
        if fltr:
            return 'Feature(s) matched on {}'.format(oxford_comma(fltr))
        return


    def _describe_encompassing(self):
        """Lists names encompassing the selected sites"""
        sites = []
        for site in self.interpreted_as('encompassing'):
            if site.field not in {'country', 'state_province', 'county'}:
                sites.append(site)
        if sites:
            mask = ('The following place names mentioned in this record'
                    ' appear to encompass the selected feature(s): {}')
            keys = [self.key(s).split(':')[-1] for s in sites]
            names = sorted({self.quote(k) for k in keys})
            return mask.format(oxford_comma(names))
        return


    def _describe_intersecting(self):
        """Lists names intersecting the selected sites"""
        sites = self.interpreted_as('intersecting') + self.sites
        # Intersection with continent is not super interesting if country was matched
        countries = [s for s in self.active() if s.site_kind in CODES_COUNTRIES]
        if countries:
            sites = [s for s in sites if s.site_kind != 'CONT']
        if sites:
            mask = ('The following place names mentioned in this record'
                    ' intersect the selected features: {}')
            keys = [self.key(s).split(':')[-1] for s in sites]
            names = sorted({self.quote(k) for k in keys})
            return mask.format(oxford_comma(names))
        return


    def _describe_multiples(self):
        """Lists names that matched multiple sited and gives interpretation"""
        selected = self.interpreted_as('selected')
        encompassed = self.interpreted_as('rejected (encompassed)')
        rejected = self.interpreted_as('rejected (interpreted elsewhere)')

        groups = self.group_by_name(selected + encompassed + rejected)
        sites = []
        for name, group in groups.items():
            count = len(group)
            if count > 1:
                name = self.quote(name.split(':', 1)[1])
                # Don't mention places that were ignored
                if name not in self.ignored():
                    mask = '{} (n={})'
                    if group[0].intersects_all(group[1:]):
                        mask = '{} (n={}, all intersecting)'
                    sites.append(mask.format(name, count))

        if sites:
            mask = ('The following place names mentioned in this record'
                    ' match multiple places: {}. The final georeference ')
            if len(selected) == 1:
                name = sites[0].split(' (n=')[0]
                explanations = self.multiples.get(name, [])
                if len(set(explanations)) != 1:
                    logger.warning('Could not explain "{}"'.format(name))
                    mask += 'uses the best match on this name'
                else:
                    mask += explanations[0]
            elif (
                len(groups) == 1
                and len(set([self.key(s) for s in selected])) == 1
            ):
                name = list(groups.keys())[0]
                count = [self.key(s) for s in selected].count(name)
                if count == len(selected):
                    mask += 'includes all features matching this name'
                else:
                    mask += 'uses {count} features matching this name'
            else:
                mask += ('encompasses the features matching each place name'
                         ' with the smallest distance between them')
            return mask.format(oxford_comma(sites))
        return


    def _describe_less_specific(self):
        """Lists names that were less specific than the selected sites"""
        sites = self.interpreted_as('less specific')
        if sites:
            mask = ('The following place names mentioned in this record'
                    ' appear to describe less specific features and'
                    ' were ignored: {}')
            keys = [self.key(s).split(':')[-1] for s in sites]
            names = sorted({self.quote(k) for k in keys})
            return mask.format(oxford_comma(names))
        return


    def _describe_more_specific(self):
        """Lists names that were more specific than the selected sites"""
        sites = self.interpreted_as('more specific')
        if sites:
            mask = ('The following place names mentioned in this record'
                    ' appear to describe more specific features but could'
                    ' not be matched: {}')
            keys = [self.key(s).split(':')[-1] for s in sites]
            names = sorted({self.quote(k) for k in keys})
            return mask.format(oxford_comma(names))
        return


    def _describe_ignored(self):
        """Lists names that could not be reconciled with the selected sites"""

        # Exclude generic features signified by curly braces
        sites = [s for s in self.ignored() if not re.match(r'^{.*}$', s)]

        if sites:
            mask = ('The following place names mentioned in this record'
                    ' could not be reconciled with other locality info'
                    ' and were ignored: {}')
            return mask.format(oxford_comma(sorted(set(sites))))
        return


    def _describe_missed(self):
        """Lists names that could not be matched at all"""
        stmt = []
        missed = self.missed()
        if missed:
            mask = ('The following place names mentioned'
                    ' in this record were not found: {}')
            stmt.append(mask.format(oxford_comma(missed)))
        ignored = [s for s in self.ignored() if re.match(r'^{.*}$', s)]
        if self.leftovers or ignored:
            stmt.append('Some data in this record could not be interpreted')
        return '. '.join(stmt) if stmt else None


    def _describe_sources(self):
        """Lists sources that provided base coordinates and geometries"""
        if self.sources:
            mask = 'This georeference is based on data from {}'
            return mask.format(oxford_comma(self.sources))
        return


    def get_uncertainty(self):
        """Calculates distance between each feature and a reference site"""
        session = Session()
        for site in self.active():
            site_kind = site.site_kind
            if site_kind.isupper() and '_' in site.location_id:
                site_kind += '_MOD'
            threshold_km = max([self.site.radius_km + 1, 500])
            row = Uncertainties(
                occurrence_id=self.site.location_id,
                site_num=site.location_id,
                site_name=site.name,
                site_kind=site_kind,
                radius=site.radius_km,
                dist_km=site.centroid_dist_km(self.site, threshold_km)
            )
            try:
                session.add(row)
                session.commit()
            except:
                session.rollback()
        session.close()


    def name(self, site):
        """Returns a descriptive name for a site"""
        higher_geo = []
        names = [None, None, None]
        if site.radius_km < 500:
            names = [site.county, site.state_province, site.country]
            for i, name in enumerate(names):
                if not i and site.country == 'United States':
                    pattern = r'\b(County|Co\.?|Area)$'
                    counties = []
                    for county in name:
                        if not re.search(pattern, county, flags=re.I):
                            county = '{} Co.'.format(county)
                        else:
                            county = county.replace('County', 'Co.')
                        counties.append(county)
                    name = counties
                if isinstance(name, list):
                    name = '/'.join(name)
                if name and (not higher_geo or higher_geo[-1] != name):
                    higher_geo.append(name)
        options = ['ADM2', 'ADM1', 'PC']
        pattern = '|'.join([o for i, o in enumerate(options) if names[i]])
        if (site.related_sites
            or not higher_geo
            or not re.match(pattern, site.site_kind)):
                higher_geo.insert(0, self.quote(site.name, bool(site.related_sites)))
        loc = ', '.join([n for n in higher_geo if n])
        # Get the url, cleaning up the trailer on proximity matches
        source = None
        if site.url:
            source = re.sub(r'\_[A-Z]+$', '', site.url) if site.url else None
            if site.site_kind.isupper():
                source = f'{site.site_kind}: {source}'
        elif site.site_source:
            source = f'via {site.site_source}'
        return '{} ({})'.format(loc, source) if source else loc


    def save_parsed(self):
        """Saves parses of locality names to a SQLite database"""
        session = Session()
        attrs = ['location_id', 'country', 'state_province', 'county']
        base = {}
        for attr in attrs:
            val = getattr(self.site, attr)
            if isinstance(val, list):
                val = ' | '.join(val)
            base[attr if attr != 'location_id' else 'occurrence_id'] = val
        missed = {s.split('=', 1)[-1].strip('"') for s in self.missed()}
        for field, features in self.features.items():
            for parsed in features:
                full = getattr(self.site, field)
                if isinstance(full, list):
                    full = ' | '.join(full)
                row = {
                    'field': field,
                    'parser': parsed.kind,
                    'parsed': str(parsed),
                    'verbatim': parsed.verbatim,
                    'verbatim_full': full,
                    'missed': 1 if parsed.verbatim.strip('"') in missed else 0,
                    'has_poly': None,
                }
                row.update(base)
                row = Localities(**row)
                try:
                    session.add(row)
                    session.commit()
                except:
                    session.rollback()
        session.close()


    @staticmethod
    def quote(val, use_quotes=False):
        """Adds quotes to a phrase"""
        if not use_quotes:
            use_quotes = '(' in val or re.search(r'\b[a-z]{4,}\b', val)
        return '"{}"'.format(val.strip('"').replace('"', "'")) if use_quotes else val
