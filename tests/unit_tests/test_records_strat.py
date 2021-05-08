import pytest

from nmnh_ms_tools.bots import AdamancerBot
from nmnh_ms_tools.records.stratigraphy.chronostrat import (
    parse_chronostrat,
    ChronoStrat
)




def test_chronostrat_range():
    data = {
        'earliestPeriodOrLowestSystem': 'Permian',
        'latestPeriodOrHighestSystem': 'Triassic'
    }
    result = parse_chronostrat(data).to_dwc()

    expected = {
        'earliestEonOrLowestEonothem': 'Phanerozoic',
        'earliestEraOrLowestErathem': 'Paleozoic',
        'earliestPeriodOrLowestSystem': 'Permian',
        'latestEonOrHighestEonothem': 'Phanerozoic',
        'latestEraOrHighestErathem': 'Mesozoic',
        'latestPeriodOrHighestSystem': 'Triassic'
    }

    assert result == expected


def test_chronostrat_synonym():
    data = {
        'earliestEpochOrLowestSeries': 'Lias',
    }
    result = parse_chronostrat(data).to_dwc()

    expected = {
        'earliestEonOrLowestEonothem': 'Phanerozoic',
        'earliestEraOrLowestErathem': 'Mesozoic',
        'earliestPeriodOrLowestSystem': 'Triassic',
        'earliestEpochOrLowestSeries': 'Upper Triassic',
        'earliestAgeOrLowestStage': 'Rhaetian',
        'latestEonOrHighestEonothem': 'Phanerozoic',
        'latestEraOrHighestErathem': 'Mesozoic',
        'latestPeriodOrHighestSystem': 'Jurassic',
        'latestEpochOrHighestSeries': 'Lower Jurassic',
        'latestAgeOrHighestStage': 'Toarcian'
    }

    assert result == expected


def test_chronostrat_delimited():
    data = 'Phanerozoic: Mesozoic: Triassic: Upper: Rhaetian'
    result = parse_chronostrat(data).to_dwc()

    expected = {
        'earliestEonOrLowestEonothem': 'Phanerozoic',
        'earliestEraOrLowestErathem': 'Mesozoic',
        'earliestPeriodOrLowestSystem': 'Triassic',
        'earliestEpochOrLowestSeries': 'Upper Triassic',
        'earliestAgeOrLowestStage': 'Rhaetian',
        'latestEonOrHighestEonothem': 'Phanerozoic',
        'latestEraOrHighestErathem': 'Mesozoic',
        'latestPeriodOrHighestSystem': 'Triassic',
        'latestEpochOrHighestSeries': 'Upper Triassic',
        'latestAgeOrHighestStage': 'Rhaetian'
    }

    assert result == expected


def test_chronostrat_delimited_with_synonym():
    data = 'Phanerozoic: Mesozoic: Triassic: Lias'
    result = parse_chronostrat(data).to_dwc()

    expected = {
        'earliestEonOrLowestEonothem': 'Phanerozoic',
        'earliestEraOrLowestErathem': 'Mesozoic',
        'earliestPeriodOrLowestSystem': 'Triassic',
        'earliestEpochOrLowestSeries': 'Upper Triassic',
        'earliestAgeOrLowestStage': 'Rhaetian',
        'latestEonOrHighestEonothem': 'Phanerozoic',
        'latestEraOrHighestErathem': 'Mesozoic',
        'latestPeriodOrHighestSystem': 'Jurassic',
        'latestEpochOrHighestSeries': 'Lower Jurassic',
        'latestAgeOrHighestStage': 'Toarcian'
    }

    assert result == expected
