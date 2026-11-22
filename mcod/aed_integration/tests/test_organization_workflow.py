"""Real ORM/API operations only in the uniquely named contract-test database."""

import json

import pytest
from django.test import override_settings

from mcod.aed_integration.institutions import review_request
from mcod.aed_integration.models import AEDOrganizationMapping, AEDOrganizationRequest, AEDIntegrationAudit
from mcod.aed_integration.tests.test_api import _auth_headers, _client, _mapping, _source_csv, _csv_upload_body, SECRET
from mcod.categories.factories import CategoryFactory
from mcod.organizations.factories import OrganizationFactory
from mcod.organizations.models import Organization
from mcod.resources.models import Resource, ResourceFile
from mcod.tags.factories import TagFactory
from mcod.users.factories import AdminFactory, UserFactory


BASE = "/integrations/aed/v1"
DATASET_OPTIONS = {
    "update_frequency": "daily", "has_dynamic_data": False, "has_high_value_data": False,
    "has_high_value_data_from_ec_list": False, "has_research_data": False,
}
INSTITUTION = {
    "title": "Isolated institution contract test", "description": "Only an isolated test database fixture.",
    "institution_type": "local", "postal_code": "00-001", "city": "Warszawa",
    "street_type": "ul.", "street": "Testowa", "street_number": "1",
    "email": "institution@example.invalid", "tel": "221234567",
    "regon": "123456785", "status": "published",
}


@pytest.fixture
def api():
    with override_settings(AED_INTEGRATION_SECRET=SECRET, AED_REQUIRE_HTTPS=True):
        yield _client()


def approve(item, manage=False, adopt=False):
    item.default_category = CategoryFactory.create(status="published")
    item.can_manage_institution = manage
    item.can_adopt_datasets = adopt
    item.save()
    item.default_tags.add(TagFactory.create())
    return review_request(item.pk, True, AdminFactory.create())


def create_approved_institution(api):
    result = api.simulate_post(BASE + "/organization-requests", headers=_auth_headers(), json={
        "external_organization_id": "org-a", "organization_name": "Isolated test organization",
        "request_type": "create",
    })
    assert result.status_code == 201, result.text
    approve(AEDOrganizationRequest.objects.get(external_organization_id="org-a"), manage=True)
    created = api.simulate_post(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json=INSTITUTION)
    assert created.status_code == 201, created.text
    return created.json["data"]["id"]


@pytest.mark.django_db
def test_catalog_is_not_replaced_by_integration_mappings(api):
    OrganizationFactory.create(status="published")
    assert api.simulate_get(BASE + "/institutions", headers=_auth_headers()).json == {"data": []}
    schema = api.simulate_get(BASE + "/schemas", headers=_auth_headers())
    assert schema.status_code == 200, schema.text
    assert schema.json["institution_catalog"] == "/api/institutions"
    assert schema.json["institution"]["regon"]["required"]
    assert schema.json["institution"]["tel"]["required"]
    assert "users" not in schema.json["institution"]
    # The original public portal API is still read-only.
    assert api.simulate_post("/institutions", json=INSTITUTION).status_code == 405


@pytest.mark.django_db
def test_pending_request_cannot_grant_itself_permissions(api):
    organization = OrganizationFactory.create(status="published")
    payload = {
        "external_organization_id": "org-a", "organization_name": "Isolated test organization",
        "request_type": "link", "mcod_institution_id": organization.pk,
    }
    submitted = api.simulate_post(BASE + "/organization-requests", headers=_auth_headers(), json=payload)
    assert submitted.status_code == 201, submitted.text
    assert submitted.json["status"] == "pending"
    repeated = api.simulate_post(BASE + "/organization-requests", headers=_auth_headers(), json=payload)
    assert repeated.status_code == 200
    forged = api.simulate_post(BASE + "/organization-requests", headers=_auth_headers(), json={**payload, "status": "approved"})
    assert forged.status_code == 422
    assert not AEDOrganizationMapping.objects.exists()
    assert api.simulate_post(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json=INSTITUTION).status_code == 403
    from django.core.exceptions import PermissionDenied
    with pytest.raises(PermissionDenied):
        review_request(AEDOrganizationRequest.objects.get().pk, True, UserFactory.create())
    approve(AEDOrganizationRequest.objects.get())
    status = api.simulate_get(BASE + "/organization-requests/org-a", headers=_auth_headers())
    assert status.json["status"] == "approved"
    assert status.json["permissions"]["manage_institution"] is False
    denied = api.simulate_patch(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json={"title": "Forbidden"})
    assert denied.status_code == 403
    organization.refresh_from_db()
    assert organization.title != "Forbidden"


@pytest.mark.django_db
def test_native_institution_creation_edit_validation_and_duplicates(api):
    institution_id = create_approved_institution(api)
    assert Organization.objects.get(pk=institution_id).regon == INSTITUTION["regon"]
    changed = api.simulate_patch(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json={"title": "Changed by approved integration"})
    assert changed.status_code == 200, changed.text
    assert changed.json["data"]["title"] == "Changed by approved integration"
    invalid = api.simulate_patch(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json={"regon": "123"})
    assert invalid.status_code == 422
    assert Organization.objects.get(pk=institution_id).regon == INSTITUTION["regon"]
    assert api.simulate_patch(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json={"users": []}).status_code == 422
    assert api.simulate_patch(BASE + "/organizations/org-a/institution", headers=_auth_headers(), json={"status": "draft"}).status_code == 422
    assert api.simulate_patch(BASE + "/organizations/unknown/institution", headers=_auth_headers(), json={"title": "Foreign"}).status_code == 404
    audit = AEDIntegrationAudit.objects.filter(action="institution_updated").get()
    assert audit.details == {"institution_id": institution_id, "changed_fields": ["title"]}
    other = AEDOrganizationRequest.objects.create(
        external_organization_id="org-b", organization_name="Other test organization", request_type="create",
    )
    approve(other, manage=True)
    duplicate = api.simulate_post(BASE + "/organizations/org-b/institution", headers=_auth_headers(), json=INSTITUTION)
    assert duplicate.status_code == 422
    assert duplicate.json["error"]["code"] == "institution_exists"
    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_dataset_file_flow_is_scoped_and_preserves_geojson(api):
    create_approved_institution(api)
    payload = {
        "external_dataset_id": "source-a", "title": "Isolated AED source",
        "description": "Declared AED locations from an isolated integration test.",
        "source_url": "https://example.org/aed", "license": "CC0 1.0", **DATASET_OPTIONS,
    }
    base = BASE + "/organizations/org-a"
    missing = api.simulate_post(base + "/datasets", headers=_auth_headers(), json={k: v for k, v in payload.items() if k != "has_dynamic_data"})
    assert missing.status_code == 422
    created = api.simulate_post(base + "/datasets", headers=_auth_headers(), json=payload)
    assert created.status_code == 201, created.text
    updated = api.simulate_patch(base + "/datasets/source-a", headers=_auth_headers(), json={"title": "Updated isolated AED source"})
    assert updated.status_code == 200
    assert api.simulate_post(base + "/datasets/source-a/publish", headers=_auth_headers()).status_code == 200
    from mcod.aed_integration.tests.test_validation import make_csv_row
    row = make_csv_row(source_dataset_id="source-a")
    longitude, latitude = float(row.pop("longitude")), float(row.pop("latitude"))
    geojson = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [longitude, latitude]}, "properties": row}
    ]}).encode()
    boundary, body = _csv_upload_body({"title": "Isolated GeoJSON AED source"}, geojson)
    body = body.replace(b'filename="source.csv"', b'filename="source.geojson"')
    uploaded = api.simulate_post(base + "/datasets/source-a/resources", body=body, headers={
        **_auth_headers(), "Content-Type": "multipart/form-data; boundary=" + boundary,
    })
    assert uploaded.status_code == 202, uploaded.text
    resource_id = uploaded.json["resource_id"]
    assert uploaded.json["status"] == "draft"
    assert uploaded.json["accepted_rows"] == 1
    main = ResourceFile.objects.get(resource_id=resource_id, is_main=True)
    original = ResourceFile.objects.get(resource_id=resource_id, is_main=False)
    assert main.file.name.endswith(".csv")
    with original.file.open("rb") as stream:
        assert stream.read() == geojson
    download = api.simulate_get(base + "/resources/{}/file".format(resource_id), headers=_auth_headers())
    assert download.status_code == 200
    assert b"device_id" in download.content
    original_download = api.simulate_get(base + "/resources/{}/files/{}".format(resource_id, original.pk), headers=_auth_headers())
    assert original_download.content == geojson
    other = OrganizationFactory.create(status="published")
    _mapping("org-b", other)
    foreign = BASE + "/organizations/org-b/resources/{}".format(resource_id)
    assert api.simulate_get(foreign, headers=_auth_headers()).status_code == 404
    assert api.simulate_get(foreign + "/file", headers=_auth_headers()).status_code == 404
    assert api.simulate_get(foreign + "/files/{}".format(original.pk), headers=_auth_headers()).status_code == 404
    assert api.simulate_post(base + "/resources/{}/publish".format(resource_id), headers=_auth_headers()).status_code == 409
    resource = Resource.objects.get(pk=resource_id)
    assert str(resource.data_date) == "2026-11-20"
    assert resource.data_tasks_last_status == "PENDING"
