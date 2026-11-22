import csv
import io
import json
import math
import os
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlparse

from openpyxl import load_workbook

from mcod.datasets.models import Dataset


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ROWS_PER_RESOURCE = 50000
REQUIRED_COLUMNS = (
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
OPTIONAL_COLUMNS = ("description", "address", "city", "verification_evidence_url")
ALLOWED_STATUSES = {
    "available": "available",
    "active": "available",
    "operational": "available",
    "unavailable": "unavailable",
    "inactive": "unavailable",
    "out_of_service": "unavailable",
    "maintenance": "maintenance",
    "unknown": "unknown",
}
ALLOWED_VERIFICATION = {"unverified", "source_reported"}


class AEDDataError(ValueError):
    def __init__(self, message, code="invalid_aed_data", field_errors=None):
        super().__init__(message)
        self.code = code
        self.field_errors = field_errors


def _read_rows(filename, content):
    extension = os.path.splitext(filename.lower())[1]
    if extension not in (".csv", ".xlsx", ".geojson", ".json"):
        raise AEDDataError("Only CSV, XLSX and GeoJSON FeatureCollection uploads are supported.", "unsupported_file")
    if not content:
        raise AEDDataError("The uploaded file is empty.", "empty_file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise AEDDataError("The uploaded file exceeds the 25 MB limit.", "file_too_large")

    if extension in (".geojson", ".json"):
        try:
            document = json.loads(content.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            raise AEDDataError("Invalid GeoJSON document.", "invalid_geojson")
        if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
            raise AEDDataError("GeoJSON must be a FeatureCollection.", "invalid_geojson")
        if document.get("crs"):
            raise AEDDataError("Supply RFC 7946 WGS84 coordinates without a custom CRS.", "unsupported_crs")
        features = document.get("features")
        if not isinstance(features, list):
            raise AEDDataError("GeoJSON features must be an array.", "invalid_geojson")
        if len(features) > MAX_ROWS_PER_RESOURCE:
            raise AEDDataError("The file exceeds the 50,000 row limit.", "too_many_rows")
        rows = []
        for feature in features:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise AEDDataError("Each GeoJSON member must be a Feature.", "invalid_geojson")
            geometry, properties = feature.get("geometry"), feature.get("properties")
            if not isinstance(geometry, dict) or geometry.get("type") != "Point" or not isinstance(properties, dict):
                raise AEDDataError("AED features require Point geometry and properties.", "invalid_geojson")
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) not in (2, 3):
                raise AEDDataError("Point coordinates must be [longitude, latitude].", "invalid_coordinates")
            if any(type(value) not in (int, float) for value in coordinates):
                raise AEDDataError("Point coordinates must be numbers.", "invalid_coordinates")
            row = dict(properties)
            for name, value in zip(("longitude", "latitude"), coordinates[:2]):
                if name in row:
                    try:
                        matches = float(row[name]) == value
                    except (TypeError, ValueError):
                        matches = False
                    if not matches:
                        raise AEDDataError("Properties conflict with Point coordinates.", "coordinate_conflict")
                row[name] = value
            rows.append(row)
        return rows

    if extension == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise AEDDataError("Expanded XLSX exceeds the 100 MB limit.", "file_too_large")
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except (zipfile.BadZipFile, ValueError, KeyError, OSError):
            raise AEDDataError("The uploaded XLSX file is invalid.", "invalid_xlsx")
        worksheet = workbook.active
        iterator = worksheet.iter_rows(values_only=True)
        headers = next(iterator, None)
        if not headers:
            raise AEDDataError("The XLSX file has no header row.", "missing_headers")
        names = [str(value or "").strip().lower() for value in headers]
        rows = []
        for values in iterator:
            if not any(value not in (None, "") for value in values):
                continue
            rows.append({names[index]: value for index, value in enumerate(values) if index < len(names)})
            if len(rows) > MAX_ROWS_PER_RESOURCE:
                raise AEDDataError("The file exceeds the 50,000 row limit.", "too_many_rows")
        return rows

    text = None
    for encoding in ("utf-8-sig", "cp1250"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AEDDataError("CSV must use UTF-8 or Windows-1250 encoding.", "invalid_encoding")

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise AEDDataError("The CSV file has no header row.", "missing_headers")
    rows = []
    for raw in reader:
        if not any(value not in (None, "") for value in raw.values()):
            continue
        rows.append({str(key or "").strip().lower(): value for key, value in raw.items()})
        if len(rows) > MAX_ROWS_PER_RESOURCE:
            raise AEDDataError("The file exceeds the 50,000 row limit.", "too_many_rows")
    return rows


def _value(row, name):
    value = row.get(name, "")
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def _https_url(value, field):
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise AEDDataError("{} must be an HTTPS URL.".format(field), "invalid_source_url")


def _parse_updated_at(value):
    if not value:
        raise AEDDataError("updated_at is required.", "missing_updated_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                pass
        else:
            raise AEDDataError("updated_at must be an ISO date or date-time.", "invalid_updated_at")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def validate_aed_file(filename, content, external_dataset_id):
    """Return canonical rows and reject incomplete or untraceable source data."""
    rows = _read_rows(filename, content)
    if not rows:
        raise AEDDataError("The file contains no AED records.", "empty_data")

    columns = set(rows[0])
    missing = sorted(set(REQUIRED_COLUMNS) - columns)
    if missing:
        raise AEDDataError("Missing required columns: {}.".format(", ".join(missing)), "missing_columns")

    allowed_licenses = {str(label) for _value, label in Dataset.LICENSES}
    seen_device_ids = set()
    normalized = []
    for line_number, row in enumerate(rows, start=2):
        device_id = _value(row, "device_id")
        if not device_id:
            raise AEDDataError("Row {} has no device_id.".format(line_number), "missing_device_id")
        dedupe_id = device_id.casefold()
        if dedupe_id in seen_device_ids:
            raise AEDDataError("Duplicate device_id at row {}.".format(line_number), "duplicate_device_id")
        seen_device_ids.add(dedupe_id)

        name = _value(row, "name")
        if not name:
            raise AEDDataError("Row {} has no name.".format(line_number), "missing_name")

        try:
            latitude = float(_value(row, "latitude"))
            longitude = float(_value(row, "longitude"))
        except (TypeError, ValueError):
            raise AEDDataError("Row {} has invalid coordinates.".format(line_number), "invalid_coordinates")
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise AEDDataError("Row {} has invalid coordinates.".format(line_number), "invalid_coordinates")
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise AEDDataError("Row {} coordinates are out of range.".format(line_number), "coordinates_out_of_range")

        status_input = _value(row, "status").casefold()
        if status_input not in ALLOWED_STATUSES:
            raise AEDDataError("Row {} has an unsupported status.".format(line_number), "invalid_status")
        verification = _value(row, "verification_status").casefold()
        if verification not in ALLOWED_VERIFICATION:
            raise AEDDataError(
                "Only unverified or source_reported verification may be supplied by this integration.",
                "invalid_verification",
            )

        for required in ("availability", "hours", "responsible_institution", "source_dataset_id", "source_url", "license"):
            if not _value(row, required):
                raise AEDDataError("Row {} is missing {}.".format(line_number, required), "missing_field")
        if _value(row, "source_dataset_id") != str(external_dataset_id):
            raise AEDDataError(
                "Row {} source_dataset_id does not match the mapped dataset.".format(line_number),
                "source_dataset_mismatch",
            )
        source_url = _value(row, "source_url")
        _https_url(source_url, "source_url")
        license_name = _value(row, "license")
        if license_name not in allowed_licenses:
            raise AEDDataError(
                "Row {} has a license not recognized by MCOD.".format(line_number),
                "unsupported_license",
            )

        normalized.append(
            {
                "device_id": device_id,
                "name": name,
                "description": _value(row, "description"),
                "latitude": "{:.8f}".format(latitude),
                "longitude": "{:.8f}".format(longitude),
                "address": _value(row, "address"),
                "city": _value(row, "city"),
                "availability": _value(row, "availability"),
                "hours": _value(row, "hours"),
                "status": ALLOWED_STATUSES[status_input],
                "updated_at": _parse_updated_at(_value(row, "updated_at")),
                "responsible_institution": _value(row, "responsible_institution"),
                "source_dataset_id": str(external_dataset_id),
                "source_url": source_url,
                "license": license_name,
                "verification_status": verification,
                "verification_evidence_url": _value(row, "verification_evidence_url"),
            }
        )
    return normalized


def write_csv(rows, columns):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")
