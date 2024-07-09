"""Tests geographic name parsers"""

import pytest

from nmnh_ms_tools.tools.geographic_names.parsers import (
    BetweenParser,
    BorderParser,
    DirectionParser,
    parse_localities,
)
from nmnh_ms_tools.tools.geographic_names.parsers.junction import get_road, get_junction
from nmnh_ms_tools.tools.geographic_names.parsers.feature import append_feature_type


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("Between Ellensburg and Kittitas", ["Ellensburg", "Kittitas"]),
        ("On road from Ellensburg to Kittitas", ["Ellensburg", "Kittitas"]),
        pytest.param("Between Ellensburg", None, marks=pytest.mark.xfail),
    ],
)
def test_between_parser(test_input, expected):
    assert BetweenParser(test_input).features == expected


@pytest.mark.parametrize(
    "test_input",
    [
        "Border of Kittitas and King Counties",
        "Border of Kittitas County and King County",
        pytest.param("Border of King Co. and Kittitas Co.", marks=pytest.mark.xfail),
    ],
)
def test_border_parser(test_input):
    expected = {"Kittitas County", "King County"}
    assert set(BorderParser(test_input).features) == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("1 km N of Ellensburg", {"dist": 1, "bearing": "N"}),
        ("Ellensburg, 1 km N of", {"dist": 1, "bearing": "N"}),
        ("Ellensburg (1 km N of)", {"dist": 1, "bearing": "N"}),
        ("1 km NW of Ellensburg", {"dist": 1, "bearing": "NW"}),
    ],
)
def test_direction_parser(test_input, expected):
    result = DirectionParser(test_input)
    assert result.avg_dist_km() == pytest.approx(expected["dist"])
    assert result.bearing == expected["bearing"]


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("10.5 km N of Ellensburg", 0.5),
        ("10.6 km N of Ellensburg", 0.2),
        ("10.75 km N of Ellensburg", 0.25),
        ("10 km N of Ellensburg", 5),
        ("40 km N of Ellensburg", 5),
        ("100 km N of Ellensburg", 50),
        ("2000 km N of Ellensburg", 500),
    ],
)
def test_direction_parser_precision(test_input, expected):
    result = DirectionParser(test_input).precision_km()
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "test_input", ["Chestnut St", "WA Route 97", "WA Rt 97", "WA 97"]
)
def test_get_road(test_input):
    assert get_road(test_input)


@pytest.mark.parametrize(
    "test_input",
    [
        "Junction between University Way and Chestnut St",
        "Past intersection with University Way",
    ],
)
def test_get_junction(test_input):
    assert get_junction(test_input)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("Cat and Dog Islands", ["Cat Island", "Dog Island"]),
        ("Cat and Dog Island", ["Cat Island", "Dog Island"]),
        ("cat and dog islands", ["Cat Island", "Dog Island"]),
        ("Cat Gulf and Dog Island", ["Cat Gulf", "Dog Island"]),
        ("Gulf and Dog Island", ["Gulf Island", "Dog Island"]),
    ],
)
def test_append_feature_type(test_input, expected):
    assert append_feature_type(test_input) == expected


@pytest.mark.parametrize(
    "test_input, expected",
    [
        (
            "20 km south of Iceland; Atlantic Ocean, North",
            ["20 km S of Iceland", "North Atlantic Ocean"],
        ),
        ("37 km E of Riberalta on road to Guayaramerin", ["37 km E of Riberalta"]),
        (
            "Approach To Windam Ray, S.Stephens Passage",
            ["Off of Windam Ray", "S Stephens Passage"],
        ),
        (
            "Aranjuez surroundings. Circa 7 km NW, S of jct. E-5 and M-40",
            ["Aranjuez (near)", "S of junction of E-5 and M-40"],
        ),
        (
            "BR 156, road between Calçoene and Oiapoque, 60 Km SSE of Oiapoque",
            ["BR 156", "Between Calcoene and Oiapoque", "60 Km SSE of Oiapoque"],
        ),
        ("Bouanane, 30 Km NE", ["30 km NE of Bouanane"]),
        (
            "Carteret Co, S Part Of Cedar Island, At U.S. Condor Installation",
            ["Carteret Co", "S Cedar Island", "U S Condor Installation"],
        ),
        (
            "Castle Hayne, 4.5mi NE of; end of NC Route 2023",
            ["4.5 mi NE of Castle Hayne", "NC Route 2023"],
        ),
        (
            "Ceylon. Gode-kanda (E. of Hiniduma): Galle District.",
            ["Ceylon", "Gode-kanda", "E of Hiniduma", "Galle District"],
        ),
        (
            "El Paso Quad. 2.5mi W Of Powwow Tanks",
            ["El Paso Quad", "2.5 mi W of Powwow Tanks"],
        ),
        ("Fayetteville, SSW of, ca. 3.4 mi (by road)", ["SSW of Fayetteville"]),
        (
            "Fiji Islands, Lau Group, Matuku Island, 200 Meters South of Happen "
            "Channel, Southside",
            [
                "Fiji Islands",
                "Lau Group",
                "Matuku Island",
                "200 m S of Happen Channel",
                "Southside",
            ],
        ),
        (
            "Great Bristol Bay, 25 Miles South Of Round Island",
            ["Great Bristol Bay", "25 mi S of Round Island"],
        ),
        (
            "Great Smoky Mountains National Park, on Miry Ridge Trail, 1.64 mi "
            "(by trail) N of its junction with Appalachian Trail",
            [
                "Great Smoky Mountains National Park",
                "Miry Ridge Trail",
                "1.64 mi N of junction of {road} and Appalachian Trail",
            ],
        ),
        (
            "Happy Island and Sad Lagoon",
            ["Happy Island and Sad Lagoon", "Happy Island", "Sad Lagoon"],
        ),
        ("In the NW 1/4 sec. 3, T. 9 S., R. 22 W.", ["NW Sec. 3 T9S R22W"]),
        ("Indianola Is. To Boothbay Pt.", ["Indianola Is", "Boothbay Pt"]),
        (
            "Indianola Is. To Gallinipyer Point. Lavaca And Matagorda Bays",
            [
                "Indianola Is",
                "Gallinipyer Point",
                "Lavaca and Matagorda Bays",
                "Lavaca Bay",
                "Matagorda Bay",
            ],
        ),
        (
            "Lamont Geological Observatory, core A167-25, on slope of Blake " "Plateau",
            ["Lamont Geological Observatory", "Blake Plateau"],
        ),
        (
            "Mauna Ulu. Approx. 250 M. S80w Of W. End Of Mauna Ulu",
            ["Mauna Ulu", "250 m S80W of W End Of Mauna Ulu"],
        ),
        (
            "Namatanai sub-province; Hans Meyer Range; lower approach ridges to "
            "Mt. Angil, c. 9 km. (map distance) N.W. of Taron on east coast.",
            ["Hans Meyer Range", "Mt Angil", "9 km NW of Taron", "Eastern {feature}"],
        ),
        ("N A R (North Astrolabe Reef)", ["North Astrolabe Reef"]),
        ("Near Bouanane", ["Bouanane (near)"]),
        (
            "Near summit of Mt. Nabemba along trail, SSW of Souanke",
            ["Mt Nabemba", "SSW of Souanke"],
        ),
        ("North Carolina", ["North Carolina"]),
        ("North Carolina - Tennessee", ["North Carolina", "Tennessee"]),
        ("North Carolina / Tennessee", ["North Carolina", "Tennessee"]),
        (
            "Outer or SE slope of Pickles Reef off Key Largo",
            ["SE Pickles Reef", "Off of Key Largo", "Outer {reef}"],
        ),
        (
            "Papua New Guinea, Hermit Islands: Tset Island, Drop Off Just West "
            "of North End of Island",
            ["Papua New Guinea", "Hermit Islands", "Tset Island", "W of N {island}"],
        ),
        (
            "Paraguay, Paraguari. Arroyo Yuguyty, 7 km E of Nueva Italia",
            ["Paraguay", "Paraguari", "Arroyo Yuguyty", "7 km E of Nueva Italia"],
        ),
        (
            "Past junction with Capstan St. Lawrence notes a resemeblance "
            "to specimens collected near Lime on opposite side of river.",
            ["Junction of {road} and Capstan St", "Lime (near)", "{river}"],
        ),
        (
            "Pembrokeshire - point inside of Skomer Island. Of western point of "
            "Martin Haven.",
            ["Pembrokeshire", "Skomer Island", "W Martin Haven"],
        ),
        (
            "Pensacola, Butcher Pen Pt. To Magnolia Bluff",
            ["Pensacola", "Butcher Pen Pt", "Magnolia Bluff"],
        ),
        (
            "Provincia de Requena, Gulf of Mexico",
            ["Provincia de Requena", "Gulf of Mexico"],
        ),
        ("Puerto Rico, South Coast", ["S Puerto Rico"]),
        (
            "Quebrada Angulo, 4 km. s. of Lebrija, Dept. de Santander",
            ["Quebrada Angulo", "4 km S of Lebrija", "dept de Santander"],
        ),
        (
            "Quininde Cantón: Bilsa Biological Station. Mache mountains, 35 km "
            "W of Quinindé, 5 km W of Santa Isabel.",
            [
                "Quininde Canton",
                "Bilsa Biological Station",
                "35 km W of Quininde",
                "5 km W of Santa Isabel",
            ],
        ),
        ("Round Island And Vicinity", ["Round Island (near)"]),
        ("S end of Gray Lake", ["S Gray Lake"]),
        ("S.Coast of Oahu Island", ["S Oahu Island"]),
        (
            "S.E. Thailand, Prov.: Trat. Koh Chang Island.",
            ["SE Thailand", "Prov", "Trat", "Koh Chang Island"],
        ),
        (
            "S.W. slope of Mt. Langford, Elev. 9100 ft. Absaroka Range",
            ["SW Mt Langford", "Absaroka Range"],
        ),
        ("Sabana de la Mar, 1.7 km W of", ["1.7 km W of Sabana de la Mar"]),
        ("Sala Y Gomez Island, North of", ["N of Sala Y Gomez Island"]),
        (
            "Seven Valleys, NNW of, on PA Route 616, two mi. NNW of its "
            "junction with PA Route 214, Springfield Township",
            [
                "NNW of Seven Valleys",
                "2 mi NNW of junction of {road} and PA Route 214",
                "Springfield Township",
                "PA Route 616",
            ],
        ),
        (
            "Seymour Canal And Kelp Bay",
            ["Seymour Canal and Kelp Bay", "Seymour Canal", "Kelp Bay"],
        ),
        (
            "Shenandoah National Park, on Pocosin Road, 0.5 mi (by road) S of "
            "its junction with Skyline Drive, near Pocosin Cabin",
            [
                "Shenandoah National Park",
                "Pocosin Road",
                "0.5 mi S of junction of {road} and Skyline Drive",
                "Pocosin Cabin (near)",
            ],
        ),
        ("Slough At S.E. End Of San Francisco Bay", ["SE San Francisco Bay"]),
        (
            "South Georgia and the South Shetland Islands",
            ["South Georgia and the South Shetland Islands"],
        ),
        ("St. Lawrence", ["St Lawrence"]),
        (
            "The Turks and Caicos Islands",
            ["Turks and Caicos Islands", "Turks Island", "Caicos Island"],
        ),
        ("U.S. Virgin Islands", ["U S Virgin Islands"]),
        ("Vicinity of Round Island", ["Round Island (near)"]),
        (
            "Vohiparara, 3 Km By Road NNW; Prefecture De Fianarantsoa",
            ["3 km NNW of Vohiparara", "Prefecture De Fianarantsoa"],
        ),
        (
            "W Of Cape Simpson, Simpson Test Well No.1, Core At 238-256ft.",
            ["W of Cape Simpson", "Simpson Test Well No 1"],
        ),
        # ('West Coast District Municipality', []),
        ("West Coast Of Florida", ["W Florida"]),
        ("Western Cape; Central Vishayas", ["Western {cape}", "Central Vishayas"]),
        ("Western point of Point Martin", ["W Point Martin"]),
        (
            "Wyville--Thomson Ridge; between the Faroe Islands and Scotland",
            ["Wyville-Thomson Ridge", "Between Faroe Islands and Scotland"],
        ),
    ],
)
def test_parse_localities(test_input, expected):
    features = []
    for parsed in parse_localities(test_input):
        for feature in parsed:
            if not isinstance(feature, list):
                feature = [feature]
            features.extend([str(f).lower().strip('"') for f in feature])
    assert set(features) == set([f.lower() for f in expected])
