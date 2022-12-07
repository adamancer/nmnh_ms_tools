"""Defines helper methods for working with the job database"""
import logging
import numpy as np

from .database import Session, Uncertainties
from ...config import GEOCONFIG




logger = logging.getLogger(__name__)




def use_observed_uncertainties(percentile=68):
    """Updates uncertainites based on difference from actual coordinates"""
    session = Session()
    uncertainties = {}
    for row in session.query(Uncertainties):
        if row.site_kind.isupper() and '_' not in row.site_kind:
            uncertainties.setdefault(row.site_kind, []).append(row.dist_km)
    session.close()
    for site_kind in sorted(uncertainties):
        dists_km = [float(d) for d in set(uncertainties[site_kind])]
        if len(dists_km) >= 20:
            old = GEOCONFIG.get_feature_radius(site_kind)
            # Toss outliers and take mean
            pct10 = np.percentile(dists_km, 5)  # probably georeferences
            pct90 = np.percentile(dists_km, 95)  # probably misses
            dists_km = [d for d in dists_km if pct10 <= d <= pct90]
            unc = np.percentile(dists_km, percentile)
            mask = 'Updated {} from {:.1f} to {:.1f} km (n={})'
            msg = mask.format(site_kind, old, unc, int(len(dists_km)))
            logger.debug(msg)
            GEOCONFIG.codes[site_kind]['SizeIndex'] = unc
