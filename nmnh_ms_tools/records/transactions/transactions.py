"""Defines tools for working with EMu transactions"""

import re
from collections import Counter
from datetime import datetime, timedelta
from functools import cached_property
from typing import Iterator

import yaml

from xmu import EMuDate, EMuRecord

from ...utils import LazyAttr, add_years


class Contact(EMuRecord):
    """Container for a transaction contact"""

    def __init__(self, *args, **kwargs):
        kwargs["module"] = "eparties"
        super().__init__(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        """The name of the contact"""
        if self.is_person():
            return self["NamFullName"]
        try:
            return the(self["NamOrganisation"])
        except KeyError:
            return ""

    @property
    def email(self) -> str:
        """The email for the contact"""
        return self["AddEmail"]

    @property
    def affiliation(self) -> str:
        """The current affiliation for the contact"""
        grid = self.grid("AffAffiliationRef_tab")
        current = grid[{"AffCurrent_tab": "Yes"}][0]
        return the(current["AffAffiliationRef_tab"]["NamOrganisation"])

    def is_person(self) -> bool:
        """Tests if the contact is a person

        Returns
        -------
        bool
            True if the contact is a person
        """
        return bool(self.get("NamLast"))

    def is_org(self) -> bool:
        """Tests if the contact is an organization

        Returns
        -------
        bool
            True if the contact is an organization
        """
        return bool(self.get("NamOrganisation"))

    def is_deceased(self) -> bool:
        """Tests if the contact is deceased

        Returns
        -------
        bool
            True if the contact is deceased
        """
        return bool(self.get("BioDeathDate"))


class ShippingInfo:
    """Container for shipping info associated with a transaction

    Attributes
    ----------
    shipped : bool
        True if the shipment has shipped
    shipped_date : EMuDate
        the most recent shipment date for an item associated with a transaction
    acknowledged_date : EMuDate
        the most recent acknowledgment date for an item associated with a transaction
    """

    def __init__(self, item):
        item_statuses = []
        item_shipped_dates = []
        item_ack_dates = []
        for shipment in item.get("ProShipmentRef_tab", []):
            item_statuses.append(shipment["InfStatus"])
            item_shipped_dates.append(shipment["DatScheduledMovementDate"])
            item_ack_dates.append(shipment["DatAcknowledgementDate"])

        item_shipped_dates = [d for d in item_shipped_dates if d]
        item_ack_dates = [d for d in item_ack_dates if d]

        self.shipped = "SHIPPED" in item_statuses
        self.shipped_date = max(item_shipped_dates) if item_shipped_dates else None
        self.acknowledged_date = max(item_ack_dates) if item_ack_dates else None


class TransactionItem(EMuRecord):
    """Container for a transaction item"""

    def __init__(self, *args, **kwargs):
        kwargs["module"] = "enmnhtransactionitems"
        super().__init__(*args, **kwargs)
        self.unit = None

    @property
    def division(self) -> str:
        """The name of the transacting division"""
        return {"GEM": "MIN"}.get(self.catalog, self.catalog)

    @property
    def catalog(self) -> str:
        """The name of the transacting catalog"""
        if self.unit != "MS":
            return self.unit
        for method, cat in (
            (self.is_gem, "GEM"),
            (self.is_met, "MET"),
            (self.is_min, "MIN"),
            (self.is_pet, "PET"),
        ):
            if method():
                return cat
        return "MS"

    @cached_property
    def shipping_info(self) -> ShippingInfo:
        """The shipping info associated with this item"""
        return ShippingInfo(self)

    @property
    def shipped_date(self) -> EMuDate:
        """The shipped date for this item"""
        return self.shipping_info.shipped_date

    @property
    def acknowledged_date(self) -> EMuDate:
        """The date on which the item was acknowledged"""
        return self.shipping_info.acknowledged_date

    def is_met(self) -> bool:
        """Tests whether a transaction item is from the meteroite collection

        Returns
        -------
        bool
            True if object is a from the meteroite collection
        """
        rec = self.get("ItmCatalogueRef", {})
        return (
            rec.get("CatDivision") == "Meteorites"
            or rec.get("CatCatalog") == "Meteorites"
            or self.get("ItmMuseumCode")
            in {
                "MET",
                "NASA",
                "NASA-G",
                "NASA-J",
                "NASA-J1",
                "NASA-J2",
                "NASA-JSC",
                "USNM",
            }
        )

    def is_min(self) -> bool:
        """Tests whether a transaction item is from the mineral collection

        Returns
        -------
        bool
            True if object is a from the mineral collection
        """
        return (
            self.get("ItmCatalogueRef", {}).get("CatCatalog") == "Minerals"
            or self.get("ItmMuseumCode") == "MIN"
        )

    def is_gem(self) -> bool:
        """Tests whether a transaction item is from the gem collection

        Returns
        -------
        bool
            True if object is a from the gem collection
        """
        return self.get("ItmCatalogueRef", {}).get("CatCatalog") == "Gems" or re.match(
            r"G[\- ]*\d", self.get("ItmCatalogueNumber", "")
        )

    def is_pet(self) -> bool:
        """Tests whether a transaction item is from the rock and ore collection

        Returns
        -------
        bool
            True if object is a from the rock and ore collection
        """
        rec = self.get("ItmCatalogueRef", {})
        return (
            rec.get("CatDivision") == "Petrology & Volcanology"
            or rec.get("CatCatalog") == "Rock & Ore Collections"
            or self.get("ItmMuseumCode") == "PET"
        )

    def is_outstanding(self) -> bool:
        """Tests whether a transaction item is outstanding

        Returns
        -------
        bool
            True if object is outstanding
        """
        return bool(self["ItmObjectCountOutstanding"])

    def shipped(self):
        """Tests whether a transaction item has been shipped

        Returns
        -------
        bool
            True if object has been shipped
        """
        return self.shipping_info.shipped


class Transaction(EMuRecord):
    """Container for a transaction

    Class Attributes
    ----------------
    trn_config : dict
        the transaction configuration, including dates and collection contacts for
        dunns
    """

    # Deferred class attributes are defined at the end of the file
    trn_config = None

    def __init__(self, *args, **kwargs):
        kwargs["module"] = "enmnhtransactions"
        super().__init__(*args, **kwargs)

    @property
    def unit(self) -> str:
        """The name of the transacting unit"""
        return {
            "Invertebrate Zoology": "IZ",
            "Paleobiology": "PAL",
            "Mineral Sciences": "MS",
        }[self["TraUnit"]]

    @property
    def division(self) -> str:
        """The name of the transacting division"""
        return {"GEM": "MIN"}.get(self.catalog, self.catalog)

    @property
    def catalog(self) -> str:
        """The name of the transacting catalog"""

        # Catalog logic is only implemented for Mineral Sciences
        if self.unit != "MS":
            return self.unit

        # Trying mapping catalog from the item list
        cats = Counter([i.catalog for i in self.tr_items if i.catalog != "DMS"])
        if cats and (len(cats) == 1 or max(cats.values()) > 2):
            return sorted(cats.items(), key=lambda kv: kv[1])[-1][0]

        # Fallback to staff who worked on the record. Note that approver is not
        # considered because that role is often handled by the chair.
        staff = []
        try:
            staff.append(self["TraInitiatorsRef_tab"][0]["NamFullName"])
        except KeyError:
            pass
        staff.append(self["TraEnteredByRef"]["NamFullName"])

        staff = [self.trn_config["initiators"].setdefault(s, "DMS") for s in staff]
        staff = [s for s in staff if s and s != "DMS"]

        if set(staff) == {"GEM", "MIN"}:
            return "GEM"
        elif len(set(staff)) == 1:
            return staff[0]
        return "DMS"

    @property
    def coll_contact(self) -> str:
        """The name of the collection contact"""
        contact = self.trn_config["map_contacts"][self.catalog]
        if contact.lower() == "initiator":
            contact = self["TraInitiatorsRef_tab"][0]["NamFullName"]
        return self.trn_config["contacts"][contact]

    @property
    def contact(self) -> Contact:
        """The current contact for the transaction"""
        try:
            grid = self.grid("TraTransactorsContactRef_tab")
            rec = grid[{"TraTransactorsRole_tab": "Primary"}][0][
                "TraTransactorsContactRef_tab"
            ]
        except KeyError:
            return Contact({})
        else:
            return Contact(rec)

    @property
    def orig_contact(self) -> Contact:
        """The original contact for the transaction"""
        grid = self.grid("TraTransactorsContactRef_tab")
        try:
            rec = grid[{"TraTransactorsRole_tab": "Original"}][0][
                "TraTransactorsContactRef_tab"
            ]
            return Contact(rec)
        except IndexError:
            return self.contact

    @property
    def org(self):
        """The organization associated with the transaction"""
        try:
            return Contact(self["TraTransactorsOrganizationRef_tab"][0])
        except (IndexError, KeyError):
            return None

    @property
    def tr_items(self) -> Iterator:
        """Iterates over the transaction item list"""
        for i, item in enumerate(self.get("TraTransactionRef_tab", [])):
            if not isinstance(item, TransactionItem):
                item = TransactionItem(item)
                item.unit = self.unit
                self["TraTransactionRef_tab"][i] == item
            yield item

    @property
    def open_date(self) -> EMuDate:
        """The date on which the transaction was opened"""
        return self["TraDateOpen"]

    @property
    def received_date(self) -> EMuDate:
        """The date on which the transaction was received by the museum"""
        return self["TraDateReceived"]

    @property
    def closed_date(self) -> EMuDate:
        """The date on which the transaction was closed"""
        return self["TraDateClosed"]

    @property
    def shipped_date(self) -> EMuDate:
        """The most recent shipment date for an item in this transaction"""
        if self.all_shipped():
            return max([i.shipped_date for i in self.tr_items])

    @property
    def acknowledged_date(self) -> EMuDate:
        """The most recent acknowledgment date for an item in this transaction"""
        if self.all_acknowledged():
            return max([i.acknowledged_date for i in self.tr_items])

    @property
    def init_date(self) -> EMuDate:
        """Returns the date that material was shipped or received"""
        dates = [
            self.open_date,
            self.received_date,
            self.shipped_date,
            self.get("AdmDateInserted"),
        ]
        return min([d for d in dates if d])

    @property
    def complete_date(self) -> EMuDate:
        """Returns the date the transaction was completed"""
        dates = [self.closed_date, self.acknowledged_date]
        return min([d for d in dates if d])

    def is_active(self) -> bool:
        """Tests whether the transaction record is active

        Returns
        -------
        bool
            True if the transaction record is active
        """
        return self["SecRecordStatus"] == "Active"

    def is_open(self) -> bool:
        """Tests whether a transaction item is active and open

        Returns
        -------
        bool
            True if the transaction is active and open
        """
        return self.is_active() and self["TraStatus"] == "OPEN"

    def is_closed(self) -> bool:
        """Tests whether a transaction item is active and closed

        Returns
        -------
        bool
            True if the transaction is active and closed
        """
        return self.is_active() and self["TraStatus"].startswith("CLOSED")

    def all_shipped(self) -> bool:
        """Tests whether all items in this transaction have shipped

        Returns
        -------
        bool
            True if all transaction items have shipped
        """
        return any(self.tr_items) and all([i.shipped() for i in self.tr_items])

    def all_acknowledged(self):
        """Tests whether all items in this transaction have been acknowledged

        Returns
        -------
        bool
            True if all transaction items have been acknowledged
        """
        return any(self.tr_items) and all([i.acknowledged_date for i in self.tr_items])


class Acquisition(Transaction):
    """Container for acquisition transactions"""

    pass


class Disposal(Transaction):
    """Container for disposal transactions"""

    pass


class LoanIncoming(Transaction):
    """Container for incoming loan transactions"""

    pass


class LoanOutgoing(Transaction):
    """Container for outgoing loan transactions"""

    @property
    def recipient(self) -> Contact:
        """The person or organization to which a loan was sent"""
        return self.org if self.org else self.orig_contact

    @property
    def level(self) -> str:
        """The dunning level for an outgoing loan"""
        if self.due_date:
            if self.is_almost_due():
                return "reminder"
            for key in ["escalate", "recall", "warn"]:
                if getattr(self, key)():
                    return key
        return "default"

    @property
    def due_date(self) -> EMuDate:
        """The due date of the loan

        If no due date is specified in the record, returns the open date plus
        three years instead.
        """
        if self["TraDueDate"]:
            return self["TraDueDate"]
        # If no due date, use three years from when the loan was opened
        return add_years(self.open_date, 3)

    @property
    def open_date(self) -> EMuDate:
        """The date on which the transaction was opened"""
        for key in ["TraDateOpen", "TraFromDate"]:
            if self[key]:
                return self[key]

    @property
    def num_dunns(self) -> int:
        """The number of dunns that have been sent since the last extension"""
        if self.due_date:
            return len(
                [d for d in self.get("LoaDunningDate0", []) if d > self.due_date]
            )
        return 0

    @property
    def last_interaction(self) -> EMuDate:
        """The date of the last interaction with the contact on this loan"""
        dates = []
        for key in ["TraDateOpen", "TraReceiptAcknowledgedDate"]:
            dates.append(self.get(key))
        for key in ["LoaDunningDate0", "LoaExtensionDate0"]:
            dates.extend(self.get(key, []))
        try:
            return sorted([d for d in dates if d])[-1]
        except IndexError:
            print(f"{self['TraNumber']}: Falling back to insert date")
            return self["AdmDateInserted"]

    def is_almost_due(self) -> bool:
        """Tests whether the loan is due within the next two weeks

        Returns
        -------
        bool
            True if the loan is due soon
        """
        return (
            self.is_open()
            and self.due_date
            and self.due_date > self.trn_config["overdue_date"]
            and (self.due_date.value - self.trn_config["overdue_date"]).days
            <= self.trn_config["grace_period"]
        )

    def is_overdue(self, grace_period=None) -> bool:
        """Tests whether the loan is overdue

        Parameters
        ----------
        grace_period : int
            a grace period in days. Added to the due date of the loan when determining
            whether to dunn.

        Returns
        -------
        bool
            True if the loan is overdue
        """
        if grace_period is None:
            grace_period = self.trn_config["grace_period"]
        return (
            self.is_open()
            and self.due_date
            and (self.trn_config["overdue_date"] - self.due_date.value).days
            > self.trn_config["grace_period"]
        )

    def warn(self) -> bool:
        """Tests if a dunning letter should warn the recipient

        True if the loan is overdue and the number of dunns is greater than the value
        for warn in the config file.
        """
        return (
            self.is_overdue()
            and self.trn_config["warn"]
            and self.num_dunns >= self.trn_config["warn"]
        )

    def escalate(self) -> bool:
        """Tests if a dunning letter should be escalated to the recipient's supervisor

        True if the loan is overdue and the number of dunns is greater than the value
        for escalate in the config file.
        """
        return (
            self.is_overdue()
            and self.trn_config["escalate"]
            and self.num_dunns >= self.trn_config["escalate"]
        )

    def recall(self) -> bool:
        """Tests if a dunning letter should recall the loan

        True if the loan is overdue and the due date is older than the recall date
        specified in the config file.
        """
        return (
            self.is_open()
            and self.trn_config["recall_date"]
            and self.due_date <= self.trn_config["recall_date"]
        )


def create_transaction(
    trn: EMuRecord,
) -> Acquisition | Disposal | LoanIncoming | LoanOutgoing | Transaction:
    """Creates a transaction object using the appropriate subclass

    Parameters
    ----------
    trn : EMuRecord
        an EMu transaction

    Returns
    -------
    Acquisition | Disposal | LoanIncoming | LoanOutgoing | Transaction
        the transaction in the appropriate subclass
    """
    try:
        return {
            "ACQUISITION": Acquisition,
            "DISPOSAL": Disposal,
            "LOAN INCOMING": LoanIncoming,
            "LOAN OUTGOING": LoanOutgoing,
        }[trn["TraType"]](trn)
    except KeyError:
        return Transaction(trn)


def the(val: str) -> str:
    """Prepends the definite article to the given value

    Parameters
    ----------
    val : str
        an organization name

    Returns
    -------
    str
        the organization name with "the" prepended if appropriate
    """
    startswith = (
        "american museum",
        "college of",
        "museum",
        "national",
        "university of",
        "state",
        "u.s.",
        "u. s.",
        "united states",
    )
    endswith = ("institute", "institute of technology", "institution")
    if not val:
        return ""
    if val.lower().startswith("the "):
        return val[0].lower() + val[1:]
    if (
        val.lower().startswith(startswith)
        or val.lower().endswith(endswith)
        or " of " in val
    ):
        return "the " + val
    return val


def _read_config(path: str = "config.yml") -> dict:
    """Reads the configuration file"""
    with open(path) as f:
        trn_config = yaml.safe_load(f)
        trn_config["dunner"] = trn_config["contacts"][trn_config["dunner"]]
        if not trn_config["overdue_date"]:
            trn_config["overdue_date"] = datetime.now().date() - timedelta(days=1)
        if not trn_config["recall_date"]:
            trn_config["recall_date"] = add_years(datetime.now().date(), -2)
    return trn_config


# Define deferred class attributes
LazyAttr(Transaction, "trn_config", _read_config)
