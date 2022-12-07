"""Tests functions in AdamancerBot class"""
import pytest
from pytest import approx


from nmnh_ms_tools.utils.coords import parse_coordinate


@pytest.mark.parametrize(
    "test_input,kind,expected",
    [
        ("45 N", "latitude", 45),
        ("-45 S", "latitude", -45),
        ("45 30", "latitude", 45.5),
        (45.5, "latitude", 45.5),
        (-45.5, "latitude", -45.5),
        # Exotic coordinate formats
        ("N 45o30'00''", "latitude", 45.5),
        ("45 30.5 N", "latitude", 45.52),
        ("450000", "latitude", 45),
        ("45----", "latitude", 45),
        ("-1350000", "longitude", -135),
        (225, "longitude", -135),
    ],
)
def test_parse_coordinate_as_decimal(test_input, kind, expected):
    coord = parse_coordinate(test_input, kind)[0]
    assert coord.decimal == approx(expected, rel=1e-2)


@pytest.mark.parametrize(
    "test_input,kind,expected",
    [
        ("45 N", "latitude", ("45", "0", "0", "N")),
        ("45 30", "latitude", ("45", "30", "0", "N")),
    ],
)
def test_parse_coordinate_as_dms(test_input, kind, expected):
    coord = parse_coordinate(test_input, kind)[0]
    degrees, minutes, seconds, hemisphere = expected
    assert coord.degrees == degrees
    assert coord.minutes == minutes
    assert coord.seconds == seconds
    assert coord.hemisphere == hemisphere


@pytest.mark.parametrize(
    "test_input,kind,expected",
    [
        ("45 N", "latitude", "45 N"),
        ("45 30", "latitude", "45 30 N"),
        (45.5, "latitude", "45.5"),
        (45.50, "latitude", "45.5"),
    ],
)
def test_coordinate_str(test_input, kind, expected):
    coord = parse_coordinate(test_input, kind)[0]
    assert str(parse_coordinate(test_input, kind)[0]) == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("45 N", 111),
        ("45 30 N", 2),
        ("45 30 30 N", 0.03),
        (45.5, 11.1),
        (45.25, 1.11),
        (45.125, 0.111),
    ],
)
def test_estimate_precision(test_input, expected):
    coord = parse_coordinate(test_input, "latitude")[0]
    assert coord.estimate_precision() == approx(expected, rel=1e-2)


@pytest.mark.parametrize(
    "test_input,kind",
    [
        ("91 N", "latitude"),
        ("365 W", "longitude"),
    ],
)
def test_out_of_bounds_coordinates(test_input, kind):
    with pytest.raises(ValueError):
        parse_coordinate(test_input, kind)


@pytest.mark.parametrize("test_input", [None])
def test_invalid_input(test_input):
    with pytest.raises(TypeError):
        parse_coordinate(test_input, "latitude")


@pytest.mark.parametrize(
    "test_input,expected", [("44 60 N", "45 N"), ("44 59 60 N", "45 N")]
)
def test_sixties(test_input, expected):
    assert str(parse_coordinate(test_input, "latitude")[0]) == expected


def test_delimited_input():
    coords = parse_coordinate("40 N; 45 N; 50 N", "latitude")
    assert [str(c) for c in coords] == ["40 N", "45 N", "50 N"]


def test_is_dms():
    assert parse_coordinate("45 0 0 N", "latitude")[0].is_dms()
    assert not parse_coordinate(45, "latitude")[0].is_dms()


def test_is_decimal():
    assert not parse_coordinate("45 0 0 N", "latitude")[0].is_decimal()
    assert parse_coordinate(45, "latitude")[0].is_decimal()


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("45.5 N", "45 30 N"),
        ("45 30.5 N", "45 30 30 N"),
        ("45 0 30.5 N", "45 0 30.5 N"),
    ],
)
def test_dms_with_decimals(test_input, expected):
    assert str(parse_coordinate(test_input, "latitude")[0]) == expected


def test_illegal_dms_with_decimals():
    with pytest.raises(ValueError):
        parse_coordinate("45 30.5 30 N", "latitude")
