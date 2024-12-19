"""Tests Reference from references2 module"""

import pytest
from xmu import EMuDate

from nmnh_ms_tools.records.references.references2 import Reference


@pytest.fixture
def ref():
    return Reference("10.1093/petrology/egu024")


def test_ref_from_doi(ref):
    assert str(ref.author[0]) == "A. T. Mansur"
    assert (
        ref.title
        == "Granulite-Facies Xenoliths in Rift Basalts of Northern Tanzania: Age, Composition and Origin of Archean Lower Crust"
    )
    assert ref.year == "2014"
    assert ref.month == "Jun"
    assert ref.journal == "Journal of Petrology"
    assert ref.volume == "55"
    assert ref.number == "7"
    assert ref.pages == "1243–1286"
    assert ref.doi == "10.1093/petrology/egu024"


def test_ref_citation(ref):
    assert (
        ref.citation()
        == "Mansur AT, Manya S, Timpa S, Rudnick RL. 2014. Granulite-Facies Xenoliths in Rift Basalts of Northern Tanzania: Age, Composition and Origin of Archean Lower Crust. J Petrol. 55(7):1243–1286. doi:10.1093/petrology/egu024."
    )


def test_ref_to_emu(ref):
    assert ref.to_emu() == {
        "AdmGUIDIsPreferred_tab": [
            "Yes",
        ],
        "AdmGUIDType_tab": [
            "DOI",
        ],
        "AdmGUIDValue_tab": [
            "https://doi.org/10.1093/petrology/egu024",
        ],
        "BibRecordType": "Article",
        "NteAttributedToRef_nesttab": [
            [
                1006206,
            ],
        ],
        "NteDate0": [
            EMuDate("today"),
        ],
        "NteText0": [
            "@article{Mansur_2014, title={Granulite-Facies Xenoliths in Rift "
            "Basalts of Northern Tanzania: Age, Composition and Origin of Archean "
            "Lower Crust}, volume={55}, ISSN={1460-2415}, "
            "url={http://dx.doi.org/10.1093/petrology/egu024}, "
            "DOI={10.1093/petrology/egu024}, number={7}, journal={Journal of "
            "Petrology}, publisher={Oxford University Press (OUP)}, "
            "author={Mansur, A. T. and Manya, S. and Timpa, S. and Rudnick, R. "
            "L.}, year={2014}, month=jun, pages={1243–1286} }",
        ],
        "RefContributorsRef_tab": [
            {
                "NamFirst": "A",
                "NamLast": "Mansur",
                "NamMiddle": "T",
                "NamPartyType": "Person",
                "NamSuffix": "",
                "NamTitle": "",
                "SecRecordStatus": "Unlisted",
            },
            {
                "NamFirst": "S",
                "NamLast": "Manya",
                "NamMiddle": "",
                "NamPartyType": "Person",
                "NamSuffix": "",
                "NamTitle": "",
                "SecRecordStatus": "Unlisted",
            },
            {
                "NamFirst": "S",
                "NamLast": "Timpa",
                "NamMiddle": "",
                "NamPartyType": "Person",
                "NamSuffix": "",
                "NamTitle": "",
                "SecRecordStatus": "Unlisted",
            },
            {
                "NamFirst": "R",
                "NamLast": "Rudnick",
                "NamMiddle": "L",
                "NamPartyType": "Person",
                "NamSuffix": "",
                "NamTitle": "",
                "SecRecordStatus": "Unlisted",
            },
        ],
        "RefContributorsRole_tab": [
            "Author",
            "Author",
            "Author",
            "Author",
        ],
        "RefDate": EMuDate("Jun 2014"),
        "RefDateRange": "Jun 2014",
        "RefIssue": "7",
        "RefJournalBookTitle": "Journal of Petrology",
        "RefOtherIdentifierSource_tab": [
            "ISSN",
        ],
        "RefOtherIdentifier_tab": [
            "1460-2415",
        ],
        "RefPage": "1243–1286",
        "RefPublisherRef": {
            "NamOrganisation": "Oxford University Press (OUP)",
            "SecRecordStatus": "Unlisted",
        },
        "RefSeries": "",
        "RefTitle": "Granulite-Facies Xenoliths in Rift Basalts of Northern Tanzania: Age, Composition and Origin of Archean Lower Crust",
        "RefVolume": "55",
        "RefWebSiteIdentifier": "http://doi.org/10.1093/petrology/egu024",
    }
