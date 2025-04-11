"""Tests Person"""

import pytest
from datetime import date, timedelta

from nmnh_ms_tools.records.transactions import (
    Transaction,
    TransactionItem,
    create_transaction,
)
from xmu import EMuDate, EMuRecord


Transaction.trn_config = {
    "dunner": "dunner@localhost",
    "overdue_date": date(1970, 1, 1),
    "recall_date": date(1968, 1, 1),
    "grace_period": 14,
    "num_days": 90,
    "warn": 1,
    "escalate": 2,
    "initiators": {
        "Meteorite Contact": "MET",
        "Mineralogy Contact": "MIN",
        "Petrology Contact": "PET",
    },
    "map_contacts": {},
    "contacts": {},
}


@pytest.fixture
def transaction():
    trn = {
        "TraNumber": 2345678,
        "TraType": "LOAN OUTGOING",
        "TraDateOpen": EMuDate("1970-01-01"),
        "LoaDunningDate0": [],
    }
    shp = {
        "InfStatus": "SHIPPED",
        "DatScheduledMovementDate": None,
        "DatAcknowledgementDate": None,
    }
    items = []
    for item in [
        {"ItmCatalogueRef": {"CatDivision": "Beep"}},
        {"ItmMuseumCode": "PET"},
        {"ItmCatalogueNumber": "G12345"},
    ]:
        item["ProShipmentRef_tab"] = [shp]
        items.append(item)
    trn["TraTransactionRef_tab"] = items
    return Transaction(trn)


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ({"TraUnit": "Invertebrate Zoology"}, "IZ"),
        ({"TraUnit": "Paleobiology"}, "PAL"),
    ],
)
def test_transaction_unit(test_input, expected):
    trn = create_transaction(test_input)
    assert trn.unit == trn.division == trn.catalog == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ({"ItmCatalogueRef": {"CatCatalog": "Gems"}}, "GEM"),
        ({"ItmCatalogueRef": {"CatCatalog": "Meteorites"}}, "MET"),
        ({"ItmCatalogueRef": {"CatCatalog": "Minerals"}}, "MIN"),
        ({"ItmCatalogueRef": {"CatCatalog": "Rock & Ore Collections"}}, "PET"),
        ({"ItmCatalogueNumber": "G10000"}, "GEM"),
        ({"ItmMuseumCode": "MET"}, "MET"),
        ({"ItmMuseumCode": "NASA"}, "MET"),
        ({"ItmMuseumCode": "USNM"}, "MET"),
        ({"ItmMuseumCode": "MIN"}, "MIN"),
        ({"ItmMuseumCode": "PET"}, "PET"),
    ],
)
def test_transaction_unit_minsci(test_input, expected):
    item = TransactionItem(test_input)
    item.unit = "MS"
    div = "MIN" if expected == "GEM" else expected
    assert item.catalog == expected
    assert item.division == div


@pytest.mark.parametrize(
    "test_input", ["TraDateOpen", "TraDateReceived", "AdmDateInserted"]
)
def test_init_date(test_input):
    trn = {}
    for key in ["TraDateOpen", "TraDateReceived", "AdmDateInserted"]:
        trn[key] = "1970-01-02"
    trn[test_input] = "1970-01-01"
    assert str(create_transaction(trn).init_date) == "1970-01-01"


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ({"TraStatus": "OPEN", "SecRecordStatus": "Active"}, True),
        ({"TraStatus": "OPEN", "SecRecordStatus": "Inactive"}, False),
        ({"TraStatus": "OPEN PENDING", "SecRecordStatus": "Active"}, False),
        ({"TraStatus": "CLOSED", "SecRecordStatus": "Active"}, False),
    ],
)
def test_is_open(test_input, expected):
    assert Transaction(test_input).is_open() == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ({"TraStatus": "CLOSED", "SecRecordStatus": "Active"}, True),
        ({"TraStatus": "CLOSED BALANCED", "SecRecordStatus": "Active"}, True),
        ({"TraStatus": "CLOSED UNBALANCED", "SecRecordStatus": "Active"}, True),
        ({"TraStatus": "CLOSED", "SecRecordStatus": "Inactive"}, False),
        ({"TraStatus": "OPEN", "SecRecordStatus": "Active"}, False),
    ],
)
def test_is_closed(test_input, expected):
    assert create_transaction(test_input).is_closed() == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ({"TraDueDate": "1968-01-01"}, True),
        ({"TraDueDate": "1969-12-15"}, True),
        ({"TraDueDate": "1969-12-20"}, False),
        ({"TraDueDate": "1970-01-01"}, False),  # exact due date
        ({"TraDueDate": "1970-01-15"}, False),
    ],
)
def test_is_overdue(test_input, expected):
    test_input.update(
        {
            "TraType": "LOAN OUTGOING",
            "TraStatus": "OPEN",
            "SecRecordStatus": "Active",
        }
    )
    assert create_transaction(test_input).is_overdue() == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ({"TraDueDate": "1968-01-01"}, False),
        ({"TraDueDate": "1969-12-15"}, False),
        ({"TraDueDate": "1970-01-01"}, False),  # exact due date
        ({"TraDueDate": "1970-01-15"}, True),
        ({"TraDueDate": "1970-01-16"}, False),
    ],
)
def test_is_overdue(test_input, expected):
    test_input.update(
        {
            "TraType": "LOAN OUTGOING",
            "TraStatus": "OPEN",
            "SecRecordStatus": "Active",
        }
    )
    assert create_transaction(test_input).is_almost_due() == expected
