"""Tests geometry helper functions"""

import pytest
from pytest import approx

from shapely.geometry import Point, box
from shapely.affinity import scale, translate as shp_translate

from nmnh_ms_tools.tools.geographic_operations import (
    NaiveGeoMetry,
    GeoMetry,
    am_longitudes,
    azimuth_uncertainty,
    bounding_box,
    crosses_180,
    draw_circle,
    draw_polygon,
    epsg_id,
    get_azimuth,
    get_dist_km,
    pm_longitudes,
    translate,
)


DEG_AT_EQUATOR = 111.2


@pytest.fixture
def shapes():
    """Creates a set of shapes for testing"""
    shape = box(0, 0, 1, 1)
    return {
        "base": shape,
        "reordered": box(1, 1, 0, 0),
        "within": scale(shape, xfact=2, yfact=2),
        "contains": scale(shape, xfact=0.5, yfact=0.5),
        "overlaps": shp_translate(shape, xoff=0.5, yoff=0.5),
        "touches": shp_translate(shape, xoff=1, yoff=1),
        "disjoint": shp_translate(shape, xoff=2, yoff=2),
    }


def test_bounding_box():
    assert bounding_box(0, 0, 1, 1) == box(0, 0, 1, 1)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("EPSG:4326", "EPSG:4326"),
        ("epsg:4326", "EPSG:4326"),
        ("WGS 84", "EPSG:4326"),
        ("WGS 1984 (WGS 1984)", "EPSG:4326"),
    ],
)
def test_epsg_id(test_input, expected):
    assert epsg_id(test_input) == expected


@pytest.mark.parametrize(
    "test_input, expected", [("N", 0), ("NW", 315), ("NNW", 337.5), (90, 90)]
)
def test_get_azimuth(test_input, expected):
    assert get_azimuth(test_input) == approx(expected, rel=1e-2)


def test_draw_polygon(shapes):
    shape = draw_polygon(0, 0, DEG_AT_EQUATOR / 2, 4)
    assert shape.area == approx(1, rel=1e-2)


def test_get_dist_km():
    assert get_dist_km(0, 0, 0, 1) == approx(110.6, rel=1e-2)
    assert get_dist_km(0, 0, 1, 0) == approx(110.6, rel=1e-2)
    assert get_dist_km(0, 0, 1, 1) == approx(156.4, rel=1e-2)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ((0, 0, "N", 110.6), (0, 1)),
        ((0, 0, "NE", 156.4), (1, 1)),
    ],
)
def test_translate(test_input, expected):
    translated = translate(*test_input)
    assert translated.x == approx(expected[0], rel=1e-2)
    assert translated.y == approx(expected[1], rel=1e-2)


@pytest.mark.parametrize(
    "test_input, expected", [("N", 45), ("NW", 22.5), ("NNW", 11.25), (125, 5.75)]
)
def test_azimuth_uncertainty(test_input, expected):
    azimuth = get_azimuth(test_input)
    assert azimuth_uncertainty(azimuth) == approx(expected, rel=1e-2)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ((0, 1), (False, [0, 1], [0, 1])),
        ((175, -175), (True, [175, -175], [175, 185])),
        ((175, 185), (True, [175, -175], [175, 185])),
    ],
)
def test_antimeridian(test_input, expected):
    assert crosses_180(test_input) == expected[0]
    assert pm_longitudes(test_input) == expected[1]
    assert am_longitudes(test_input) == expected[2]


def test_naive_geometry_bool(shapes):
    assert NaiveGeoMetry(shapes["base"])


@pytest.mark.skip
def test_naive_geometry_eq(shapes):
    assert NaiveGeoMetry(shapes["base"]) == NaiveGeoMetry(shapes["reordered"])


def test_native_geometry_iter(shapes):
    expected = [(0, 1), (1, 1), (1, 0), (0, 0), (0, 1)]
    assert list(NaiveGeoMetry(shapes["base"])) == expected


def test_native_geometry_len(shapes):
    assert len(NaiveGeoMetry(shapes["base"])) == 5


def test_native_geometry_str(shapes):
    expected = "POLYGON ((1 0, 1 1, 0 1, 0 0, 1 0))"
    assert str(NaiveGeoMetry(shapes["base"])) == expected


def test_native_geometry_centroid(shapes):
    lng, lat = NaiveGeoMetry(shapes["base"]).centroid.coords[0]
    assert lng == 0.5
    assert lat == 0.5


def test_native_geometry_change_crs(shapes):
    with pytest.raises(AttributeError):
        NaiveGeoMetry(shapes["base"]).crs = "FAKE CRS"


@pytest.mark.skip
def test_native_geometry_ellipse(shapes):
    pass


def test_native_geometry_height_km(shapes):
    height_km = NaiveGeoMetry(shapes["base"]).height_km
    assert height_km == approx(DEG_AT_EQUATOR, rel=1e-2)


def test_native_geometry_lat_lngs(shapes):
    expected = [(0, 1), (1, 1), (1, 0), (0, 0), (0, 1)]
    assert NaiveGeoMetry(shapes["base"]).lat_lngs == expected


def test_native_geometry_latitudes(shapes):
    expected = [0, 1, 1, 0, 0]
    assert NaiveGeoMetry(shapes["base"]).latitudes == expected


def test_native_geometry_longitudes(shapes):
    expected = [1, 1, 0, 0, 1]
    assert NaiveGeoMetry(shapes["base"]).longitudes == expected


def test_native_geometry_width_km(shapes):
    width_km = NaiveGeoMetry(shapes["base"]).width_km
    assert width_km == approx(DEG_AT_EQUATOR, rel=1e-2)


def test_native_geometry_xy(shapes):
    expected = [(1, 1, 0, 0, 1), (0, 1, 1, 0, 0)]
    assert NaiveGeoMetry(shapes["base"]).xy == expected


def test_native_geometry_x(shapes):
    expected = [1, 1, 0, 0, 1]
    assert NaiveGeoMetry(shapes["base"]).x == expected


def test_native_geometry_y(shapes):
    expected = [0, 1, 1, 0, 0]
    assert NaiveGeoMetry(shapes["base"]).y == expected


def test_native_geometry_radius_km(shapes):
    geom = NaiveGeoMetry(shapes["base"])
    geom._radius_km = None
    assert geom.radius_km == approx(78.4, rel=1e-2)


def test_native_geometry_radius_km_of_point(shapes):
    geom = NaiveGeoMetry(Point(0, 0))
    geom.radius_km = DEG_AT_EQUATOR / 2
    assert geom.area == approx(1, rel=1e-2)


def test_native_geometry_invalid_radius_km(shapes):
    with pytest.raises(ValueError):
        NaiveGeoMetry(shapes["base"]).radius_km = "str"


def test_native_geometry_shape(shapes):
    geom = NaiveGeoMetry(Point(0, 0), radius_km=DEG_AT_EQUATOR / 2)
    assert geom.area == approx(1, rel=1e-2)


@pytest.mark.skip
def test_native_geometry_hull(shapes):
    pass


def test_center(shapes):
    assert NaiveGeoMetry(shapes["base"]).center == Point(0.5, 0.5)


def test_centroid(shapes):
    centroid = NaiveGeoMetry(shapes["base"]).centroid
    assert centroid == NaiveGeoMetry(Point(0.5, 0.5))


def test_contains(shapes):
    assert NaiveGeoMetry(shapes["base"]).contains(shapes["contains"])


def test_within(shapes):
    assert NaiveGeoMetry(shapes["base"]).within(shapes["within"])


def test_overlaps(shapes):
    assert NaiveGeoMetry(shapes["base"]).overlaps(shapes["overlaps"])


def test_touches(shapes):
    assert NaiveGeoMetry(shapes["base"]).touches(shapes["touches"])


def test_disjoint(shapes):
    assert NaiveGeoMetry(shapes["base"]).disjoint(shapes["disjoint"])


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("contains", True),
        ("within", True),
        ("overlaps", True),
        ("touches", True),
        ("disjoint", False),
    ],
)
def test_intersects(shapes, test_input, expected):
    if expected:
        assert NaiveGeoMetry(shapes["base"]).intersects(shapes[test_input])
    else:
        assert not NaiveGeoMetry(shapes["base"]).intersects(shapes[test_input])


def test_intersects(shapes):
    geom = NaiveGeoMetry(shapes["base"])
    other = NaiveGeoMetry(shapes["contains"])
    assert geom.intersection(other) == other


def test_clone(shapes):
    geom = NaiveGeoMetry(shapes["base"])
    assert geom.clone() == geom


def test_similar_to(shapes):
    bbox = box(0.0001, 0.0001, 0.9999, 0.9999)
    assert NaiveGeoMetry(shapes["base"]).similar_to(bbox)


def test_similar_to_with_args(shapes):
    bbox = box(0.1, 0.1, 0.9, 0.9)
    assert NaiveGeoMetry(shapes["base"]).similar_to(bbox, 0.9, 0.5)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("N", (0.0, 0.5, 1.0, 1.0)),
        ("W", (0.0, 0, 0.5, 1.0)),
        ("NW", (0.0, 0.5, 0.5, 1.0)),
        ("center", (0.25, 0.25, 0.75, 0.75)),
    ],
)
def test_subsection(shapes, test_input, expected):
    geom = NaiveGeoMetry(shapes["base"])
    subsection = geom.subsection(test_input)
    assert geom.subsection(test_input).bounds == expected
    assert subsection.supersection() == geom
