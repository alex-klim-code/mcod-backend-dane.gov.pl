import csv
import io
from datetime import date

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from mcod.aed_integration.models import (
    AEDAggregateState,
    AEDDatasetMapping,
    AEDOrganizationMapping,
)
from mcod.aed_integration.services import rebuild_aggregate_catalog
from mcod.categories.factories import CategoryFactory
from mcod.datasets.factories import DatasetFactory
from mcod.datasets.models import Dataset
from mcod.organizations.factories import OrganizationFactory
from mcod.resources.models import Resource, ResourceFile
from mcod.tags.factories import TagFactory


HEADERS = (
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


def _row(dataset_id, device_id, name, latitude, longitude, updated_at, address, city):
    return {
        "device_id": device_id,
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "availability": "public",
        "hours": "24/7",
        "status": "active",
        "updated_at": updated_at,
        "responsible_institution": "AED test institution",
        "source_dataset_id": dataset_id,
        "source_url": "https://example.org/{}".format(dataset_id),
        "license": Dataset.LICENSE_CODE_TO_NAME[Dataset.LICENSE_CC0],
        "verification_status": "source_reported",
        "address": address,
        "city": city,
    }


def _csv(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=HEADERS + ("address", "city"),
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _mapping(external_id, organization, category, tag):
    mapping = AEDOrganizationMapping.objects.create(
        external_organization_id=external_id,
        organization=organization,
        default_category=category,
    )
    mapping.default_tags.add(tag)
    return mapping


def _source_dataset(mapping, external_id):
    dataset = DatasetFactory.create(
        organization=mapping.organization,
        category=mapping.default_category,
        license_chosen=Dataset.LICENSE_CC0,
        status=Dataset.STATUS.published,
        update_frequency="daily",
    )
    dataset.categories.add(mapping.default_category)
    dataset.tags.add(*mapping.default_tags.all())
    AEDDatasetMapping.objects.create(
        organization_mapping=mapping,
        external_dataset_id=external_id,
        dataset=dataset,
    )
    return dataset


def _source_resource(dataset, filename, rows):
    resource = Resource.objects.create(
        dataset=dataset,
        status="published",
        title="AED source data",
        description="Test source file for the AED aggregation pipeline.",
        data_date=date(2026, 11, 20),
    )
    ResourceFile.objects.create(
        resource=resource,
        is_main=True,
        file=SimpleUploadedFile(filename, _csv(rows), content_type="text/csv"),
    )
    return resource


@pytest.mark.django_db
def test_aggregate_publishes_latest_records_and_keeps_previous_resource(
    tmp_path, monkeypatch
):
    storage = ResourceFile._meta.get_field("file").storage
    original_location = storage._location
    storage._location = str(tmp_path)
    monkeypatch.setattr(
        "mcod.aed_integration.services.check_all_resource_validations_status",
        lambda resource: None,
    )

    try:
        category_a = CategoryFactory.create()
        category_b = CategoryFactory.create()
        tag_a = TagFactory.create()
        tag_b = TagFactory.create()
        organization_a = OrganizationFactory.create(
            title="AED Aggregate Test A",
            status="published",
        )
        organization_b = OrganizationFactory.create(
            title="AED Aggregate Test B",
            status="published",
        )
        mapping_a = _mapping("aggregate-test-a", organization_a, category_a, tag_a)
        mapping_b = _mapping("aggregate-test-b", organization_b, category_b, tag_b)
        dataset_a = _source_dataset(mapping_a, "source-a")
        dataset_b = _source_dataset(mapping_b, "source-b")

        rows_a = [
            _row("source-a", "aed-001", "Station 1", "52.2297", "21.0122", "2026-11-18", "Main Street 1", "Warsaw"),
            _row("source-a", "aed-002", "Community Center", "52.2300", "21.0100", "2026-11-18", "Main Street 2", "Warsaw"),
            _row("source-a", "aed-003", "Station 3", "52.2400", "21.0200", "2026-11-18", "Oak Street 3", "Warsaw"),
        ]
        rows_b = [
            _row("source-b", "aed-001", "Station 1 updated", "52.2297", "21.0122", "2026-11-20", "Main Street 1", "Warsaw"),
            _row("source-b", "aed-004", "Community Center", "52.2301", "21.0101", "2026-11-19", "Main Street 2", "Warsaw"),
        ]
        source_a = _source_resource(dataset_a, "source-a.csv", rows_a)
        _source_resource(dataset_b, "source-b.csv", rows_b)
        state = AEDAggregateState.objects.create(
            owner_mapping=mapping_a,
            license_chosen=Dataset.LICENSE_CC0,
        )

        first_run = rebuild_aggregate_catalog()
        first_resource_id = first_run.published_resource_id
        first_resource = first_run.published_resource
        with first_resource.main_file.open("rb") as file_obj:
            aggregate_rows = list(csv.DictReader(io.StringIO(file_obj.read().decode("utf-8-sig"))))

        assert first_run.status == AEDAggregateState.STATUS_PUBLISHED
        assert first_run.record_count == 4
        assert len(aggregate_rows) == 4
        station = next(row for row in aggregate_rows if row["device_id"] == "aed-001")
        assert station["name"] == "Station 1 updated"
        assert station["source_dataset_id"] == "source-a;source-b"
        near_duplicates = {
            row["device_id"]: row["potential_duplicate"]
            for row in aggregate_rows
            if row["device_id"] in {"aed-002", "aed-004"}
        }
        assert near_duplicates == {"aed-002": "true", "aed-004": "true"}
        assert all(row["verification_status"] == "source_reported" for row in aggregate_rows)

        rows_a[-1]["name"] = "Station 3 revised"
        rows_a[-1]["updated_at"] = "2026-11-21"
        source_file = ResourceFile.objects.get(resource=source_a, is_main=True)
        source_file.file.save(
            "source-a-updated.csv",
            ContentFile(_csv(rows_a)),
            save=True,
        )

        second_run = rebuild_aggregate_catalog()
        assert second_run.status == AEDAggregateState.STATUS_PUBLISHED
        assert second_run.published_resource_id != first_resource_id
        assert ResourceFile.objects.filter(resource_id=first_resource_id).exists()
        first_run.published_resource.refresh_from_db()
        assert first_run.published_resource.status == "draft"
        with second_run.published_resource.main_file.open("rb") as file_obj:
            updated_rows = list(csv.DictReader(io.StringIO(file_obj.read().decode("utf-8-sig"))))
        station_three = next(row for row in updated_rows if row["device_id"] == "aed-003")
        assert station_three["name"] == "Station 3 revised"
    finally:
        storage._location = original_location
