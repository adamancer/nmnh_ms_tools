"""Tests evaluator"""
from random import randint

import pytest

from nmnh_ms_tools.databases.geonames import GeoNamesFeatures
from nmnh_ms_tools.records import Site
from nmnh_ms_tools.routines.georeferencer.evaluators import MatchEvaluator


class Helpers:
    geonames_db = GeoNamesFeatures()

    def search_json(self, name):
        return self.sitify(self.geonames_db.search_json(name))

    def sitify(self, data):
        if isinstance(data, list):
            return [self.sitify(d) for d in data]
        site = Site(data)
        if not site.field:
            site.field = "locality"
        site.filter.setdefault("name", site.site_names[0])
        return site

    @staticmethod
    def same_as(*args):
        sitelists = [{s.location_id for s in a} for a in args]
        return all([s == sitelists[0] for s in sitelists])


@pytest.fixture
def helpers():
    return Helpers()


@pytest.fixture
def evaluator():
    ref_site = Site(
        {
            "country": "United States",
            "state_province": "Hawaii",
            "county": "Honolulu Co.",
            "municipality": "Honolulu",
            "island": "Oahu",
        }
    )
    ref_site.get_admin_polygons()
    return MatchEvaluator(ref_site, None, [ref_site])


@pytest.fixture
def site():
    site = Site()
    site.field = "locality"
    site.filter["name"] = "test"
    return site


def test_missing_attribute(evaluator):
    with pytest.raises(AttributeError):
        evaluator.fakeattr


def test_iter(evaluator, helpers):
    sites = helpers.search_json("united states")
    evaluator.results = sites
    results_sites = []
    for result in evaluator:
        results_sites.extend(result.sites)
    assert helpers.same_as(results_sites, sites)
    assert helpers.same_as(evaluator.sites, sites)


def test_len(evaluator, helpers):
    sites = helpers.search_json("united states")
    evaluator.results = sites
    assert len(evaluator) == 1


def test_append(evaluator, helpers):
    sites = helpers.search_json("united states")
    evaluator.results = []
    evaluator.append(sites[0])
    assert helpers.same_as(evaluator.results[0].sites, sites)
    assert helpers.same_as(evaluator.sites, sites)
    assert len(evaluator) == 1


def test_extend(evaluator, helpers):
    sites = helpers.search_json("united states")
    evaluator.results = []
    evaluator.extend(sites)
    assert helpers.same_as(evaluator.results[0].sites, sites)
    assert helpers.same_as(evaluator.sites, sites)
    assert len(evaluator) == 1


def test_removing_repeats_when_setting_sites(evaluator, helpers):
    sites = helpers.search_json("united states")
    sites.append(sites[0])
    sites[-1].field = "locality"
    evaluator.sites = sites
    assert evaluator.sites == sites[:-1]


def test_key(evaluator, helpers):
    site = helpers.search_json("united states")[0]
    assert evaluator.key(site) == "locality:United States"


def test_select(evaluator, helpers):
    site = helpers.search_json("oahu")[0]
    evaluator.sites = [site]
    assert evaluator.select([site]) == evaluator.select([site], site.geometry)


def test_constrain(evaluator, helpers):
    islands = helpers.search_json("hawaiian islands")[0]
    county = helpers.search_json("honolulu county")[0]
    constrained = evaluator.constrain(islands, county, "county")
    lng, lat = constrained.centroid.coords[0]
    assert lat == pytest.approx(24.76, rel=1e-2)
    assert lng == pytest.approx(-167.04, rel=1e-2)


@pytest.mark.skip
def test_extend_into_ocean(evaluator, helpers):
    pass


@pytest.mark.skip
def test_disentangle_names(evaluator, helpers):
    pass


def test_interpretation(evaluator, helpers):
    enc = helpers.search_json("hawaiian islands")
    sel = helpers.search_json("oahu")
    rej = helpers.search_json("washington")
    sites = enc + sel + rej

    evaluator.results = sites
    assert helpers.same_as(evaluator.uninterpreted(), sites)
    evaluator.interpret(enc, "encompassing")
    evaluator.interpret(sel, "selected")
    evaluator.interpret(rej, "rejected (disjoint)")
    assert helpers.same_as(evaluator.interpreted_as("encompassing"), enc)
    assert helpers.same_as(evaluator.interpreted_as("selected"), sel)
    assert helpers.same_as(evaluator.interpreted_as("rejected (disjoint)"), rej)

    assert helpers.same_as(evaluator.active(), enc + sel)
    assert helpers.same_as(evaluator.inactive(), rej)
    assert evaluator.ignored() == [s.name for s in rej]
    assert evaluator.uninterpreted() == []

    evaluator.uninterpret(status="selected")
    assert helpers.same_as(evaluator.uninterpreted(), sel)
    evaluator.uninterpret(sites=rej)
    assert helpers.same_as(evaluator.uninterpreted(), sel + rej)


def test_unrecognized_interpretation(evaluator, helpers):
    sites = helpers.search_json("oahu")
    evaluator.results = sites
    with pytest.raises(KeyError):
        evaluator.interpret(sites, "valid")


def test_reject_interpreted(evaluator, helpers):
    sites = helpers.search_json("honolulu")
    sites = [s for s in sites if s.site_kind == "PPLA"]
    sel = sites[:1]
    rej = sites[1:]
    evaluator.results = sites
    rej_status = "rejected (interpreted elsewhere)"
    evaluator.interpret(sites[:1], "selected", reject_similar=True)
    assert helpers.same_as(evaluator.interpreted_as("selected"), sel)
    assert helpers.same_as(evaluator.active(), sel)
    assert helpers.same_as(evaluator.active(include_selected=False), [])
    assert helpers.same_as(evaluator.interpreted_as(rej_status), rej)
    assert helpers.same_as(evaluator.inactive(), rej)


def test_too_many_sites(evaluator, site):
    with pytest.raises(ValueError):
        evaluator.encompass([site] * 500)


def test_encompass_name(evaluator, helpers):
    sites = helpers.search_json("honolulu")
    sites = [s for s in sites if s.site_kind == "PPLA"]
    result = evaluator.encompass_name(sites)[0]
    lng, lat = result.centroid.coords[0]
    assert lat == pytest.approx(21.31, rel=1e-2)
    assert lng == pytest.approx(-157.86, rel=1e-2)


def test_encompass_name_with_max_dist_km(evaluator, helpers):
    sites = helpers.search_json("honolulu")
    sites = [s for s in sites if s.site_kind == "PPLA"]
    result = evaluator.encompass_name(sites, max_dist_km=1)[0]
    lng, lat = result.centroid.coords[0]
    assert lat == pytest.approx(21.31, rel=1e-2)
    assert lng == pytest.approx(-157.86, rel=1e-2)
