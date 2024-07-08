"""Tests geographic name database operations"""

import csv
import json
import os

import pytest

from nmnh_ms_tools.config import TEST_DIR
from nmnh_ms_tools.databases.admin import AdminFeatures, AdminThesaurus
from nmnh_ms_tools.databases.custom import CustomFeatures
from nmnh_ms_tools.databases.geonames import GeoNamesFeatures


def test_get_json():
    result = GeoNamesFeatures().get_json(5793639)
    assert result["geonameId"] == 5793639
    assert result["name"] == "Ellensburg"


def test_get_many():
    feat_db = GeoNamesFeatures()
    rows = feat_db.session().query(feat_db.features.geoname_id)
    expected = {r.geoname_id for r in rows}
    results = feat_db.get_many(expected)
    assert {r["geonameId"] for r in results} == expected


def test_search_json():
    feat_db = GeoNamesFeatures()
    result = {r["geonameId"] for r in feat_db.search_json("Ellensburg")}
    assert 5793639 in result


def test_fill_record():
    feat_db = GeoNamesFeatures()
    session = feat_db.session()
    row = session.query(feat_db.features).filter_by(geoname_id=5793639).first()
    row.admin_name_1 = None
    session.merge(row)
    session.commit()
    row = session.query(feat_db.features).filter_by(geoname_id=5793639).first()
    assert row.admin_name_1 is None
    feat_db.fill_record(row, session=session)
    row = session.query(feat_db.features).filter_by(geoname_id=5793639).first()
    assert row.admin_name_1 == "Washington"
    session.close()


def test_fill_record_undersea():
    feat_db = GeoNamesFeatures()
    session = feat_db.session()
    row = session.query(feat_db.features).filter_by(geoname_id=4031274).first()
    row.ocean = None
    session.merge(row)
    session.commit()
    row = session.query(feat_db.features).filter_by(geoname_id=4031274).first()
    assert row.ocean is None
    feat_db.fill_record(row, session=session)
    row = session.query(feat_db.features).filter_by(geoname_id=4031274).first()
    assert row.ocean == "North Pacific Ocean"
    session.close()


@pytest.mark.parametrize("feat_db_class", [GeoNamesFeatures, CustomFeatures])
def test_update_alt_names(feat_db_class):
    feat_db = feat_db_class()
    session = feat_db.session()
    expected = set(session.query(feat_db.names.st_name))
    feat_db.update_alt_names()
    assert set(session.query(feat_db.names.st_name)) == expected
    session.close()


def test_index_names():
    feat_db = GeoNamesFeatures()
    feat_db.index_names(False, True)
    feat_db.index_names(True, True)
    feat_db.index_names(True, False)
    feat_db.index_names(False, False)


def test_to_csv(tmp_path):
    feat_db = GeoNamesFeatures()
    fp = tmp_path / "temp.csv"
    feat_db.to_csv(fp, terms=[5793639, "Ellensburg"])
    with open(fp, "r", encoding="utf-8-sig", newline="") as f:
        assert next(f).startswith("#")
        assert next(f).startswith("geonameId")
        assert next(f).startswith("5793639")
        assert next(f).startswith("7173377")


@pytest.mark.parametrize(
    "feat_db_class,fn",
    [
        (GeoNamesFeatures, "test_geonames.csv"),
        (CustomFeatures, "test_custom.csv"),
    ],
)
def test_from_csv(feat_db_class, fn):
    feat_db = feat_db_class()
    feat_db.keys = None
    feat_db.delim = "|"
    feat_db.csv_kwargs = {"dialect": "excel"}
    session = feat_db.session()
    expected = set(session.query(feat_db.features.geoname_id))
    feat_db.from_csv(os.path.join(TEST_DIR, fn))
    assert set(session.query(feat_db.features.geoname_id)) == expected
    session.close()


def test_from_included_gazetteer(mocker):
    def open_file(inst, fp, *args, **kwargs):
        with open(fp, "r"):
            return

    mocker.patch(
        "nmnh_ms_tools.databases.geonames.GeoNamesFeatures.from_csv", open_file
    )
    CustomFeatures().from_included_gazetteer("GVP")


def test_from_included_gazetteer_invalid():
    with pytest.raises(KeyError):
        CustomFeatures().from_included_gazetteer("FAKE GAZETTEER")


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (("United States",), {"country": ["United States"]}),
        (
            ("United States", "Washington"),
            {"country": ["United States"], "state_province": ["Washington"]},
        ),
        (
            ("United States", "Washington", "Kittitas Co."),
            {
                "country": ["United States"],
                "state_province": ["Washington"],
                "county": ["Kittitas County"],
            },
        ),
        (
            ("US", "WA", "037"),
            {
                "country": ["United States"],
                "state_province": ["Washington"],
                "county": ["Kittitas County"],
            },
        ),
    ],
)
def test_get_admin_names(test_input, expected):
    assert AdminFeatures().get_admin_names(*test_input) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (("United States",), {"country_code": ["US"]}),
        (
            ("United States", "Washington"),
            {"country_code": ["US"], "admin_code_1": ["WA"]},
        ),
        (
            ("United States", "Washington", "Kittitas Co."),
            {
                "country_code": ["US"],
                "admin_code_1": ["WA"],
                "admin_code_2": ["037"],
            },
        ),
        (
            ("US", "WA", "037"),
            {
                "country_code": ["US"],
                "admin_code_1": ["WA"],
                "admin_code_2": ["037"],
            },
        ),
    ],
)
def test_get_admin_codes(test_input, expected):
    assert AdminFeatures().get_admin_codes(*test_input) == expected


def test_map_deprecated():
    admin = AdminFeatures()
    with pytest.raises(ValueError):
        result = admin.get("United States", "Washington", "Ellensburg")
    # Add mapping to thesaurus and repeat query
    session = admin.session()
    row = session.query(AdminThesaurus).filter_by(county="Ellensburg").first()
    row.mapping = json.dumps({"county": "Kittitas", "municipality": "Ellensburg"})
    session.merge(row)
    session.commit()
    session.close()
    result = admin.get("United States", "Washington", "Ellensburg")
    assert result["county"] == ["Kittitas County"]
    assert result["admin_code_2"] == ["037"]
    assert result["municipality"] == ["Ellensburg"]
