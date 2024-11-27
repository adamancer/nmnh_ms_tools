"""Tests DirectionParser"""

import pytest

from shapely.geometry import Point

from nmnh_ms_tools.records.sites import Site


@pytest.fixture
def site():
    return Site(
        {
            "location_id": 5793639,
            "site_names": ["Ellensburg"],
            "site_kind": "PPLA2",
            "continent": "North America",
            "country": "United States",
            "state_province": "Washington",
            "county": "Kittitas Co",
            "municipality": "Ellensburg",
            "synonyms": ["Ellen's Burgh", "Robbers Roost"],
            "geometry": "<GeoMetry name=None crs='EPSG:4326' radius_km=0.0 geom='POINT (-120.55 46.99)'",
        }
    )


def test_name(site):
    assert site.name == "Ellensburg"


def test_geometry(site):
    assert site.geom_type == "Point"
    assert site.y == pytest.approx(46.99, rel=1e-2)
    assert site.x == pytest.approx(-120.55, rel=1e-2)


def test_site_class(site):
    assert site.site_class == "P"


def test_summarize(site):
    assert site.summarize() == "Ellensburg (5793639)"


def test_summarize_with_admin_mask(site):
    expected = "Kittitas Co, Washington, United States"
    assert site.summarize(mask="admin") == expected


def test_validate(site):
    assert site.validate()


def test_map_admin(site):
    site.map_admin()
    assert site.country_code == "US"
    assert site.admin_code_1 == ["WA"]
    assert site.admin_code_2 == ["037"]
    # Clear names and remap from codes
    site = site.update({"country": None, "state_province": None, "county": None})
    site.map_admin()
    assert site.country == "United States"
    assert site.state_province == ["Washington"]
    assert site.county == ["Kittitas County"]


def test_map_continent(site):
    site.map_admin()
    assert site.continent_code == "NA"


def test_has_name(site):
    assert site.has_name("Ellen's Burgh")
    assert site.has_name("Robbers Roost")
    assert not site.has_name("Ellensburgh")


def test_subsection(site):
    subsection = site.subsection("N")
    assert site in subsection.related_sites
    # Shape is a box, so area of subsection should be roughly half the original
    assert subsection.area / site.area == pytest.approx(0.5, rel=1e-2)


def test_copy(site):
    assert site == site.copy()
    assert site is not site.copy()


def test_partial_copy(site):
    pcopy = site.copy(["country", "state_province", "county"])
    assert site.country == pcopy.country
    assert site.state_province == pcopy.state_province
    assert site.county == pcopy.county
    assert not pcopy.location_id
    assert not pcopy.site_names


def test_terrestrial(site):
    assert site.is_terrestrial()
    assert not site.is_marine()
