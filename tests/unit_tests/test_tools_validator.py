from pathlib import Path

import pandas as pd
import pytest
import yaml
from xmu import EMuRecord, write_xml

from nmnh_ms_tools.tools.importer import ImportRecord, Job, Validator


@pytest.fixture(scope="session")
def output_dir(tmpdir_factory):
    return tmpdir_factory.mktemp("importer")


@pytest.fixture(scope="session")
def validation_dir(output_dir):
    path = output_dir / "validation"
    path.mkdir()
    return path


@pytest.fixture
def validators(validation_dir):
    for key in ["fields", "grids", "hierarchies", "related"]:
        path = validation_dir / f"validate_{key}.yml"
        with open(path, "w") as f:
            pass


def test_validate_int(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"common": {"irn": "Integer"}, "ecatalogue": {"NotNmnhText0": "Integer"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["123456"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_str(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "[A-Z][a-z]{4}"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_empty(output_dir, validation_dir, validators):
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": [""]},
        {"irn": 1234568, "NotNmnhText0": ["--"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 0


def test_validate_date(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "Date"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["1970-01-01"]},
        {"irn": 1234568, "NotNmnhText0": ["Jan 1970"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_latitude(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "Latitude"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["45 50 15 N"]},
        {"irn": 1234568, "NotNmnhText0": ["45.5"]},
        {"CatNumber": 123456, "NotNmnhText0": ["91 S"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "91 S",
    }


def test_validate_longitude(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "Longitude"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["90 30 15 W"]},
        {"irn": 1234568, "NotNmnhText0": ["90.5"]},
        {"CatNumber": 123456, "NotNmnhText0": ["181 E"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "181 E",
    }


def test_validate_admin(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecollectionevents": {"LocCountry": None, "LocProvinceStateTerritory": None}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {
            "irn": 1234567,
            "LocCountry": "United States",
            "LocProvinceStateTerritory": "Washington",
        },
        {
            "irn": 1234568,
            "LocCountry": "United States",
            "LocProvinceStateTerritory": "Mashington",
        },
    ]
    write_xml([EMuRecord(r, module="ecollectionevents") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecollectionevents",
        "Field": "LocCountry/LocProvinceStateTerritory/LocDistrictCountyShire",
        "Value": "['United States', ['Mashington'], []]",
    }


def test_validate_path_exists(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "PathExists"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": [str(path)]},
        {"irn": 1234568, "NotNmnhText0": [str(validation_dir / "validate_fields.yml")]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_yes_no(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "YesNo"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Yes"]},
        {"irn": 1234568, "NotNmnhText0": ["No"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_yes_no_unk(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "YesNoUnknown"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Yes"]},
        {"irn": 1234568, "NotNmnhText0": ["No"]},
        {"irn": 1234569, "NotNmnhText0": ["Unknown"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_doi(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "DOI"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["https://doi.org/10.1093/petrology/egu024"]},
        {"irn": 1234568, "NotNmnhText0": ["10.1093/petrology/egu024"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_taxon(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "Taxon"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val = Validator(path, validation_dir=validation_dir)
    val._tree = {"Valid": 1000000}
    val_path = val.validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }


def test_validate_meteorite_name(output_dir, validation_dir, validators):
    # Create vocabulary file
    path = validation_dir / "vocabs" / "ecatalogue" / "MetMeteoriteName.txt"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(["Valid"]))
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": "MeteoriteName"}}
    with open(validation_dir / "validate_fields.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["ALH 12345"]},
        {"irn": 1234568, "NotNmnhText0": ["ALH 12345,1"]},
        {"irn": 12345670, "NotNmnhText0": ["ALH 12345,A"]},
        {"irn": 12345670, "NotNmnhText0": ["ALH 12345,1A"]},
        {"irn": 12345671, "NotNmnhText0": ["Valid"]},
        {"CatNumber": 123456, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val = Validator(path, validation_dir=validation_dir)
    val._tree = {"Valid": 1000000}
    val_path = val.validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }
    # Remove vocab file so that it doesn't interfere with other tests
    Path(validation_dir / "vocabs" / "ecatalogue" / "MetMeteoriteName.txt").unlink()


def test_validate_from_vocab_file(output_dir, validation_dir, validators):
    # Create vocabulary file
    path = validation_dir / "vocabs" / "ecatalogue" / "NotNmnhText0.txt"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(["Valid"]))
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"]},
        {"irn": 1234568, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "Invalid data",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Invalid",
    }
    # Remove vocab file so that it doesn't interfere with other tests
    Path(validation_dir / "vocabs" / "ecatalogue" / "NotNmnhText0.txt").unlink()


def test_validate_undefined(output_dir, validation_dir, validators):
    # Update validation file
    with open(validation_dir / "validate_fields.yml", "w") as f:
        pass
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 1
    assert df.iloc[0].to_dict() == {
        "Warning": "No validation defined",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Valid",
    }


def test_validate_grid(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": ["NotNmnhType_tab", "NotNmnhText0"]}}
    with open(validation_dir / "validate_grids.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"], "NotNmnhType_tab": ["Valid"]},
        {"irn": 1234568, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 4
    assert df.iloc[-1].to_dict() == {
        "Warning": "Missing required values from grid",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Missing ['NotNmnhType_tab'] (1234568)",
    }


def test_validate_hierarchy(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": ["NotNmnhType_tab", "NotNmnhText0"]}}
    with open(validation_dir / "validate_hierarchies.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"], "NotNmnhType_tab": ["Valid"]},
        {"irn": 1234568, "NotNmnhText0": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 4
    assert df.iloc[-1].to_dict() == {
        "Warning": "Missing required values from hierarchy",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Missing ['NotNmnhType_tab'] (1234568)",
    }


def test_validate_related(output_dir, validation_dir, validators):
    # Update validation file
    dct = {"ecatalogue": {"NotNmnhText0": ["NotNmnhType_tab"]}}
    with open(validation_dir / "validate_related.yml", "w") as f:
        yaml.dump(dct, f, sort_keys=False, indent=4, allow_unicode=True)
    # Create import
    path = output_dir / "import.xml"
    records = [
        {"irn": 1234567, "NotNmnhText0": ["Valid"], "NotNmnhType_tab": ["Valid"]},
        {"irn": 1234568, "NotNmnhText0": ["Valid"], "NotNmnhType_tab": ["Invalid"]},
    ]
    write_xml([EMuRecord(r, module="ecatalogue") for r in records], path)
    # Validate
    val_path = Validator(path, validation_dir=validation_dir).validate()
    df = pd.read_csv(val_path)
    assert len(df) == 4
    assert df.iloc[-1].to_dict() == {
        "Warning": "Inconsistent data in related fields (diff=[('Valid', 'Invalid')])",
        "Module": "ecatalogue",
        "Field": "NotNmnhText0",
        "Value": "Valid",
    }
