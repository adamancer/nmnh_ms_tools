"""Tests geography helper functions"""

import pytest

from nmnh_ms_tools.utils.geo import (
    get_azimuth,
    get_dist_km,
    get_dist_km_geolib,
    get_dist_km_haversine,
    get_dist_km_pyproj,
    translate,
    translate_geolib,
    translate_pyproj,
)


@pytest.mark.parametrize(
    "test_input,expected",
    [("N", 0), ("NE", 45), ("NNE", 22.5)],
)
def test_get_azimuth(test_input, expected):
    assert get_azimuth(test_input) == pytest.approx(expected)


@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2,expected",
    [
        (46.999, -120.577, 47.068, -120.671, 10.477),
        (47, -121, 47, -121, 0),
    ],
)
def test_get_dist_km(lat1, lon1, lat2, lon2, expected):
    assert get_dist_km(lat1, lon1, lat2, lon2) == pytest.approx(expected, rel=1e-2)
    assert get_dist_km_geolib(lat1, lon1, lat2, lon2) == pytest.approx(
        expected, rel=1e-2
    )
    assert get_dist_km_haversine(lat1, lon1, lat2, lon2) == pytest.approx(
        expected, rel=1e-2
    )
    assert get_dist_km_pyproj(lat1, lon1, lat2, lon2) == pytest.approx(
        expected, rel=1e-2
    )


@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2,expected",
    [
        (46.999, -120.577, 47.068, -120.671, 10.477),
        (47, -121, 47, -121, 0),
    ],
)
def test_get_dist_km(lat1, lon1, lat2, lon2, expected):
    assert get_dist_km(lat1, lon1, lat2, lon2) == pytest.approx(expected, rel=1e-2)


@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2,expected",
    [
        (46.999, -120.577, 47.068, -120.671, 10.477),
        (47, -121, 47, -121, 0),
    ],
)
def test_get_dist_km_geolib(lat1, lon1, lat2, lon2, expected):
    assert get_dist_km_geolib(lat1, lon1, lat2, lon2) == pytest.approx(
        expected, rel=1e-2
    )


@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2,expected",
    [
        (46.999, -120.577, 47.068, -120.671, 10.477),
        (47, -121, 47, -121, 0),
    ],
)
def test_get_dist_km_haversine(lat1, lon1, lat2, lon2, expected):
    assert get_dist_km_haversine(lat1, lon1, lat2, lon2) == pytest.approx(
        expected, rel=1e-2
    )


@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2,expected",
    [
        (46.999, -120.577, 47.068, -120.671, 10.477),
        (47, -121, 47, -121, 0),
    ],
)
def test_get_dist_km_pyproj(lat1, lon1, lat2, lon2, expected):
    assert get_dist_km_pyproj(lat1, lon1, lat2, lon2) == pytest.approx(
        expected, rel=1e-2
    )


@pytest.mark.parametrize(
    "lats,lons,bearing,dist_km,expected",
    [
        ([46.999], [-120.577], "N", 10, (-120.577, 47.089)),
        ([46.999], [-120.577], "NE", 100, (-119.636, 47.631)),
    ],
)
def test_translate(lats, lons, bearing, dist_km, expected):
    translated = translate(lats, lons, bearing, dist_km)
    assert translated.x == pytest.approx(expected[0], rel=1e-4)
    assert translated.y == pytest.approx(expected[1], rel=1e-4)
    assert get_dist_km(lats[0], lons[0], translated.y, translated.x) == pytest.approx(
        dist_km, rel=1e-4
    )


@pytest.mark.parametrize(
    "lats,lons,bearing,dist_km,expected",
    [
        ([46.999], [-120.577], "N", 10, (-120.577, 47.089)),
        ([46.999], [-120.577], "NE", 100, (-119.636, 47.631)),
    ],
)
def test_translate_geolib(lats, lons, bearing, dist_km, expected):
    translated = translate_geolib(lats, lons, bearing, dist_km)
    assert translated.x == pytest.approx(expected[0], rel=1e-4)
    assert translated.y == pytest.approx(expected[1], rel=1e-4)
    assert get_dist_km(lats[0], lons[0], translated.y, translated.x) == pytest.approx(
        dist_km, rel=1e-4
    )


@pytest.mark.parametrize(
    "lats,lons,bearing,dist_km,expected",
    [
        ([46.999], [-120.577], "N", 10, (-120.577, 47.089)),
        ([46.999], [-120.577], "NE", 100, (-119.636, 47.631)),
    ],
)
def test_translate_pyproj(lats, lons, bearing, dist_km, expected):
    translated = translate_pyproj(lats, lons, bearing, dist_km)
    assert translated.x == pytest.approx(expected[0], rel=1e-4)
    assert translated.y == pytest.approx(expected[1], rel=1e-4)
    assert get_dist_km(lats[0], lons[0], translated.y, translated.x) == pytest.approx(
        dist_km, rel=1e-4
    )
