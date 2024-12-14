import pytest

from nmnh_ms_tools.databases.gvp import GVPVolcanoes


@pytest.fixture
def gvp():
    return GVPVolcanoes()


@pytest.mark.parametrize(
    "test_input, expected",
    [
        (("321030",), "321030"),
        (("Rainier",), "321030"),
        (("Rainier", "volcano"), "321030"),
        (("Rainier", "volcano", "United States"), "321030"),
        (("Rainier", "volcano", "United States | Canada"), "321030"),
        (("Rainier", "volcano", ["Canada", "United States"]), "321030"),
    ],
)
def test_find(test_input, expected, gvp):
    assert gvp.find(*test_input).iloc[0]["site_num"] == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        (("321030",), "321030"),
        (("Rainier",), "321030"),
        (("Sakurajima",), "282080"),
    ],
)
def test_find_volcano(test_input, expected, gvp):
    assert gvp.find_volcano(test_input)["site_num"] == expected
