"""Tests GeoNamesBot class"""
from collections import namedtuple

import pytest

from nmnh_ms_tools.bots import (
    Bot,
    AdamancerBot,
    ElsevierBot,
    GeoDeepDiveBot,
    GeoGalleryBot,
    GeoNamesBot,
    GNRDBot,
    ITISBot,
    MacrostratBot,
    MetBullBot,
    PLSSBot,
)
from nmnh_ms_tools.bots.elsevier import xml_to_text


class FakeGeoNamesResponse:
    def __init__(self, geonames_error_code):
        self.url = "http://"
        self.status_code = "fake_status_code"
        self.geonames_error_code = geonames_error_code

    def json(self):
        return {"status": {"value": self.geonames_error_code}}


def test_adamancer_bot_strat():
    response = AdamancerBot().chronostrat("Cambrian")
    assert response["data"]["earliest"]["system"] == "Cambrian"
    assert response["data"]["earliest"]["max_ma"] == 541


def test_adamancer_bot_metbull():
    response = AdamancerBot().metbull("Lafayette (stone)")
    assert response["data"][0]["mass"] == "800 g"
    assert response["data"][0]["type"] == "Martian (nakhlite)"
    assert response["data"][0]["year"] == "1931"


# Elsevier has (characteristically) locked down its API, so can't trust
# that these tests will run.
@pytest.mark.skip
def test_elsevier_api_key():
    with pytest.raises(ValueError):
        ElsevierBot(api_key=None)


@pytest.mark.skip
def test_elsevier_search():
    query = {
        "ttl": ["calcite AND dolomite AND cm AND isotope"],
        "src": "Geochimica et Cosmochimica Acta",
        "openaccess": 1,
    }
    response = ElsevierBot().search(query=query, field="doi", count=100)
    assert "10.1016/j.gca.2019.06.012" in response.text


@pytest.mark.skip
def test_elsevier_article():
    response = ElsevierBot().article("10.1016/j.gca.2019.06.012")
    text = xml_to_text(response.text)
    assert text[0].startswith("# Calcite and dolomite formation in the CM")


def test_geodeepdive_get_article():
    response = GeoDeepDiveBot().get_article("10.1029/2018GC007630")
    article = response.first()
    assert article["title"] == (
        "Carbon fluxes and primary magma CO 2 contents"
        " along the global mid-ocean ridge system"
    )


def test_geodeepdive_get_snippets():
    response = GeoDeepDiveBot().get_snippets("NMNH 111312-44")
    assert "san carlos olivine" in str(response).lower()


def test_geodeepdive_list_coauthors():
    coauthors = GeoDeepDiveBot().list_coauthors("Elizabeth Cottrell")
    assert "Elizabeth C. Cottrell" in coauthors


@pytest.mark.parametrize("test_input", ["NMNH 111312-44", "111312-44"])
def test_geogallery_get_specimen_by_catalog_number(test_input):
    expected = {"7d5368b985824980b2c18231f7965356", "fb96f4dd739e4c0ca91d581084c86416"}
    results = GeoGalleryBot().get_specimen_by_id(test_input)
    assert {r["occurrenceID"] for r in results} == expected


def test_geogallery_get_specimen_by_irn():
    irn = 10795272
    response = GeoGalleryBot().get_specimen_by_id(irn)
    assert response.one()["occurrenceID"] == "7d5368b985824980b2c18231f7965356"


@pytest.mark.parametrize(
    "test_input",
    [
        "ark:/65665/37d5368b9-8582-4980-b2c1-8231f7965356",
        "7d5368b9-8582-4980-b2c1-8231f7965356",
        "7d5368b985824980b2c18231f7965356",
    ],
)
def test_geogallery_get_specimen_by_guid(test_input):
    response = GeoGalleryBot().get_specimen_by_id(test_input)
    assert response.one()["occurrenceID"] == "7d5368b985824980b2c18231f7965356"


def test_geogallery_get_specimens():
    kwargs = {
        #'collection': 'Smithsonian Microbeam Standards',  # not indexed
        "classification": "olivine",
        "location_id": "1055203",
        "country": "United States",
        "state": "Arizona",
        "limit": 100,
    }
    response = GeoGalleryBot().get_specimens(**kwargs)
    for rec in response:
        if rec["occurrenceID"] == "7d5368b985824980b2c18231f7965356":
            break
    else:
        assert False
    assert True


@pytest.mark.parametrize(
    "test_input,expected", [(None, True), (11, True), (13, False), (26, False)]
)
def test_geonames_validate(mocker, test_input, expected):
    def get_none(*args, **kwargs):
        return None

    mocker.patch("nmnh_ms_tools.bots.core.Bot.delete_cached_url", get_none)
    result = GeoNamesBot().validate(FakeGeoNamesResponse(test_input))
    assert result if expected else not result


@pytest.mark.parametrize("test_input", [10, 18, 19, 20])
def test_geonames_validate_errors(mocker, test_input):
    def get_none(*args, **kwargs):
        return None

    mocker.patch("nmnh_ms_tools.bots.core.Bot.delete_cached_url", get_none)
    with pytest.raises(SystemExit):
        GeoNamesBot().validate(FakeGeoNamesResponse(test_input))


def test_geonames_get_json():
    response = GeoNamesBot().get_json(5793639)
    assert response["geonameId"] == 5793639
    assert response["name"] == "Ellensburg"


def test_geonames_search_json():
    kwargs = {"adminCode1": "WA", "featureCode": "PPLA2"}
    response = GeoNamesBot().search_json("Ellensburg", **kwargs)
    assert {r["geonameId"] for r in response} == {5793639}


def test_geonames_search_json_illegal_param():
    with pytest.raises(ValueError):
        GeoNamesBot().search_json(country_code="US")


def test_geonames_search_json_too_many_names():
    with pytest.raises(ValueError):
        GeoNamesBot().search_json(name="a", name_equals="b", q="c")


def test_geonames_find_nearby():
    response = GeoNamesBot().find_nearby_json(46.997, -120.548, dec_places=3)
    assert 5793639 in {r["geonameId"] for r in response}


def test_geonames_country_subdivision_json():
    response = GeoNamesBot().country_subdivision_json(46.997, -120.548)
    assert response["adminCode1"] == "WA"
    assert response["countryCode"] == "US"


def test_geonames_ocean_json():
    response = GeoNamesBot().ocean_json(20.307, -157.858)
    assert response["ocean"]["name"] == "North Pacific Ocean"


def test_geonames_get_state():
    response = GeoNamesBot().get_state("Washington", "US")
    assert response["adminCode1"] == "WA"


def test_geonames_get_country():
    response = GeoNamesBot().get_country("United States")
    assert response["countryCode"] == "US"


def test_gnrd_find_names():
    response = GNRDBot().find_names("American robin (Turdus migratorius)")
    assert "Turdus migratorius" in {n["scientificName"] for n in response["names"]}


def test_gnrd_resolve_names():
    response = GNRDBot().resolve_names(["Turdus migratorius"])
    assert response["data"][0]["results"][0]["canonical_form"] == "Turdus migratorius"


def test_itis_get_taxon():
    name = "Turdus migratorius"
    response = ITISBot().get_taxon(name)
    assert name in {n.text for n in response.xpath(".//ax21:combinedName")}


def test_itis_get_hierarchy():
    expected = [
        "158852",
        "174371",
        "178265",
        "179751",
        "179752",
        "179759",
        "179760",
        "179761",
        "179762",
        "179763",
        "179764",
        "179765",
        "202423",
        "331030",
        "914154",
        "914156",
        "914179",
        "914181",
        "919538",
    ]
    response = ITISBot().get_hierarchy("179759")
    assert sorted({n.text for n in response.xpath(".//ax21:tsn")}) == expected


def test_macrostrat_get_units_by_name():
    response = MacrostratBot().get_units_by_name("Herkimer Limestone")
    assert set([r["strat_name_id"] for r in response]) == {3628}


def test_macrostrat_get_units_by_id():
    response = MacrostratBot().get_units_by_id(3628)
    assert set([r["unit_name"] for r in response]) == {"Herkimer Limestone"}


def test_metbull_get_meteorites():
    bot = MetBullBot()
    bot.start_param = None
    bot.limit_param = None
    bot.paged = False
    response = bot.get_meteorites(sea="Lafayette")
    expected = {"Lafayette (iron)", "Lafayette (stone)"}
    assert {r["name"] for r in response} == expected


def test_metbull_get_limit():
    nt = namedtuple("_", ["text"])
    fake_response = nt(text="Showing data for page 1 of 100")
    assert MetBullBot.get_limit(fake_response) == 100


def test_plss_get_sections():
    response = PLSSBot().get_sections("WA", "T17N", "R18E", "2")
    lng, lat = response[0].centroid.coords[0]
    assert lng == pytest.approx(-120.54, rel=1e-2)
    assert lat == pytest.approx(47.0, rel=1e-2)


def test_plss_empthy_section():
    assert PLSSBot().get_section(None, None) == []


def test_plss_township_does_not_exist():
    assert PLSSBot().get_townships("WA", "T99N", "R99E") == []


def test_plss_section_does_not_exist(mocker):
    def get_fake_response(*args, **kwrgs):
        return [{"attributes": {"FRSTDIVNO": "99"}}]

    bot = PLSSBot()
    plss_id = bot.get_townships("WA", "T17N", "R18E")[0]
    mocker.patch("nmnh_ms_tools.bots.core.Bot.get", get_fake_response)
    assert bot.get_section(plss_id, "2") is None


def test_plss_get_section_no_response(mocker):
    def get_none(*args, **kwargs):
        return None

    mocker.patch("nmnh_ms_tools.bots.core.Bot.get", get_none)
    assert PLSSBot().get_section("fake_plss_id", "fake_sec") is None


def test_plss_get_townships_no_response(mocker):
    def get_none(*args, **kwargs):
        return None

    mocker.patch("nmnh_ms_tools.bots.core.Bot.get", get_none)
    result = PLSSBot().get_townships("fake_state", "fake_twp", "fake_rng")
    assert result == []
