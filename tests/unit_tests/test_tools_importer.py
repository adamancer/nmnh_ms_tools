import csv

import pandas as pd
import pytest
import shutil
import yaml
from xmu import EMuDate, EMuFloat, EMuLatitude, EMuLongitude, EMuReader, EMuRecord

from nmnh_ms_tools.tools.importer import ImportRecord, Job


@pytest.fixture
def output_dir(tmpdir_factory):
    return tmpdir_factory.mktemp("output")


@pytest.fixture
def job(output_dir):

    # Create original file
    orig_import_file = output_dir / "import-file-original.xlsx"
    rows = [
        {
            "Division": "Petrology & Volcanology",
            "Number": "C123456-78",
            "Field Number": "ABC-123",
            "Primary Taxon": "Basalt (aphyric)",
            "Associated Taxa": "Plagioclase (phenocrystic; tabular) | Olivine",
            "Earliest Period": "Cambrian-Silurian",
            "Start Date": "Jan 1970",
            "End Date": "Feb 1970",
            "Latitude": "47 00 10 N",
            "Longitude": "120 33 8 W",
            "Radius": "100 m",
            "Start Depth": "1000 to 1100 m",
            "Start Elevation": "1.4 to 1.6 miles",
            "Min Weight": "4-5 kg",
            "Cat Note": "Catalog note",
            "Loc Note": "Collection event note 1 | Collection Event Note 2",
            "Collector": "Homer Simpson",
            "Thin Sections": 2,
            "Grain Mounts": "See 123456-79",
            "Child": "NMNH 123456-78A",
            "Station Number": "ABC-1",
            "Station Name": "A. B. Camp #1",
            "Building": "BLDG",
            "Room": "E123",
            "Case": "001",
            "Drawer": "01",
            "Subfeature": "Columbia Crest",
            "References": "Simpson, 2024",
            "Unmapped": "Unmapped",
        },
        {
            "Division": "Petrology & Volcanology",
            "Prefix": "C",
            "Number": "123456",
            "Suffix": "78",
            "Field Number": "ABC-123",
            "Primary Taxon": "Basalt",
            "Associated Taxa": "Plagioclase (tabular; phenocrystic) | Olivine",
            "Texture/Structure": "aphyric",
            "Earliest Period": "Cambrian",
            "Latest Period": "Silurian",
            "Start Date": "Jan 1970",
            "End Date": "Feb 1970",
            "Latitude": "47 00 10 N",
            "Longitude": "120 33 8 W",
            "Radius": "100",
            "Radius Unit": "m",
            "Start Depth": "1000",
            "End Depth": "1100",
            "Depth Unit": "m",
            "Start Elevation": "1.4",
            "End Elevation": "1.6",
            "Elevation Unit": "miles",
            "Min Weight": "4",
            "Max Weight": "5",
            "Weight Unit": "kg",
            "Cat Note": "Catalog note",
            "Loc Note": "Collection event note 1 | Collection Event Note 2",
            "Collector": "Homer Simpson",
            "Thin Sections": 2,
            "Grain Mounts": "See 123456-79",
            "Child": "NMNH 123456-78A",
            "Station Number": "ABC-1",
            "Station Name": "A. B. Camp #1",
            "Building": "BLDG",
            "Room": "E123",
            "Case": "1",
            "Drawer": "1",
            "Volcano": "Rainier",
            "GVPNum": "321030",
            "Subfeature": "Columbia Crest",
            "References": "Simpson, 2024",
            "Unmapped": "Unmapped",
        },
    ]
    # Create clean file
    import_file = output_dir / "import-file.xlsx"
    pd.DataFrame(rows).to_excel(import_file)

    # Create original file
    rows[0]["Number"] = "123465"
    rows[0]["Cat Note"] = rows[0]["Loc Note"]
    rows[0]["Loc Note"] = None
    pd.DataFrame(rows).to_excel(orig_import_file)

    job = {
        "job": {
            "job_id": "ImporterTest",
            "import_file": str(import_file),
            "orig_import_file": str(orig_import_file),
            "name": "Test Import",
            "tailored": False,
        },
        "fields": {
            "cataloging": {
                "catalog_number": {
                    "method": "map_catalog_number",
                    "kwargs": {
                        "code": "NMNH",
                        "prefix": "prefix",
                        "number": "number",
                        "suffix": "suffix",
                    },
                    "required": True,
                },
                "cataloged_by": {
                    "method": "map_cataloger",
                    "kwargs": {"src": "Homer Simpson"},
                },
                "cataloged_date": {
                    "default": "1970-01-01",
                    "dst": "CatDateCataloged",
                },
                "division": {
                    "src": "Division",
                    "dst": "CatDivision",
                },
            },
            "test": {
                "age": {
                    "method": "map_age",
                    "kwargs": {
                        "src_earliest": "Earliest period",
                        "time_unit": "period",
                        "src_latest": "Latest period",
                    },
                },
                "primary_taxa": {
                    "method": "map_primary_taxa",
                    "kwargs": {
                        "src": "Primary Taxon",
                        "texture_structure": "Texture/structure",
                    },
                },
                "associated_taxa": {
                    "method": "map_associated_taxa",
                    "kwargs": {
                        "src": "Associated Taxa",
                    },
                },
                "field_number": {
                    "method": "map_contingent",
                    "kwargs": {
                        "src": "Field Number",
                        "dst": "CatOtherNumbersValue_tab",
                        "contingent": {
                            "CatOtherNumbersType_tab": "Collector's field number"
                        },
                    },
                },
                "coordinates": {
                    "method": "map_coordinates",
                    "kwargs": {
                        "lats": "Latitude",
                        "lons": "Longitude",
                        "crs": 4326,
                        "source": "Collector",
                        "method": "Included in sample documentation",
                        "det_by": "Homer Simpson",
                        "det_date": "1970-01-01",
                        "radius": "Radius",
                        "radius_unit": "Radius unit",
                        "notes": "No notes",
                    },
                },
                "date": {
                    "method": "map_dates",
                    "kwargs": {
                        "src_from": "Start date",
                        "dst_from": "BioEventSiteRef.ColDateVisitedFrom",
                        "src_to": "End date",
                        "dst_to": "BioEventSiteRef.ColDateVisitedTo",
                        "dst_verbatim": "BioEventSiteRef.ColVerbatimDate",
                    },
                },
                "depth": {
                    "method": "map_depths",
                    "kwargs": {
                        "src_from": "Start depth",
                        "unit": "Depth unit",
                        "src_to": "End depth",
                        "water_depth": True,
                        "bottom_depth": True,
                    },
                },
                "elevation": {
                    "method": "map_elevations",
                    "kwargs": {
                        "src_from": "Start elevation",
                        "unit": "Elevation unit",
                        "src_to": "End elevation",
                    },
                },
                "measurement": {
                    "method": "map_measurements",
                    "kwargs": {
                        "src_from": "Min weight",
                        "kind": "Weight",
                        "src_to": "Max weight",
                        "unit": "Weight unit",
                        "by": "Homer Simpson",
                        "date": "Jan 1970",
                    },
                },
                "note_cat": {
                    "method": "map_notes",
                    "kwargs": {
                        "src": "Cat Note",
                    },
                },
                "note_evt": {
                    "method": "map_notes",
                    "kwargs": {
                        "src": "Loc Note",
                        "dst": "BioEventSiteRef",
                        "by": "Homer Simpson",
                    },
                },
                "collector": {
                    "method": "map_parties",
                    "kwargs": {
                        "src": "Collector",
                        "dst": "BioEventSiteRef.ColParticipantRef_tab",
                        "contingent": {
                            "BioEventSiteRef.ColParticipantRole_tab": "Collector",
                        },
                    },
                },
                "thin_sections": {
                    "method": "map_prep",
                    "kwargs": {
                        "src": "Thin sections",
                        "prep": "Thin section",
                    },
                },
                "grain_mounts": {
                    "method": "map_prep",
                    "kwargs": {
                        "src": "Grain mounts",
                        "prep": "Grain mount",
                        "remarks": "Multiple samples",
                        "remarks_only": True,
                    },
                },
                "related": {
                    "method": "map_related",
                    "kwargs": {
                        "src": "Child",
                        "relationship": "Child",
                    },
                },
                "site_number": {
                    "method": "map_site_number",
                    "kwargs": {"site_num": "Station number", "name": "Station name"},
                },
                "storage_location": {
                    "method": "map_storage_location",
                    "kwargs": {
                        "building": "Building",
                        "room_pod": "Room",
                        "case_shelves": "Case",
                        "drawer_shelf": "Drawer",
                    },
                },
                "volcano": {
                    "method": "map_volcano",
                    "kwargs": {
                        "src_name": "Volcano",
                        "src_num": "GVPNum",
                        "src_feature": "Subfeature",
                    },
                },
                "references": {
                    "src": "References",
                    "dst": "BibBibliographyRef_tab",
                    "map": {"Simpson, 2024": 2345678},
                    "action": ["fill_reference"],
                },
            },
        },
        "ignore": ["Index"],
    }
    with open(output_dir / "job.yml", "w") as f:
        yaml.dump(job, f, sort_keys=False, indent=4, allow_unicode=True)
    return Job(output_dir / "job.yml")


@pytest.fixture
def expected():
    return EMuRecord(
        {
            "AgeGeologicAgeEarliestPeriod": "Cambrian",
            "AgeGeologicAgeLatestPeriod": "Silurian",
            "BibBibliographyRef_tab": [2345678],
            "BioEventSiteRef": {
                "AdmGUIDIsPreferred_tab": [],
                "AdmGUIDType_tab": [],
                "AdmGUIDValue_tab": [],
                "AquBottomDepthDetermination": "",
                "AquBottomDepthFromMet": EMuFloat("1000"),
                "AquBottomDepthFromModifier": "",
                "AquBottomDepthToMet": EMuFloat("1100"),
                "AquBottomDepthToModifier": "",
                "AquCruiseNumber": "",
                "AquDepthDetermination": "",
                "AquDepthFromMet": EMuFloat("1000"),
                "AquDepthFromModifier": "",
                "AquDepthToMet": EMuFloat("1100"),
                "AquDepthToModifier": "",
                "AquVerbatimBottomDepth": "1000 to 1100 m",
                "AquVerbatimDepth": "1000 to 1100 m",
                "AquVesselName": "",
                "ColBibliographicRef_tab": [],
                "ColCollectionMethod": "",
                "ColContractDescription_tab": [],
                "ColContractNumber_tab": [],
                "ColContractRecipientRef_tab": [],
                "ColDateVisitedConjunction": "",
                "ColDateVisitedFrom": EMuDate("Jan 1970"),
                "ColDateVisitedFromModifier": "",
                "ColDateVisitedTo": EMuDate("Feb 1970"),
                "ColDateVisitedToModifier": "",
                "ColParticipantEtAl": "",
                "ColParticipantRef_tab": [],
                "ColParticipantRole_tab": [],
                "ColPermitDescription_tab": [],
                "ColPermitIssuerRef_tab": [],
                "ColPermitNumber_tab": [],
                "ColSiteVisitNumbers_tab": [],
                "ColTimeVisitedConjunction_tab": [],
                "ColTimeVisitedFrom0": [],
                "ColTimeVisitedFromModifier_tab": [],
                "ColTimeVisitedTo0": [],
                "ColTimeVisitedToModifier_tab": [],
                "ColVerbatimDate": "Jan 1970 to Feb 1970",
                "DepSourceOfSample": "",
                "ExpCompletionDate": None,
                "ExpExpeditionName": "",
                "ExpProjectNumber": "",
                "ExpStartDate": None,
                "LatDatum_tab": ["4326"],
                "LatDetDate0": [EMuDate("1970-01-01")],
                "LatDetSource_tab": ["Homer Simpson"],
                "LatDeterminedByRef_tab": [
                    {
                        "NamFirst": "Homer",
                        "NamLast": "Simpson",
                        "NamMiddle": "",
                        "NamPartyType": "Person",
                        "NamSuffix": "",
                        "NamTitle": "",
                    }
                ],
                "LatGeometry_tab": ["Point"],
                "LatGeoreferencingNotes0": ["No notes"],
                "LatLatLongDetermination_tab": ["Included in sample " "documentation"],
                "LatLatitudeVerbatim_nesttab": [["47 00 10 N"]],
                "LatLatitude_nesttab": [[EMuLatitude("47 0 10 N")]],
                "LatLongitudeVerbatim_nesttab": [["120 33 8 W"]],
                "LatLongitude_nesttab": [[EMuLongitude("120 33 8 W")]],
                "LatRadiusNumeric_tab": [EMuFloat("100")],
                "LatRadiusUnit_tab": ["meters"],
                "LatRadiusVerbatim_tab": ["100 meters"],
                "LocArchipelago": "",
                "LocBaySound": "",
                "LocContinent": "",
                "LocCountry": "",
                "LocDistrictCountyShire": "",
                "LocGeologicSetting": "",
                "LocGeomorphologicalLocation": "",
                "LocIslandGrouping": "",
                "LocIslandName": "",
                "LocJurisdiction": "",
                "LocMineName": "",
                "LocMiningDistrict": "",
                "LocNoFurtherLocalityData": "",
                "LocOcean": "",
                "LocPreciseLocation": "",
                "LocProvinceStateTerritory": "",
                "LocQUAD": "",
                "LocRecordClassification": "Event",
                "LocSeaGulf": "",
                "LocSiteName_tab": ["A. B. Camp #1"],
                "LocSiteNumberSource": "",
                "LocSiteOwnerRef_tab": [],
                "LocSiteParentRef": None,
                "LocSiteStationNumber": "ABC-1",
                "LocTownship": "",
                "MapCoords": "",
                "MapName": "",
                "MapNumber": "",
                "MapOriginalCoordinateSystem": "",
                "MapOtherComment_tab": [],
                "MapOtherCoordA_tab": [],
                "MapOtherCoordB_tab": [],
                "MapOtherDatum_tab": [],
                "MapOtherDeterminedByRef_tab": [],
                "MapOtherKind_tab": [],
                "MapOtherMethod_tab": [],
                "MapOtherOffset_tab": [],
                "MapOtherSource_tab": [],
                "MapScale": "",
                "MapType": "",
                "MapUTMComment_tab": [],
                "MapUTMDatum_tab": [],
                "MapUTMDeterminedByRef_tab": [],
                "MapUTMEastingFloat_tab": [],
                "MapUTMFalseEasting_tab": [],
                "MapUTMFalseNorthing_tab": [],
                "MapUTMMethod_tab": [],
                "MapUTMNorthingFloat_tab": [],
                "MapUTMZone_tab": [],
                "MulMultiMediaRef_tab": [],
                "NteAttributedToRef_nesttab": [
                    [
                        {
                            "NamFirst": "Homer",
                            "NamLast": "Simpson",
                            "NamMiddle": "",
                            "NamPartyType": "Person",
                            "NamSuffix": "",
                            "NamTitle": "",
                        }
                    ],
                    [
                        {
                            "NamFirst": "Homer",
                            "NamLast": "Simpson",
                            "NamMiddle": "",
                            "NamPartyType": "Person",
                            "NamSuffix": "",
                            "NamTitle": "",
                        }
                    ],
                ],
                "NteDate0": [EMuDate("1970-01-01"), EMuDate("1970-01-01")],
                "NteMetadata_tab": ["No", "No"],
                "NteText0": ["Collection event note 1", "Collection Event Note 2"],
                "NteType_tab": ["Comments", "Comments"],
                "TerElevationDetermination": "",
                "TerElevationFromFt": EMuFloat("7391.999999999999"),
                "TerElevationFromMet": None,
                "TerElevationFromModifier": "",
                "TerElevationToFt": EMuFloat("7391.999999999999"),
                "TerElevationToMet": None,
                "TerElevationToModifier": "",
                "TerVerbatimElevation": "1.4 to 1.6 miles",
                "VolEruptionDateFrom": None,
                "VolEruptionDateTo": None,
                "VolEruptionID": "",
                "VolEruptionNotes": "",
                "VolSubfeature": "Columbia Crest",
                "VolVolcanoName": "Rainier",
                "VolVolcanoNumber": "321030",
            },
            "CatCatalogedByRef": {
                "NamFirst": "Homer",
                "NamLast": "Simpson",
                "NamMiddle": "",
                "NamPartyType": "Person",
                "NamSuffix": "",
                "NamTitle": "",
            },
            "CatDateCataloged": EMuDate("1970-01-01"),
            "CatDivision": "Petrology & Volcanology",
            "CatMuseumAcronym": "NMNH",
            "CatNumber": 123456,
            "CatOtherNumbersType_tab": ["Collector's field number"],
            "CatOtherNumbersValue_tab": ["ABC-123"],
            "CatPrefix": "C",
            "CatSuffix": "78",
            "IdeComments_tab": ["", "", ""],
            "IdeIdentifiedByRef_tab": [None, None, None],
            "IdeNamedPart_tab": ["Primary", "Associated", "Associated"],
            "IdeTaxonRef_tab": [1001689, 1010730, 1009644],
            "IdeTextureStructure_tab": ["aphyric", "phenocrystic; tabular", ""],
            "LocLocationRef_tab": [
                {
                    "LocLevel1": "BLDG",
                    "LocLevel2": "E123",
                    "LocLevel3": "001",
                    "LocLevel4": "01",
                    "LocLevel5": "",
                    "LocLevel6": "",
                    "LocLevel7": "",
                    "LocLevel8": "",
                }
            ],
            "LocPermanentLocationRef": {
                "LocLevel1": "BLDG",
                "LocLevel2": "E123",
                "LocLevel3": "001",
                "LocLevel4": "01",
                "LocLevel5": "",
                "LocLevel6": "",
                "LocLevel7": "",
                "LocLevel8": "",
            },
            "MeaByRef_tab": [
                {
                    "NamFirst": "Homer",
                    "NamLast": "Simpson",
                    "NamMiddle": "",
                    "NamPartyType": "Person",
                    "NamSuffix": "",
                    "NamTitle": "",
                },
                {
                    "NamFirst": "Homer",
                    "NamLast": "Simpson",
                    "NamMiddle": "",
                    "NamPartyType": "Person",
                    "NamSuffix": "",
                    "NamTitle": "",
                },
            ],
            "MeaCurrent_tab": ["Yes", "Yes"],
            "MeaDate0": [EMuDate("Jan 1970"), EMuDate("Jan 1970")],
            "MeaRemarks_tab": ["4 to 5 kg", "4 to 5 kg"],
            "MeaType_tab": ["Weight (Min)", "Weight (Max)"],
            "MeaVerbatimUnit_tab": ["kilograms", "kilograms"],
            "MeaVerbatimValue_tab": [EMuFloat("4"), EMuFloat("5")],
            "NotNmnhAttributedToRef_nesttab": [
                [
                    {
                        "NamFirst": "Homer",
                        "NamLast": "Simpson",
                        "NamMiddle": "",
                        "NamPartyType": "Person",
                        "NamSuffix": "",
                        "NamTitle": "",
                    }
                ]
            ],
            "NotNmnhDate0": [EMuDate("1970-01-01")],
            "NotNmnhText0": ["Catalog note"],
            "NotNmnhType_tab": ["Comments"],
            "NotNmnhWeb_tab": ["No"],
            "RelNhDate0": [EMuDate("1970-01-01")],
            "RelNhIDType_tab": ["NMNH catalog number"],
            "RelNhIdentifyByRef_tab": [
                {
                    "NamFirst": "Homer",
                    "NamLast": "Simpson",
                    "NamMiddle": "",
                    "NamPartyType": "Person",
                    "NamSuffix": "",
                    "NamTitle": "",
                }
            ],
            "RelNhURI_tab": ["NMNH 123456-78A"],
            "RelObjectsRef_tab": [
                {
                    "CatMuseumAcronym": "NMNH",
                    "CatNumber": 123456,
                    "CatPrefix": "",
                    "CatSuffix": "78A",
                }
            ],
            "RelRelationship_tab": ["Child"],
            "ZooPreparationCount_tab": [2, None],
            "ZooPreparationRemarks_tab": ["", "See 123456-79. Multiple samples."],
            "ZooPreparation_tab": ["Thin section", "Grain mount"],
        },
        module="ecatalogue",
    )


@pytest.fixture
def mapped(job):
    ImportRecord.job = job
    records = []
    for path in ImportRecord.csvs():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rec = ImportRecord(module="ecatalogue")
                rec.source = row
                records.append(rec)
    return records


def test_csvs(output_dir, job):
    ImportRecord.job = job
    assert ImportRecord.csvs() == [str(output_dir / "csvs" / "import-file_Sheet1.csv")]


def test_map_data(mapped, expected):
    assert mapped[0] == mapped[1]
    assert mapped[0] == expected


@pytest.mark.skip("Failing due to error in catnums module")
def test_receipt(mapped):
    for rec in mapped:
        with open(rec.add_receipt(), encoding="utf-8") as f:
            assert (
                f.read()
                == """# Verbatim data for C123456-78 from cataloging spreadsheet
Division: Petrology & Volcanology
Number: C123456-78
Field Number: ABC-123
Primary Taxon: Basalt (aphyric)
Associated Taxa: Plagioclase (phenocrystic; tabular) | Olivine
Earliest Period: Cambrian-Silurian
Start Date: Jan 1970
End Date: Feb 1970
Latitude: 47 00 10 N
Longitude: 120 33 8 W
Radius: 100 m
Start Depth: 1000 to 1100 m
Start Elevation: 1.4 to 1.6 miles
Min Weight: 4-5 kg
Cat Note: Catalog note
Loc Note: Collection event note 1 | Collection Event Note 2
Collector: Homer Simpson
Thin Sections: 2
Grain Mounts: See 123456-79
Child: NMNH 123456-78A
Station Number: ABC-1
Station Name: A. B. Camp #1
Building: BLDG
Room: E123
Case: 001
Drawer: 01
Subfeature: Columbia Crest
References: Simpson, 2024
Unmapped: Unmapped"""
            )


def test_import_source_files(output_dir, job):
    path = str(output_dir / "import_source_files.xml")
    job.import_source_files(path)
    for rec in EMuReader(path):
        assert rec["Multimedia"] == str(output_dir / "import-file.xlsx")
        assert rec["MulCreator_tab"] == ["Homer Simpson"]


def test_compare(job):
    changes = job.compare()
    assert changes.iloc[0].to_dict() == {
        "clean": "C123456-78",
        "col": "Number",
        "lev_dist": 5,
        "note": "",
        "orig": "123465",
        "row": 0,
        "sheet": "Sheet1",
    }
    assert changes.iloc[1].to_dict() == {
        "sheet": "Sheet1",
        "row": 0,
        "col": "Cat Note",
        "orig": "Collection event note 1 | Collection Event Note 2",
        "clean": "Catalog note",
        "lev_dist": 40,
        "note": "",
    }
    assert changes.iloc[2].to_dict() == {
        "sheet": "Sheet1",
        "row": 0,
        "col": "Loc Note",
        "orig": "",
        "clean": "Collection event note 1 | Collection Event Note 2",
        "lev_dist": 49,
        "note": "Moved from Cat Note",
    }
