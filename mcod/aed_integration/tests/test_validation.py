import csv
import io
import json

import pytest

from mcod.aed_integration.validation import AEDDataError, validate_aed_file
from mcod.datasets.models import Dataset


HEADER = (
    "device_id",
    "name",
    "latitude",
    "longitude",
    "availability",
    "hours",
    "status",
    "updated_at",
    "responsible_institution",
    "source_dataset_id",
    "source_url",
    "license",
    "verification_status",
)


def make_csv_row(**overrides):
    values = {
        "device_id": "aed-001",
        "name": "AED at City Hall",
        "latitude": "52.2297",
        "longitude": "21.0122",
        "availability": "public",
        "hours": "24/7",
        "status": "active",
        "updated_at": "2026-11-20",
        "responsible_institution": "City Hall",
        "source_dataset_id": "city-aed",
        "source_url": "https://example.org/aed",
        "license": Dataset.LICENSE_CODE_TO_NAME[Dataset.LICENSE_CC0],
        "verification_status": "source_reported",
    }
    values.update(overrides)
    return values


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def test_valid_aed_rows_are_normalized_and_not_claimed_as_physically_verified():
    parsed = validate_aed_file("locations.csv", csv_bytes([make_csv_row()]), "city-aed")

    assert len(parsed) == 1
    assert parsed[0]["status"] == "available"
    assert parsed[0]["latitude"] == "52.22970000"
    assert parsed[0]["verification_status"] == "source_reported"
    assert parsed[0]["updated_at"].endswith("+00:00")


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({"latitude": "91"}, "coordinates_out_of_range"),
        ({"longitude": "NaN"}, "invalid_coordinates"),
        ({"verification_status": "physically_verified"}, "invalid_verification"),
        ({"source_dataset_id": "another-dataset"}, "source_dataset_mismatch"),
        ({"source_url": "http://example.org/aed"}, "invalid_source_url"),
    ],
)
def test_invalid_rows_are_rejected(override, expected_code):
    with pytest.raises(AEDDataError) as error:
        validate_aed_file("locations.csv", csv_bytes([make_csv_row(**override)]), "city-aed")

    assert error.value.code == expected_code


def test_duplicate_device_ids_inside_one_source_file_are_rejected():
    rows = [make_csv_row(), make_csv_row(name="Second record")]

    with pytest.raises(AEDDataError) as error:
        validate_aed_file("locations.csv", csv_bytes(rows), "city-aed")

    assert error.value.code == "duplicate_device_id"


def test_malformed_xlsx_is_a_validation_error():
    with pytest.raises(AEDDataError) as error:
        validate_aed_file("locations.xlsx", b"not an Excel file", "city-aed")
    assert error.value.code == "invalid_xlsx"


def geojson_bytes(row=None, geometry=None):
    properties = dict(row or make_csv_row())
    properties.pop("latitude", None)
    properties.pop("longitude", None)
    return json.dumps({
        "type": "FeatureCollection", "features": [{
            "type": "Feature",
            "geometry": geometry or {"type": "Point", "coordinates": [21.0122, 52.2297]},
            "properties": properties,
        }],
    }).encode()


def test_geojson_uses_real_point_coordinates_without_inventing_properties():
    parsed = validate_aed_file("aed.geojson", geojson_bytes(), "city-aed")
    assert parsed[0]["longitude"] == "21.01220000"
    assert parsed[0]["latitude"] == "52.22970000"
    assert parsed[0]["verification_status"] == "source_reported"


@pytest.mark.parametrize("geometry", [
    {"type": "LineString", "coordinates": [[21, 52], [22, 53]]},
    {"type": "Point", "coordinates": [True, 52]},
    {"type": "Point", "coordinates": [21, 152]},
])
def test_geojson_rejects_non_point_or_invalid_coordinates(geometry):
    with pytest.raises(AEDDataError):
        validate_aed_file("aed.geojson", geojson_bytes(geometry=geometry), "city-aed")


def test_geojson_requires_real_licensing_and_availability():
    row = make_csv_row()
    row.pop("availability")
    with pytest.raises(AEDDataError) as error:
        validate_aed_file("aed.geojson", geojson_bytes(row=row), "city-aed")
    assert error.value.code == "missing_columns"


def test_geojson_rejects_conflicting_property_coordinates():
    document = json.loads(geojson_bytes())
    document["features"][0]["properties"]["latitude"] = 10
    with pytest.raises(AEDDataError) as error:
        validate_aed_file("aed.geojson", json.dumps(document).encode(), "city-aed")
    assert error.value.code == "coordinate_conflict"
