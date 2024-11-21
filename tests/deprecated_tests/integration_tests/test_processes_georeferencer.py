"""Tests georeferencing operations"""

import csv
import os
import pytest

from nmnh_ms_tools.config import TEST_DIR
from nmnh_ms_tools.records import Site
from nmnh_ms_tools.processes.georeferencer import Georeferencer
from nmnh_ms_tools.processes.georeferencer.pipes import (
    MatchGeoNames,
    MatchOffshore,
    MatchPLSS,
)
from nmnh_ms_tools.utils import skip_hashed


# Locality info for georeference tests is stored in a CSV in the main data dir
test_data = {}
fp = os.path.join(TEST_DIR, "test_georeferencer.csv")
with open(fp, "r", encoding="utf-8-sig", newline="") as f:
    rows = csv.reader(skip_hashed(f), dialect="excel")
    keys = next(rows)
    for row in rows:
        site = Site(dict(zip(keys, row)))
        test_data[site.location_id] = site


@pytest.fixture
def geo(mocker):
    mocker.patch("nmnh_ms_tools.processes.georeferencer.Georeferencer.configure_log")
    geo = Georeferencer()
    geo.id_key = r"\btest(_[a-z]+)+\b"
    geo.raise_on_error = True
    return geo


def test_from_file(mocker):
    mocker.patch("nmnh_ms_tools.processes.georeferencer.Georeferencer.configure_log")
    fp = os.path.join(TEST_DIR, "test_georeferencer.csv")
    geo = Georeferencer(fp, pipes=[MatchGeoNames()], skip=1, limit=1)
    geo.id_key = r"\btest(_[a-z]+)+\b"
    geo.raise_on_error = True
    geo.georeference()


def test_from_file_with_tests(mocker):
    mocker.patch("nmnh_ms_tools.processes.georeferencer.Georeferencer.configure_log")
    fp = os.path.join(TEST_DIR, "test_georeferencer.csv")
    geo = Georeferencer(fp, pipes=[MatchGeoNames()])
    geo.id_key = r"\btest(_[a-z]+)+\b"
    geo.raise_on_error = True
    geo.tests = geo.read_tests(fp)[:1]
    geo.georeference()


def test_simple_locality(geo):
    result = geo.georeference_one(test_data["test_simple_locality"])
    assert result["dist_km"] <= result["radius_km"]


def test_multiple_localities(geo):
    result = geo.georeference_one(test_data["test_multiple_localities"])
    assert result["dist_km"] <= result["radius_km"]


def test_between(geo):
    result = geo.georeference_one(test_data["test_between"])
    assert result["dist_km"] <= result["radius_km"]


def test_border(geo):
    # FIXME: Should this work without forcing a bigger max_dist_km?
    geo.eval_params["max_dist_km"] = 1000
    result = geo.georeference_one(test_data["test_border"])
    assert result["dist_km"] <= result["radius_km"]


def test_direction(geo):
    result = geo.georeference_one(test_data["test_direction"])
    assert result["dist_km"] <= result["radius_km"]


def test_offshore(geo):
    geo.pipes.append(MatchOffshore())
    geo.allow_sparse = True
    result = geo.georeference_one(test_data["test_offshore"])
    assert result["dist_km"] <= result["radius_km"]


def test_plss(geo):
    geo.pipes.append(MatchPLSS())
    result = geo.georeference_one(test_data["test_plss"])
    assert result["dist_km"] <= result["radius_km"]


def test_county_fallback(geo):
    result = geo.georeference_one(test_data["test_county_fallback"])
    assert result["dist_km"] <= result["radius_km"]


def test_state_province(geo):
    geo.allow_sparse = True
    result = geo.georeference_one(test_data["test_state_province"])
    assert result["dist_km"] <= result["radius_km"]


def test_country(geo):
    geo.allow_sparse = True
    result = geo.georeference_one(test_data["test_country"])
    assert result["dist_km"] <= result["radius_km"]


def test_adm3(geo):
    result = geo.georeference_one(test_data["test_adm3"])
    assert result["dist_km"] <= result["radius_km"]


@pytest.mark.skip("offshore localities not working")
def test_large_distance(geo):
    print(test_data["test_large_distance"].to_dict())
    result = geo.georeference_one(test_data["test_large_distance"])
    assert result["dist_km"] <= result["radius_km"]


@pytest.mark.skip("Antarctica failing")
def test_continent(geo):
    result = geo.georeference_one(test_data["test_continent"])
    assert result["dist_km"] <= result["radius_km"]


@pytest.mark.parametrize("site", test_data.values())
def test_meets_criteria_any(geo, site):
    geo.allow_sparse = True
    geo.coord_type = "any"
    geo.place_type = "any"
    assert geo.meets_criteria(site)


@pytest.mark.parametrize("site", test_data.values())
def test_meets_criteria_detailed(geo, site):
    geo.allow_sparse = False
    geo.coord_type = "any"
    geo.place_type = "any"
    if "sparse" in site.georeference_remarks:
        assert not geo.meets_criteria(site)
    else:
        assert geo.meets_criteria(site)


@pytest.mark.parametrize("site", test_data.values())
def test_meets_criteria_marine(geo, site):
    geo.allow_sparse = True
    geo.coord_type = "any"
    geo.place_type = "marine"
    if "marine" in site.georeference_remarks:
        assert geo.meets_criteria(site)
    else:
        assert not geo.meets_criteria(site)


@pytest.mark.parametrize("site", test_data.values())
def test_meets_criteria_terrestrial(geo, site):
    geo.allow_sparse = True
    geo.coord_type = "any"
    geo.place_type = "terrestrial"
    if "terrestrial" in site.georeference_remarks:
        assert geo.meets_criteria(site)
    else:
        assert not geo.meets_criteria(site)


@pytest.mark.parametrize("site", test_data.values())
def test_meets_criteria_measured(geo, site):
    geo.allow_sparse = True
    geo.coord_type = "measured"
    geo.place_type = "any"
    if site.georeference_protocol in {"", "collector", "unknown"}:
        assert geo.meets_criteria(site)
    else:
        assert not geo.meets_criteria(site)


@pytest.mark.parametrize("site", test_data.values())
def test_meets_criteria_georeferenced(geo, site):
    geo.allow_sparse = True
    geo.coord_type = "georeferenced"
    geo.place_type = "any"
    if site.georeference_protocol in {"", "collector", "unknown"}:
        assert not geo.meets_criteria(site)
    else:
        assert geo.meets_criteria(site)
